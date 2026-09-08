"""Exercise XKB resource ownership without opening an X11 display."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

import pytest

from mint_computer_mcp.domain.x11 import ProtocolVersion
from mint_computer_mcp.native.x11.xkb import XkbClosedError, XkbKeyboard, XkbSetup, ffi

if TYPE_CHECKING:
    from cffi import CData

    from mint_computer_mcp.native.x11 import xkb
    from mint_computer_mcp.native.x11.client import X11Client


@dataclass(slots=True)
class CommonLibrary:
    unrefs: int = 0

    def xkb_context_new(self, flags: int) -> CData:
        assert flags == 0
        return ffi.cast("struct xkb_context *", 1)

    def xkb_context_unref(self, context: CData) -> None:
        assert context != ffi.NULL
        self.unrefs += 1


class X11Library:
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


def keyboard(common: CommonLibrary) -> XkbKeyboard:
    pointer = ffi.cast("xcb_connection_t *", 1)
    return XkbKeyboard(
        client=cast("X11Client", object()),
        common=cast("xkb._XkbCommonLib", cast("object", common)),  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        x11=cast("xkb._XkbX11Lib", cast("object", X11Library())),  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        connection=pointer,
        context=ffi.cast("struct xkb_context *", 2),
        setup=XkbSetup(version=ProtocolVersion(major=1, minor=0), device_id=3),
    )


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
