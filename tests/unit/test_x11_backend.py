"""Exercise observation orchestration using real runtime and backend code."""

from dataclasses import dataclass, field
from types import TracebackType
from typing import TYPE_CHECKING, Self, cast

import pytest

from mint_computer_mcp.backend import (
    CapabilityUnavailableError,
    DisplayGenerationMismatchError,
    PixelFormat,
    PixelFrame,
    TargetUnavailableError,
)
from mint_computer_mcp.domain.geometry import (
    DesktopLayoutPoint,
    RootPoint,
    RootRect,
    Size,
    SnapshotPoint,
)
from mint_computer_mcp.domain.identifiers import OutputRef, RandrOutputId, WindowId
from mint_computer_mcp.domain.input import PointerButton
from mint_computer_mcp.domain.observation import (
    ActiveWindowTarget,
    DesktopTarget,
    OutputTarget,
)
from mint_computer_mcp.domain.x11 import ProtocolVersion, RandrOutput
from mint_computer_mcp.native.x11.backend import X11Backend
from mint_computer_mcp.native.x11.capture import X11Capture
from mint_computer_mcp.native.x11.client import X11Client

if TYPE_CHECKING:
    from mint_computer_mcp.native.x11.input import X11Input
from mint_computer_mcp.runtime import DesktopRuntime, StaleSnapshotError


@dataclass(slots=True)
class Client:
    root: RootRect = field(default_factory=lambda: RootRect(0, 0, 160, 80))
    outputs: tuple[RandrOutput, ...] = (
        RandrOutput(RandrOutputId(1), "left", RootRect(0, 0, 80, 80), primary=True),
        RandrOutput(RandrOutputId(2), "right", RootRect(80, 0, 80, 80), primary=False),
    )
    active: RootRect | None = field(default_factory=lambda: RootRect(-10, 20, 60, 80))
    extension_names: frozenset[str] = frozenset({"RANDR", "XTEST"})
    randr_protocol: ProtocolVersion = field(default_factory=lambda: ProtocolVersion(1, 3))
    xtest_protocol: ProtocolVersion = field(default_factory=lambda: ProtocolVersion(2, 2))
    connect_calls: list[str] = field(default_factory=list)
    closed: bool = False
    close_order: list[str] | None = None

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def extensions(self) -> frozenset[str]:
        self.connect_calls.append("extensions")
        return self.extension_names

    def randr_version(self) -> ProtocolVersion:
        self.connect_calls.append("randr-version")
        return self.randr_protocol

    def xtest_version(self) -> ProtocolVersion:
        self.connect_calls.append("xtest-version")
        return self.xtest_protocol

    def root_window(self) -> WindowId:
        self.connect_calls.append("root")
        return WindowId(1)

    def root_rect(self) -> RootRect:
        return self.root

    def randr_outputs(self, *, root: WindowId, version: ProtocolVersion) -> tuple[RandrOutput, ...]:
        assert root == 1
        assert version == ProtocolVersion(1, 3)
        return self.outputs

    def active_window(self, *, root: WindowId) -> WindowId | None:
        assert root == 1
        return None if self.active is None else WindowId(5)

    def window_frame_geometry(self, *, window: WindowId, root: WindowId) -> RootRect | None:
        assert window == 5
        assert root == 1
        return self.active

    def window_title(self, *, window: WindowId) -> str:
        assert window == 5
        return "Test window"

    def close(self) -> None:
        self.closed = True
        if self.close_order is not None:
            self.close_order.append("client")


@dataclass(slots=True)
class Capture:
    rects: list[RootRect] = field(default_factory=list)
    closed: bool = False
    close_order: list[str] | None = None

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def capture_rect(self, rect: RootRect) -> PixelFrame:
        self.rects.append(rect)
        return PixelFrame(
            memoryview(bytes(rect.width * rect.height * 4)),
            Size(rect.width, rect.height),
            rect.width * 4,
            PixelFormat.BGRX,
        )

    def close(self) -> None:
        self.closed = True
        if self.close_order is not None:
            self.close_order.append("capture")


