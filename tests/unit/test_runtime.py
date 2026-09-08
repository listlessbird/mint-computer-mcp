from typing import Literal

import pytest

from mint_computer_mcp.domain.geometry import (
    DesktopLayoutPoint,
    Size,
    SnapshotPoint,
)
from mint_computer_mcp.domain.identifiers import SnapshotId
from mint_computer_mcp.domain.input import (
    Click,
    InputAction,
    KeyName,
    MovePointer,
    PointerButton,
    PressKeys,
    TypeText,
)
from mint_computer_mcp.domain.observation import DesktopTarget
from mint_computer_mcp.runtime import (
    DesktopRuntime,
    DesktopRuntimeClosedError,
    StaleSnapshotError,
)
from tests.support import ClickCall, FakeBackend, PointerMoveCall


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
