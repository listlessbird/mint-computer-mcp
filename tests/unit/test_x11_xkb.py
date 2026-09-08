"""Exercise XKB resource ownership without opening an X11 display."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

import pytest

from mint_computer_mcp.domain.x11 import ProtocolVersion
from mint_computer_mcp.native.x11.xkb import XkbClosedError, XkbError, XkbKeyboard, XkbSetup, ffi

if TYPE_CHECKING:
    from cffi import CData

    from mint_computer_mcp.native.x11 import xkb
    from mint_computer_mcp.native.x11.client import X11Client


@dataclass(slots=True)
class CommonLibrary:
    unrefs: int = 0
    map_unrefs: int = 0
    state_unrefs: int = 0

    def xkb_context_new(self, flags: int) -> CData:
        assert flags == 0
        return ffi.cast("struct xkb_context *", 1)

    def xkb_context_unref(self, context: CData) -> None:
        assert context != ffi.NULL
        self.unrefs += 1

    def xkb_keymap_unref(self, keymap: CData) -> None:
        assert keymap != ffi.NULL
        self.map_unrefs += 1

    def xkb_state_unref(self, state: CData) -> None:
        assert state != ffi.NULL
        self.state_unrefs += 1


@dataclass(slots=True)
class X11Library:
    fail_at: str = ""

    def xkb_x11_keymap_new_from_device(
        self, context: CData, connection: CData, device: int, flags: int
    ) -> CData:
        _ = context, connection, device, flags
        return ffi.NULL if self.fail_at == "map" else ffi.cast("struct xkb_keymap *", 3)

    def xkb_x11_state_new_from_device(self, keymap: CData, connection: CData, device: int) -> CData:
        _ = keymap, connection, device
        return ffi.NULL if self.fail_at == "state" else ffi.cast("struct xkb_state *", 4)

    def xkb_x11_setup_xkb_extension(  # noqa: PLR0913, PLR0917
        self,
        connection: CData,
        major: int,
        minor: int,
        flags: int,
        major_out: CData,
        minor_out: CData,
        base_event_out: CData,
        base_error_out: CData,
    ) -> int:
        _ = (
            connection,
            major,
            minor,
            flags,
            major_out,
            minor_out,
            base_event_out,
            base_error_out,
        )
        raise AssertionError

    def xkb_x11_get_core_keyboard_device_id(self, connection: CData) -> int:
        _ = connection
        raise AssertionError


def keyboard(common: CommonLibrary, fail_at: str = "") -> XkbKeyboard:
    pointer = ffi.cast("xcb_connection_t *", 1)
    board = object.__new__(XkbKeyboard)
    board._initialize(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        client=cast("X11Client", object()),
        common=cast("xkb._XkbCommonLib", cast("object", common)),  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        x11=cast("xkb._XkbX11Lib", cast("object", X11Library(fail_at=fail_at))),  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        connection=pointer,
        context=ffi.cast("struct xkb_context *", 2),
        setup=XkbSetup(version=ProtocolVersion(major=1, minor=0), device_id=3),
    )
    return board


def test_close_releases_context_once() -> None:
    common = CommonLibrary()
    xkb = keyboard(common)

    xkb.close()
    xkb.close()

    assert common.unrefs == 1


def test_diagnostics_fail_after_close() -> None:
    xkb = keyboard(CommonLibrary())
    xkb.close()

    with pytest.raises(XkbClosedError, match="boundary is closed"):
        _ = xkb.protocol_version

    with pytest.raises(XkbClosedError, match="boundary is closed"):
        _ = xkb.device_id


@pytest.mark.parametrize("fail_at", ["", "map", "state"])
def test_snapshot_releases_resources_on_success_and_failure(fail_at: str) -> None:
    common = CommonLibrary()
    with keyboard(common, fail_at) as board:
        if fail_at:
            with pytest.raises(XkbError, match="snapshot"):
                _ = board.resolve_key_names(())
        else:
            assert board.resolve_key_names(()) == ()
    assert common.unrefs == 1
    assert common.map_unrefs == (0 if fail_at == "map" else 1)
    assert common.state_unrefs == (0 if fail_at else 1)
