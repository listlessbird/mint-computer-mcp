"""Validated external desktop actions and domain conversion."""

from typing import Annotated, Literal, assert_never

from pydantic import Field

from mint_computer_mcp.api.model import ApiModel
from mint_computer_mcp.domain.geometry import SnapshotPoint
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

Coordinate = Annotated[int, Field(ge=0)]
NonEmptyText = Annotated[str, Field(min_length=1)]
NonEmptyKeyName = Annotated[str, Field(min_length=1)]


class ClickAction(ApiModel):
    """Click a pixel in a previously observed snapshot."""

    kind: Literal["click"]
    snapshot_id: SnapshotId
    x: Coordinate
    y: Coordinate
    button: Literal["left", "middle", "right"] = "left"


class MoveAction(ApiModel):
    """Move to a pixel in a previously observed snapshot."""

    kind: Literal["move"]
    snapshot_id: SnapshotId
    x: Coordinate
    y: Coordinate


class TypeTextAction(ApiModel):
    """Type nonempty literal text."""

    kind: Literal["type_text"]
    text: NonEmptyText


class KeyPressAction(ApiModel):
    """Press one nonempty ordered key chord."""

    kind: Literal["key_press"]
    keys: Annotated[
        tuple[NonEmptyKeyName, ...],
        Field(min_length=1),
    ]


DesktopAction = Annotated[
    ClickAction | MoveAction | TypeTextAction | KeyPressAction,
    Field(discriminator="kind"),
]


class ActionResult(ApiModel):
    """Successful completion of one runtime input action."""

    status: Literal["completed"] = "completed"


def to_domain_action(action: DesktopAction) -> InputAction:
    """Translate validated API input into the backend-neutral domain union."""
    match action:
        case ClickAction(
            snapshot_id=snapshot_id,
            x=x,
            y=y,
            button=button,
        ):
            return Click(
                snapshot_id=snapshot_id,
                point=SnapshotPoint(x=x, y=y),
                button=PointerButton(button),
            )

        case MoveAction(
            snapshot_id=snapshot_id,
            x=x,
            y=y,
        ):
            return MovePointer(
                snapshot_id=snapshot_id,
                point=SnapshotPoint(x=x, y=y),
            )

        case TypeTextAction(text=text):
            return TypeText(text=text)

        case KeyPressAction(keys=keys):
            return PressKeys(
                keys=tuple(KeyName(key) for key in keys),
            )

        case _:
            assert_never(action)
