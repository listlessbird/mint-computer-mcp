"""X11 implementation of the desktop backend contract."""

from contextlib import ExitStack
from dataclasses import dataclass
from types import TracebackType
from typing import Self, final

from mint_computer_mcp.backend import (
    BackendCapture,
    BackendError,
    CapabilityUnavailableError,
    TargetUnavailableError,
)
from mint_computer_mcp.domain.geometry import (
    DesktopLayoutPoint,
    DesktopLayoutRect,
    RootRect,
    Size,
    SnapshotPoint,
    bounding_root_rect,
    intersect_root_rect,
    snapshot_to_root,
)
from mint_computer_mcp.domain.identifiers import OutputRef, WindowId, WindowRef
from mint_computer_mcp.domain.input import KeyName, PointerButton
from mint_computer_mcp.domain.observation import (
    ActiveWindowTarget,
    DesktopState,
    DesktopTarget,
    ObservationTarget,
    OutputInfo,
    OutputTarget,
    WindowInfo,
)
from mint_computer_mcp.domain.x11 import ProtocolVersion, RandrOutput
from mint_computer_mcp.native.x11.capture import X11Capture
from mint_computer_mcp.native.x11.client import X11Client


@dataclass(frozen=True, slots=True)
class X11SnapshotState:
    """X11-native coordinate state for a snapshot."""

    capture_rect: RootRect


@dataclass(frozen=True, slots=True)
class _DisplaySignature:
    """X11 layout values whose change invalidates spatial snapshots."""

    root: RootRect
    outputs: tuple[RandrOutput, ...]


@dataclass(frozen=True, slots=True)
class _ActiveWindow:
    """One active X11 window and its native geometry."""

    info: WindowInfo
    rect: RootRect


_X11_INPUT_UNAVAILABLE_MESSAGE = "X11 input injection is not implemented"


