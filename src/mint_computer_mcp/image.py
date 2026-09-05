"""Image encoding for backend pixel frames."""

from io import BytesIO

from PIL import Image

from mint_computer_mcp.backend import PixelFormat, PixelFrame
from mint_computer_mcp.domain.observation import JpegImage

DEFAULT_JPEG_QUALITY = 85
_MIN_JPEG_QUALITY = 20
_MAX_JPEG_QUALITY = 95


def encode_jpeg(
    frame: PixelFrame,
    *,
    quality: int = DEFAULT_JPEG_QUALITY,
) -> JpegImage:
    """Decode BGRX into Pillow's RGB storage, then encode it as JPEG."""
    if not _MIN_JPEG_QUALITY <= quality <= _MAX_JPEG_QUALITY:
        msg = f"JPEG quality must be between {_MIN_JPEG_QUALITY} and {_MAX_JPEG_QUALITY}"
        raise ValueError(msg)

    match frame.format:
        case PixelFormat.BGRX:
            raw_mode = "BGRX"

    output = BytesIO()

    with Image.frombytes(
        "RGB",
        (frame.size.width, frame.size.height),
        frame.data,
        "raw",
        raw_mode,
        frame.stride,
        1,
    ) as image:
        image.save(
            output,
            format="JPEG",
            quality=quality,
        )

    return JpegImage(
        size=frame.size,
        data=output.getvalue(),
    )
