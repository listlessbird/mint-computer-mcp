"""X11 pixel capture boundary."""

from types import TracebackType
from typing import Self, final

from mss import MSS, ScreenShotError

from mint_computer_mcp.backend import BackendError, PixelFormat, PixelFrame
from mint_computer_mcp.domain.geometry import RootRect, Size


class X11CaptureError(BackendError):
    """Raised when X11 pixel capture fails."""


@final
class X11Capture:
    """Persistent MSS capture resources for one X11 display."""

    def __init__(self, *, display: str) -> None:
        """Open a persistent X11 screenshot backend."""
        self._mss = MSS(
            display=display,
            backend="xshmgetimage",
            with_cursor=False,
        )

    @property
    def performance_status(self) -> tuple[str, ...]:
        """Return MSS backend performance diagnostics."""
        return tuple(self._mss.performance_status)

    def capture_rect(self, rect: RootRect) -> PixelFrame:
        """Capture visible composited pixels inside one root-space rectangle."""
        try:
            shot = self._mss.grab(
                (
                    rect.x,
                    rect.y,
                    rect.x + rect.width,
                    rect.y + rect.height,
                )
            )
        except ScreenShotError as exc:
            msg = f"X11 capture failed for {rect!r}: {exc}"
            raise X11CaptureError(msg) from exc

        size = Size(
            width=int(shot.width),
            height=int(shot.height),
        )
        expected = Size(
            width=rect.width,
            height=rect.height,
        )

        if size != expected:
            msg = f"X11 capture returned {size!r}, expected {expected!r}"
            raise X11CaptureError(msg)

        return PixelFrame(
            data=memoryview(shot.raw),
            size=size,
            stride=size.width * 4,
            format=PixelFormat.BGRX,
        )

    def close(self) -> None:
        """Release MSS-owned native resources."""
        self._mss.close()

    def __enter__(self) -> Self:
        """Return this capture object for scoped ownership."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close capture resources."""
        self.close()
