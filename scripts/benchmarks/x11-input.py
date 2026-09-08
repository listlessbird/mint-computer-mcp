"""Benchmark verified GTK editor responses to X11 input on an explicit display."""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import select
import subprocess
import sys
import time
from array import array
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryFile
from typing import TYPE_CHECKING, ClassVar, Literal, final

from pydantic import BaseModel, ConfigDict

from mint_computer_mcp.domain.geometry import RootPoint
from mint_computer_mcp.domain.input import KeyName, PointerButton
from mint_computer_mcp.native.x11.client import X11Client
from mint_computer_mcp.native.x11.input import X11Input
from mint_computer_mcp.native.x11.xkb import XkbKeyboard

if TYPE_CHECKING:
    from collections.abc import Generator
    from typing import BinaryIO

_KIB = 1024
_SEED = "Hello X11! The quick brown fox jumps over 42 lazy dogs.\n"


@final
class _Arguments(argparse.Namespace):
    display: str | None = None
    iterations: int = 100
    warmup: int = 5
    timeout: float = 5.0
    editor_python: str = "/usr/bin/python3"


class _Reply(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(strict=True, extra="forbid")

    request_id: int
    status: Literal["ready", "prepared", "done"]
    completed_ns: int
    x: int
    y: int
    text: str
    selection: str
    focused: bool


@dataclass(frozen=True, slots=True)
class _Case:
    name: str
    mode: Literal["focus", "select", "type"]
    text: str = ""


@dataclass(slots=True)
class _Measurement:
    case: _Case
    seconds: array[float] = field(default_factory=lambda: array("d"))
    failures: int = 0


def _arguments() -> _Arguments:
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument(
        "--display",
        help="Input target; defaults only to MINT_COMPUTER_INPUT_DISPLAY, never DISPLAY",
    )
    _ = parser.add_argument("--iterations", type=int, default=100)
    _ = parser.add_argument("--warmup", type=int, default=5)
    _ = parser.add_argument("--timeout", type=float, default=5.0)
    _ = parser.add_argument(
        "--editor-python",
        default="/usr/bin/python3",
        help="Python interpreter with PyGObject and GTK 3 installed",
    )
    arguments = _Arguments()
    arguments.display = os.environ.get("MINT_COMPUTER_INPUT_DISPLAY")
    _ = parser.parse_args(namespace=arguments)
    if not arguments.display or not arguments.display.strip():
        parser.error("--display or MINT_COMPUTER_INPUT_DISPLAY is required")
    if arguments.iterations <= 0:
        parser.error("--iterations must be positive")
    if arguments.warmup < 0:
        parser.error("--warmup must be nonnegative")
    if not math.isfinite(arguments.timeout) or arguments.timeout <= 0:
        parser.error("--timeout must be finite and positive")
    return arguments


def _rss_bytes(pid: int | None = None) -> int:
    for line in Path(f"/proc/{pid or os.getpid()}/status").read_text(encoding="utf-8").splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) * _KIB
    msg = "VmRSS was not available in /proc/self/status"
    raise RuntimeError(msg)


def _percentile(values: array[float], fraction: float) -> float:
    """Return a nearest-rank percentile in milliseconds."""
    if not values:
        return float("nan")
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)] * 1000


@final
class _Editor:
    def __init__(self, process: subprocess.Popen[bytes], log: BinaryIO, timeout: float) -> None:
        self.process = process
        self._log = log
        self._timeout = timeout
        self._buffer = b""
        self._request_id = 0

    def receive(self, status: str) -> _Reply:
        """Wait for a matching application acknowledgement within a bounded deadline."""
        if self.process.stdout is None:
            msg = "editor stdout is unavailable"
            raise RuntimeError(msg)
        deadline = time.monotonic() + self._timeout
        while True:
            while b"\n" in self._buffer:
                line, self._buffer = self._buffer.split(b"\n", 1)
                reply = _Reply.model_validate_json(line)
                if reply.request_id == self._request_id and reply.status == status:
                    return reply
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([self.process.stdout], [], [], remaining)[0]:
                msg = f"editor timed out waiting for {status}"
                raise TimeoutError(msg)
            chunk = os.read(self.process.stdout.fileno(), 65536)
            if not chunk:
                _ = self._log.seek(0)
                msg = f"editor exited: {self._log.read().decode(errors='replace')}"
                raise RuntimeError(msg)
            self._buffer += chunk

    def prepare(self, case: _Case) -> _Reply:
        """Reset and paint the editor outside the timed operation."""
        self._request_id += 1
        command = {"request_id": self._request_id, "case": case.mode, "text": case.text}
        if self.process.stdin is None:
            msg = "editor stdin is unavailable"
            raise RuntimeError(msg)
        _ = self.process.stdin.write((json.dumps(command) + "\n").encode())
        self.process.stdin.flush()
        reply = self.receive("prepared")
        expected_text = case.text if case.mode == "select" else ""
        if (
            reply.text != expected_text
            or reply.selection
            or reply.focused != (case.mode != "focus")
        ):
            msg = "editor preparation did not establish the requested initial state"
            raise RuntimeError(msg)
        return reply


