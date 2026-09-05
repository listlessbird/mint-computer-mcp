"""Exercise the native X11 boundary without opening a display."""

# Fake request methods retain xcffib's protocol names.
# ruff: noqa: N802

import struct
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import cast

import pytest
import xcffib
import xcffib.randr
import xcffib.xproto

from mint_computer_mcp.domain.geometry import RootRect
from mint_computer_mcp.domain.identifiers import WindowId
from mint_computer_mcp.domain.x11 import ProtocolVersion, WindowManagerInfo
from mint_computer_mcp.native.x11.client import X11Client, X11ConnectionError
from mint_computer_mcp.native.x11.probe import X11ProbeError, probe_x11

ROOT = 10
HELPER = 20
CHECK_ATOM = 100
NAME_ATOM = 101
UTF8_ATOM = 102


@dataclass(frozen=True, slots=True)
class Reply:
    value: SimpleNamespace | xcffib.xproto.WindowError

    def reply(self) -> SimpleNamespace:
        if isinstance(self.value, xcffib.xproto.WindowError):
            raise self.value
        return self.value


@dataclass(frozen=True, slots=True)
class PropertyValue:
    data: bytes

    def buf(self) -> bytes:
        return self.data


def property_reply(type_atom: int, format_bits: int, data: bytes, bytes_after: int = 0) -> Reply:
    return Reply(
        SimpleNamespace(
            type=type_atom,
            format=format_bits,
            value=PropertyValue(data),
            bytes_after=bytes_after,
        )
    )


def window_reply(window: int) -> Reply:
    return property_reply(xcffib.xproto.Atom.WINDOW, 32, struct.pack("=I", window))


@dataclass(slots=True)
class Core:
    atoms: dict[bytes, int] = field(default_factory=dict)
    properties: dict[tuple[int, int], Reply] = field(default_factory=dict)
    property_requests: list[dict[str, int | bool]] = field(default_factory=list)
    extension_names: tuple[str, ...] = ()

    def InternAtom(self, *, only_if_exists: bool, name_len: int, name: bytes) -> Reply:
        assert only_if_exists
        assert name_len == len(name)
        return Reply(SimpleNamespace(atom=self.atoms.get(name, 0)))

    def GetProperty(self, **request: int | bool) -> Reply:
        self.property_requests.append(request)
        return self.properties[request["window"], request["property"]]

    def ListExtensions(self) -> Reply:
        return Reply(
            SimpleNamespace(
                names=[
                    SimpleNamespace(name=SimpleNamespace(to_string=name.__str__))
                    for name in self.extension_names
                ]
            )
        )


@dataclass(slots=True)
class Randr:
    version: tuple[int, int] | None = None
    connection: int = xcffib.randr.Connection.Connected
    crtc: int = 30
    width: int = 1920
    height: int = 1080
    calls: list[str] = field(default_factory=list)

    def QueryVersion(self, major: int, minor: int) -> Reply:
        assert (major, minor) == (xcffib.randr.MAJOR_VERSION, xcffib.randr.MINOR_VERSION)
        assert self.version is not None, "QueryVersion called without RandR"
        self.calls.append("version")
        return Reply(SimpleNamespace(major_version=self.version[0], minor_version=self.version[1]))

    def GetScreenResources(self, root: int) -> Reply:
        assert root == ROOT
        assert self.version is not None
        assert self.version >= (1, 2)
        self.calls.append("resources")
        return Reply(SimpleNamespace(outputs=[40]))

    def GetOutputPrimary(self, root: int) -> Reply:
        assert root == ROOT
        assert self.version is not None
        assert self.version >= (1, 3)
        self.calls.append("primary")
        return Reply(SimpleNamespace(output=40))

    def GetOutputInfo(self, output: int, timestamp: int) -> Reply:
        assert (output, timestamp) == (40, xcffib.CurrentTime)
        self.calls.append("output")
        return Reply(SimpleNamespace(connection=self.connection, crtc=self.crtc, name=b"DP-1"))

    def GetCrtcInfo(self, crtc: int, timestamp: int) -> Reply:
        assert self.connection == xcffib.randr.Connection.Connected
        assert self.crtc != 0
        assert (crtc, timestamp) == (self.crtc, xcffib.CurrentTime)
        self.calls.append("crtc")
        return Reply(SimpleNamespace(x=-1920, y=0, width=self.width, height=self.height))


