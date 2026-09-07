"""Own desktop resources and bounded observation metadata."""

import secrets
from collections import OrderedDict
from dataclasses import dataclass
from time import monotonic
from types import TracebackType
from typing import Self, assert_never, final

from mint_computer_mcp.backend import DesktopBackend, DisplayGenerationMismatchError
from mint_computer_mcp.domain.geometry import DesktopLayoutPoint, SnapshotPoint
from mint_computer_mcp.domain.identifiers import SnapshotId
from mint_computer_mcp.domain.input import Click, InputAction, MovePointer, PressKeys, TypeText
from mint_computer_mcp.domain.observation import (
    Observation,
    ObservationTarget,
    OutputInfo,
    Snapshot,
)
from mint_computer_mcp.image import DEFAULT_JPEG_QUALITY, JpegEncoder

_DEFAULT_SNAPSHOT_LIMIT = 64


class DesktopRuntimeError(RuntimeError):
    "Base runtime error."


class DesktopRuntimeClosedError(DesktopRuntimeError):
    "Raised when a closed runtime is accessed."


class StaleSnapshotError(DesktopRuntimeError):
    """Raised when metadata is unavailable or spatially stale."""


@dataclass(frozen=True, slots=True)
class _SnapshotEntry[SnapshotStateT]:
    """Retained public metadata and backend coordinate mapping."""

    snapshot: Snapshot
    backend_state: SnapshotStateT


@final
class DesktopRuntime[SnapshotStateT]:
    """Own a persistent backend and bounded snapshot coordinate metadata."""

    def __init__(
        self,
        backend: DesktopBackend[SnapshotStateT],
        *,
        snapshot_limit: int = _DEFAULT_SNAPSHOT_LIMIT,
        jpeg_quality: int = DEFAULT_JPEG_QUALITY,
    ) -> None:
        """Take ownership of a backend and configure observation retention."""
        if snapshot_limit <= 0:
            msg = "snapshot limit must be over zero"
            raise ValueError(msg)

        self._backend = backend
        self._snapshot_limit = snapshot_limit
        self._encoder = JpegEncoder(quality=jpeg_quality)
        self._snapshots: OrderedDict[SnapshotId, _SnapshotEntry[SnapshotStateT]] = OrderedDict()
        self._closed = False

    def outputs(self) -> tuple[OutputInfo, ...]:
        """Return backend's current desktop outputs."""
        self._ensure_open()
        return self._backend.outputs()

    def observe(self, target: ObservationTarget) -> Observation:
        """Capture, encode, and register one desktop observation."""
        self._ensure_open()

        captured_at = monotonic()
        capture = self._backend.capture(target)

        image = self._encoder.encode(capture.frame)

        snapshot = Snapshot(
            id=SnapshotId(f"snap_{secrets.token_urlsafe(18)}"),
            captured_at=captured_at,
            source_size=capture.frame.size,
            encoded_size=image.size,
            display_generation=capture.display_generation,
        )

        self._store_snapshot(
            snapshot,
            capture.snapshot_state,
        )

        return Observation(
            target=target,
            snapshot=snapshot,
            image=image,
            state=capture.desktop_state,
        )

    def snapshot(self, snapshot_id: SnapshotId) -> Snapshot:
        """Return current snapshot metadata or report it as stale."""
        return self._snapshot_entry(snapshot_id).snapshot

    def resolve_point(self, snapshot_id: SnapshotId, point: SnapshotPoint) -> DesktopLayoutPoint:
        """Resolve a snapshot pixel after validating its display layout."""
        resolved, _ = self._resolve_action_point(snapshot_id, point)
        return resolved

    def _snapshot_entry(self, snapshot_id: SnapshotId) -> _SnapshotEntry[SnapshotStateT]:
        """Look up retained coordinate state and reject obsolete display layouts."""
        self._ensure_open()

        entry = self._snapshots.get(snapshot_id)

        if entry is None:
            msg = f"snapshot is unknown or expired: {snapshot_id}"
            raise StaleSnapshotError(msg)

        if entry.snapshot.display_generation != self._backend.display_generation:
            self._snapshots.clear()
            msg = f"snapshot belongs to an old display layout: {snapshot_id}"
            raise StaleSnapshotError(msg)

        return entry

    def close(self) -> None:
        """Release backend resources and retained snapshot metadata."""
        if self._closed:
            return

        self._closed = True
        self._snapshots.clear()
        try:
            self._encoder.close()
        finally:
            self._backend.close()

    def __enter__(self) -> Self:
        """Return this runtime for scoped ownership."""
        self._ensure_open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close runtime-owned native resources."""
        self.close()

    def _store_snapshot(
        self,
        snapshot: Snapshot,
        backend_state: SnapshotStateT,
    ) -> None:
        """Retain only bounded snapshot metadata and backend coordinate state."""
        self._snapshots[snapshot.id] = _SnapshotEntry(
            snapshot=snapshot,
            backend_state=backend_state,
        )

        while len(self._snapshots) > self._snapshot_limit:
            _ = self._snapshots.popitem(last=False)

    def _ensure_open(self) -> None:
        """Reject operations after close."""
        if self._closed:
            msg = "desktop runtime is closed"
            raise DesktopRuntimeClosedError(msg)

    def _resolve_action_point(
        self, snapshot_id: SnapshotId, point: SnapshotPoint
    ) -> tuple[DesktopLayoutPoint, int]:
        entry = self._snapshot_entry(snapshot_id)

        resolved = self._backend.resolve_point(
            entry.backend_state, point, entry.snapshot.encoded_size
        )

        return resolved, entry.snapshot.display_generation

    def act(self, action: InputAction) -> None:
        """Handle an action."""
        self._ensure_open()

        match action:
            case MovePointer(snapshot_id=snapshot_id, point=point):
                resolved, generation = self._resolve_action_point(
                    snapshot_id,
                    point,
                )

                try:
                    self._backend.move_pointer(
                        resolved,
                        expected_display_generation=generation,
                    )
                except DisplayGenerationMismatchError as exc:
                    self._snapshots.clear()
                    msg = f"snapshot became stale before pointer movement: {snapshot_id}"
                    raise StaleSnapshotError(msg) from exc

            case Click(
                snapshot_id=snapshot_id,
                point=point,
                button=button,
            ):
                resolved, generation = self._resolve_action_point(
                    snapshot_id,
                    point,
                )

                try:
                    self._backend.click(
                        resolved,
                        button,
                        expected_display_generation=generation,
                    )
                except DisplayGenerationMismatchError as exc:
                    self._snapshots.clear()
                    msg = f"snapshot became stale before click: {snapshot_id}"
                    raise StaleSnapshotError(msg) from exc

            case TypeText(text=text):
                self._backend.type_text(text)

            case PressKeys(keys=keys):
                self._backend.press_keys(keys)

            case _:
                assert_never(action)
