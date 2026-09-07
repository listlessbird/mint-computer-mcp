from dataclasses import dataclass
from typing import final

import pytest

from mint_computer_mcp.backend import (
    BackendCapture,
    PixelFormat,
    PixelFrame,
)
from mint_computer_mcp.domain.geometry import (
    DesktopLayoutPoint,
    DesktopLayoutRect,
    Size,
    SnapshotPoint,
)
from mint_computer_mcp.domain.identifiers import OutputRef
from mint_computer_mcp.domain.observation import (
    DesktopState,
    DesktopTarget,
    ObservationTarget,
    OutputInfo,
)
from mint_computer_mcp.runtime import (
    DesktopRuntime,
    DesktopRuntimeClosedError,
    StaleSnapshotError,
)


@dataclass(frozen=True, slots=True)
class FakeSnapshotState:
    """Backend-private test snapshot state."""

    sequence: int


@final
class FakeBackend:
    """Typed in-memory desktop backend."""

    def __init__(self) -> None:
        self.generation = 0
        self.sequence = 0
        self.closed = False
        self.last_target: ObservationTarget | None = None

    @property
    def display_generation(self) -> int:
        return self.generation

    def outputs(self) -> tuple[OutputInfo, ...]:
        return (
            OutputInfo(
                ref=OutputRef("output-1"),
                name="Test Output",
                layout=DesktopLayoutRect(
                    x=0,
                    y=0,
                    width=2,
                    height=2,
                ),
                primary=True,
            ),
        )

    def capture(
        self,
        target: ObservationTarget,
    ) -> BackendCapture[FakeSnapshotState]:
        self.sequence += 1
        self.last_target = target

        pixels = bytearray(
            (
                0,
                0,
                0,
                0,
            )
            * 4
        )

        return BackendCapture(
            frame=PixelFrame(
                data=memoryview(pixels),
                size=Size(width=2, height=2),
                stride=8,
                format=PixelFormat.BGRX,
            ),
            snapshot_state=FakeSnapshotState(
                sequence=self.sequence,
            ),
            desktop_state=DesktopState(
                outputs=self.outputs(),
                active_window=None,
            ),
            display_generation=self.generation,
        )

    def resolve_point(
        self, state: FakeSnapshotState, point: SnapshotPoint, encoded_size: Size
    ) -> DesktopLayoutPoint:
        assert state.sequence > 0
        assert encoded_size == Size(2, 2)
        return DesktopLayoutPoint(point.x, point.y)

    def close(self) -> None:
        self.closed = True


def test_runtime_observes_and_registers_snapshot() -> None:
    backend = FakeBackend()

    with DesktopRuntime(backend) as runtime:
        target = DesktopTarget()
        observation = runtime.observe(target)

        assert backend.last_target == target
        assert observation.target == target
        assert observation.image.data.startswith(b"\xff\xd8")
        assert observation.snapshot.source_size == Size(width=2, height=2)
        assert runtime.snapshot(observation.snapshot.id) == observation.snapshot


def test_runtime_evicts_oldest_snapshot() -> None:
    backend = FakeBackend()

    with DesktopRuntime(
        backend,
        snapshot_limit=1,
    ) as runtime:
        first = runtime.observe(DesktopTarget())
        second = runtime.observe(DesktopTarget())

        with pytest.raises(StaleSnapshotError, match="unknown or expired"):
            _ = runtime.snapshot(first.snapshot.id)

        assert runtime.snapshot(second.snapshot.id) == second.snapshot


def test_runtime_rejects_snapshot_from_old_display_generation() -> None:
    backend = FakeBackend()

    with DesktopRuntime(backend) as runtime:
        observation = runtime.observe(DesktopTarget())

        backend.generation += 1

        with pytest.raises(StaleSnapshotError, match="old display layout"):
            _ = runtime.snapshot(observation.snapshot.id)


def test_runtime_owns_backend_lifetime() -> None:
    backend = FakeBackend()
    runtime = DesktopRuntime(backend)

    runtime.close()

    assert backend.closed

    with pytest.raises(DesktopRuntimeClosedError):
        _ = runtime.observe(DesktopTarget())
