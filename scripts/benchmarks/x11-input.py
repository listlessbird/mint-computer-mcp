"""Benchmark X11 input on an explicit display, including fresh XKB snapshots."""

from __future__ import annotations

import argparse
import math
import os
import sys
import time
from array import array
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, final

from mint_computer_mcp.domain.geometry import RootPoint
from mint_computer_mcp.domain.input import KeyName, PointerButton
from mint_computer_mcp.native.x11.client import X11Client
from mint_computer_mcp.native.x11.input import X11Input
from mint_computer_mcp.native.x11.xkb import XkbKeyboard

if TYPE_CHECKING:
    from collections.abc import Callable

_TEXT = "Hello X11! " * 4
_KEYS = (KeyName("Control_L"), KeyName("a"))
_KIB = 1024


@final
class _Arguments(argparse.Namespace):
    display: str | None = None
    iterations: int = 1000
    warmup: int = 20


@dataclass(frozen=True, slots=True)
class _Measurement:
    name: str
    operation: Callable[[], object]
    seconds: array[float]


def _arguments() -> _Arguments:
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument(
        "--display",
        help="Input target; defaults only to MINT_COMPUTER_INPUT_DISPLAY, never DISPLAY",
    )
    _ = parser.add_argument("--iterations", type=int, default=1000)
    _ = parser.add_argument("--warmup", type=int, default=20)
    arguments = _Arguments()
    arguments.display = os.environ.get("MINT_COMPUTER_INPUT_DISPLAY")
    _ = parser.parse_args(namespace=arguments)
    if not arguments.display or not arguments.display.strip():
        parser.error("--display or MINT_COMPUTER_INPUT_DISPLAY is required")
    if arguments.iterations <= 0:
        parser.error("--iterations must be positive")
    if arguments.warmup < 0:
        parser.error("--warmup must be nonnegative")
    return arguments


def _rss_bytes() -> int:
    for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) * _KIB
    msg = "VmRSS was not available in /proc/self/status"
    raise RuntimeError(msg)


def _percentile(values: array[float], fraction: float) -> float:
    """Return a nearest-rank percentile in milliseconds."""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)] * 1000


def _measurements(
    input_: X11Input,
    keyboard: XkbKeyboard,
    iterations: int,
) -> tuple[_Measurement, ...]:
    plans = keyboard.plan_text(_TEXT)
    chords = tuple((*plan.modifiers, plan.key) for plan in plans)
    point = RootPoint(80, 90)
    operations: tuple[tuple[str, Callable[[], object]], ...] = (
        ("Pointer move dispatch", lambda: input_.move_pointer(point)),
        ("Click dispatch", lambda: input_.click(point, PointerButton.LEFT)),
        ("Key chord (fresh snapshot + resolve + inject)", lambda: input_.press_keys(_KEYS)),
        # Empty resolution acquires and frees a fresh map/state without any symbol lookup.
        ("XKB snapshot acquisition + release", lambda: keyboard.resolve_key_names(())),
        (
            "Key-name resolution (including fresh snapshot)",
            lambda: keyboard.resolve_key_names(_KEYS),
        ),
        ("Text planning (including fresh snapshot)", lambda: keyboard.plan_text(_TEXT)),
        # Reuse the production ownership/cleanup path; no alternate benchmark injector.
        ("Preplanned text injection", lambda: input_._inject_chords(chords)),  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        ("End-to-end text action", lambda: input_.type_text(_TEXT)),
    )
    # Allocate sample storage before warmup so retaining timings does not inflate RSS growth.
    return tuple(
        _Measurement(name, operation, array("d", [0.0]) * iterations)
        for name, operation in operations
    )


def _run(measurements: tuple[_Measurement, ...], arguments: _Arguments) -> tuple[int, int, int]:
    rss_before = _rss_bytes()
    for _ in range(arguments.warmup):
        for measurement in measurements:
            _ = measurement.operation()
    rss_warm = _rss_bytes()
    for index in range(arguments.iterations):
        for measurement in measurements:
            start = time.perf_counter()
            _ = measurement.operation()
            measurement.seconds[index] = time.perf_counter() - start
    return rss_before, rss_warm, _rss_bytes()


def _report(
    measurements: tuple[_Measurement, ...],
    arguments: _Arguments,
    rss: tuple[int, int, int],
) -> str:
    lines = [
        "X11 input benchmark",
        f"  display: {arguments.display}",
        f"  warmup rounds: {arguments.warmup}",
        f"  measured rounds: {arguments.iterations} ({len(measurements)} operations per round)",
        f"  text length: {len(_TEXT)} codepoints per text operation",
        "  chord: Control_L + a",
        "",
        "Latency (ms)",
        f"  {'operation':54} {'p50':>10} {'p95':>10}",
    ]
    lines.extend(
        f"  {item.name:54} {_percentile(item.seconds, 0.50):10.3f} {_percentile(item.seconds, 0.95):10.3f}"
        for item in measurements
    )
    lines.extend(("", "Text throughput"))
    for item in measurements[-2:]:
        throughput = arguments.iterations * len(_TEXT) / sum(item.seconds)
        lines.append(f"  {item.name}: {throughput:.1f} codepoints/s")
    before, warm, end = rss
    lines.extend(
        (
            "",
            "RSS (sample buffers and input resources allocated before warmup)",
            f"  before warmup: {before / _KIB:.1f} KiB",
            f"  after warmup: {warm / _KIB:.1f} KiB",
            f"  after {arguments.iterations * len(measurements)} operations: {end / _KIB:.1f} KiB",
            f"  growth after warmup: {(end - warm) / _KIB:.1f} KiB",
            "",
            "Dispatch includes checked XTEST requests and one explicit flush per action.",
            "These are server dispatch timings, not application response latency.",
            "Resolution and planning include rebuilding the map/state; snapshot cost is also shown alone.",
            "Only the injection-only measurement reuses a plan. Normal actions still rebuild XKB.",
        )
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    """Run all measurements against the explicitly selected input target."""
    arguments = _arguments()
    # Validation happens before opening any connection or synthesizing any input.
    if arguments.display is None:
        msg = "explicit input display is required"
        raise RuntimeError(msg)
    with X11Client.connect(arguments.display) as client, XkbKeyboard.connect(client) as keyboard:
        _ = client.xtest_version()
        input_ = X11Input(client=client, root=client.root_window(), keyboard=keyboard)
        measurements = _measurements(input_, keyboard, arguments.iterations)
        rss = _run(measurements, arguments)
    _ = sys.stdout.write(_report(measurements, arguments, rss))


if __name__ == "__main__":
    main()