@dataclass(slots=True)
class Connection:
    core: Core = field(default_factory=Core)
    randr: Randr = field(default_factory=Randr)
    pref_screen: int = 0
    closed: bool = False

    def __call__(self, key: object) -> Randr:
        assert key is xcffib.randr.key
        return self.randr

    def get_setup(self) -> SimpleNamespace:
        return SimpleNamespace(
            vendor=SimpleNamespace(to_string=lambda: "test"),
            protocol_major_version=11,
            protocol_minor_version=0,
            release_number=1,
            roots=[SimpleNamespace(root=ROOT, width_in_pixels=1920, height_in_pixels=1080)],
        )

    def disconnect(self) -> None:
        self.closed = True


@pytest.fixture
def connection(monkeypatch: pytest.MonkeyPatch) -> Connection:
    connection = Connection()

    def connect(*, display: str) -> xcffib.Connection:
        assert display == ":unit-test"
        # Only the native connection boundary needs a cast; the fakes stay typed.
        return cast("xcffib.Connection", cast("object", connection))

    monkeypatch.setattr(xcffib, "connect", connect)
    monkeypatch.setenv("DISPLAY", ":unit-test")
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    monkeypatch.delenv("XDG_CURRENT_DESKTOP", raising=False)
    return connection


@pytest.mark.parametrize(
    ("version", "calls"),
    [
        (None, []),
        ((1, 1), ["version"]),
        ((1, 2), ["version", "resources", "output", "crtc"]),
        ((1, 3), ["version", "resources", "primary", "output", "crtc"]),
        ((1, 6), ["version", "resources", "primary", "output", "crtc"]),
    ],
)
def test_randr_version_gates_requests(
    connection: Connection,
    version: tuple[int, int] | None,
    calls: list[str],
) -> None:
    connection.randr.version = version
    connection.core.extension_names = () if version is None else ("RANDR",)

    report = probe_x11()

    assert report.randr_version == (
        None if version is None else ProtocolVersion(major=version[0], minor=version[1])
    )
    assert connection.randr.calls == calls
    if version is not None and version >= (1, 2):
        assert len(report.outputs) == 1
        output = report.outputs[0]
        assert output.output_id == 40
        assert output.name == "DP-1"
        assert output.geometry == RootRect(x=-1920, y=0, width=1920, height=1080)
        assert output.primary == (version >= (1, 3))
    else:
        assert report.outputs == ()
    assert connection.closed


@pytest.mark.parametrize(
    ("status", "crtc", "size", "queries_crtc"),
    [
        (xcffib.randr.Connection.Disconnected, 30, (1920, 1080), False),
        (xcffib.randr.Connection.Connected, 0, (1920, 1080), False),
        (xcffib.randr.Connection.Connected, 30, (0, 1080), True),
        (xcffib.randr.Connection.Connected, 30, (1920, 0), True),
    ],
)
def test_unusable_outputs_are_ignored(
    connection: Connection,
    status: int,
    crtc: int,
    size: tuple[int, int],
    *,
    queries_crtc: bool,
) -> None:
    connection.randr = Randr(
        version=(1, 2), connection=status, crtc=crtc, width=size[0], height=size[1]
    )
    connection.core.extension_names = ("RANDR",)

    assert probe_x11().outputs == ()
    assert connection.randr.calls == ["version", "resources", "output"] + (
        ["crtc"] if queries_crtc else []
    )


@pytest.mark.parametrize("screen", [-1, 1])
def test_invalid_preferred_screen_fails_cleanly(connection: Connection, screen: int) -> None:
    connection.pref_screen = screen

    with pytest.raises(X11ProbeError, match=f"invalid preferred X11 screen: {screen}") as error:
        _ = probe_x11()

    assert isinstance(error.value.__cause__, X11ConnectionError)
    assert connection.closed


