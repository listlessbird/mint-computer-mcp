"""Exercise real input on an owned Xvfb server, never the inherited DISPLAY."""

import pytest
import xcffib.xkb

from mint_computer_mcp.domain.geometry import SnapshotPoint
from mint_computer_mcp.domain.input import Click, KeyName, MovePointer, PointerButton, PressKeys
from mint_computer_mcp.domain.observation import DesktopTarget
from mint_computer_mcp.native.x11.backend import X11Backend
from mint_computer_mcp.runtime import DesktopRuntime

pytestmark = pytest.mark.integration


def test_pointer_position_after_runtime_move(
    isolated_x11_display: str,
    isolated_x11_reader: xcffib.Connection,
) -> None:
    with DesktopRuntime(X11Backend.connect(isolated_x11_display)) as runtime:
        observation = runtime.observe(DesktopTarget())
        runtime.act(MovePointer(observation.snapshot.id, SnapshotPoint(123, 234)))
        root = isolated_x11_reader.get_setup().roots[isolated_x11_reader.pref_screen].root
        pointer = isolated_x11_reader.core.QueryPointer(root).reply()
        assert pointer.same_screen
        assert (pointer.root_x, pointer.root_y) == (123, 234)


def test_click_finishes_with_button_released(
    isolated_x11_display: str,
    isolated_x11_reader: xcffib.Connection,
) -> None:
    with DesktopRuntime(X11Backend.connect(isolated_x11_display)) as runtime:
        observation = runtime.observe(DesktopTarget())
        runtime.act(Click(observation.snapshot.id, SnapshotPoint(80, 90), PointerButton.LEFT))
        root = isolated_x11_reader.get_setup().roots[isolated_x11_reader.pref_screen].root
        pointer = isolated_x11_reader.core.QueryPointer(root).reply()
        assert (pointer.root_x, pointer.root_y) == (80, 90)
        assert pointer.mask & (1 << 8) == 0  # Core Button1Mask.


def test_caps_lock_changes_server_state_and_restores_it(
    isolated_x11_display: str,
    isolated_x11_reader: xcffib.Connection,
) -> None:
    extension = isolated_x11_reader(xcffib.xkb.key)
    assert extension.UseExtension(1, 0).reply().supported
    core_keyboard = 0x0100  # XkbUseCoreKbd.
    with DesktopRuntime(X11Backend.connect(isolated_x11_display)) as runtime:
        original = extension.GetState(core_keyboard).reply().lockedMods
        chord = PressKeys((KeyName("Caps_Lock"),))
        try:
            runtime.act(chord)
            assert extension.GetState(core_keyboard).reply().lockedMods != original
        finally:
            if extension.GetState(core_keyboard).reply().lockedMods != original:
                runtime.act(chord)
            assert extension.GetState(core_keyboard).reply().lockedMods == original
