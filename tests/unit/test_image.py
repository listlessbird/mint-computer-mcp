from io import BytesIO

import pytest
from PIL import Image

from mint_computer_mcp.backend import PixelFormat, PixelFrame
from mint_computer_mcp.domain.geometry import Size
from mint_computer_mcp.image import encode_jpeg


@pytest.mark.parametrize("padding", [0, 12])
def test_encodes_bgrx_colors_and_row_stride(padding: int) -> None:
    # Large color blocks keep JPEG chroma subsampling away from sampled pixels.
    row = bytes((0, 0, 255, 0)) * 16 + bytes((255, 0, 0, 0)) * 16 + bytes(padding)
    result = encode_jpeg(
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
    frame = PixelFrame(
        data=memoryview(bytearray(4)),
        size=Size(width=1, height=1),
        stride=4,
        format=PixelFormat.BGRX,
    )

    with pytest.raises(ValueError, match="JPEG quality"):
        _ = encode_jpeg(frame, quality=quality)