@pytest.mark.parametrize("missing", [b"_NET_WM_NAME", b"UTF8_STRING"])
def test_missing_atom_skips_property_request(connection: Connection, missing: bytes) -> None:
    connection.core.atoms = {b"_NET_WM_NAME": NAME_ATOM, b"UTF8_STRING": UTF8_ATOM}
    del connection.core.atoms[missing]
    with X11Client.connect(":unit-test") as client:
        assert client.atom(missing.decode()) is None
        assert client.utf8_property(window=WindowId(ROOT), name="_NET_WM_NAME") is None
        assert client.window_property(window=WindowId(ROOT), name="missing") is None
    assert connection.core.property_requests == []


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        (window_reply(HELPER), HELPER),
        (property_reply(UTF8_ATOM, 32, struct.pack("=I", HELPER)), None),
        (property_reply(xcffib.xproto.Atom.WINDOW, 8, struct.pack("=I", HELPER)), None),
        (property_reply(xcffib.xproto.Atom.WINDOW, 32, b"\x01\x02"), None),
        (property_reply(xcffib.xproto.Atom.WINDOW, 32, struct.pack("=II", HELPER, HELPER)), None),
        (property_reply(xcffib.xproto.Atom.WINDOW, 32, struct.pack("=I", HELPER), 4), None),
    ],
    ids=["valid", "wrong-type", "wrong-format", "short-value", "extra-value", "truncated"],
)
def test_window_property_validation(
    connection: Connection,
    reply: Reply,
    expected: int | None,
) -> None:
    connection.core.atoms[b"_NET_SUPPORTING_WM_CHECK"] = CHECK_ATOM
    connection.core.properties[ROOT, CHECK_ATOM] = reply
    with X11Client.connect(":unit-test") as client:
        assert (
            client.window_property(window=WindowId(ROOT), name="_NET_SUPPORTING_WM_CHECK")
            == expected
        )
    assert connection.core.property_requests == [
        {
            "delete": False,
            "window": ROOT,
            "property": CHECK_ATOM,
            "type": xcffib.xproto.Atom.WINDOW,
            "long_offset": 0,
            "long_length": 1,
        }
    ]


@pytest.mark.parametrize(
    ("type_atom", "format_bits", "bytes_after", "expected"),
    [
        (UTF8_ATOM, 8, 0, "Muffin"),
        (0, 8, 0, None),
        (UTF8_ATOM, 32, 0, None),
        (UTF8_ATOM, 8, 1, None),
    ],
)
def test_utf8_property_validation(
    connection: Connection,
    type_atom: int,
    format_bits: int,
    bytes_after: int,
    expected: str | None,
) -> None:
    connection.core.atoms = {b"_NET_WM_NAME": NAME_ATOM, b"UTF8_STRING": UTF8_ATOM}
    connection.core.properties[HELPER, NAME_ATOM] = property_reply(
        type_atom, format_bits, b"Muffin\0", bytes_after
    )
    with X11Client.connect(":unit-test") as client:
        assert client.utf8_property(window=WindowId(HELPER), name="_NET_WM_NAME") == expected
    assert connection.core.property_requests == [
        {
            "delete": False,
            "window": HELPER,
            "property": NAME_ATOM,
            "type": UTF8_ATOM,
            "long_offset": 0,
            "long_length": 1024,
        }
    ]


@pytest.mark.parametrize("handshake", ["valid", "missing", "mismatch", "stale", "stale-name"])
def test_wm_supporting_window_handshake(connection: Connection, handshake: str) -> None:
    connection.core.atoms = {
        b"_NET_SUPPORTING_WM_CHECK": CHECK_ATOM,
        b"_NET_WM_NAME": NAME_ATOM,
        b"UTF8_STRING": UTF8_ATOM,
    }
    connection.core.properties[ROOT, CHECK_ATOM] = window_reply(HELPER)
    connection.core.properties[HELPER, CHECK_ATOM] = window_reply(HELPER)
    connection.core.properties[HELPER, NAME_ATOM] = property_reply(UTF8_ATOM, 8, b"Muffin")
    if handshake == "missing":
        connection.core.properties[HELPER, CHECK_ATOM] = property_reply(0, 0, b"")
    elif handshake == "mismatch":
        connection.core.properties[HELPER, CHECK_ATOM] = window_reply(ROOT)
    elif handshake in {"stale", "stale-name"}:
        atom = CHECK_ATOM if handshake == "stale" else NAME_ATOM
        # A real native exception type, without needing an X11 wire packet to construct it.
        connection.core.properties[HELPER, atom] = Reply(
            xcffib.xproto.WindowError.__new__(xcffib.xproto.WindowError)
        )

    report = probe_x11()

    assert report.window_manager == WindowManagerInfo(
        ewmh_detected=handshake in {"valid", "stale-name"},
        name="Muffin" if handshake == "valid" else None,
        supporting_window=WindowId(HELPER),
    )
    assert len(connection.core.property_requests) == (
        3 if handshake in {"valid", "stale-name"} else 2
    )
    assert connection.closed
