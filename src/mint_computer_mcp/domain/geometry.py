"""Integer pixel geometry with half-open rectangle bounds."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Size:
    """Positive pixel dimensions."""

    width: int
    height: int

    def __post_init__(self) -> None:
        """Reject empty or inverted dimensions."""
        if self.width <= 0:
            msg = "width must be positive"
            raise ValueError(msg)

        if self.height <= 0:
            msg = "height must be positive"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class RootPoint:
    """A pixel in root space; coordinates may be negative."""

    x: int
    y: int


@dataclass(frozen=True, slots=True)
class SnapshotPoint:
    """A pixel in snapshot space; bounds are checked during resolution."""

    x: int
    y: int


@dataclass(frozen=True, slots=True)
class RootRect:
    """A positive-sized root region, excluding its right and bottom edges."""

    x: int
    y: int
    width: int
    height: int

    def __post_init__(self) -> None:
        """Reject empty or inverted dimensions."""
        if self.width <= 0:
            msg = "width must be positive"
            raise ValueError(msg)

        if self.height <= 0:
            msg = "height must be positive"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class SnapshotRect:
    """A positive-sized snapshot region with half-open bounds."""

    x: int
    y: int
    width: int
    height: int

    def __post_init__(self) -> None:
        """Reject empty or inverted dimensions."""
        if self.width <= 0:
            msg = "width must be positive"
            raise ValueError(msg)

        if self.height <= 0:
            msg = "height must be positive"
            raise ValueError(msg)


def snapshot_to_root(
    point: SnapshotPoint,
    *,
    capture: RootRect,
    encoded_size: Size,
) -> RootPoint:
    """Map a snapshot pixel to the top-left root pixel of its scaled cell.

    Use integer floor scaling, with no floating-point rounding. Input coordinates
    must lie in [0, width) and [0, height) of the encoded image. The result stays
    inside the capture, including for negative root origins and one-pixel images.
    Downsampling can leave the capture's last pixel unselected.
    """
    if not (0 <= point.x < encoded_size.width and 0 <= point.y < encoded_size.height):
        msg = "snapshot point is outside the encoded image"
        raise ValueError(msg)

    return RootPoint(
        x=capture.x + point.x * capture.width // encoded_size.width,
        y=capture.y + point.y * capture.height // encoded_size.height,
    )