@contextmanager
def _editor(arguments: _Arguments) -> Generator[_Editor]:
    environment = os.environ.copy()
    environment["DISPLAY"] = str(arguments.display)
    environment["GDK_BACKEND"] = "x11"
    environment["NO_AT_BRIDGE"] = "1"
    script = Path(__file__).with_name("_x11_input_editor.py")
    with TemporaryFile() as log:
        process = subprocess.Popen(  # noqa: S603 - explicit interpreter, fixed local helper.
            [arguments.editor_python, str(script)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=log,
            env=environment,
        )
        try:
            editor = _Editor(process, log, arguments.timeout)
            _ = editor.receive("ready")
            yield editor
        finally:
            process.terminate()
            try:
                _ = process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                _ = process.wait(timeout=5)
            if process.stdin is not None:
                process.stdin.close()
            if process.stdout is not None:
                process.stdout.close()


def _sample(input_: X11Input, editor: _Editor, case: _Case, arrival_delay: float) -> float:
    prepared = editor.prepare(case)
    # Spread input arrivals across the frame cycle instead of always following the reset paint.
    time.sleep(arrival_delay)
    start = time.monotonic_ns()
    match case.mode:
        case "focus":
            input_.click(RootPoint(prepared.x, prepared.y), PointerButton.LEFT)
        case "select":
            input_.press_keys((KeyName("Control_L"), KeyName("a")))
        case "type":
            input_.type_text(case.text)
    dispatched = time.monotonic_ns()
    reply = editor.receive("done")
    match case.mode:
        case "focus":
            matched = reply.focused
        case "select":
            matched = reply.selection == case.text
        case "type":
            matched = reply.text == case.text
    if not matched:
        msg = f"editor verification failed for {case.name}"
        raise ValueError(msg)
    # Both processes use CLOCK_MONOTONIC. Exclude pipe delivery time but include
    # completion of the input action and the editor's matching paint cycle.
    return (max(dispatched, reply.completed_ns) - start) / 1_000_000_000


def _run(
    input_: X11Input,
    editor: _Editor,
    arguments: _Arguments,
) -> tuple[tuple[_Measurement, ...], tuple[tuple[int, int], ...]]:
    cases = (
        _Case("Click → editor focused", "focus"),
        _Case("Ctrl+A → selection verified", "select", (_SEED * 2)[:100]),
        *(
            _Case(f"Type {length} → text verified", "type", (_SEED * 20)[:length])
            for length in (10, 100, 1000)
        ),
    )
    measurements = tuple(_Measurement(case) for case in cases)
    arrivals = random.Random(0)  # noqa: S311 - reproducible benchmark scheduling, not security.
    rss = [(_rss_bytes(), _rss_bytes(editor.process.pid))]
    for _ in range(arguments.warmup):
        for case in cases:
            _ = _sample(input_, editor, case, arrivals.uniform(0, 0.020))
    rss.append((_rss_bytes(), _rss_bytes(editor.process.pid)))
    for _ in range(arguments.iterations):
        for measurement in measurements:
            try:
                elapsed = _sample(input_, editor, measurement.case, arrivals.uniform(0, 0.020))
            except (TimeoutError, ValueError):
                measurement.failures += 1
            else:
                measurement.seconds.append(elapsed)
    rss.append((_rss_bytes(), _rss_bytes(editor.process.pid)))
    return measurements, tuple(rss)


def _report(
    measurements: tuple[_Measurement, ...],
    rss: tuple[tuple[int, int], ...],
    arguments: _Arguments,
) -> str:
    lines = [
        "X11 editor input benchmark",
        f"  display: {arguments.display}",
        "  application: separate GTK 3 TextView editor process",
        f"  warmup rounds: {arguments.warmup}",
        f"  measured rounds: {arguments.iterations} ({len(measurements)} operations per round)",
        "  completion: exact widget state verified after a GTK paint cycle",
        "  arrival phase: seeded 0-20 ms idle delay, outside the timing",
        "",
        f"  {'operation':32} {'p50 ms':>10} {'p95 ms':>10} {'failures':>10}",
    ]
    for item in measurements:
        lines.append(
            f"  {item.case.name:32} {_percentile(item.seconds, 0.50):10.3f} {_percentile(item.seconds, 0.95):10.3f} {item.failures:10}"
        )
        if item.case.mode == "type" and item.seconds:
            throughput = len(item.seconds) * len(item.case.text) / sum(item.seconds)
            lines.append(f"    verified throughput: {throughput:.1f} characters/s")
    lines.extend(("", "RSS (KiB)", f"  {'phase':24} {'driver':>12} {'editor':>12}"))
    for label, values in zip(
        ("before warmup", "after warmup", "after measured operations"), rss, strict=True
    ):
        lines.append(f"  {label:24} {values[0] / _KIB:12.1f} {values[1] / _KIB:12.1f}")
    warm, end = rss[1], rss[2]
    lines.append(
        f"  {'growth after warmup':24} {(end[0] - warm[0]) / _KIB:12.1f} {(end[1] - warm[1]) / _KIB:12.1f}"
    )
    lines.extend(
        (
            "",
            "Preparation and IPC delivery are outside the timing; XKB rebuilding and planning are included.",
            "Paint completion is GTK-side, not physical display presentation or compositor latency.",
            "Percentiles and throughput use successful samples; failures cause a nonzero exit.",
        )
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    """Measure verified editor responses using the production X11 input path."""
    arguments = _arguments()
    if arguments.display is None:
        msg = "explicit input display is required"
        raise RuntimeError(msg)
    with _editor(arguments) as editor, X11Client.connect(arguments.display) as client:
        _ = client.xtest_version()
        with XkbKeyboard.connect(client) as keyboard:
            input_ = X11Input(client=client, root=client.root_window(), keyboard=keyboard)
            measurements, rss = _run(input_, editor, arguments)
    _ = sys.stdout.write(_report(measurements, rss, arguments))
    if any(item.failures for item in measurements):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
