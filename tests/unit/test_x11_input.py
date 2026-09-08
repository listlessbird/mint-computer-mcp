"""Exercise X11 pointer input without opening a display."""

from dataclasses import dataclass, field
from typing import cast

import pytest

from mint_computer_mcp.backend import InputStateUncertainError, UnsupportedTextInputError
from mint_computer_mcp.domain.geometry import RootPoint
from mint_computer_mcp.domain.identifiers import WindowId, X11Keycode
from mint_computer_mcp.domain.input import KeyName, PointerButton
from mint_computer_mcp.native.x11.client import X11Client, X11Error
from mint_computer_mcp.native.x11.input import X11Input
from mint_computer_mcp.native.x11.xkb import KeyStroke, XkbKeyboard

ROOT = WindowId(10)

type InputCall = tuple[str, int, int] | tuple[str, int, bool] | tuple[str]


@dataclass(slots=True)
class Client:
    calls: list[InputCall] = field(default_factory=list)
    release_failures: int = 0
    press_failure: int | None = None

    def xtest_pointer_motion(self, *, root: WindowId, point: RootPoint) -> None:
        assert root == ROOT
        self.calls.append(("motion", point.x, point.y))

    def xtest_button(self, *, root: WindowId, button: int, pressed: bool) -> None:
        assert root == ROOT
        self.calls.append(("button", button, pressed))
        if not pressed and self.release_failures:
            self.release_failures -= 1
            msg = "synthetic release failure"
            raise X11Error(msg)

    def xtest_key(self, *, root: WindowId, keycode: X11Keycode, pressed: bool) -> None:
        assert root == ROOT
        self.calls.append(("key", keycode, pressed))
        if pressed and keycode == self.press_failure:
            msg = "synthetic press failure"
            raise X11Error(msg)
        if not pressed and self.release_failures:
            self.release_failures -= 1
            msg = "synthetic release failure"
            raise X11Error(msg)

    def flush(self) -> None:
        self.calls.append(("flush",))


def x11_input(client: Client) -> X11Input:
    return X11Input(client=cast("X11Client", cast("object", client)), root=ROOT)


def test_move_pointer_sends_motion_then_flushes() -> None:
    client = Client()

    x11_input(client).move_pointer(RootPoint(x=-12, y=34))

    assert client.calls == [("motion", -12, 34), ("flush",)]


@pytest.mark.parametrize(
    ("button", "code"),
    [
        (PointerButton.LEFT, 1),
        (PointerButton.MIDDLE, 2),
        (PointerButton.RIGHT, 3),
    ],
)
def test_click_maps_button_and_preserves_request_order(
    button: PointerButton,
    code: int,
) -> None:
    client = Client()

    x11_input(client).click(RootPoint(x=20, y=30), button)

    assert client.calls == [
        ("motion", 20, 30),
        ("button", code, True),
        ("button", code, False),
        ("flush",),
    ]


def test_click_retries_release_after_first_release_failure() -> None:
    client = Client(release_failures=1)
    input_ = x11_input(client)

    with pytest.raises(X11Error, match="synthetic release failure"):
        input_.click(RootPoint(x=20, y=30), PointerButton.LEFT)

    input_.move_pointer(RootPoint(x=40, y=50))

    assert client.calls == [
        ("motion", 20, 30),
        ("button", 1, True),
        ("button", 1, False),
        ("button", 1, False),
        ("flush",),
        ("motion", 40, 50),
        ("flush",),
    ]


def test_click_becomes_unhealthy_when_release_cleanup_also_fails() -> None:
    client = Client(release_failures=2)
    input_ = x11_input(client)

    with pytest.raises(InputStateUncertainError, match="cleanup failed"):
        input_.click(RootPoint(x=20, y=30), PointerButton.LEFT)

    with pytest.raises(InputStateUncertainError, match="uncertain after failed cleanup"):
        input_.move_pointer(RootPoint(x=40, y=50))

    assert client.calls == [
        ("motion", 20, 30),
        ("button", 1, True),
        ("button", 1, False),
        ("button", 1, False),
    ]


