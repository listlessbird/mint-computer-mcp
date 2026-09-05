"""Inspect the current X11 desktop without changing its state."""

import os
import sys

from mint_computer_mcp.domain.identifiers import WindowId
from mint_computer_mcp.domain.x11 import (
    ExtensionStatus,
    ProtocolVersion,
    WindowManagerInfo,
    X11Extension,
    X11ProbeReport,
)
from mint_computer_mcp.native.x11.client import X11Client, X11Error

_NET_SUPPORTING_WM_CHECK = "_NET_SUPPORTING_WM_CHECK"
_NET_WM_NAME = "_NET_WM_NAME"


class X11ProbeError(RuntimeError):
    """Base error raised during the X11 environment probe."""


class UnsupportedSessionError(X11ProbeError):
    """Raised when the current desktop explicitly isn't X11."""


class MissingDisplayError(X11ProbeError):
    """Raised when DISPLAY is unavailable."""


def _probe_wm(client: X11Client, *, root: WindowId) -> WindowManagerInfo:
    """Detect the window manager through its EWMH supporting-window handshake.

    Root window -- _NET_SUPPORTING_WM_CHECK --> helper window A
    Helper window A -- _NET_SUPPORTING_WM_CHECK --> itself

    identifies EWMH spec support.
    """
    supporting_window = client.window_property(window=root, name=_NET_SUPPORTING_WM_CHECK)

    if supporting_window is None:
        return WindowManagerInfo(ewmh_detected=False, name=None, supporting_window=None)

    self_check = client.window_property(window=supporting_window, name=_NET_SUPPORTING_WM_CHECK)

    if self_check != supporting_window:
        return WindowManagerInfo(
            ewmh_detected=False, name=None, supporting_window=supporting_window
        )

    return WindowManagerInfo(
        ewmh_detected=True,
        name=client.utf8_property(window=supporting_window, name=_NET_WM_NAME),
        supporting_window=supporting_window,
    )


def probe_x11() -> X11ProbeReport:
    """Inspect the current X11 desktop and report expected native failures."""
    session_type = os.environ.get("XDG_SESSION_TYPE")

    if session_type is not None and session_type.casefold() != "x11":
        msg = f"expected X11, got {session_type!r}"
        raise UnsupportedSessionError(msg)

    display = os.environ.get("DISPLAY")

    if not display:
        msg = "DISPLAY is not set"
        raise MissingDisplayError(msg)

    try:
        with X11Client.connect(display) as client:
            exts = client.extensions()
            root = client.root_window()

            exts_status = tuple(
                ExtensionStatus(extension=ext, available=ext.value.upper() in exts)
                for ext in X11Extension
            )

            randr_available = "RANDR" in exts

            randr_version: ProtocolVersion | None = None
            outputs = ()

            if randr_available:
                randr_version = client.randr_version()
                if (randr_version.major, randr_version.minor) >= (1, 2):
                    outputs = client.randr_outputs(root=root, version=randr_version)

            return X11ProbeReport(
                session_type=session_type,
                desktop=os.environ.get("XDG_CURRENT_DESKTOP"),
                display=display,
                vendor=client.vendor,
                protocol=client.protocol_version,
                release_number=client.release_number,
                preferred_screen=client.preferred_screen,
                screens=client.screens(),
                extensions=exts_status,
                randr_version=randr_version,
                outputs=outputs,
                window_manager=_probe_wm(client=client, root=root),
            )
    except X11Error as exc:
        raise X11ProbeError(str(exc)) from exc


def format_probe_report(report: X11ProbeReport) -> str:
    """Format report."""
    lines = [
        "Session",
        f"  type: {report.session_type or 'unknown'}",
        f"  desktop: {report.desktop or 'unknown'}",
        f"  display: {report.display}",
        "",
        "X server",
        f"  vendor: {report.vendor}",
        f"  protocol: {report.protocol.major}.{report.protocol.minor}",
        f"  release: {report.release_number}",
        f"  preferred screen: {report.preferred_screen}",
    ]

    lines.extend(
        f"  screen {screen.index}: {screen.size.width}x{screen.size.height} root=0x{int(screen.root):x}"
        for screen in report.screens
    )

    lines.extend(
        [
            "",
            "Extensions",
        ]
    )

    for status in report.extensions:
        available = "yes" if status.available else "no"

        lines.append(f"  {status.extension.value:<10} {available}")

    lines.extend(
        [
            "",
            "RandR",
        ]
    )

    if report.randr_version is None:
        lines.append("  unavailable")
    else:
        lines.append(f"  version: {report.randr_version.major}.{report.randr_version.minor}")

    lines.extend(
        [
            "",
            "Outputs",
        ]
    )

    if not report.outputs:
        lines.append("  none")
    else:
        for output in report.outputs:
            marker = "*" if output.primary else " "
            rect = output.geometry

            lines.append(
                f"  {marker} {output.name:<12} {rect.width}x{rect.height} {rect.x:+d}{rect.y:+d}"
            )

    wm = report.window_manager

    lines.extend(
        [
            "",
            "Window manager",
            f"  EWMH detected: {'yes' if wm.ewmh_detected else 'no'}",
            f"  name: {wm.name or 'unknown'}",
        ]
    )

    if wm.supporting_window is not None:
        lines.append(f"  supporting window: 0x{int(wm.supporting_window):x}")

    return "\n".join(lines)


def main() -> None:
    """Run the probe."""
    try:
        report = probe_x11()
    except X11ProbeError as exc:
        _ = sys.stderr.write(f"X11 probe failed: {exc}\n")
        raise SystemExit(1) from exc

    _ = sys.stdout.write(format_probe_report(report))
    _ = sys.stdout.write("\n")


if __name__ == "__main__":
    main()
