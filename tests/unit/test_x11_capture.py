from dataclasses import dataclass, field
from typing import cast

import pytest
from mss import MSS

import mint_computer_mcp.native.x11.capture as capture_module
from mint_computer_mcp.backend import PixelFormat
from mint_computer_mcp.domain.geometry import RootRect
from mint_computer_mcp.native.x11.capture import X11Capture


@dataclass(slots=True)
class FakeShot:
    width: int
    height: int
    raw: bytearray


@dataclass(slots=True)
class FakeMSS:
    calls: list[tuple[int, int, int, int]] = field(default_factory=list)
    closed: bool = False

    @property
    def performance_status(self) -> list[str]:
        return ["fake capture"]

    def grab(self, box: tuple[int, int, int, int]) -> FakeShot:
        self.calls.append(box)
        width = box[2] - box[0]
        height = box[3] - box[1]

        return FakeShot(
            width=width,
            height=height,
            raw=bytearray(width * height * 4),
        )

    def close(self) -> None:
        self.closed = True


def test_capture_translates_root_rect_to_mss_bbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeMSS()

    def create_mss(**_: object) -> MSS:
        return cast("MSS", cast("object", fake))

    monkeypatch.setattr(capture_module, "MSS", create_mss)

    with X11Capture(display=":unit-test") as capture:
        frame = capture.capture_rect(
            RootRect(
                x=-100,
                y=50,
                width=200,
                height=100,
            )
        )

        assert fake.calls == [(-100, 50, 100, 150)]
        assert frame.size.width == 200
        assert frame.size.height == 100
        assert frame.stride == 800
        assert frame.format is PixelFormat.BGRX

    assert fake.closed
