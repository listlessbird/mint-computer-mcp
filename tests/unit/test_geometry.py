import pytest
from hypothesis import given
from hypothesis import strategies as st

from mint_computer_mcp.domain.geometry import (
    RootPoint,
    RootRect,
    Size,
    SnapshotPoint,
    SnapshotRect,
    snapshot_to_root,
)


@pytest.mark.parametrize(("width", "height"), [(0, 1), (1, 0), (-1, 1), (1, -1)])
def test_rejects_nonpositive_dimensions(width: int, height: int) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        _ = Size(width, height)
    with pytest.raises(ValueError, match="must be positive"):
        _ = RootRect(0, 0, width, height)
    with pytest.raises(ValueError, match="must be positive"):
        _ = SnapshotRect(0, 0, width, height)


@given(
    capture=st.builds(
        RootRect,
        x=st.integers(-10_000, 10_000),
        y=st.integers(-10_000, 10_000),
        width=st.integers(1, 8_000),
        height=st.integers(1, 8_000),
    ),
    encoded=st.builds(
        Size,
        width=st.integers(1, 4_000),
        height=st.integers(1, 4_000),
    ),
    data=st.data(),
)
def test_conversion_bounds_and_origin(
    capture: RootRect,
    encoded: Size,
    data: st.DataObject,
) -> None:
    root_x, root_y = capture.x, capture.y
    width, height = capture.width, capture.height
    encoded_width, encoded_height = encoded.width, encoded.height
    origin = snapshot_to_root(SnapshotPoint(0, 0), capture=capture, encoded_size=encoded)
    assert origin == RootPoint(root_x, root_y)
    point = SnapshotPoint(
        data.draw(st.integers(0, encoded_width - 1)),
        data.draw(st.integers(0, encoded_height - 1)),
    )
    result = snapshot_to_root(point, capture=capture, encoded_size=encoded)
    assert root_x <= result.x < root_x + width
    assert root_y <= result.y < root_y + height
    corner = snapshot_to_root(
        SnapshotPoint(encoded_width - 1, encoded_height - 1),
        capture=capture,
        encoded_size=encoded,
    )
    assert result.x <= corner.x < root_x + width
    assert result.y <= corner.y < root_y + height
    assert root_x + width - 1 - corner.x <= (width - 1) // encoded_width
    assert root_y + height - 1 - corner.y <= (height - 1) // encoded_height
    identity = snapshot_to_root(
        point, capture=RootRect(root_x, root_y, encoded_width, encoded_height), encoded_size=encoded
    )
    assert identity == RootPoint(root_x + point.x, root_y + point.y)


@pytest.mark.parametrize(
    "point", [SnapshotPoint(-1, 0), SnapshotPoint(0, -1), SnapshotPoint(4, 0), SnapshotPoint(0, 4)]
)
def test_rejects_points_outside_snapshot(point: SnapshotPoint) -> None:
    with pytest.raises(ValueError, match="outside the encoded image"):
        _ = snapshot_to_root(point, capture=RootRect(-10, -10, 3, 3), encoded_size=Size(4, 4))


def test_floor_scaling_at_edges_and_large_coordinates() -> None:
    assert snapshot_to_root(
        SnapshotPoint(3, 3), capture=RootRect(-1, -1, 3, 3), encoded_size=Size(4, 4)
    ) == RootPoint(1, 1)
    large = 2**60
    assert snapshot_to_root(
        SnapshotPoint(large - 1, 0), capture=RootRect(0, -2, large, 1), encoded_size=Size(large, 1)
    ) == RootPoint(large - 1, -2)
    assert snapshot_to_root(
        SnapshotPoint(0, 0), capture=RootRect(-3, -2, 10, 10), encoded_size=Size(1, 1)
    ) == RootPoint(-3, -2)
