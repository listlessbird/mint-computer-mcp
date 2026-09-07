"""Stateful X11 input injection built on narrow XTEST operations."""

from typing import assert_never, final

import xcffib

from mint_computer_mcp.backend import InputStateUncertainError
from mint_computer_mcp.domain.geometry import RootPoint
from mint_computer_mcp.domain.identifiers import WindowId
from mint_computer_mcp.domain.input import PointerButton
from mint_computer_mcp.native.x11.client import X11Client, X11Error


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

    def close(self) -> None:
        """Release input-owned resources."""

    def _ensure_healthy(self) -> None:
        """Reject input after held-state cleanup could not be guaranteed."""
        if not self._healthy:
            msg = "X11 input state is uncertain after failed cleanup"
            raise InputStateUncertainError(msg)
