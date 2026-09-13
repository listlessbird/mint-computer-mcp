"""Check the synthetic MCP benchmark entry point."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "benchmarks" / "mcp.py"


def test_mcp_benchmark_runs_without_a_desktop() -> None:
    environment = os.environ.copy()
    environment["DISPLAY"] = ":ambient-must-not-be-used"
    result = subprocess.run(  # noqa: S603 - fixed local benchmark script.
        [
            sys.executable,
            str(_SCRIPT),
            "--iterations",
            "2",
            "--warmup",
            "1",
            "--width",
            "16",
            "--height",
            "16",
        ],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )

    assert result.returncode == 0, result.stderr
    assert "Runtime observe" in result.stdout
    assert "MCP desktop_observe" in result.stdout
    assert "Runtime act" in result.stdout
    assert "MCP desktop_act" in result.stdout
    assert "structured metadata JSON" in result.stdout
    assert "growth after warmup" in result.stdout


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (("--iterations", "0"), "--iterations must be positive"),
        (("--warmup", "-1"), "--warmup must be nonnegative"),
        (("--width", "0"), "--width and --height must be positive"),
        (("--height", "0"), "--width and --height must be positive"),
    ],
)
def test_mcp_benchmark_rejects_invalid_arguments(
    arguments: tuple[str, ...],
    message: str,
) -> None:
    result = subprocess.run(  # noqa: S603 - fixed local script with invalid arguments.
        [sys.executable, str(_SCRIPT), *arguments],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )

    assert result.returncode == 2
    assert message in result.stderr
    assert "Traceback" not in result.stderr
