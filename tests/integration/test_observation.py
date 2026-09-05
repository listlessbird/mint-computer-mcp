"""Integration tests for real X11 desktop observation."""

import os

import pytest

from mint_computer_mcp.domain.geometry import SnapshotPoint
from mint_computer_mcp.domain.observation import (
    ActiveWindowTarget,
    DesktopTarget,
    OutputTarget,
)
from mint_computer_mcp.native.x11.backend import (
    X11Backend,
    X11SnapshotState,
)
from mint_computer_mcp.runtime import DesktopRuntime


def _runtime() -> DesktopRuntime[X11SnapshotState]:
    display = os.environ.get("DISPLAY")

    if not display:
        pytest.fail("DISPLAY is required for X11 integration tests")

    return DesktopRuntime(
        X11Backend.connect(display),
    )


@pytest.mark.integration
def test_observes_visible_desktop_as_jpeg() -> None:
    with _runtime() as runtime:
        observation = runtime.observe(DesktopTarget())

        assert observation.image.data.startswith(b"\xff\xd8")
        assert observation.image.data.endswith(b"\xff\xd9")
        assert observation.image.size.width > 0
        assert observation.image.size.height > 0
        assert observation.state.outputs


@pytest.mark.integration
def test_observes_randr_output() -> None:
    with _runtime() as runtime:
        outputs = runtime.outputs()

        assert outputs

        observation = runtime.observe(
            OutputTarget(
                output=outputs[0].ref,
            )
        )

        assert observation.image.size.width == outputs[0].layout.width
        assert observation.image.size.height == outputs[0].layout.height


@pytest.mark.integration
def test_observes_active_window_region() -> None:
    with _runtime() as runtime:
        observation = runtime.observe(ActiveWindowTarget())

        assert observation.state.active_window is not None
        window = observation.state.active_window.layout
        outputs = observation.state.outputs
        assert outputs
        left = max(window.x, min(output.layout.x for output in outputs))
        top = max(window.y, min(output.layout.y for output in outputs))
        right = min(
            window.x + window.width,
            max(output.layout.x + output.layout.width for output in outputs),
        )
        bottom = min(
            window.y + window.height,
            max(output.layout.y + output.layout.height for output in outputs),
        )
        assert observation.image.size.width == right - left
        assert observation.image.size.height == bottom - top
        origin = runtime.resolve_point(observation.snapshot.id, SnapshotPoint(0, 0))
        assert (origin.x, origin.y) == (left, top)
