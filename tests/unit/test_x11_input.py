"""Exercise X11 pointer input without opening a display."""

from dataclasses import dataclass, field
from typing import cast

import pytest

from mint_computer_mcp.backend import InputStateUncertainError
from mint_computer_mcp.domain.geometry import RootPoint
from mint_computer_mcp.domain.identifiers import WindowId
from mint_computer_mcp.domain.input import PointerButton
from mint_computer_mcp.native.x11.client import X11Client, X11Error
from mint_computer_mcp.native.x11.input import X11Input

ROOT = WindowId(10)

type InputCall = tuple[str, int, int] | tuple[str, int, bool] | tuple[str]


@dataclass(slots=True)
class Client:
    calls: list[InputCall] = field(default_factory=list)
    release_failures: int = 0

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
