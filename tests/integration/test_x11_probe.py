"""Integration tests against the real desktop."""

import pytest

from mint_computer_mcp.domain.x11 import X11Extension
from mint_computer_mcp.native.x11.probe import probe_x11


@pytest.mark.integration
def test_x11_environment_supports_required_capabilities() -> None:
    report = probe_x11()

    assert report.supports(X11Extension.RANDR)
    assert report.supports(X11Extension.XTEST)

    assert report.randr_version is not None
    assert report.outputs

    assert report.window_manager.ewmh_detected
    assert report.window_manager.name is not None
