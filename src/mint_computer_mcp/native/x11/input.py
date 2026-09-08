"""Stateful X11 input injection built on narrow XTEST operations."""

from typing import assert_never, final

import xcffib

from mint_computer_mcp.backend import InputStateUncertainError
from mint_computer_mcp.domain.geometry import RootPoint
from mint_computer_mcp.domain.identifiers import WindowId, X11Keycode
from mint_computer_mcp.domain.input import KeyName, PointerButton
from mint_computer_mcp.native.x11.client import X11Client, X11Error
from mint_computer_mcp.native.x11.xkb import XkbKeyboard


def _button_code(button: PointerButton) -> int:
    """Map backend-neutral pointer buttons to X11 core button details."""
    match button:
        case PointerButton.LEFT:
            return 1
        case PointerButton.MIDDLE:
            return 2
        case PointerButton.RIGHT:
            return 3
        case _:
            assert_never(button)


@final
class X11Input:
    """Inject X11 input while tracking whether held-state cleanup is reliable."""

    def __init__(self, *, client: X11Client, root: WindowId) -> None:
        """Bind input injection to one client and root window."""
        self._client = client
        self._root = root
        self._healthy = True
        self._keyboard_uncertain = False
        self._keyboard: XkbKeyboard | None = None

    def move_pointer(self, point: RootPoint) -> None:
        """Move the pointer and flush the request."""
        self._ensure_healthy()
        self._client.xtest_pointer_motion(root=self._root, point=point)
        self._client.flush()

    def click(self, point: RootPoint, button: PointerButton) -> None:
        """Move, press, and release a pointer button without leaking held state."""
        self._ensure_healthy()
        code = _button_code(button)
        held = False

        try:
            self._client.xtest_pointer_motion(root=self._root, point=point)
            self._client.xtest_button(root=self._root, button=code, pressed=True)
            held = True
            self._client.xtest_button(root=self._root, button=code, pressed=False)
            held = False
        finally:
            if held:
                try:
                    self._client.xtest_button(root=self._root, button=code, pressed=False)
                except (X11Error, xcffib.XcffibException) as exc:
                    self._healthy = False
                    msg = "X11 button release cleanup failed; input state is uncertain"
                    raise InputStateUncertainError(msg) from exc

            self._client.flush()

    def _get_keyboard(self) -> XkbKeyboard:
        if self._keyboard is None:
            self._keyboard = XkbKeyboard.connect(self._client)
        return self._keyboard

    def press_keys(self, keys: tuple[KeyName, ...]) -> None:
        """Press in tuple order and release in reverse order without hidden modifiers."""
        self._ensure_healthy()
        codes = self._get_keyboard().resolve_key_names(keys)
        self._inject_chord(codes)

    def type_text(self, text: str) -> None:
        """Plan every character before emitting the first key event."""
        self._ensure_healthy()
        plans = self._get_keyboard().plan_text(text)
        for plan in plans:
            self._inject_chord((*plan.modifiers, plan.key))

    def _inject_chord(self, codes: tuple[X11Keycode, ...]) -> None:
        held: list[X11Keycode] = []
        try:
            for code in codes:
                self._client.xtest_key(root=self._root, keycode=code, pressed=True)
                held.append(code)
            while held:
                self._client.xtest_key(root=self._root, keycode=held[-1], pressed=False)
                _ = held.pop()
        finally:
            cleanup_error: Exception | None = None
            for code in reversed(held):
                try:
                    self._client.xtest_key(root=self._root, keycode=code, pressed=False)
                except (X11Error, xcffib.XcffibException) as exc:
                    cleanup_error = exc
            try:
                self._client.flush()
            except (X11Error, xcffib.XcffibException) as exc:
                cleanup_error = exc
            if cleanup_error is not None:
                self._healthy = False
                self._keyboard_uncertain = True
                msg = "synthetic keyboard state could not be safely restored"
                raise InputStateUncertainError(msg) from cleanup_error

    def close(self) -> None:
        """Release input-owned resources."""
        if self._keyboard is not None:
            self._keyboard.close()

    def _ensure_healthy(self) -> None:
        """Reject input after held-state cleanup could not be guaranteed."""
        if self._keyboard_uncertain:
            msg = "synthetic keyboard state could not be safely restored"
            raise InputStateUncertainError(msg)
        if not self._healthy:
            msg = "X11 input state is uncertain after failed cleanup"
            raise InputStateUncertainError(msg)
