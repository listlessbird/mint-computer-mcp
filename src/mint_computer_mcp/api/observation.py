"""Validated external observation targets and result metadata."""

from typing import Annotated, Literal, assert_never

from pydantic import Field

from mint_computer_mcp.api.model import ApiModel
from mint_computer_mcp.domain.identifiers import (
    OutputRef,
    SnapshotId,
    WindowRef,
)
from mint_computer_mcp.domain.observation import (
    ActiveWindowTarget,
    DesktopTarget,
    Observation,
    ObservationTarget,
    OutputTarget,
)


class DesktopObservationTarget(ApiModel):
    """Observe the complete visible desktop."""

    kind: Literal["desktop"]


class ActiveWindowObservationTarget(ApiModel):
    """Observe the visible active window."""

    kind: Literal["active_window"]


class OutputObservationTarget(ApiModel):
    """Observe one desktop output."""

    kind: Literal["output"]
    output: OutputRef


DesktopObserveTarget = Annotated[
    DesktopObservationTarget | ActiveWindowObservationTarget | OutputObservationTarget,
    Field(discriminator="kind"),
]


def to_domain_target(target: DesktopObserveTarget) -> ObservationTarget:
    """Translate an external observation target into the domain union."""
    match target:
        case DesktopObservationTarget():
            return DesktopTarget()

        case ActiveWindowObservationTarget():
            return ActiveWindowTarget()

        case OutputObservationTarget(output=output):
            return OutputTarget(output=output)

        case _:
            assert_never(target)


PositiveDimension = Annotated[int, Field(gt=0)]


class ImageSize(ApiModel):
    """Pixel dimensions."""

    width: PositiveDimension
    height: PositiveDimension


class LayoutRect(ApiModel):
    """Rectangle in the backend-neutral desktop layout."""

    x: int
    y: int
    width: PositiveDimension
    height: PositiveDimension


class OutputMetadata(ApiModel):
    """Visible desktop output metadata."""

    ref: OutputRef
    name: str
    layout: LayoutRect
    primary: bool


class WindowMetadata(ApiModel):
    """Observed active-window metadata."""

    ref: WindowRef
    title: str | None
    layout: LayoutRect


class ObserveMetadata(ApiModel):
    """Structured metadata accompanying one JPEG observation."""

    snapshot_id: SnapshotId
    target: DesktopObserveTarget
    source_size: ImageSize
    encoded_size: ImageSize
    outputs: tuple[OutputMetadata, ...]
    active_window: WindowMetadata | None


def _size(width: int, height: int) -> ImageSize:
    return ImageSize(
        width=width,
        height=height,
    )


def _layout_rect(
    x: int,
    y: int,
    width: int,
    height: int,
) -> LayoutRect:
    return LayoutRect(
        x=x,
        y=y,
        width=width,
        height=height,
    )


def _from_domain_target(
    target: ObservationTarget,
) -> DesktopObserveTarget:
    match target:
        case DesktopTarget():
            return DesktopObservationTarget(kind="desktop")

        case ActiveWindowTarget():
            return ActiveWindowObservationTarget(kind="active_window")

        case OutputTarget(output=output):
            return OutputObservationTarget(
                kind="output",
                output=output,
            )

        case _:
            assert_never(target)


def from_domain_observation(
    observation: Observation,
) -> ObserveMetadata:
    """Translate runtime observation metadata for external transport."""
    snapshot = observation.snapshot
    state = observation.state

    return ObserveMetadata(
        snapshot_id=snapshot.id,
        target=_from_domain_target(observation.target),
        source_size=_size(
            snapshot.source_size.width,
            snapshot.source_size.height,
        ),
        encoded_size=_size(
            snapshot.encoded_size.width,
            snapshot.encoded_size.height,
        ),
        outputs=tuple(
            OutputMetadata(
                ref=output.ref,
                name=output.name,
                layout=_layout_rect(
                    output.layout.x,
                    output.layout.y,
                    output.layout.width,
                    output.layout.height,
                ),
                primary=output.primary,
            )
            for output in state.outputs
        ),
        active_window=(
            None
            if state.active_window is None
            else WindowMetadata(
                ref=state.active_window.ref,
                title=state.active_window.title,
                layout=_layout_rect(
                    state.active_window.layout.x,
                    state.active_window.layout.y,
                    state.active_window.layout.width,
                    state.active_window.layout.height,
                ),
            )
        ),
    )
