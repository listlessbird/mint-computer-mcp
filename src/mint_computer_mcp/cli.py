"""Command-line composition root."""

import logging
import os

from mint_computer_mcp.backend import BackendError
from mint_computer_mcp.native.x11.backend import X11Backend
from mint_computer_mcp.native.x11.client import X11Error
from mint_computer_mcp.observability import configure_logging, log_event
from mint_computer_mcp.runtime import DesktopRuntime
from mint_computer_mcp.server import create_server


def main() -> None:
    """Run the X11 desktop runtime over stdio MCP."""
    configure_logging()
    display = os.environ.get("DISPLAY")

    if not display:
        log_event(logging.ERROR, "mcp server startup", status="error", reason="DISPLAY is not set")
        msg = "DISPLAY is not set"
        raise SystemExit(msg)

    try:
        backend = X11Backend.connect(display)
    except (BackendError, X11Error) as exc:
        log_event(
            logging.ERROR,
            "mcp server startup",
            status="error",
            display=display,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        raise

    with DesktopRuntime(backend) as runtime:
        outputs = runtime.outputs()

        log_event(
            logging.INFO,
            "mcp server startup",
            status="ok",
            display=display,
            output_count=len(outputs),
            outputs=tuple(output.name for output in outputs),
        )

        server = create_server(runtime)
        server.run("stdio")
