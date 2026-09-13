"""Benchmark runtime calls against the in-memory MCP protocol path."""

# ruff: noqa: E402 - SDK imports must follow the direct-execution path fix below.

from __future__ import annotations

import argparse
import base64
import gc
import json
import math
import os
import sys
import time
from array import array
from dataclasses import dataclass
from pathlib import Path
from typing import cast, final

# The requested benchmark filename matches the SDK package. Remove the script
# directory so direct execution resolves `mcp` from the environment.
_SCRIPT_DIRECTORY = Path(__file__).resolve().parent
sys.path = [entry for entry in sys.path if Path(entry or Path.cwd()).resolve() != _SCRIPT_DIRECTORY]

import anyio
from mcp import Client
from mcp.types import CallToolResult, ImageContent

from mint_computer_mcp.backend import BackendCapture, PixelFormat, PixelFrame
from mint_computer_mcp.domain.geometry import (
    DesktopLayoutPoint,
    DesktopLayoutRect,
    Size,
    SnapshotPoint,
)
from mint_computer_mcp.domain.identifiers import OutputRef
from mint_computer_mcp.domain.input import KeyName, MovePointer, PointerButton
from mint_computer_mcp.domain.observation import (
    DesktopState,
    DesktopTarget,
    ObservationTarget,
    OutputInfo,
)
from mint_computer_mcp.runtime import DesktopRuntime
from mint_computer_mcp.server import create_server

_KIB = 1024
_DEFAULT_ITERATIONS = 1000
_DEFAULT_WARMUP = 20
_DEFAULT_WIDTH = 1920
_DEFAULT_HEIGHT = 1080


@final
class _Arguments(argparse.Namespace):
    iterations: int = _DEFAULT_ITERATIONS
    warmup: int = _DEFAULT_WARMUP
    width: int = _DEFAULT_WIDTH
    height: int = _DEFAULT_HEIGHT


@dataclass(frozen=True, slots=True)
class _SnapshotState:
    sequence: int


@final
class _SyntheticBackend:
    """Provide a stable frame and no-op input for protocol overhead measurements."""

    def __init__(self, size: Size) -> None:
        self._size = size
        self._sequence = 0
        pixel_count = size.width * size.height
        pattern = bytes(range(256))
        byte_count = pixel_count * 4
        self._pixels = bytearray((pattern * math.ceil(byte_count / len(pattern)))[:byte_count])
        self._output = OutputInfo(
            ref=OutputRef("benchmark-output"),
            name="Synthetic benchmark output",
            layout=DesktopLayoutRect(x=0, y=0, width=size.width, height=size.height),
            primary=True,
        )

    @property
    def display_generation(self) -> int:
        return 0

    def outputs(self) -> tuple[OutputInfo, ...]:
        return (self._output,)

    def capture(self, target: ObservationTarget) -> BackendCapture[_SnapshotState]:
        del target
        self._sequence += 1
        return BackendCapture(
            frame=PixelFrame(
                data=memoryview(self._pixels),
                size=self._size,
                stride=self._size.width * 4,
                format=PixelFormat.BGRX,
            ),
            snapshot_state=_SnapshotState(self._sequence),
            desktop_state=DesktopState(outputs=self.outputs(), active_window=None),
            display_generation=self.display_generation,
        )

    def resolve_point(
        self,
        state: _SnapshotState,
        point: SnapshotPoint,
        encoded_size: Size,
    ) -> DesktopLayoutPoint:
        if state.sequence <= 0 or encoded_size != self._size:
            msg = "invalid synthetic snapshot state"
            raise RuntimeError(msg)
        return DesktopLayoutPoint(point.x, point.y)

    def move_pointer(
        self,
        point: DesktopLayoutPoint,
        *,
        expected_display_generation: int,
    ) -> None:
        del point, expected_display_generation

    def click(
        self,
        point: DesktopLayoutPoint,
        button: PointerButton,
        *,
        expected_display_generation: int,
    ) -> None:
        del point, button, expected_display_generation

    def press_keys(self, keys: tuple[KeyName, ...]) -> None:
        del keys

    def type_text(self, text: str) -> None:
        del text

    def close(self) -> None:
        self._pixels.clear()


@dataclass(frozen=True, slots=True)
class _PayloadSizes:
    jpeg: int
    base64: int
    metadata_json: int


@dataclass(frozen=True, slots=True)
class _Measurements:
    size: Size
    warmup: int
    iterations: int
    runtime_observe: array[float]
    mcp_observe: array[float]
    runtime_act: array[float]
    mcp_act: array[float]
    payload: _PayloadSizes
    rss: tuple[int, int, int, int]


def _arguments() -> _Arguments:
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("--iterations", type=int, default=_DEFAULT_ITERATIONS)
    _ = parser.add_argument("--warmup", type=int, default=_DEFAULT_WARMUP)
    _ = parser.add_argument("--width", type=int, default=_DEFAULT_WIDTH)
    _ = parser.add_argument("--height", type=int, default=_DEFAULT_HEIGHT)
    arguments = _Arguments()
    _ = parser.parse_args(namespace=arguments)
    if arguments.iterations <= 0:
        parser.error("--iterations must be positive")
    if arguments.warmup < 0:
        parser.error("--warmup must be nonnegative")
    if arguments.width <= 0 or arguments.height <= 0:
        parser.error("--width and --height must be positive")
    return arguments


def _rss_bytes() -> int:
    for line in Path(f"/proc/{os.getpid()}/status").read_text(encoding="utf-8").splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) * _KIB
    msg = "VmRSS was not available in /proc/self/status"
    raise RuntimeError(msg)


