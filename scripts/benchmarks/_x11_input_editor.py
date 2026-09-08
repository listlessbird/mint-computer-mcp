"""GTK editor subprocess for the input benchmark; communicate over stdin/stdout."""

from __future__ import annotations

import importlib
import json
import sys
import time
from typing import TYPE_CHECKING, Protocol, cast, final

if TYPE_CHECKING:
    from collections.abc import Callable


# Keep PyGObject's dynamic native API behind a small, typed adapter.
class _Widget(Protocol):
    def connect(self, signal: str, handler: Callable[..., object]) -> int: ...
    def grab_focus(self) -> None: ...
    def has_focus(self) -> bool: ...
    def queue_draw(self) -> None: ...


class _Iter(Protocol): ...


class _Buffer(Protocol):
    def connect(self, signal: str, handler: Callable[..., object]) -> int: ...
    def set_text(self, text: str) -> None: ...
    def get_bounds(self) -> tuple[_Iter, _Iter]: ...
    def get_text(self, start: _Iter, end: _Iter, *, include_hidden_chars: bool) -> str: ...
    def get_selection_bounds(self) -> tuple[_Iter, _Iter] | tuple[()]: ...


class _GdkWindow(Protocol):
    def get_origin(self) -> tuple[int, int, int]: ...
    def focus(self, timestamp: int) -> None: ...


class _TextView(_Widget, Protocol):
    def get_buffer(self) -> _Buffer: ...
    def get_window(self, window_type: int) -> _GdkWindow: ...


class _Clock(Protocol):
    def connect(self, signal: str, handler: Callable[..., object]) -> int: ...


class _Window(_Widget, Protocol):
    def set_title(self, title: str) -> None: ...
    def set_default_size(self, width: int, height: int) -> None: ...
    def add(self, widget: _Widget) -> None: ...
    def show_all(self) -> None: ...
    def get_window(self) -> _GdkWindow: ...
    def get_frame_clock(self) -> _Clock: ...


class _Box(_Widget, Protocol):
    def set_orientation(self, orientation: int) -> None: ...
    def pack_start(self, widget: _Widget, *, expand: bool, fill: bool, padding: int) -> None: ...


class _Button(_Widget, Protocol):
    def set_label(self, label: str) -> None: ...


class _Gtk(Protocol):
    Window: Callable[[], _Window]
    TextView: Callable[[], _TextView]
    Button: Callable[[], _Button]
    Box: Callable[[], _Box]

    def main(self) -> None: ...
    def main_quit(self) -> None: ...


class _GLib(Protocol):
    IO_IN: int

    def io_add_watch(
        self, channel: int, condition: int, callback: Callable[[int, int], bool]
    ) -> int: ...


class _Gi(Protocol):
    def require_version(self, namespace: str, version: str) -> None: ...


@final
class _Editor:
    def __init__(self, gtk: _Gtk, glib: _GLib) -> None:
        self._gtk = gtk
        self._window = gtk.Window()
        self._window.set_title("Mint input benchmark editor")
        self._window.set_default_size(640, 420)
        box = gtk.Box()
        box.set_orientation(1)  # Gtk.Orientation.VERTICAL.
        self._other = gtk.Button()
        self._other.set_label("Focus target outside the editor")
        self._view = gtk.TextView()
        self._buffer = self._view.get_buffer()
        box.pack_start(self._other, expand=False, fill=False, padding=0)
        box.pack_start(self._view, expand=True, fill=True, padding=0)
        self._window.add(box)
        self._request_id = 0
        self._case = ""
        self._expected = ""
        self._pending = "ready"
        self._armed = False
        _ = self._buffer.connect("changed", self._changed)
        _ = self._buffer.connect("notify::has-selection", self._selection_changed)
        _ = self._view.connect("notify::has-focus", self._focus_changed)
        _ = self._window.connect("destroy", self._destroyed)
        self._window.show_all()
        self._window.get_window().focus(0)
        _ = self._window.get_frame_clock().connect("after-paint", self._after_paint)
        _ = glib.io_add_watch(sys.stdin.fileno(), glib.IO_IN, self._command)
        self._window.queue_draw()

    def _destroyed(self, _window: _Window) -> None:
        self._gtk.main_quit()

    def _contents(self) -> str:
        return self._buffer.get_text(*self._buffer.get_bounds(), include_hidden_chars=True)

    def _selected(self) -> str:
        bounds = self._buffer.get_selection_bounds()
        return self._buffer.get_text(*bounds, include_hidden_chars=True) if bounds else ""

    def _matches(self) -> bool:
        match self._case:
            case "focus":
                return self._view.has_focus()
            case "select":
                return self._selected() == self._expected
            case "type":
                return self._contents() == self._expected
            case _:
                return False

    def _check(self) -> None:
        if self._armed and self._matches():
            self._pending = "done"
            self._view.queue_draw()

    def _changed(self, _buffer: _Buffer) -> None:
        self._check()

    def _selection_changed(self, _buffer: _Buffer, _parameter: object) -> None:
        self._check()

    def _focus_changed(self, _view: _TextView, _parameter: object) -> None:
        self._check()

    def _after_paint(self, _clock: _Clock) -> None:
        if not self._pending:
            return
        status = self._pending
        if status == "done" and not self._matches():
            return
        self._pending = ""
        self._armed = status == "prepared"
        _, x, y = self._view.get_window(2).get_origin()  # Gtk.TextWindowType.TEXT.
        reply = {
            "request_id": self._request_id,
            "status": status,
            "completed_ns": time.monotonic_ns(),
            "x": x + 16,
            "y": y + 16,
            "text": self._contents(),
            "selection": self._selected(),
            "focused": self._view.has_focus(),
        }
        _ = sys.stdout.write(json.dumps(reply) + "\n")
        _ = sys.stdout.flush()

    def _command(self, _channel: int, _condition: int) -> bool:
        line = sys.stdin.readline()
        if not line:
            self._gtk.main_quit()
            return False
        raw = cast("object", json.loads(line))
        if not isinstance(raw, dict):
            msg = "expected an editor preparation object"
            raise TypeError(msg)
        command = cast("dict[str, object]", raw)
        request_id, case, text = command["request_id"], command["case"], command["text"]
        if (
            not isinstance(request_id, int)
            or not isinstance(case, str)
            or not isinstance(text, str)
        ):
            msg = "invalid editor preparation fields"
            raise TypeError(msg)
        self._armed = False
        self._request_id = request_id
        self._case = case
        self._expected = text
        self._buffer.set_text(text if case == "select" else "")
        if case == "focus":
            self._other.grab_focus()
        else:
            self._view.grab_focus()
        self._pending = "prepared"
        self._window.queue_draw()
        return True


def main() -> None:
    """Start a GTK text editor using the system Python's PyGObject installation."""
    gi = cast("_Gi", cast("object", importlib.import_module("gi")))
    gi.require_version("Gtk", "3.0")
    gtk = cast("_Gtk", cast("object", importlib.import_module("gi.repository.Gtk")))
    glib = cast("_GLib", cast("object", importlib.import_module("gi.repository.GLib")))
    _editor = _Editor(gtk, glib)
    gtk.main()


if __name__ == "__main__":
    main()
