"""Exercise observation orchestration using real runtime and backend code."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

import pytest

from mint_computer_mcp.backend import PixelFormat, PixelFrame, TargetUnavailableError
from mint_computer_mcp.domain.geometry import DesktopLayoutPoint, RootRect, Size, SnapshotPoint
from mint_computer_mcp.domain.identifiers import OutputRef, RandrOutputId, WindowId
from mint_computer_mcp.domain.observation import (
    ActiveWindowTarget,
    DesktopTarget,
    OutputTarget,
)
from mint_computer_mcp.domain.x11 import ProtocolVersion, RandrOutput
from mint_computer_mcp.native.x11.backend import X11Backend
from mint_computer_mcp.native.x11.capture import X11Capture

if TYPE_CHECKING:
    from mint_computer_mcp.native.x11.client import X11Client
from mint_computer_mcp.runtime import DesktopRuntime, StaleSnapshotError


@dataclass(slots=True)
class Client:
    root: RootRect = field(default_factory=lambda: RootRect(0, 0, 160, 80))
    outputs: tuple[RandrOutput, ...] = (
        RandrOutput(RandrOutputId(1), "left", RootRect(0, 0, 80, 80), primary=True),
        RandrOutput(RandrOutputId(2), "right", RootRect(80, 0, 80, 80), primary=False),
    )
    active: RootRect | None = field(default_factory=lambda: RootRect(-10, 20, 60, 80))

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
        pass


@dataclass(slots=True)
class Capture:
    rects: list[RootRect] = field(default_factory=list)
    closed: bool = False

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


def backend(client: Client, capture: Capture) -> X11Backend:
    # Substitute only the native boundaries; orchestration and coordinate mapping are real.
    return X11Backend(
        display=":unit-test",
        client=cast("X11Client", cast("object", client)),
        capture=cast("X11Capture", cast("object", capture)),
        root=WindowId(1),
        randr_version=ProtocolVersion(1, 3),
    )


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