@dataclass(slots=True)
class Input:
    moves: list[RootPoint] = field(default_factory=list)
    clicks: list[tuple[RootPoint, PointerButton]] = field(default_factory=list)
    close_order: list[str] | None = None

    def move_pointer(self, point: RootPoint) -> None:
        self.moves.append(point)

    def click(self, point: RootPoint, button: PointerButton) -> None:
        self.clicks.append((point, button))

    def close(self) -> None:
        if self.close_order is not None:
            self.close_order.append("input")


def backend(client: Client, capture: Capture, input_: Input | None = None) -> X11Backend:
    # Substitute only the native boundaries; orchestration and coordinate mapping are real.
    return X11Backend(
        display=":unit-test",
        client=cast("X11Client", cast("object", client)),
        capture=cast("X11Capture", cast("object", capture)),
        input_=cast("X11Input", cast("object", input_ or Input())),
        root=WindowId(1),
        randr_version=ProtocolVersion(1, 3),
    )


def patch_connect(
    monkeypatch: pytest.MonkeyPatch,
    *,
    client: Client,
    capture: Capture,
) -> None:
    def connect(display: str) -> X11Client:
        assert display == ":unit-test"
        return cast("X11Client", cast("object", client))

    def create_capture(*, display: str) -> X11Capture:
        assert display == ":unit-test"
        client.connect_calls.append("capture")
        return cast("X11Capture", cast("object", capture))

    monkeypatch.setattr(X11Client, "connect", staticmethod(connect))
    monkeypatch.setattr("mint_computer_mcp.native.x11.backend.X11Capture", create_capture)


type CapabilityCase = tuple[
    frozenset[str],
    tuple[int, int],
    tuple[int, int],
    list[str],
    str,
]


@pytest.mark.parametrize(
    "case",
    [
        (frozenset({"XTEST"}), (1, 3), (2, 2), ["extensions"], "RANDR is required"),
        (frozenset({"RANDR"}), (1, 3), (2, 2), ["extensions"], "XTEST is required"),
        (
            frozenset({"RANDR", "XTEST"}),
            (1, 1),
            (2, 2),
            ["extensions", "randr-version"],
            "RANDR 1.2 or newer",
        ),
        (
            frozenset({"RANDR", "XTEST"}),
            (1, 3),
            (2, 0),
            ["extensions", "randr-version", "xtest-version"],
            "XTEST 2.1 or newer",
        ),
    ],
)
def test_connect_requires_input_and_observation_protocols(
    monkeypatch: pytest.MonkeyPatch,
    case: CapabilityCase,
) -> None:
    extensions, randr_version, xtest_version, calls, message = case
    client = Client(
        extension_names=extensions,
        randr_protocol=ProtocolVersion(*randr_version),
        xtest_protocol=ProtocolVersion(*xtest_version),
    )
    capture = Capture()
    patch_connect(monkeypatch, client=client, capture=capture)

    with pytest.raises(CapabilityUnavailableError, match=message):
        _ = X11Backend.connect(":unit-test")

    assert client.connect_calls == calls
    assert client.closed
    assert not capture.closed


