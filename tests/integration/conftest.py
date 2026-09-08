"""Shared fixtures for integration tests that own an isolated X11 server."""

from __future__ import annotations

import os
import select
import shutil
import subprocess
from typing import TYPE_CHECKING

import pytest
import xcffib

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture(scope="module")
def isolated_x11_display(tmp_path_factory: pytest.TempPathFactory) -> Generator[str]:
    """Start an owned Xvfb server and yield its display name."""
    executable = shutil.which("Xvfb")
    if executable is None:
        pytest.fail("Xvfb is required for isolated X11 integration tests; install xvfb")

    log_path = tmp_path_factory.mktemp("xvfb") / "server.log"
    read_fd, write_fd = os.pipe()
    with os.fdopen(read_fd, "rb") as ready, os.fdopen(write_fd, "wb") as notification:
        with log_path.open("w") as log:
            process = subprocess.Popen(  # noqa: S603 - resolved Xvfb executable, fixed arguments.
                [
                    executable,
                    "-displayfd",
                    str(notification.fileno()),
                    "-screen",
                    "0",
                    "800x600x24",
                    "-nolisten",
                    "tcp",
                    "-noreset",
                ],
                pass_fds=(notification.fileno(),),
                stdout=log,
                stderr=log,
            )
        try:
            if not select.select([ready], [], [], 10)[0]:
                pytest.fail(f"Xvfb did not become ready: {log_path.read_text()}")
            number = ready.readline().strip()
            if not number.isdigit():
                pytest.fail(f"Xvfb returned an invalid display: {log_path.read_text()}")
            yield f":{number.decode('ascii')}"
        finally:
            process.terminate()
            try:
                _ = process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                _ = process.wait(timeout=5)


@pytest.fixture
def isolated_x11_reader(
    isolated_x11_display: str,
) -> Generator[xcffib.Connection]:
    """Open an independent X11 connection for integration assertions."""
    connection = xcffib.connect(display=isolated_x11_display)
    try:
        yield connection
    finally:
        connection.disconnect()
