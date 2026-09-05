"""JPEG encoding with one reusable decode buffer."""

from io import BytesIO
from types import TracebackType
from typing import Self, final

from PIL import Image

from mint_computer_mcp.backend import PixelFormat, PixelFrame
from mint_computer_mcp.domain.observation import JpegImage

DEFAULT_JPEG_QUALITY = 85
_MIN_JPEG_QUALITY = 20
_MAX_JPEG_QUALITY = 95


@final
class JpegEncoder:
    """Reuse one RGB buffer; encoded results own their bytes independently."""

    def __init__(self, *, quality: int = DEFAULT_JPEG_QUALITY) -> None:
        """Configure encoding quality; allocate pixels only on the first frame."""
        if not _MIN_JPEG_QUALITY <= quality <= _MAX_JPEG_QUALITY:
            msg = f"JPEG quality must be between {_MIN_JPEG_QUALITY} and {_MAX_JPEG_QUALITY}"
            raise ValueError(msg)
        self._quality = quality
        self._image: Image.Image | None = None
        self._closed = False

    def encode(self, frame: PixelFrame) -> JpegImage:
        """Overwrite the decode buffer completely, then encode it as JPEG."""
        if self._closed:
            msg = "JPEG encoder is closed"
            raise RuntimeError(msg)

        size = (frame.size.width, frame.size.height)
        if self._image is None or self._image.size != size:
            if self._image is not None:
                self._image.close()
                self._image = None
            # The raw decoder writes every pixel, so no initial fill is needed.
            self._image = Image.new("RGB", size, color=None)

        match frame.format:
            case PixelFormat.BGRX:
                raw_mode = "BGRX"

        self._image.frombytes(frame.data, "raw", raw_mode, frame.stride, 1)
        with BytesIO() as output:
            self._image.save(output, format="JPEG", quality=self._quality)
            return JpegImage(size=frame.size, data=output.getvalue())

    def close(self) -> None:
        """Release the retained RGB buffer."""
        self._closed = True
        if self._image is not None:
            self._image.close()
            self._image = None

    def __enter__(self) -> Self:
        """Return this encoder for scoped ownership."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Release the decode buffer."""
        self.close()