class Keyboard:
    def resolve_key_names(self, names: tuple[KeyName, ...]) -> tuple[X11Keycode, ...]:
        assert names == (KeyName("Control_L"), KeyName("a"))
        return (X11Keycode(50), X11Keycode(70))


def test_chord_preserves_order(monkeypatch: pytest.MonkeyPatch) -> None:
    client = Client()

    def connect(_client: X11Client) -> XkbKeyboard:
        return cast("XkbKeyboard", cast("object", Keyboard()))

    monkeypatch.setattr(XkbKeyboard, "connect", connect)
    x11_input(client).press_keys((KeyName("Control_L"), KeyName("a")))
    assert client.calls == [
        ("key", 50, True),
        ("key", 70, True),
        ("key", 70, False),
        ("key", 50, False),
        ("flush",),
    ]


@pytest.mark.parametrize("failures", [1, 2, 3])
def test_keyboard_cleanup_attempts_every_owned_key(
    monkeypatch: pytest.MonkeyPatch, failures: int
) -> None:
    def connect(_client: X11Client) -> XkbKeyboard:
        return cast("XkbKeyboard", cast("object", Keyboard()))

    monkeypatch.setattr(XkbKeyboard, "connect", connect)
    client = Client(release_failures=failures)
    input_ = x11_input(client)
    expected = InputStateUncertainError if failures >= 2 else X11Error
    with pytest.raises(expected):
        input_.press_keys((KeyName("Control_L"), KeyName("a")))
    assert client.calls[-3:] == [("key", 70, False), ("key", 50, False), ("flush",)]
    if failures >= 2:
        with pytest.raises(InputStateUncertainError, match="safely restored"):
            input_.move_pointer(RootPoint(x=0, y=0))
    else:
        input_.move_pointer(RootPoint(x=0, y=0))


@pytest.mark.parametrize("unsupported", [False, True])
def test_text_is_fully_planned_before_any_injection(
    monkeypatch: pytest.MonkeyPatch, *, unsupported: bool
) -> None:
    client = Client()

    def plan_text(_self: XkbKeyboard, text: str) -> tuple[KeyStroke, ...]:
        assert text == "aA"
        assert not client.calls
        if unsupported:
            msg = "unsupported codepoint U+4E16 at character index 1"
            raise UnsupportedTextInputError(msg)
        return (
            KeyStroke(modifiers=(), key=X11Keycode(70)),
            KeyStroke(modifiers=(X11Keycode(50),), key=X11Keycode(70)),
        )

    def connect(_client: X11Client) -> XkbKeyboard:
        return object.__new__(XkbKeyboard)

    monkeypatch.setattr(XkbKeyboard, "connect", connect)
    monkeypatch.setattr(XkbKeyboard, "plan_text", plan_text)
    input_ = x11_input(client)
    if unsupported:
        with pytest.raises(UnsupportedTextInputError):
            input_.type_text("aA")
        assert not client.calls
    else:
        input_.type_text("aA")
        assert client.calls == [
            ("key", 70, True),
            ("key", 70, False),
            ("flush",),
            ("key", 50, True),
            ("key", 70, True),
            ("key", 70, False),
            ("key", 50, False),
            ("flush",),
        ]


def test_failed_keydown_releases_only_previously_pressed_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def connect(_client: X11Client) -> XkbKeyboard:
        return cast("XkbKeyboard", cast("object", Keyboard()))

    monkeypatch.setattr(XkbKeyboard, "connect", connect)
    client = Client(press_failure=70)
    with pytest.raises(X11Error, match="press failure"):
        x11_input(client).press_keys((KeyName("Control_L"), KeyName("a")))
    assert client.calls == [
        ("key", 50, True),
        ("key", 70, True),
        ("key", 50, False),
        ("flush",),
    ]
