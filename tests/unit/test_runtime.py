from dataclasses import dataclass
from typing import Literal, final

import pytest

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
from mint_computer_mcp.domain.identifiers import OutputRef, SnapshotId
from mint_computer_mcp.domain.input import (
    Click,
    InputAction,
    KeyName,
    MovePointer,
    PointerButton,
    PressKeys,
    TypeText,
)
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


@dataclass(frozen=True, slots=True)
class PointerMoveCall:
    point: DesktopLayoutPoint
    generation: int


@dataclass(frozen=True, slots=True)
class ClickCall:
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


def test_move_resolves_snapshot_point_before_backend_call() -> None:
    backend = FakeBackend()

    with DesktopRuntime(backend) as runtime:
        snapshot = runtime.observe(DesktopTarget()).snapshot
        runtime.act(MovePointer(snapshot.id, SnapshotPoint(1, 0)))

    assert backend.events == ["resolve", "move"]
    assert backend.moves == [PointerMoveCall(DesktopLayoutPoint(11, 20), generation=0)]


def test_click_resolves_snapshot_point_before_backend_call() -> None:
    backend = FakeBackend()

    with DesktopRuntime(backend) as runtime:
        snapshot = runtime.observe(DesktopTarget()).snapshot
        runtime.act(Click(snapshot.id, SnapshotPoint(0, 1), PointerButton.LEFT))

    assert backend.events == ["resolve", "click"]
    assert backend.clicks == [
        ClickCall(DesktopLayoutPoint(10, 21), PointerButton.LEFT, generation=0)
    ]


def test_click_preserves_button_during_dispatch() -> None:
    backend = FakeBackend()

    with DesktopRuntime(backend) as runtime:
        snapshot = runtime.observe(DesktopTarget()).snapshot
        runtime.act(Click(snapshot.id, SnapshotPoint(0, 0), PointerButton.RIGHT))

    assert backend.clicks[0].button is PointerButton.RIGHT


def test_stale_snapshot_performs_no_input() -> None:
    backend = FakeBackend()

    with DesktopRuntime(backend) as runtime:
        snapshot = runtime.observe(DesktopTarget()).snapshot
        backend.generation += 1

        with pytest.raises(StaleSnapshotError, match="old display layout"):
            runtime.act(MovePointer(snapshot.id, SnapshotPoint(0, 0)))

    assert backend.events == []
    assert backend.moves == []


@pytest.mark.parametrize(
    "action_kind",
    ["move", "click"],
)
def test_backend_generation_race_becomes_stale_snapshot_error(
    action_kind: Literal["move", "click"],
) -> None:
    backend = FakeBackend()

    with DesktopRuntime(backend) as runtime:
        snapshot = runtime.observe(DesktopTarget()).snapshot
        backend.fail_spatial_actions = True

        if action_kind == "move":
            action: InputAction = MovePointer(snapshot.id, SnapshotPoint(0, 0))
        else:
            action = Click(snapshot.id, SnapshotPoint(0, 0), PointerButton.MIDDLE)

        with pytest.raises(StaleSnapshotError, match="became stale"):
            runtime.act(action)

    assert backend.moves == []
    assert backend.clicks == []


def test_generation_race_failure_clears_snapshots() -> None:
    backend = FakeBackend()

    with DesktopRuntime(backend) as runtime:
        first = runtime.observe(DesktopTarget()).snapshot
        second = runtime.observe(DesktopTarget()).snapshot
        backend.fail_spatial_actions = True

        with pytest.raises(StaleSnapshotError):
            runtime.act(MovePointer(first.id, SnapshotPoint(0, 0)))

        with pytest.raises(StaleSnapshotError, match="unknown or expired"):
            _ = runtime.snapshot(second.id)


def test_type_text_dispatches_directly() -> None:
    backend = FakeBackend()

    with DesktopRuntime(backend) as runtime:
        runtime.act(TypeText("hello\nworld"))

    assert backend.typed == ["hello\nworld"]
    assert backend.events == []


def test_press_keys_dispatches_directly() -> None:
    backend = FakeBackend()
    keys = (KeyName("CTRL"), KeyName("SHIFT"), KeyName("P"))

    with DesktopRuntime(backend) as runtime:
        runtime.act(PressKeys(keys))

    assert backend.key_chords == [keys]
    assert backend.events == []


@pytest.mark.parametrize(
    "action",
    [
        TypeText("x"),
        PressKeys((KeyName("ENTER"),)),
        MovePointer(SnapshotId("missing"), SnapshotPoint(0, 0)),
        Click(SnapshotId("missing"), SnapshotPoint(0, 0), PointerButton.LEFT),
    ],
)
def test_closed_runtime_rejects_actions(action: InputAction) -> None:
    backend = FakeBackend()
    runtime = DesktopRuntime(backend)
    runtime.close()

    with pytest.raises(DesktopRuntimeClosedError):
        runtime.act(action)

    assert backend.events == []
    assert backend.moves == []
    assert backend.clicks == []
    assert backend.typed == []
    assert backend.key_chords == []
