"""Check input benchmark target validation without connecting to any display."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "benchmarks" / "x11-input.py"


@pytest.mark.parametrize(
    ("input_display", "arguments", "message"),
    [
        (None, (), "--display or MINT_COMPUTER_INPUT_DISPLAY is required"),
        (":explicit-env", ("--iterations", "0"), "--iterations must be positive"),
        (
            ":explicit-env",
            ("--display", ""),
            "--display or MINT_COMPUTER_INPUT_DISPLAY is required",
        ),
        (None, ("--display", ":explicit-cli", "--warmup", "-1"), "--warmup must be nonnegative"),
    ],
)
def test_target_validation_precedes_connections(
    input_display: str | None,
    arguments: tuple[str, ...],
    message: str,
) -> None:
    environment = os.environ.copy()
    environment["DISPLAY"] = ":ambient-must-not-be-used"
    _ = environment.pop("MINT_COMPUTER_INPUT_DISPLAY", None)
    if input_display is not None:
        environment["MINT_COMPUTER_INPUT_DISPLAY"] = input_display
    result = subprocess.run(  # noqa: S603 - fixed local script, invalid arguments prevent all input.
        [sys.executable, str(_SCRIPT), *arguments],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 2
    assert message in result.stderr
    assert "Traceback" not in result.stderr