def _percentile(values: array[float], fraction: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * fraction) - 1)
    return ordered[index] * 1000


def _metadata(result: CallToolResult) -> dict[str, object]:
    metadata = cast("dict[str, object] | None", result.structured_content)
    if metadata is None:
        msg = "desktop_observe returned no structured metadata"
        raise RuntimeError(msg)
    return metadata


def _payload_sizes(result: CallToolResult) -> _PayloadSizes:
    images = [item for item in result.content if isinstance(item, ImageContent)]
    if len(images) != 1:
        msg = f"desktop_observe returned {len(images)} images"
        raise RuntimeError(msg)
    encoded = images[0].data
    return _PayloadSizes(
        jpeg=len(base64.b64decode(encoded, validate=True)),
        base64=len(encoded.encode("ascii")),
        metadata_json=len(json.dumps(_metadata(result), separators=(",", ":")).encode("utf-8")),
    )


async def _measure(arguments: _Arguments) -> _Measurements:
    size = Size(arguments.width, arguments.height)
    backend = _SyntheticBackend(size)
    runtime_observe = array("d")
    mcp_observe = array("d")
    runtime_act = array("d")
    mcp_act = array("d")
    target = DesktopTarget()
    point = SnapshotPoint(0, 0)
    rss_start = _rss_bytes()

    with DesktopRuntime(backend) as runtime:
        server = create_server(runtime)
        async with Client(server, raise_exceptions=True) as client:
            for _ in range(arguments.warmup):
                _ = runtime.observe(target)
                _ = await client.call_tool("desktop_observe", {})

            gc.collect()
            rss_after_warmup = _rss_bytes()

            for _ in range(arguments.iterations):
                started = time.perf_counter()
                observation = runtime.observe(target)
                runtime_observe.append(time.perf_counter() - started)
                del observation

            gc.collect()
            rss_after_runtime = _rss_bytes()

            mcp_result: CallToolResult | None = None
            for _ in range(arguments.iterations):
                started = time.perf_counter()
                mcp_result = await client.call_tool("desktop_observe", {})
                mcp_observe.append(time.perf_counter() - started)

            if mcp_result is None:
                msg = "MCP observation benchmark produced no result"
                raise RuntimeError(msg)
            payload = _payload_sizes(mcp_result)
            mcp_snapshot_id = _metadata(mcp_result)["snapshot_id"]
            if not isinstance(mcp_snapshot_id, str):
                msg = "desktop_observe returned an invalid snapshot_id"
                raise TypeError(msg)
            del mcp_result
            gc.collect()
            rss_after_mcp = _rss_bytes()

            direct_observation = runtime.observe(target)
            direct_action = MovePointer(direct_observation.snapshot.id, point)
            for _ in range(arguments.iterations):
                started = time.perf_counter()
                runtime.act(direct_action)
                runtime_act.append(time.perf_counter() - started)

            mcp_action = {
                "action": {
                    "kind": "move",
                    "snapshot_id": mcp_snapshot_id,
                    "x": point.x,
                    "y": point.y,
                }
            }
            for _ in range(arguments.iterations):
                started = time.perf_counter()
                result = await client.call_tool("desktop_act", mcp_action)
                mcp_act.append(time.perf_counter() - started)
                if result.is_error:
                    msg = "desktop_act returned a tool error"
                    raise RuntimeError(msg)

    return _Measurements(
        size=size,
        warmup=arguments.warmup,
        iterations=arguments.iterations,
        runtime_observe=runtime_observe,
        mcp_observe=mcp_observe,
        runtime_act=runtime_act,
        mcp_act=mcp_act,
        payload=payload,
        rss=(rss_start, rss_after_warmup, rss_after_runtime, rss_after_mcp),
    )


def _latency_lines(name: str, values: array[float]) -> tuple[str, str, str]:
    return (
        name,
        f"  p50: {_percentile(values, 0.50):.3f} ms",
        f"  p95: {_percentile(values, 0.95):.3f} ms",
    )


def _report(measurements: _Measurements) -> str:
    rss_start, rss_after_warmup, rss_after_runtime, rss_after_mcp = measurements.rss
    payload = measurements.payload

    lines = [
        "MCP adapter benchmark",
        "  backend: synthetic in-process frame and no-op input",
        f"  frame: {measurements.size.width}x{measurements.size.height}",
        f"  warmup operations per path: {measurements.warmup}",
        f"  measured operations per path: {measurements.iterations}",
        "",
        *_latency_lines("Runtime observe", measurements.runtime_observe),
        "",
        *_latency_lines("MCP desktop_observe", measurements.mcp_observe),
        "",
        *_latency_lines("Runtime act", measurements.runtime_act),
        "",
        *_latency_lines("MCP desktop_act", measurements.mcp_act),
        "",
        "Observation payload",
        f"  JPEG: {payload.jpeg / _KIB:.1f} KiB",
        f"  base64: {payload.base64 / _KIB:.1f} KiB",
        f"  structured metadata JSON: {payload.metadata_json} bytes",
        "",
        "RSS",
        f"  start: {rss_start / _KIB:.1f} KiB",
        f"  after warmup: {rss_after_warmup / _KIB:.1f} KiB",
        f"  after runtime observations: {rss_after_runtime / _KIB:.1f} KiB",
        f"  after MCP observations: {rss_after_mcp / _KIB:.1f} KiB",
        f"  growth after warmup: {(rss_after_mcp - rss_after_warmup) / _KIB:.1f} KiB",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    """Run the synthetic runtime and MCP benchmark."""
    arguments = _arguments()
    report = _report(anyio.run(_measure, arguments))
    _ = sys.stdout.write(report)


if __name__ == "__main__":
    main()
