"""Tests for X11 domain models."""

from mint_computer_mcp.domain.x11 import (
    ExtensionStatus,
    ProtocolVersion,
    WindowManagerInfo,
    X11Extension,
    X11ProbeReport,
)


def test_probe_report_reports_supported_extension() -> None:
    report = X11ProbeReport(
        session_type="x11",
        desktop="X-Cinnamon",
        display=":0",
        vendor="test",
        protocol=ProtocolVersion(major=11, minor=0),
        release_number=1,
        preferred_screen=0,
        screens=(),
        extensions=(
            ExtensionStatus(
                extension=X11Extension.XTEST,
                available=True,
            ),
            ExtensionStatus(
                extension=X11Extension.DAMAGE,
                available=False,
            ),
        ),
        randr_version=None,
        outputs=(),
        window_manager=WindowManagerInfo(
            ewmh_detected=False,
            name=None,
            supporting_window=None,
        ),
    )

    assert report.supports(X11Extension.XTEST)
    assert not report.supports(X11Extension.DAMAGE)
