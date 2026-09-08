"""Shared fakes for unit tests."""

from dataclasses import dataclass
from typing import final

from mint_computer_mcp.backend import (
    BackendCapture,
    DisplayGenerationMismatchError,
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
from mint_computer_mcp.domain.input import KeyName, PointerButton
from mint_computer_mcp.domain.observation import (
    DesktopState,
    ObservationTarget,
    OutputInfo,
)


@dataclass(frozen=True, slots=True)
class FakeSnapshotState:
    """Backend-private test snapshot state."""

    sequence: int


@dataclass(frozen=True, slots=True)
class PointerMoveCall:
    """Recorded pointer movement."""

    point: DesktopLayoutPoint
    generation: int


@dataclass(frozen=True, slots=True)
class ClickCall:
    """Recorded pointer click."""

    point: DesktopLayoutPoint
    button: PointerButton
    generation: int


@final
class FakeBackend:
    """Typed in-memory desktop backend."""

    def __init__(self) -> None:
        self.generation = 0
        self.sequence = 0
        self.closed = False
        self.last_target: ObservationTarget | None = None
        self.moves: list[PointerMoveCall] = []
        self.clicks: list[ClickCall] = []
        self.typed: list[str] = []
        self.key_chords: list[tuple[KeyName, ...]] = []
        self.events: list[str] = []
        self.fail_spatial_actions = False

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
        self.events.append("resolve")
        return DesktopLayoutPoint(point.x + 10, point.y + 20)

    def move_pointer(
        self,
        point: DesktopLayoutPoint,
        *,
        expected_display_generation: int,
    ) -> None:
        self.events.append("move")
        if self.fail_spatial_actions:
            raise DisplayGenerationMismatchError
        self.moves.append(PointerMoveCall(point, expected_display_generation))

    def click(
        self,
        point: DesktopLayoutPoint,
        button: PointerButton,
        *,
        expected_display_generation: int,
    ) -> None:
        self.events.append("click")
        if self.fail_spatial_actions:
            raise DisplayGenerationMismatchError
        self.clicks.append(ClickCall(point, button, expected_display_generation))

    def press_keys(self, keys: tuple[KeyName, ...]) -> None:
        self.key_chords.append(keys)

    def type_text(self, text: str) -> None:
        self.typed.append(text)

    def close(self) -> None:
        self.closed = True
