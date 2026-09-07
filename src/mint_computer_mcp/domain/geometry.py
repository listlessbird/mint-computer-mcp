"""Integer pixel geometry with half-open rectangle bounds."""

from collections.abc import Iterable
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


def intersect_root_rect(first: RootRect, second: RootRect) -> RootRect | None:
    """Return intersection of two root space rectangles."""
    left = max(first.x, second.x)
    top = max(first.y, second.y)
    right = min(first.x + first.width, second.x + second.width)
    bottom = min(first.y + first.height, second.y + second.height)

    if right <= left or bottom <= top:
        return None

    return RootRect(x=left, y=top, width=right - left, height=bottom - top)


def bounding_root_rect(rects: Iterable[RootRect]) -> RootRect | None:
    """Return smallest root space rectangle containing all inputs."""
    items = tuple(rects)

    if not items:
        return None

    left = min(rect.x for rect in items)
    top = min(rect.y for rect in items)
    right = max(rect.x + rect.width for rect in items)
    bottom = max(rect.y + rect.height for rect in items)

    return RootRect(
        x=left,
        y=top,
        width=right - left,
        height=bottom - top,
    )


@dataclass(frozen=True, slots=True)
class DesktopLayoutPoint:
    """A resolved point in the backend's desktop layout space."""

    x: int
    y: int


@dataclass(frozen=True, slots=True)
class DesktopLayoutRect:
    """A rectangle in the desktop backend's logical layout space."""

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
