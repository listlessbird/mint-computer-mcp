"""Small boundary around xcffib."""

import struct
import sys
from types import TracebackType
from typing import Self

import xcffib
import xcffib.randr
import xcffib.xproto

from mint_computer_mcp.domain.geometry import RootRect, Size
from mint_computer_mcp.domain.identifiers import AtomId, RandrOutputId, WindowId
from mint_computer_mcp.domain.x11 import FrameExtents, ProtocolVersion, RandrOutput, X11Screen

"""
X11        protocol / graphical system
X server   program implementing the server side of X11
X client   program talking to the X server
XCB        C library for speaking the X11 protocol
Window     X11 server-side resource identified by an integer
Root       special top-level X11 window
Property   metadata attached to an X11 window
Atom       numeric identifier for a string such as "_NET_WM_NAME"
WM         Window Manager, an X11 client controlling window placement/policy
EWMH       standard conventions allowing applications and WMs to communicate
"""


_PROPERTY_FORMAT_32 = 32
_PROPERTY_FORMAT_8 = 8
_WINDOW_VALUE = struct.Struct("=I")
_FRAME_EXTENTS = struct.Struct("=IIII")


class X11Error(RuntimeError):
    """An expected X11 connection or protocol failure."""


class X11ConnectionError(X11Error):
    """Raised when the X server connection or preferred screen is invalid."""


