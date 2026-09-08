"""Integration tests for XKB inspection of the current X11 keyboard."""

import os

import pytest

from mint_computer_mcp.native.x11.client import X11Client
from mint_computer_mcp.native.x11.xkb import XkbKeyboard


@pytest.mark.integration
def test_connects_to_core_x11_keyboard() -> None:
    display = os.environ.get("DISPLAY")

    if not display:
        pytest.fail("DISPLAY is required for X11 integration tests")

    with X11Client.connect(display) as client, XkbKeyboard.connect(client) as keyboard:
        version = keyboard.protocol_version

        assert (version.major, version.minor) >= (1, 0)
        assert keyboard.device_id >= 0