@final
class X11Backend:
    """Persistent X11 observation backend."""

    def __init__(
        self,
        *,
        display: str,
        client: X11Client,
        capture: X11Capture,
        root: WindowId,
        randr_version: ProtocolVersion,
    ) -> None:
        """X11 native resources."""
        self._display = display
        self._client = client
        self._capture = capture
        self._root = root
        self._randr_version = randr_version

        self._display_generation = 0
        self._signature: _DisplaySignature | None = None
        self._native_outputs: tuple[RandrOutput, ...] = ()
        self._closed = False

    @classmethod
    def connect(cls, display: str) -> Self:
        """Connect persistent X11 metadata and pixel-capture resources."""
        with ExitStack() as stack:
            client = stack.enter_context(X11Client.connect(display))

            extensions = client.extensions()

            if "RANDR" not in extensions:
                msg = "X11 RANDR is required for desktop observation"
                raise CapabilityUnavailableError(msg)

            randr_version = client.randr_version()

            if (randr_version.major, randr_version.minor) < (1, 2):
                msg = (
                    "X11 RANDR 1.2 or newer is required for output observation; "
                    f"server provides {randr_version.major}.{randr_version.minor}"
                )
                raise CapabilityUnavailableError(msg)

            capture = stack.enter_context(X11Capture(display=display))
            root = client.root_window()

            backend = cls(
                display=display,
                client=client,
                capture=capture,
                root=root,
                randr_version=randr_version,
            )
            backend._refresh_layout()

            _ = stack.pop_all()

            return backend

    @property
    def display_generation(self) -> int:
        """Return the current X11 display-layout generation."""
        self._ensure_open()
        self._refresh_layout()
        return self._display_generation

    def resolve_point(
        self, state: X11SnapshotState, point: SnapshotPoint, encoded_size: Size
    ) -> DesktopLayoutPoint:
        """Translate captured image coordinates into the X11 desktop layout."""
        self._ensure_open()
        root = snapshot_to_root(point, capture=state.capture_rect, encoded_size=encoded_size)
        return DesktopLayoutPoint(x=root.x, y=root.y)

    def move_pointer(
        self,
        point: DesktopLayoutPoint,
        *,
        expected_display_generation: int,
    ) -> None:
        """Report that X11 pointer injection is not available yet."""
        self._ensure_open()
        _ = (point, expected_display_generation)
        raise CapabilityUnavailableError(_X11_INPUT_UNAVAILABLE_MESSAGE)

    def click(
        self,
        point: DesktopLayoutPoint,
        button: PointerButton,
        *,
        expected_display_generation: int,
    ) -> None:
        """Report that X11 pointer injection is not available yet."""
        self._ensure_open()
        _ = (point, button, expected_display_generation)
        raise CapabilityUnavailableError(_X11_INPUT_UNAVAILABLE_MESSAGE)

    def press_keys(self, keys: tuple[KeyName, ...]) -> None:
        """Report that X11 keyboard injection is not available yet."""
        self._ensure_open()
        _ = keys
        raise CapabilityUnavailableError(_X11_INPUT_UNAVAILABLE_MESSAGE)

    def type_text(self, text: str) -> None:
        """Report that X11 text injection is not available yet."""
        self._ensure_open()
        _ = text
        raise CapabilityUnavailableError(_X11_INPUT_UNAVAILABLE_MESSAGE)

    @property
    def capture_performance_status(self) -> tuple[str, ...]:
        """Return X11 capture-backend performance diagnostics."""
        return self._capture.performance_status

    def outputs(self) -> tuple[OutputInfo, ...]:
        """Return the current RandR outputs as neutral metadata."""
        self._ensure_open()
        self._refresh_layout()

        return tuple(self._output_info(output) for output in self._native_outputs)

    def capture(
        self,
        target: ObservationTarget,
    ) -> BackendCapture[X11SnapshotState]:
        """Capture one visible X11 desktop target."""
        self._ensure_open()
        self._refresh_layout()

        active_window = self._read_active_window()

        desktop_state = DesktopState(
            outputs=tuple(self._output_info(output) for output in self._native_outputs),
            active_window=None if active_window is None else active_window.info,
        )

        match target:
            case DesktopTarget():
                rect = self._desktop_rect()

            case ActiveWindowTarget():
                if active_window is None:
                    msg = "no capturable active X11 window is available"
                    raise TargetUnavailableError(msg)

                visible_rect = intersect_root_rect(
                    active_window.rect,
                    self._desktop_rect(),
                )

                if visible_rect is None:
                    msg = "the active X11 window is outside the visible desktop"
                    raise TargetUnavailableError(msg)

                rect = visible_rect

            case OutputTarget(output=output_ref):
                rect = self._output_by_ref(output_ref).geometry

        frame = self._capture.capture_rect(rect)

        return BackendCapture(
            frame=frame,
            snapshot_state=X11SnapshotState(
                capture_rect=rect,
            ),
            desktop_state=desktop_state,
            display_generation=self._display_generation,
        )

    def close(self) -> None:
        """Release X11 metadata and capture connections."""
        if self._closed:
            return

        self._closed = True

        try:
            self._capture.close()
        finally:
            self._client.close()

    def __enter__(self) -> Self:
        """Return this backend for scoped ownership."""
        self._ensure_open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close backend resources."""
        self.close()

    def _ensure_open(self) -> None:
        """Reject use after close."""
        if self._closed:
            msg = "X11 backend is closed"
            raise BackendError(msg)

    def _refresh_layout(self) -> None:
        """Refresh RandR layout and invalidate spatial generation on change."""
        root = self._client.root_rect()
        outputs = self._client.randr_outputs(
            root=self._root,
            version=self._randr_version,
        )

        signature = _DisplaySignature(
            root=root,
            outputs=outputs,
        )

        if self._signature is None:
            self._signature = signature
            self._native_outputs = outputs
            return

        if signature == self._signature:
            return

        replacement_capture = X11Capture(display=self._display)
        previous_capture = self._capture

        self._capture = replacement_capture
        self._signature = signature
        self._native_outputs = outputs
        self._display_generation += 1

        previous_capture.close()

    def _desktop_rect(self) -> RootRect:
        """Return the visible X11 desktop bounding rectangle."""
        bounds = bounding_root_rect(output.geometry for output in self._native_outputs)

        if bounds is not None:
            return bounds

        if self._signature is None:
            msg = "X11 display layout has not been initialized"
            raise BackendError(msg)

        return self._signature.root

    def _output_by_ref(self, ref: OutputRef) -> RandrOutput:
        """Resolve one opaque runtime output reference."""
        for output in self._native_outputs:
            if self._output_ref(output) == ref:
                return output

        msg = f"X11 output is no longer available: {ref}"
        raise TargetUnavailableError(msg)

    def _read_active_window(self) -> _ActiveWindow | None:
        """Read current EWMH active-window metadata and frame geometry."""
        window = self._client.active_window(root=self._root)

        if window is None:
            return None

        rect = self._client.window_frame_geometry(
            window=window,
            root=self._root,
        )

        if rect is None:
            return None

        return _ActiveWindow(
            info=WindowInfo(
                ref=WindowRef(f"x11-window:{int(window)}"),
                title=self._client.window_title(window=window),
                layout=self._layout_rect(rect),
            ),
            rect=rect,
        )

    @staticmethod
    def _output_ref(output: RandrOutput) -> OutputRef:
        """Translate a RandR resource ID into an opaque runtime reference."""
        return OutputRef(f"x11-output:{int(output.output_id)}")

    @classmethod
    def _output_info(cls, output: RandrOutput) -> OutputInfo:
        """Translate one native RandR output into backend-neutral metadata."""
        return OutputInfo(
            ref=cls._output_ref(output),
            name=output.name,
            layout=cls._layout_rect(output.geometry),
            primary=output.primary,
        )

    @staticmethod
    def _layout_rect(rect: RootRect) -> DesktopLayoutRect:
        """Translate X11 root geometry into generic layout metadata."""
        return DesktopLayoutRect(
            x=rect.x,
            y=rect.y,
            width=rect.width,
            height=rect.height,
        )