class X11Client:
    """Translate xcffib replies into domain types."""

    def __init__(self, connection: xcffib.Connection) -> None:
        """Wrap an existing connection and take responsibility for closing it."""
        self._connection: xcffib.Connection = connection
        self._atoms: dict[str, AtomId] = {}

    @classmethod
    def connect(cls, display: str) -> Self:
        "Connect to an x11 display."
        try:
            connection = xcffib.connect(display=display)
        except xcffib.ConnectionException as exc:
            msg = f"Couldnt connect to X display {display!r}"
            raise X11ConnectionError(msg) from exc
        return cls(connection)

    def close(self) -> None:
        """Close the xcb connection."""
        self._connection.disconnect()

    def __enter__(self) -> Self:
        """Return this client for scoped connection use."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Close the connection and translate native failures from the scoped operations."""
        self.close()
        if isinstance(exc_value, (xcffib.ConnectionException, xcffib.Error)):
            msg = f"X11 request failed: {exc_value}"
            raise X11Error(msg) from exc_value

    def root_rect(self) -> RootRect:
        """Query current root dimensions, including framebuffer resizes since connection."""
        geometry = self._connection.core.GetGeometry(int(self.root_window())).reply()
        return RootRect(x=0, y=0, width=geometry.width, height=geometry.height)

    def active_window(self, *, root: WindowId) -> WindowId | None:
        """Return EWMH active client window."""
        return self.window_property(window=root, name="_NET_ACTIVE_WINDOW")

    def window_title(self, *, window: WindowId) -> str | None:
        """Return a window's EWMH UTF-8 title."""
        return self.utf8_property(window=window, name="_NET_WM_NAME")

    def client_geometry(self, *, window: WindowId, root: WindowId) -> RootRect | None:
        """Return an x11 client window's geometry in root coordinates."""
        try:
            geometry = self._connection.core.GetGeometry(int(window)).reply()
            translated = self._connection.core.TranslateCoordinates(
                int(window), int(root), 0, 0
            ).reply()
        except (xcffib.xproto.DrawableError, xcffib.xproto.WindowError):
            return None

        if not translated.same_screen:
            return None

        width = int(geometry.width)
        height = int(geometry.height)

        if width <= 0 or height <= 0:
            return None

        return RootRect(
            x=int(translated.dst_x), y=int(translated.dst_y), width=width, height=height
        )

    def frame_extents(self, *, window: WindowId) -> FrameExtents | None:
        """Return EWMH window manager decoration extents."""
        result = self._property_bytes(
            window=window,
            property_atom=self.atom("_NET_FRAME_EXTENTS"),
            type_atom=int(xcffib.xproto.Atom.CARDINAL),
            long_length=4,
        )

        if result is None:
            return None

        format_bits, data = result

        if format_bits != _PROPERTY_FORMAT_32 or len(data) != _FRAME_EXTENTS.size:
            return None

        left, right, top, bottom = (
            int.from_bytes(data[offset : offset + 4], byteorder=sys.byteorder)
            for offset in range(0, _FRAME_EXTENTS.size, 4)
        )

        return FrameExtents(left=left, right=right, top=top, bottom=bottom)

    def window_frame_geometry(self, *, window: WindowId, root: WindowId) -> RootRect | None:
        """Return a top level window rectangle including WM decorations when known."""
        client = self.client_geometry(window=window, root=root)

        if client is None:
            return None

        extents = self.frame_extents(window=window)

        if extents is None:
            return client

        return RootRect(
            x=client.x - extents.left,
            y=client.y - extents.top,
            width=client.width + extents.left + extents.right,
            height=client.height + extents.top + extents.bottom,
        )

    @property
    def preferred_screen(self) -> int:
        """Return preferred screen x11 index."""
        return int(self._connection.pref_screen)

    @property
    def vendor(self) -> str:
        """Return x11 server vendor string."""
        return str(self._connection.get_setup().vendor.to_string())

    @property
    def protocol_version(self) -> ProtocolVersion:
        """Return core x11 proto version."""
        setup = self._connection.get_setup()

        return ProtocolVersion(
            major=int(setup.protocol_major_version), minor=int(setup.protocol_minor_version)
        )

    @property
    def release_number(self) -> int:
        """Return the X server release number."""
        return int(self._connection.get_setup().release_number)

    def screens(self) -> tuple[X11Screen, ...]:
        """Return X11 screens exposed by the server."""
        setup = self._connection.get_setup()

        return tuple(
            X11Screen(
                index=index,
                root=WindowId(int(screen.root)),
                size=Size(
                    width=int(screen.width_in_pixels),
                    height=int(screen.height_in_pixels),
                ),
            )
            for index, screen in enumerate(setup.roots)
        )

    def root_window(self) -> WindowId:
        """Return the root window of the preferred X11 screen."""
        return self._preferred_screen_info().root

    def extensions(self) -> frozenset[str]:
        """Return advertised X11 extension names normalized to uppercase."""
        reply = self._connection.core.ListExtensions().reply()

        return frozenset(item.name.to_string().upper() for item in reply.names)

    def atom(self, name: str) -> AtomId | None:
        """Look up an existing atom without creating it; cache successful lookups."""
        cached = self._atoms.get(name)

        if cached is not None:
            return cached

        encoded_name = name.encode("utf-8")
        reply = self._connection.core.InternAtom(
            only_if_exists=True,
            name_len=len(encoded_name),
            name=encoded_name,
        ).reply()

        if reply.atom == 0:
            return None

        atom = AtomId(reply.atom)
        self._atoms[name] = atom

        return atom

    def window_property(
        self,
        *,
        window: WindowId,
        name: str,
    ) -> WindowId | None:
        """Read a WINDOW/32 property."""
        result = self._property_bytes(
            window=window,
            property_atom=self.atom(name),
            type_atom=int(xcffib.xproto.Atom.WINDOW),
            long_length=1,
        )

        if result is None:
            return None

        format_bits, data = result

        if format_bits != _PROPERTY_FORMAT_32 or len(data) != _WINDOW_VALUE.size:
            return None

        raw_window = int.from_bytes(data, byteorder=sys.byteorder)

        return WindowId(raw_window)

    def utf8_property(
        self,
        *,
        window: WindowId,
        name: str,
    ) -> str | None:
        """Read a complete UTF8_STRING/8 property, returning None above 4096 bytes."""
        result = self._property_bytes(
            window=window,
            property_atom=self.atom(name),
            type_atom=self.atom("UTF8_STRING"),
            long_length=1024,
        )

        if result is None:
            return None

        format_bits, data = result

        if format_bits != _PROPERTY_FORMAT_8:
            return None

        return data.rstrip(b"\0").decode(
            "utf-8",
            errors="replace",
        )

    def randr_version(self) -> ProtocolVersion:
        """Negotiate and return the RandR protocol version."""
        randr = self._connection(xcffib.randr.key)

        reply = randr.QueryVersion(
            xcffib.randr.MAJOR_VERSION,
            xcffib.randr.MINOR_VERSION,
        ).reply()

        return ProtocolVersion(
            major=int(reply.major_version),
            minor=int(reply.minor_version),
        )

    def randr_outputs(
        self,
        *,
        root: WindowId,
        version: ProtocolVersion,
    ) -> tuple[RandrOutput, ...]:
        """Return connected RandR outputs backed by active CRTCs."""
        randr = self._connection(xcffib.randr.key)

        # The current variant avoids a hardware poll on every observation.
        resources = (
            randr.GetScreenResourcesCurrent(int(root)).reply()
            if (version.major, version.minor) >= (1, 3)
            else randr.GetScreenResources(int(root)).reply()
        )

        primary_output = 0

        if (version.major, version.minor) >= (1, 3):
            primary_output = int(randr.GetOutputPrimary(int(root)).reply().output)

        outputs: list[RandrOutput] = []

        for raw_output_id in resources.outputs:
            output = self._randr_output(
                randr=randr,
                raw_output_id=int(raw_output_id),
                primary_output=primary_output,
            )

            if output is not None:
                outputs.append(output)

        outputs.sort(
            key=lambda output: (
                not output.primary,
                output.geometry.x,
                output.geometry.y,
                output.name,
            )
        )

        return tuple(outputs)

    def _randr_output(
        self,
        *,
        randr: xcffib.randr.randrExtension,
        raw_output_id: int,
        primary_output: int,
    ) -> RandrOutput | None:
        """Translate one RandR output into the domain model."""
        info = randr.GetOutputInfo(
            raw_output_id,
            xcffib.CurrentTime,
        ).reply()

        if info.connection != xcffib.randr.Connection.Connected:
            return None

        if not info.crtc:
            return None

        crtc = randr.GetCrtcInfo(
            info.crtc,
            xcffib.CurrentTime,
        ).reply()

        if crtc.width <= 0 or crtc.height <= 0:
            return None

        return RandrOutput(
            output_id=RandrOutputId(raw_output_id),
            name=bytes(info.name).decode(
                "utf-8",
                errors="replace",
            ),
            geometry=RootRect(
                x=int(crtc.x),
                y=int(crtc.y),
                width=int(crtc.width),
                height=int(crtc.height),
            ),
            primary=raw_output_id == primary_output,
        )

    def _property_bytes(
        self,
        *,
        window: WindowId,
        property_atom: AtomId | None,
        type_atom: int | None,
        long_length: int,
    ) -> tuple[int, bytes] | None:
        """Read a complete property, rejecting missing, mismatched, or truncated values."""
        if property_atom is None or type_atom is None:
            return None

        try:
            reply = self._connection.core.GetProperty(
                delete=False,
                window=window,
                property=property_atom,
                type=type_atom,
                long_offset=0,
                long_length=long_length,
            ).reply()
        except xcffib.xproto.WindowError:
            return None

        if reply.type != type_atom or reply.bytes_after != 0:
            return None

        return int(reply.format), bytes(reply.value.buf())

    def _preferred_screen_info(self) -> X11Screen:
        """Return the preferred screen."""
        screens = self.screens()
        index = self.preferred_screen

        if not 0 <= index < len(screens):
            msg = f"invalid preferred X11 screen: {index}"
            raise X11ConnectionError(msg)

        return screens[index]
