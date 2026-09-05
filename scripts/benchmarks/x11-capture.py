"""Benchmark real X11 capture, JPEG encoding, and RSS behavior."""

import argparse
import math
import os
import sys
import time
from pathlib import Path

from mint_computer_mcp.domain.observation import OutputInfo, OutputTarget
from mint_computer_mcp.image import DEFAULT_JPEG_QUALITY, JpegEncoder
from mint_computer_mcp.native.x11.backend import X11Backend
from mint_computer_mcp.runtime import DesktopRuntime

_DEFAULT_ITERATIONS = 1000
_DEFAULT_WARMUP = 20
_BYTES_PER_KIBIBYTE = 1024
_PERCENTILE_50 = 0.50
_PERCENTILE_95 = 0.95


def _parser() -> argparse.ArgumentParser:
    """Build the benchmark CLI."""
    parser = argparse.ArgumentParser()

    _ = parser.add_argument(
        "--iterations",
        type=int,
        default=_DEFAULT_ITERATIONS,
    )
    _ = parser.add_argument(
        "--warmup",
        type=int,
        default=_DEFAULT_WARMUP,
    )
    _ = parser.add_argument(
        "--quality",
        type=int,
        default=DEFAULT_JPEG_QUALITY,
    )

    _ = parser.add_argument(
        "--runtime",
        action="store_true",
        help="Measure complete observations and snapshot retention",
    )

    return parser


def _rss_bytes() -> int:
    """Return current Linux process RSS."""
    status = Path("/proc/self/status").read_text(encoding="utf-8")

    for line in status.splitlines():
        if not line.startswith("VmRSS:"):
            continue

        fields = line.split()

        return int(fields[1]) * _BYTES_PER_KIBIBYTE

    msg = "VmRSS was not available in /proc/self/status"
    raise RuntimeError(msg)


def _percentile(values: list[float], percentile: float) -> float:
    """Return a nearest-rank percentile from a nonempty sample."""
    if not values:
        msg = "percentile requires at least one value"
        raise ValueError(msg)

    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * percentile) - 1)

    return ordered[index]


def _primary_output(outputs: tuple[OutputInfo, ...]) -> OutputInfo:
    """Choose primary output, falling back to the first available output."""
    if not outputs:
        msg = "benchmark requires at least one desktop output"
        raise RuntimeError(msg)

    return next(
        (output for output in outputs if output.primary),
        outputs[0],
    )


def main() -> None:
    """Run the capture benchmark."""
    args = _parser().parse_args()

    iterations = int(args.iterations)
    warmup = int(args.warmup)
    quality = int(args.quality)

    if iterations <= 0:
        msg = "iterations must be positive"
        raise ValueError(msg)

    if warmup < 0:
        msg = "warmup must be nonnegative"
        raise ValueError(msg)

    display = os.environ.get("DISPLAY")

    if not display:
        msg = "DISPLAY is required"
        raise RuntimeError(msg)

    capture_times: list[float] = []
    encode_times: list[float] = []
    encoded_sizes: list[int] = []

    rss_start = _rss_bytes()

    backend = X11Backend.connect(display)
    with (
        DesktopRuntime(backend, jpeg_quality=quality) as runtime,
        JpegEncoder(quality=quality) as encoder,
    ):
        output = _primary_output(backend.outputs())
        target = OutputTarget(output=output.ref)

        for _ in range(warmup):
            if args.runtime:
                runtime.observe(target)
            else:
                capture = backend.capture(target)
                encoder.encode(capture.frame)
                del capture

        rss_after_warmup = _rss_bytes()

        for _ in range(iterations):
            capture_start = time.perf_counter()
            if args.runtime:
                observation = runtime.observe(target)
                capture_end = time.perf_counter()
                encoded_sizes.append(len(observation.image.data))
                del observation
            else:
                capture = backend.capture(target)
                capture_end = time.perf_counter()
                image = encoder.encode(capture.frame)
                encode_times.append((time.perf_counter() - capture_end) * 1000)
                encoded_sizes.append(len(image.data))
                del capture, image

            capture_times.append((capture_end - capture_start) * 1000)

        rss_end = _rss_bytes()

        status = backend.capture_performance_status

    lines = [
        "Capture benchmark",
        f"  display: {display}",
        f"  output: {output.name}",
        f"  size: {output.layout.width}x{output.layout.height}",
        f"  iterations: {iterations}",
        f"  jpeg quality: {quality}",
        "",
        "Observation latency" if args.runtime else "Capture latency",
        f"  p50: {_percentile(capture_times, _PERCENTILE_50):.3f} ms",
        f"  p95: {_percentile(capture_times, _PERCENTILE_95):.3f} ms",
        *(
            []
            if args.runtime
            else [
                "",
                "JPEG latency",
                f"  p50: {_percentile(encode_times, _PERCENTILE_50):.3f} ms",
                f"  p95: {_percentile(encode_times, _PERCENTILE_95):.3f} ms",
            ]
        ),
        "",
        "Encoded size",
        f"  average: {sum(encoded_sizes) / len(encoded_sizes) / _BYTES_PER_KIBIBYTE:.1f} KiB",
        "",
        "RSS",
        f"  start: {rss_start / _BYTES_PER_KIBIBYTE:.1f} KiB",
        f"  after warmup: {rss_after_warmup / _BYTES_PER_KIBIBYTE:.1f} KiB",
        f"  end: {rss_end / _BYTES_PER_KIBIBYTE:.1f} KiB",
        f"  growth after warmup: {(rss_end - rss_after_warmup) / _BYTES_PER_KIBIBYTE:.1f} KiB",
    ]

    if status:
        lines.extend(
            (
                "",
                "Capture backend",
                *(f"  {item}" for item in status),
            )
        )

    _ = sys.stdout.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
