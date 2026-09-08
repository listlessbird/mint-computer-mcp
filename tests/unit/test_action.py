import pytest
from pydantic import TypeAdapter, ValidationError

from mint_computer_mcp.api.action import (
    ClickAction,
    DesktopAction,
    KeyPressAction,
    MoveAction,
    TypeTextAction,
    to_domain_action,
)
from mint_computer_mcp.domain.geometry import SnapshotPoint
from mint_computer_mcp.domain.identifiers import SnapshotId
from mint_computer_mcp.domain.input import (
    Click,
    KeyName,
    MovePointer,
    PointerButton,
    PressKeys,
    TypeText,
)

adapter = TypeAdapter[DesktopAction](DesktopAction)


@pytest.mark.parametrize(
    "action",
    [
        ClickAction(kind="click", snapshot_id=SnapshotId("s1"), x=0, y=20),
        MoveAction(kind="move", snapshot_id=SnapshotId("s1"), x=10, y=0),
        TypeTextAction(kind="type_text", text="hello\n世界"),
        KeyPressAction(kind="key_press", keys=("Control_L", "a")),
    ],
)
def test_action_json_round_trip(action: DesktopAction) -> None:
    restored = adapter.validate_json(adapter.dump_json(action))
    assert type(restored) is type(action)
    assert restored == action


@pytest.mark.parametrize(
    ("payload", "error_type"),
    [
        ({"kind": "click", "snapshot_id": "s1", "x": 1, "y": 2, "text": "oops"}, "extra_forbidden"),
        ({"kind": "click", "snapshot_id": "s1", "x": "1", "y": 2}, "int_type"),
        ({"kind": "click", "snapshot_id": "s1", "x": True, "y": 2}, "int_type"),
        ({"kind": "click", "snapshot_id": "s1", "x": 1.0, "y": 2}, "int_type"),
        ({"kind": "click", "snapshot_id": "s1", "x": -1, "y": 2}, "greater_than_equal"),
        ({"kind": "move", "snapshot_id": "s1", "x": 1, "y": -2}, "greater_than_equal"),
        ({"kind": "click", "x": 1, "y": 2}, "missing"),
        ({"kind": "move", "snapshot_id": 1, "x": 1, "y": 2}, "string_type"),
        (
            {"kind": "click", "snapshot_id": "s1", "x": 1, "y": 2, "button": "other"},
            "literal_error",
        ),
        ({"kind": "type_text", "x": 100}, "missing"),
        ({"kind": "unknown"}, "union_tag_invalid"),
        ({"x": 1}, "union_tag_not_found"),
        ({"kind": "key_press", "keys": ()}, "too_short"),
        ({"kind": "key_press", "keys": ("",)}, "string_too_short"),
        ({"kind": "type_text", "text": ""}, "string_too_short"),
    ],
)
def test_invalid_actions(payload: dict[str, object], error_type: str) -> None:
    with pytest.raises(ValidationError) as error:
        _ = adapter.validate_python(payload)
    assert error_type in {item["type"] for item in error.value.errors()}


def test_json_key_array_and_snapshot_identifier() -> None:
    assert adapter.validate_json('{"kind":"key_press","keys":["Return"]}') == KeyPressAction(
        kind="key_press", keys=("Return",)
    )
    action = adapter.validate_json('{"kind":"click","snapshot_id":"s1","x":0,"y":0}')
    assert isinstance(action, ClickAction)
    assert action.snapshot_id == SnapshotId("s1")
    assert action.button == "left"


def test_click_action_converts_to_domain() -> None:
    action = ClickAction(
        kind="click",
        snapshot_id=SnapshotId("snap_1"),
        x=12,
        y=34,
        button="right",
    )

    assert to_domain_action(action) == Click(
        snapshot_id=SnapshotId("snap_1"),
        point=SnapshotPoint(12, 34),
        button=PointerButton.RIGHT,
    )


def test_move_action_converts_to_domain() -> None:
    action = MoveAction(
        kind="move",
        snapshot_id=SnapshotId("snap_1"),
        x=12,
        y=34,
    )

    assert to_domain_action(action) == MovePointer(
        snapshot_id=SnapshotId("snap_1"),
        point=SnapshotPoint(12, 34),
    )


def test_type_text_action_converts_to_domain() -> None:
    assert to_domain_action(TypeTextAction(kind="type_text", text="hello")) == TypeText("hello")


def test_key_press_action_converts_to_domain() -> None:
    assert to_domain_action(
        KeyPressAction(
            kind="key_press",
            keys=("Control_L", "a"),
        )
    ) == PressKeys(
        (
            KeyName("Control_L"),
            KeyName("a"),
        )
    )
