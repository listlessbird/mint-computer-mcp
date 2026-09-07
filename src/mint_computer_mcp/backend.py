"""Backend contract between native desktops and DesktopRuntime."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from mint_computer_mcp.domain.geometry import DesktopLayoutPoint, Size, SnapshotPoint
from mint_computer_mcp.domain.observation import (
    DesktopState,
    ObservationTarget,
    OutputInfo,
)


class BackendError(RuntimeError):
    """Base error."""


class CapabilityUnavailableError(BackendError):
    """Raised when a backend cannot provide a requested capability."""


class TargetUnavailableError(BackendError):
    """Raised when an observation target is not currently available."""


class PixelFormat(StrEnum):
    """Raw CPU pixel layouts accepted by the image encoder."""

    BGRX = "bgrx"


@dataclass(frozen=True, slots=True)
class PixelFrame:
    """Ephemeral pixel data from a backend."""

    data: memoryview
    size: Size
    stride: int
    format: PixelFormat

    def __post_init__(self) -> None:
        """Validate the currently supported pixel representation."""
        match self.format:
            case PixelFormat.BGRX:
                minimum_stride = self.size.width * 4

        if self.stride < minimum_stride:
            msg = "pixel stride is smaller than one image row"
            raise ValueError(msg)

        required_bytes = self.stride * self.size.height

        if len(self.data) < required_bytes:
            msg = "pixel buffer is smaller than the declared image extent"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class BackendCapture[SnapshotStateT]:
    """Raw capture plus backend-private state."""

    frame: PixelFrame
    snapshot_state: SnapshotStateT
    desktop_state: DesktopState
    display_generation: int


class DesktopBackend[SnapshotStateT](Protocol):
    """Native desktop operations required by DesktopRuntime."""

    @property
    def display_generation(self) -> int:
        """Return the current backend spatial-layout generation."""
        ...

    def outputs(self) -> tuple[OutputInfo, ...]:
        """Return the current output layout."""
        ...

    def capture(
        self,
        target: ObservationTarget,
    ) -> BackendCapture[SnapshotStateT]:
        """Capture one observation target."""
        ...

    def resolve_point(
        self,
        state: SnapshotStateT,
        point: SnapshotPoint,
        encoded_size: Size,
    ) -> DesktopLayoutPoint:
        """Resolve an image pixel using the backend's retained capture mapping."""
        ...

    def close(self) -> None:
        """Release backend-owned native resources."""
        ...
