import pytest
from pydantic import TypeAdapter, ValidationError

from mint_computer_mcp.api.observation import (
    ActiveWindowObservationTarget,
    DesktopObservationTarget,
    DesktopObserveTarget,
    LayoutRect,
    OutputObservationTarget,
    from_domain_observation,
    to_domain_target,
)
from mint_computer_mcp.domain.geometry import DesktopLayoutRect, Size
from mint_computer_mcp.domain.identifiers import OutputRef, SnapshotId
from mint_computer_mcp.domain.observation import (
    ActiveWindowTarget,
    DesktopState,
    DesktopTarget,
    JpegImage,
    Observation,
    OutputInfo,
    OutputTarget,
    Snapshot,
)

target_adapter = TypeAdapter[DesktopObserveTarget](DesktopObserveTarget)


@pytest.mark.parametrize(
    ("payload", "target_type"),
    [
        ({"kind": "desktop"}, DesktopObservationTarget),
        ({"kind": "active_window"}, ActiveWindowObservationTarget),
        (
            {"kind": "output", "output": "x11-output:1"},
            OutputObservationTarget,
        ),
    ],
)
def test_all_observation_target_variants_validate(
    payload: dict[str, object],
    target_type: type[object],
) -> None:
    target = target_adapter.validate_python(payload)

    assert type(target) is target_type


def test_unknown_observation_target_kind_fails() -> None:
    with pytest.raises(ValidationError) as error:
        _ = target_adapter.validate_python({"kind": "unknown"})

    assert "union_tag_invalid" in {item["type"] for item in error.value.errors()}


def test_observation_target_extra_fields_fail() -> None:
    with pytest.raises(ValidationError) as error:
        _ = target_adapter.validate_python({"kind": "desktop", "typo": True})

    assert "extra_forbidden" in {item["type"] for item in error.value.errors()}


@pytest.mark.parametrize(
    ("payload", "error_type"),
    [
        ({"kind": "output", "output": 1}, "string_type"),
        ({"kind": "output", "output": True}, "string_type"),
        ({"kind": "output", "output": 1.0}, "string_type"),
    ],
)
def test_observation_target_rejects_string_coercion(
    payload: dict[str, object],
    error_type: str,
) -> None:
    with pytest.raises(ValidationError) as error:
        _ = target_adapter.validate_python(payload)

    assert error_type in {item["type"] for item in error.value.errors()}


def test_observation_target_requires_output() -> None:
    with pytest.raises(ValidationError) as error:
        _ = target_adapter.validate_python({"kind": "output"})

    assert "missing" in {item["type"] for item in error.value.errors()}


@pytest.mark.parametrize(
    ("api_target", "expected"),
    [
        (DesktopObservationTarget(kind="desktop"), DesktopTarget()),
        (ActiveWindowObservationTarget(kind="active_window"), ActiveWindowTarget()),
        (
            OutputObservationTarget(kind="output", output=OutputRef("x11-output:1")),
            OutputTarget(output=OutputRef("x11-output:1")),
        ),
    ],
)
def test_observation_target_conversion_produces_domain_types(
    api_target: DesktopObserveTarget,
    expected: DesktopTarget | ActiveWindowTarget | OutputTarget,
) -> None:
    converted = to_domain_target(api_target)

    assert type(converted) is type(expected)
    assert converted == expected


def test_observation_api_rejects_string_to_integer_coercion() -> None:
    with pytest.raises(ValidationError) as error:
        _ = LayoutRect.model_validate({"x": "1", "y": 2, "width": 3, "height": 4})

    assert error.value.errors()[0]["type"] == "int_type"


def test_observation_conversion_preserves_negative_output_coordinates() -> None:
    output_layout = DesktopLayoutRect(
        x=-1920,
        y=-120,
        width=1920,
        height=1080,
    )
    observation = Observation(
        target=OutputTarget(output=OutputRef("x11-output:1")),
        snapshot=Snapshot(
            id=SnapshotId("snapshot-1"),
            captured_at=1.0,
            source_size=Size(width=1920, height=1080),
            encoded_size=Size(width=960, height=540),
            display_generation=1,
        ),
        image=JpegImage(
            size=Size(width=960, height=540),
            data=b"jpeg",
        ),
        state=DesktopState(
            outputs=(
                OutputInfo(
                    ref=OutputRef("x11-output:1"),
                    name="HDMI-1",
                    layout=output_layout,
                    primary=True,
                ),
            ),
            active_window=None,
        ),
    )

    metadata = from_domain_observation(observation)

    assert metadata.outputs[0].layout == LayoutRect(
        x=-1920,
        y=-120,
        width=1920,
        height=1080,
    )
