from io import BytesIO
from typing import TYPE_CHECKING

import pytest
from PIL import Image

from mint_computer_mcp.backend import PixelFormat, PixelFrame
from mint_computer_mcp.domain.geometry import Size
from mint_computer_mcp.image import JpegEncoder

if TYPE_CHECKING:
    from mint_computer_mcp.domain.observation import JpegImage


@pytest.mark.parametrize("padding", [0, 12])
def test_encodes_bgrx_colors_and_row_stride(padding: int) -> None:
    # Large color blocks keep JPEG chroma subsampling away from sampled pixels.
    row = bytes((0, 0, 255, 0)) * 16 + bytes((255, 0, 0, 0)) * 16 + bytes(padding)
    with JpegEncoder() as encoder:
        result = encoder.encode(
            PixelFrame(
                data=memoryview(row * 16),
                size=Size(32, 16),
                stride=len(row),
                format=PixelFormat.BGRX,
            )
        )
    with Image.open(BytesIO(result.data)) as decoded:
        assert decoded.size == (32, 16)
        assert decoded.format == "JPEG"
        rgb = decoded.tobytes()
        for x, expected in [(8, (255, 0, 0)), (24, (0, 0, 255))]:
            offset = (8 * 32 + x) * 3
            actual = rgb[offset : offset + 3]
            assert all(abs(a - e) <= 5 for a, e in zip(actual, expected, strict=True))


@pytest.mark.parametrize("quality", [0, 96])
def test_rejects_invalid_jpeg_quality(quality: int) -> None:
    with pytest.raises(ValueError, match="JPEG quality"):
        _ = JpegEncoder(quality=quality)


def test_encoder_overwrites_pixels_and_replaces_buffer_on_resize() -> None:
    with JpegEncoder() as encoder:
        images: list[JpegImage] = []
        for size, color in [
            (Size(16, 16), (0, 0, 255, 0)),
            (Size(16, 16), (255, 0, 0, 0)),
            (Size(32, 8), (0, 255, 0, 0)),
        ]:
            frame = PixelFrame(
                memoryview(bytes(color) * (size.width * size.height)),
                size,
                size.width * 4,
                PixelFormat.BGRX,
            )
            images.append(encoder.encode(frame))
    for encoded, expected in zip(images, [(255, 0, 0), (0, 0, 255), (0, 255, 0)], strict=True):
        with Image.open(BytesIO(encoded.data)) as decoded:
            assert decoded.size == (encoded.size.width, encoded.size.height)
            assert all(
                abs(actual - wanted) <= 5
                for actual, wanted in zip(decoded.tobytes()[:3], expected, strict=True)
            )
    with pytest.raises(RuntimeError, match="closed"):
        _ = encoder.encode(frame)