def test_connect_negotiates_protocols_before_native_owners(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = Client()
    capture = Capture()
    patch_connect(monkeypatch, client=client, capture=capture)

    X11Backend.connect(":unit-test").close()

    assert client.connect_calls == [
        "extensions",
        "randr-version",
        "xtest-version",
        "capture",
        "root",
    ]
    assert capture.closed
    assert client.closed


def test_output_and_clipped_window_resolve_from_the_captured_origin() -> None:
    capture = Capture()
    with DesktopRuntime(backend(Client(), capture)) as runtime:
        output = runtime.observe(OutputTarget(OutputRef("x11-output:2")))
        assert capture.rects[-1] == RootRect(80, 0, 80, 80)
        assert runtime.resolve_point(
            output.snapshot.id, SnapshotPoint(7, 11)
        ) == DesktopLayoutPoint(87, 11)

        window = runtime.observe(ActiveWindowTarget())
        assert capture.rects[-1] == RootRect(0, 20, 50, 60)
        assert runtime.resolve_point(window.snapshot.id, SnapshotPoint(0, 0)) == DesktopLayoutPoint(
            0, 20
        )
        assert runtime.resolve_point(
            window.snapshot.id, SnapshotPoint(49, 59)
        ) == DesktopLayoutPoint(49, 79)
        assert output.snapshot.captured_at <= window.snapshot.captured_at
        with pytest.raises(ValueError, match="outside"):
            _ = runtime.resolve_point(window.snapshot.id, SnapshotPoint(50, 0))


@pytest.mark.parametrize("change", ["root", "outputs"])
def test_layout_change_invalidates_without_another_observation(
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    client, capture, replacement = Client(), Capture(), Capture()

    def create_capture(*, display: str) -> X11Capture:
        assert display == ":unit-test"
        return cast("X11Capture", cast("object", replacement))

    monkeypatch.setattr("mint_computer_mcp.native.x11.backend.X11Capture", create_capture)
    with DesktopRuntime(backend(client, capture)) as runtime:
        observation = runtime.observe(DesktopTarget())
        if change == "root":
            client.root = RootRect(0, 0, 200, 100)
        else:
            client.outputs = client.outputs[:1]
        with pytest.raises(StaleSnapshotError, match="old display layout"):
            _ = runtime.resolve_point(observation.snapshot.id, SnapshotPoint(0, 0))
        assert capture.closed
        current = runtime.observe(DesktopTarget())
        assert current.snapshot.display_generation == observation.snapshot.display_generation + 1
    assert replacement.closed


def test_unavailable_targets_do_not_capture_pixels() -> None:
    client, capture = Client(active=None), Capture()
    with DesktopRuntime(backend(client, capture)) as runtime:
        with pytest.raises(TargetUnavailableError, match="no capturable"):
            _ = runtime.observe(ActiveWindowTarget())
        with pytest.raises(TargetUnavailableError, match="no longer available"):
            _ = runtime.observe(OutputTarget(OutputRef("x11-output:missing")))
        client.active = RootRect(200, 0, 20, 20)
        with pytest.raises(TargetUnavailableError, match="outside"):
            _ = runtime.observe(ActiveWindowTarget())
        assert capture.rects == []


def test_desktop_without_outputs_uses_current_root() -> None:
    capture = Capture()
    client = Client(root=RootRect(0, 0, 120, 100), outputs=())
    with DesktopRuntime(backend(client, capture)) as runtime:
        _ = runtime.observe(DesktopTarget())
        assert capture.rects == [client.root]


def test_pointer_input_uses_root_coordinates_when_generation_matches() -> None:
    input_ = Input()

    with backend(Client(), Capture(), input_) as x11_backend:
        x11_backend.move_pointer(
            DesktopLayoutPoint(x=-20, y=30),
            expected_display_generation=0,
        )
        x11_backend.click(
            DesktopLayoutPoint(x=40, y=50),
            PointerButton.RIGHT,
            expected_display_generation=0,
        )

    assert input_.moves == [RootPoint(x=-20, y=30)]
    assert input_.clicks == [(RootPoint(x=40, y=50), PointerButton.RIGHT)]


def test_pointer_input_rejects_generation_changed_during_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = Client()
    capture = Capture()
    replacement = Capture()
    input_ = Input()

    def create_capture(*, display: str) -> X11Capture:
        assert display == ":unit-test"
        return cast("X11Capture", cast("object", replacement))

    monkeypatch.setattr("mint_computer_mcp.native.x11.backend.X11Capture", create_capture)

    with backend(client, capture, input_) as x11_backend:
        assert x11_backend.display_generation == 0
        client.root = RootRect(0, 0, 200, 100)

        with pytest.raises(
            DisplayGenerationMismatchError,
            match="expected=0, actual=1",
        ):
            x11_backend.move_pointer(
                DesktopLayoutPoint(x=10, y=20),
                expected_display_generation=0,
            )

    assert input_.moves == []
    assert capture.closed
    assert replacement.closed


def test_backend_closes_native_owners_in_dependency_order() -> None:
    close_order: list[str] = []
    client = Client(close_order=close_order)
    capture = Capture(close_order=close_order)
    input_ = Input(close_order=close_order)

    backend(client, capture, input_).close()

    assert close_order == ["input", "capture", "client"]
