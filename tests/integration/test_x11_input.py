"""Exercise real input on an owned Xvfb server, never the inherited DISPLAY."""

from __future__ import annotations

import os
import select
import shutil
import subprocess
from typing import TYPE_CHECKING

import pytest
import xcffib
import xcffib.xkb

from mint_computer_mcp.domain.geometry import SnapshotPoint
from mint_computer_mcp.domain.input import Click, KeyName, MovePointer, PointerButton, PressKeys
from mint_computer_mcp.domain.observation import DesktopTarget
from mint_computer_mcp.native.x11.backend import X11Backend
from mint_computer_mcp.runtime import DesktopRuntime

if TYPE_CHECKING:
    from collections.abc import Generator

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def input_display(tmp_path_factory: pytest.TempPathFactory) -> Generator[str]:
    executable = shutil.which("Xvfb")
    if executable is None:
        pytest.fail("Xvfb is required for isolated input integration tests; install xvfb")

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
def reader(input_display: str) -> Generator[xcffib.Connection]:
    connection = xcffib.connect(display=input_display)
    try:
        yield connection
    finally:
        connection.disconnect()


def test_pointer_position_after_runtime_move(
    input_display: str,
    reader: xcffib.Connection,
) -> None:
    with DesktopRuntime(X11Backend.connect(input_display)) as runtime:
        observation = runtime.observe(DesktopTarget())
        runtime.act(MovePointer(observation.snapshot.id, SnapshotPoint(123, 234)))
        root = reader.get_setup().roots[reader.pref_screen].root
        pointer = reader.core.QueryPointer(root).reply()
        assert pointer.same_screen
        assert (pointer.root_x, pointer.root_y) == (123, 234)


def test_click_finishes_with_button_released(
    input_display: str,
    reader: xcffib.Connection,
) -> None:
    with DesktopRuntime(X11Backend.connect(input_display)) as runtime:
        observation = runtime.observe(DesktopTarget())
        runtime.act(Click(observation.snapshot.id, SnapshotPoint(80, 90), PointerButton.LEFT))
        root = reader.get_setup().roots[reader.pref_screen].root
        pointer = reader.core.QueryPointer(root).reply()
        assert (pointer.root_x, pointer.root_y) == (80, 90)
        assert pointer.mask & (1 << 8) == 0  # Core Button1Mask.


def test_caps_lock_changes_server_state_and_restores_it(
    input_display: str,
    reader: xcffib.Connection,
) -> None:
    extension = reader(xcffib.xkb.key)
    assert extension.UseExtension(1, 0).reply().supported
    core_keyboard = 0x0100  # XkbUseCoreKbd.
    with DesktopRuntime(X11Backend.connect(input_display)) as runtime:
        original = extension.GetState(core_keyboard).reply().lockedMods
        chord = PressKeys((KeyName("Caps_Lock"),))
        try:
            runtime.act(chord)
            assert extension.GetState(core_keyboard).reply().lockedMods != original
        finally:
            if extension.GetState(core_keyboard).reply().lockedMods != original:
                runtime.act(chord)
            assert extension.GetState(core_keyboard).reply().lockedMods == original
