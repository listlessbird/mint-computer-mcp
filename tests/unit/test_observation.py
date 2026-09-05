import pytest

from mint_computer_mcp.domain.observation import DesktopLayoutRect


@pytest.mark.parametrize(
    ("width", "height"),
    [
        (0, 1),
        (1, 0),
        (-1, 1),
        (1, -1),
    ],
)
def test_desktop_layout_rect_requires_positive_size(width: int, height: int) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        _ = DesktopLayoutRect(
            x=-100,
            y=-100,
            width=width,
            height=height,
        )


def test_desktop_layout_rect_allows_negative_origins() -> None:
    assert (
        DesktopLayoutRect(
            x=-1920,
            y=-200,
            width=1920,
            height=1080,
        ).x
        == -1920
    )
