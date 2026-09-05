"""Backend-neutral desktop observation domain types."""

from dataclasses import dataclass

from mint_computer_mcp.domain.geometry import Size
from mint_computer_mcp.domain.identifiers import (
    OutputRef,
    SnapshotId,
    WindowRef,
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


@dataclass(frozen=True, slots=True)
class DesktopTarget:
    """Observe the visible desktop surface."""


@dataclass(frozen=True, slots=True)
class ActiveWindowTarget:
    """Observe the visible region occupied by the active window."""


@dataclass(frozen=True, slots=True)
class OutputTarget:
    """Observe one backend output."""

    output: OutputRef


type ObservationTarget = DesktopTarget | ActiveWindowTarget | OutputTarget


@dataclass(frozen=True, slots=True)
class OutputInfo:
    """Backend-neutral output metadata."""

    ref: OutputRef
    name: str
    layout: DesktopLayoutRect
    primary: bool


@dataclass(frozen=True, slots=True)
class WindowInfo:
    """Backend-neutral active-window metadata."""

    ref: WindowRef
    title: str | None
    layout: DesktopLayoutRect


@dataclass(frozen=True, slots=True)
class DesktopState:
    """Desktop metadata observed alongside a frame."""

    outputs: tuple[OutputInfo, ...]
    active_window: WindowInfo | None


@dataclass(frozen=True, slots=True)
class Snapshot:
    """Observation metadata; captured_at is process-monotonic time in seconds."""

    id: SnapshotId
    captured_at: float
    source_size: Size
    encoded_size: Size
    display_generation: int


@dataclass(frozen=True, slots=True)
class JpegImage:
    """A JPEG image produced for model transport."""

    size: Size
    data: bytes


@dataclass(frozen=True, slots=True)
class Observation:
    """One encoded desktop observation."""

    target: ObservationTarget
    snapshot: Snapshot
    image: JpegImage
    state: DesktopState
