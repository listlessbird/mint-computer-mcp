"""Command-line composition root."""

import os

from mint_computer_mcp.native.x11.backend import X11Backend
from mint_computer_mcp.runtime import DesktopRuntime
from mint_computer_mcp.server import create_server


def main() -> None:
    """Run the X11 desktop runtime over stdio MCP."""
    display = os.environ.get("DISPLAY")

    if not display:
        msg = "DISPLAY is not set"
        raise SystemExit(msg)

    with DesktopRuntime(
        X11Backend.connect(display),
    ) as runtime:
        server = create_server(runtime)
        server.run("stdio")
