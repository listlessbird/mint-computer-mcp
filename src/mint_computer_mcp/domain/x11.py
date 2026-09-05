"""Domain types describing an X11 desktop."""

from dataclasses import dataclass
from enum import StrEnum

from mint_computer_mcp.domain.geometry import RootRect, Size
from mint_computer_mcp.domain.identifiers import RandrOutputId, WindowId


class X11Extension(StrEnum):
    """X11 extensions used or expected by the desktop runtime."""

    XTEST = "XTEST"
    RANDR = "RANDR"
    MIT_SHM = "MIT-SHM"
    DAMAGE = "DAMAGE"
    XFIXES = "XFIXES"
    COMPOSITE = "COMPOSITE"


@dataclass(frozen=True, slots=True)
class ProtocolVersion:
    """Protocol major and minor version."""

    major: int
    minor: int


@dataclass(frozen=True, slots=True)
class ExtensionStatus:
    """Availability of an X11 extension."""

    extension: X11Extension
    available: bool


@dataclass(frozen=True, slots=True)
class X11Screen:
    """One X11 screen exposed by the server."""

    index: int
    root: WindowId
    size: Size


@dataclass(frozen=True, slots=True)
class RandrOutput:
    """A connected RandR output with an active CRTC."""

    output_id: RandrOutputId
    name: str
    geometry: RootRect
    primary: bool


@dataclass(frozen=True, slots=True)
class WindowManagerInfo:
    """EWMH information for the active window manager."""

    ewmh_detected: bool
    name: str | None
    supporting_window: WindowId | None


@dataclass(frozen=True, slots=True)
class X11ProbeReport:
    """Observed capabilities of the current X11 desktop."""

    session_type: str | None
    desktop: str | None
    display: str

    vendor: str
    protocol: ProtocolVersion
    release_number: int

    preferred_screen: int
    screens: tuple[X11Screen, ...]

    extensions: tuple[ExtensionStatus, ...]

    randr_version: ProtocolVersion | None
    outputs: tuple[RandrOutput, ...]

    window_manager: WindowManagerInfo

    def supports(self, extension: X11Extension) -> bool:
        """Return whether the server advertises an extension."""
        return any(status.extension == extension and status.available for status in self.extensions)
