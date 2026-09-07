"""neutral desktop input actions."""

from dataclasses import dataclass
from enum import StrEnum
from typing import NewType

from mint_computer_mcp.domain.geometry import SnapshotPoint
from mint_computer_mcp.domain.identifiers import SnapshotId

KeyName = NewType("KeyName", str)


class PointerButton(StrEnum):  # noqa: D101
    LEFT = "left"
    MIDDLE = "middle"
    RIGHT = "right"


@dataclass(frozen=True, slots=True)
class MovePointer:  # noqa: D101
    snapshot_id: SnapshotId
    point: SnapshotPoint


@dataclass(frozen=True, slots=True)
class Click:  # noqa: D101
    snapshot_id: SnapshotId
    point: SnapshotPoint
    button: PointerButton


@dataclass(frozen=True, slots=True)
class TypeText:  # noqa: D101
    text: str

    def __post_init__(self) -> None:
        """Reject empty text actions."""
        if not self.text:
            msg = "text must not be empty"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class PressKeys:
    """Press one nonempty key chord."""

    keys: tuple[KeyName, ...]

    def __post_init__(self) -> None:
        """Reject empty key chords and key names."""
        if not self.keys:
            msg = "key chord must not be empty"
            raise ValueError(msg)

        if any(not key for key in self.keys):
            msg = "key names must not be empty"
            raise ValueError(msg)


type InputAction = MovePointer | Click | TypeText | PressKeys
