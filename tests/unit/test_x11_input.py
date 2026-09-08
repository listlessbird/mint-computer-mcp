"""Exercise input ordering and ownership using only fake native boundaries."""

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
    flush_failure: bool = False
    held: set[X11Keycode] = field(default_factory=set)
    user_held: frozenset[X11Keycode] = frozenset({X11Keycode(133)})

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

        if pressed:
            self.held.add(keycode)
        else:
            # The fake offers no generic modifier release. Every release must be owned.
            assert keycode not in self.user_held
            self.held.remove(keycode)

    def flush(self) -> None:
        self.calls.append(("flush",))
        if self.flush_failure:
            msg = "synthetic flush failure"
            raise X11Error(msg)


def x11_input(client: Client, keyboard: "Keyboard | None" = None) -> X11Input:
    return X11Input(
        client=cast("X11Client", cast("object", client)),
        root=ROOT,
        keyboard=cast("XkbKeyboard", cast("object", keyboard or Keyboard())),
    )


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


@dataclass(slots=True)
class Keyboard:
    plans: tuple[KeyStroke, ...] = (
        KeyStroke(modifiers=(), key=X11Keycode(70)),
        KeyStroke(modifiers=(X11Keycode(50),), key=X11Keycode(70)),
    )
    text_error: UnsupportedTextInputError | None = None
    planned: list[str] = field(default_factory=list)
    closed: bool = False

    def resolve_key_names(self, names: tuple[KeyName, ...]) -> tuple[X11Keycode, ...]:
        assert names == (KeyName("Control_L"), KeyName("a"))
        return (X11Keycode(50), X11Keycode(70))

    def plan_text(self, text: str) -> tuple[KeyStroke, ...]:
        self.planned.append(text)
        if self.text_error is not None:
            raise self.text_error
        return self.plans

    def close(self) -> None:
        self.closed = True


def test_chord_preserves_order() -> None:
    client = Client()

    x11_input(client).press_keys((KeyName("Control_L"), KeyName("a")))
    assert client.calls == [
        ("key", 50, True),
        ("key", 70, True),
        ("key", 70, False),
        ("key", 50, False),
        ("flush",),
    ]


@pytest.mark.parametrize("failures", [1, 2, 3])
def test_keyboard_cleanup_attempts_every_owned_key(failures: int) -> None:
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


def test_text_flushes_once_after_the_complete_plan() -> None:
    client, keyboard = Client(), Keyboard()
    x11_input(client, keyboard).type_text("aA")
    assert keyboard.planned == ["aA"]
    assert client.calls == [
        ("key", 70, True),
        ("key", 70, False),
        ("key", 50, True),
        ("key", 70, True),
        ("key", 70, False),
        ("key", 50, False),
        ("flush",),
    ]
    assert not client.held


def test_unsupported_text_emits_no_events_or_flush() -> None:
    client = Client()
    keyboard = Keyboard(
        text_error=UnsupportedTextInputError("unsupported codepoint U+4E16 at character index 3")
    )
    with pytest.raises(UnsupportedTextInputError, match=r"U\+4E16"):
        x11_input(client, keyboard).type_text("abc世")
    assert keyboard.planned == ["abc世"]
    assert client.calls == []
    assert not client.held


def test_failed_keydown_releases_only_previously_pressed_keys() -> None:
    client = Client(press_failure=70)
    with pytest.raises(X11Error, match="press failure"):
        x11_input(client).press_keys((KeyName("Control_L"), KeyName("a")))
    assert client.calls == [
        ("key", 50, True),
        ("key", 70, True),
        ("key", 50, False),
        ("flush",),
    ]


@pytest.mark.parametrize("modifiers", [(50,), (92,), (50, 92)])
def test_text_stroke_releases_modifiers_in_reverse_order(modifiers: tuple[int, ...]) -> None:
    client = Client()
    codes = tuple(X11Keycode(code) for code in modifiers)
    keyboard = Keyboard(plans=(KeyStroke(modifiers=codes, key=X11Keycode(70)),))
    x11_input(client, keyboard).type_text("A")
    assert client.calls == [
        *(("key", code, True) for code in codes),
        ("key", 70, True),
        ("key", 70, False),
        *(("key", code, False) for code in reversed(codes)),
        ("flush",),
    ]
    assert not client.held
    assert client.user_held == {133}


@pytest.mark.parametrize("release_failures", [0, 1])
def test_text_failure_cleans_only_owned_modifiers(release_failures: int) -> None:
    client = Client(press_failure=70, release_failures=release_failures)
    keyboard = Keyboard(
        plans=(
            KeyStroke(modifiers=(X11Keycode(50), X11Keycode(92)), key=X11Keycode(70)),
            KeyStroke(modifiers=(), key=X11Keycode(80)),
        )
    )
    input_ = x11_input(client, keyboard)
    expected = InputStateUncertainError if release_failures else X11Error
    with pytest.raises(expected):
        input_.type_text("Aa")
    assert client.calls == [
        ("key", 50, True),
        ("key", 92, True),
        ("key", 70, True),
        ("key", 92, False),
        ("key", 50, False),
        ("flush",),
    ]
    assert client.user_held == {133}
    if release_failures:
        assert client.held == {92}
        with pytest.raises(InputStateUncertainError):
            input_.type_text("again")
        assert keyboard.planned == ["Aa"]
    else:
        assert not client.held
        input_.move_pointer(RootPoint(0, 0))


@pytest.mark.parametrize("action", ["text", "chord", "click", "move"])
def test_uncertain_keyboard_rejects_every_subsequent_action(action: str) -> None:
    client = Client(press_failure=70, release_failures=1)
    keyboard = Keyboard(plans=(KeyStroke(modifiers=(X11Keycode(50),), key=X11Keycode(70)),))
    input_ = x11_input(client, keyboard)
    with pytest.raises(InputStateUncertainError):
        input_.type_text("A")
    before = client.calls.copy()
    actions = {
        "text": lambda: input_.type_text("A"),
        "chord": lambda: input_.press_keys((KeyName("Control_L"), KeyName("a"))),
        "click": lambda: input_.click(RootPoint(0, 0), PointerButton.LEFT),
        "move": lambda: input_.move_pointer(RootPoint(0, 0)),
    }
    with pytest.raises(InputStateUncertainError, match="safely restored"):
        actions[action]()
    assert client.calls == before
    assert keyboard.planned == ["A"]


def test_flush_failure_marks_keyboard_unhealthy() -> None:
    client = Client(flush_failure=True)
    input_ = x11_input(client)
    with pytest.raises(InputStateUncertainError):
        input_.type_text("aA")
    assert not client.held
    before = client.calls.copy()
    with pytest.raises(InputStateUncertainError):
        input_.type_text("aA")
    assert client.calls == before


def test_close_releases_injected_keyboard() -> None:
    keyboard = Keyboard()
    x11_input(Client(), keyboard).close()
    assert keyboard.closed
