"""Validated external actions; pointer coordinates refer to a named snapshot."""

from typing import Annotated, Literal

from pydantic import Field

from mint_computer_mcp.api.model import ApiModel
from mint_computer_mcp.domain.identifiers import SnapshotId

Coordinate = Annotated[int, Field(ge=0)]


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
    """Type literal text."""

    kind: Literal["type_text"]
    text: str


class KeyPressAction(ApiModel):
    """Press a nonempty chord; TODO: resolve keys."""

    kind: Literal["key_press"]
    keys: Annotated[tuple[Annotated[str, Field(min_length=1)], ...], Field(min_length=1)]


DesktopAction = Annotated[
    ClickAction | MoveAction | TypeTextAction | KeyPressAction,
    Field(discriminator="kind"),
]
