"""Narrow libxkbcommon boundary for the active X11 keyboard."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from itertools import combinations
from typing import TYPE_CHECKING, Never, Protocol, Self, cast, final
from unicodedata import category

from cffi import FFI
from xcffib.ffi import ffi as xcffib_ffi

from mint_computer_mcp.backend import (
    KeyboardStateConflictError,
    UnsupportedKeyError,
    UnsupportedTextInputError,
)
from mint_computer_mcp.domain.identifiers import X11Keycode
from mint_computer_mcp.domain.x11 import ProtocolVersion
from mint_computer_mcp.native.x11.client import X11Client, X11Error

if TYPE_CHECKING:
    from collections.abc import Generator
    from types import TracebackType

    from cffi import CData

    from mint_computer_mcp.domain.input import KeyName


_RETURN = 0xFF0D
_TAB = 0xFF09
_XKB_CONTEXT_NO_FLAGS = 0
_XKB_X11_SETUP_NO_FLAGS = 0
_XKB_MIN_VERSION = (1, 0)

_LIB_XKBCOMMON = "libxkbcommon.so.0"
_LIB_XKBCOMMON_X11 = "libxkbcommon-x11.so.0"


ffi = FFI()

ffi.cdef(
    """
    typedef struct xcb_connection_t xcb_connection_t;

    struct xkb_context;
    struct xkb_keymap;
    struct xkb_state;
    struct xkb_state * xkb_state_new(struct xkb_keymap *keymap);
    uint32_t xkb_state_serialize_mods(struct xkb_state *state, int components);
    uint32_t xkb_state_serialize_layout(struct xkb_state *state, int components);
    int xkb_state_update_mask(struct xkb_state *state, uint32_t depressed, uint32_t latched, uint32_t locked, uint32_t depressed_layout, uint32_t latched_layout, uint32_t locked_layout);
    int xkb_state_update_key(struct xkb_state *state, uint32_t key, int direction);
    uint32_t xkb_state_key_get_one_sym(struct xkb_state *state, uint32_t key);
    int xkb_state_key_get_utf8(struct xkb_state *state, uint32_t key, char *buffer, size_t size);
    uint32_t xkb_state_key_get_consumed_mods2(struct xkb_state *state, uint32_t key, int mode);
    void xkb_keymap_unref(struct xkb_keymap *keymap);
    void xkb_state_unref(struct xkb_state *state);
    uint32_t xkb_keysym_from_name(const char *name, int flags);
    uint32_t xkb_keymap_min_keycode(struct xkb_keymap *keymap);
    uint32_t xkb_keymap_max_keycode(struct xkb_keymap *keymap);
    uint32_t xkb_keymap_num_layouts_for_key(struct xkb_keymap *keymap, uint32_t key);
    uint32_t xkb_keymap_num_levels_for_key(struct xkb_keymap *keymap, uint32_t key, uint32_t layout);
    int xkb_keymap_key_get_syms_by_level(struct xkb_keymap *keymap, uint32_t key, uint32_t layout, uint32_t level, const uint32_t **out);
    uint32_t xkb_state_key_get_layout(struct xkb_state *state, uint32_t key);
    struct xkb_keymap * xkb_x11_keymap_new_from_device(struct xkb_context *context, xcb_connection_t *connection, int32_t device, int flags);
    struct xkb_state * xkb_x11_state_new_from_device(struct xkb_keymap *keymap, xcb_connection_t *connection, int32_t device);

    struct xkb_context *
    xkb_context_new(int flags);

    void
    xkb_context_unref(struct xkb_context *context);

    int
    xkb_x11_setup_xkb_extension(
        xcb_connection_t *connection,
        uint16_t major_xkb_version,
        uint16_t minor_xkb_version,
        int flags,
        uint16_t *major_xkb_version_out,
        uint16_t *minor_xkb_version_out,
        uint8_t *base_event_out,
        uint8_t *base_error_out
    );

    int32_t
    xkb_x11_get_core_keyboard_device_id(
        xcb_connection_t *connection
    );
    """
)


class XkbError(X11Error):
    """Base error for XKB keyboard inspection."""


class XkbUnavailableError(XkbError):
    """Required XKB functionality is unavailable."""


class XkbClosedError(XkbError):
    """An already-closed XKB object was accessed."""


class _XkbCommonLib(Protocol):
    def xkb_state_new(self, keymap: CData) -> CData: ...

    def xkb_state_serialize_mods(self, state: CData, components: int) -> int: ...

    def xkb_state_serialize_layout(self, state: CData, components: int) -> int: ...

    def xkb_state_update_mask(  # noqa: PLR0913, PLR0917
        self,
        state: CData,
        depressed: int,
        latched: int,
        locked: int,
        depressed_layout: int,
        latched_layout: int,
        locked_layout: int,
    ) -> int: ...

    def xkb_state_update_key(self, state: CData, key: int, direction: int) -> int: ...

    def xkb_state_key_get_one_sym(self, state: CData, key: int) -> int: ...

    def xkb_state_key_get_utf8(self, state: CData, key: int, buffer: CData, size: int) -> int: ...

    def xkb_state_key_get_consumed_mods2(self, state: CData, key: int, mode: int) -> int: ...

    def xkb_keymap_unref(self, keymap: CData) -> None: ...

    def xkb_state_unref(self, state: CData) -> None: ...

    def xkb_keysym_from_name(self, name: bytes, flags: int) -> int: ...

    def xkb_keymap_min_keycode(self, keymap: CData) -> int: ...

    def xkb_keymap_max_keycode(self, keymap: CData) -> int: ...

    def xkb_keymap_num_layouts_for_key(self, keymap: CData, key: int) -> int: ...

    def xkb_keymap_num_levels_for_key(self, keymap: CData, key: int, layout: int) -> int: ...

    def xkb_keymap_key_get_syms_by_level(
        self, keymap: CData, key: int, layout: int, level: int, out: CData
    ) -> int: ...

    def xkb_state_key_get_layout(self, state: CData, key: int) -> int: ...

    def xkb_context_new(self, flags: int) -> CData:
        """Create a new xkbcommon context."""
        ...

    def xkb_context_unref(self, context: CData) -> None:
        """Release an xkbcommon context reference."""
        ...


class _XkbX11Lib(Protocol):
    def xkb_x11_keymap_new_from_device(
        self, context: CData, connection: CData, device: int, flags: int
    ) -> CData: ...

    def xkb_x11_state_new_from_device(
        self, keymap: CData, connection: CData, device: int
    ) -> CData: ...

    def xkb_x11_setup_xkb_extension(  # noqa: PLR0913, PLR0917
        self,
        connection: CData,
        major: int,
        minor: int,
        flags: int,
        major_out: CData,
        minor_out: CData,
        base_event_out: CData,
        base_error_out: CData,
    ) -> int:
        """Negotiate XKB support for an XCB connection."""
        ...

    def xkb_x11_get_core_keyboard_device_id(self, connection: CData) -> int:
        """Return the X11 core keyboard device identifier."""
        ...


@dataclass(frozen=True, slots=True)
class XkbSetup:
    """Negotiated XKB connection metadata."""

    version: ProtocolVersion
    device_id: int


def _load_libraries() -> tuple[_XkbCommonLib, _XkbX11Lib]:
    try:
        common = cast("_XkbCommonLib", ffi.dlopen(_LIB_XKBCOMMON))
        x11 = cast("_XkbX11Lib", ffi.dlopen(_LIB_XKBCOMMON_X11))
    except OSError as exc:
        msg = "libxkbcommon X11 support is unavailable"
        raise XkbUnavailableError(msg) from exc

    return common, x11


def _borrow_xcb_connection(client: X11Client) -> CData:
    """Borrow the native XCB connection owned by an X11 client."""
    connection = client._connection  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
    native = connection._conn  # noqa: SLF001

    if native is None:
        msg = "xcffib returned a null XCB connection"
        raise XkbError(msg)

    address = int(xcffib_ffi.cast("uintptr_t", native))

    if address == 0:
        msg = "xcffib returned a null XCB connection"
        raise XkbError(msg)

    return ffi.cast("xcb_connection_t *", address)


def _setup_xkb(*, library: _XkbX11Lib, connection: CData) -> ProtocolVersion:
    major_out = ffi.new("uint16_t *")
    minor_out = ffi.new("uint16_t *")

    success = library.xkb_x11_setup_xkb_extension(
        connection,
        _XKB_MIN_VERSION[0],
        _XKB_MIN_VERSION[1],
        _XKB_X11_SETUP_NO_FLAGS,
        major_out,
        minor_out,
        ffi.NULL,
        ffi.NULL,
    )

    if success != 1:
        msg = "X server does not provide usable XKB support"
        raise XkbUnavailableError(msg)

    version = ProtocolVersion(major=int(major_out[0]), minor=int(minor_out[0]))

    if (version.major, version.minor) < _XKB_MIN_VERSION:
        msg = f"XKB 1.0 or newer is required; server negotiated {version.major}.{version.minor}"
        raise XkbUnavailableError(msg)

    return version


def _core_keyboard_device(*, library: _XkbX11Lib, connection: CData) -> int:
    device_id = int(library.xkb_x11_get_core_keyboard_device_id(connection))

    if device_id < 0:
        msg = "could not resolve the X11 core keyboard device"
        raise XkbUnavailableError(msg)

    return device_id


def _new_context(library: _XkbCommonLib) -> CData:
    context = library.xkb_context_new(_XKB_CONTEXT_NO_FLAGS)

    if context == ffi.NULL:
        msg = "could not create libxkbcommon context"
        raise XkbError(msg)

    return context


@dataclass(frozen=True, slots=True)
class _KeyboardState:
    depressed_mods: int
    latched_mods: int
    locked_mods: int
    depressed_layout: int
    latched_layout: int
    locked_layout: int

    @property
    def persistent(self) -> tuple[int, int, int, int]:
        return self.latched_mods, self.locked_mods, self.latched_layout, self.locked_layout


@dataclass(frozen=True, slots=True)
class KeyStroke:
    """One literal key event and its explicitly synthesized modifiers."""

    modifiers: tuple[X11Keycode, ...]
    key: X11Keycode


@final
class XkbKeyboard:
    """Borrow one XCB connection and own its xkbcommon context."""

    def _initialize(  # noqa: PLR0913
        self,
        *,
        client: X11Client,
        common: _XkbCommonLib,
        x11: _XkbX11Lib,
        connection: CData,
        context: CData,
        setup: XkbSetup,
    ) -> None:
        """Retain borrowed connection state and take ownership of the context."""
        self._client = client
        self._common = common
        self._x11 = x11
        self._connection = connection
        self._context = context
        self._setup = setup
        self._closed = False

    def __init__(self, *, client: X11Client) -> None:
        """Inspect the core keyboard through the X11 client's connection."""
        common, x11 = _load_libraries()
        connection = _borrow_xcb_connection(client)
        version = _setup_xkb(library=x11, connection=connection)
        device_id = _core_keyboard_device(library=x11, connection=connection)
        context = _new_context(common)
        self._initialize(
            client=client,
            common=common,
            x11=x11,
            connection=connection,
            context=context,
            setup=XkbSetup(version=version, device_id=device_id),
        )

    @classmethod
    def connect(cls, client: X11Client) -> Self:
        """Create a keyboard boundary without exposing native pointers."""
        return cls(client=client)

    @property
    def protocol_version(self) -> ProtocolVersion:
        """Return the XKB protocol version negotiated with the server."""
        self._ensure_open()
        return self._setup.version

    @property
    def device_id(self) -> int:
        """Return the X11 core keyboard device identifier."""
        self._ensure_open()
        return self._setup.device_id

    @contextmanager
    def _snapshot(self) -> Generator[tuple[CData, CData]]:
        self._ensure_open()
        keymap = self._x11.xkb_x11_keymap_new_from_device(
            self._context, self._connection, self.device_id, 0
        )
        if keymap == ffi.NULL:
            msg = "could not snapshot XKB keymap"
            raise XkbError(msg)
        try:
            state = self._x11.xkb_x11_state_new_from_device(
                keymap, self._connection, self.device_id
            )
            if state == ffi.NULL:
                msg = "could not snapshot XKB state"
                raise XkbError(msg)
            try:
                yield keymap, state
            finally:
                self._common.xkb_state_unref(state)
        finally:
            self._common.xkb_keymap_unref(keymap)

    def resolve_key_names(self, names: tuple[KeyName, ...]) -> tuple[X11Keycode, ...]:
        """Resolve a chord from one fresh server snapshot without adding modifiers."""
        with self._snapshot() as (keymap, state):
            return tuple(self._resolve(keymap, state, name) for name in names)

    def _resolve(self, keymap: CData, state: CData, name: KeyName) -> X11Keycode:
        symbol = self._common.xkb_keysym_from_name(name.encode("utf-8"), 0)
        matches: list[tuple[bool, int, int]] = []
        if symbol and "\0" not in name:
            for key in self._keycodes(keymap):
                active = self._common.xkb_state_key_get_layout(state, key)
                for layout in range(self._common.xkb_keymap_num_layouts_for_key(keymap, key)):
                    for level in range(
                        self._common.xkb_keymap_num_levels_for_key(keymap, key, layout)
                    ):
                        out = ffi.new("const uint32_t **")
                        count = self._common.xkb_keymap_key_get_syms_by_level(
                            keymap, key, layout, level, out
                        )
                        # CFFI's generic indexing stub returns integers; preserve pointer typing here.
                        symbols = cast("CData", cast("object", out[0]))
                        if any(symbols[index] == symbol for index in range(count)):
                            matches.append((layout != active, level, key))
        if not matches:
            msg = f"unsupported XKB key name: {name!r}"
            raise UnsupportedKeyError(msg)
        return X11Keycode(min(matches)[2])

    def _keycodes(self, keymap: CData) -> range:
        return range(
            max(8, self._common.xkb_keymap_min_keycode(keymap)),
            min(255, self._common.xkb_keymap_max_keycode(keymap)) + 1,
        )

    def plan_text(self, text: str) -> tuple[KeyStroke, ...]:
        """Plan the entire string from a fresh map; never emit input while planning."""
        with self._snapshot() as (keymap, state):
            baseline = self._state_components(state)
            if baseline.latched_mods or baseline.latched_layout:
                msg = "literal text is unsafe while an XKB modifier or group latch is active"
                raise KeyboardStateConflictError(msg)
            plans, conflicts = self._text_candidates(keymap, state, baseline)
            result: list[KeyStroke] = []
            for index, character in enumerate(text):
                if category(character) in {"Cc", "Cs"} and character not in {"\n", "\t"}:
                    self._unsupported(character, index)
                plan = plans.get(character)
                if plan is None:
                    if character in conflicts or baseline.depressed_mods:
                        msg = f"unconsumed keyboard modifiers at character index {index}"
                        raise KeyboardStateConflictError(msg)
                    self._unsupported(character, index)
                result.append(plan)
            return tuple(result)

    @staticmethod
    def _unsupported(character: str, index: int) -> Never:
        msg = f"unsupported codepoint U+{ord(character):04X} at character index {index}"
        raise UnsupportedTextInputError(msg)

    def _state_components(self, state: CData) -> _KeyboardState:
        return _KeyboardState(
            self._common.xkb_state_serialize_mods(state, 1),
            self._common.xkb_state_serialize_mods(state, 2),
            self._common.xkb_state_serialize_mods(state, 4),
            self._common.xkb_state_serialize_layout(state, 16),
            self._common.xkb_state_serialize_layout(state, 32),
            self._common.xkb_state_serialize_layout(state, 64),
        )

    def _restore_state(self, state: CData, baseline: _KeyboardState) -> None:
        _ = self._common.xkb_state_update_mask(
            state,
            baseline.depressed_mods,
            baseline.latched_mods,
            baseline.locked_mods,
            baseline.depressed_layout,
            baseline.latched_layout,
            baseline.locked_layout,
        )

    @contextmanager
    def _candidate_state(self, keymap: CData, baseline: _KeyboardState) -> Generator[CData]:
        state = self._common.xkb_state_new(keymap)
        if state == ffi.NULL:
            msg = "could not create candidate XKB state"
            raise XkbError(msg)
        try:
            self._restore_state(state, baseline)
            yield state
        finally:
            self._common.xkb_state_unref(state)

    def _text_modifiers(self, keymap: CData, state: CData) -> tuple[X11Keycode, ...]:
        # Only keys whose current symbol is a text selector may be synthesized.
        groups = (
            ("Shift_L", "Shift_R"),
            ("ISO_Level3_Shift", "Mode_switch"),
            ("ISO_Level5_Shift",),
        )
        result: list[X11Keycode] = []
        for names in groups:
            symbols = {self._common.xkb_keysym_from_name(name.encode(), 0) for name in names}
            codes = [
                X11Keycode(key)
                for key in self._keycodes(keymap)
                if self._common.xkb_state_key_get_one_sym(state, key) in symbols
            ]
            # Different physical selectors can carry different actions in custom maps.
            result.extend(codes)
        return tuple(sorted(set(result)))

    def _literal(self, state: CData, key: int) -> str:
        symbol = self._common.xkb_state_key_get_one_sym(state, key)
        if symbol == _RETURN:
            return "\n"
        if symbol == _TAB:
            return "\t"
        size = self._common.xkb_state_key_get_utf8(state, key, ffi.NULL, 0)
        if size <= 0:
            return ""
        buffer = ffi.new(f"char[{size + 1}]")
        _ = self._common.xkb_state_key_get_utf8(state, key, buffer, size + 1)
        return ffi.string(buffer).decode("utf-8")

    def _text_candidates(
        self, keymap: CData, state: CData, baseline: _KeyboardState
    ) -> tuple[dict[str, KeyStroke], set[str]]:
        plans: dict[str, KeyStroke] = {}
        conflicts: set[str] = set()
        modifiers = self._text_modifiers(keymap, state)
        # At most one selector per Shift/Level3/Level5 is useful. Bound custom maps too.
        for count in range(min(3, len(modifiers)) + 1):
            for chord in combinations(modifiers, count):
                with self._candidate_state(keymap, baseline) as candidate:
                    redundant = False
                    for modifier in chord:
                        before = self._state_components(candidate)
                        _ = self._common.xkb_state_update_key(candidate, modifier, 1)
                        if self._state_components(candidate) == before:
                            redundant = True
                    if redundant:
                        continue
                    components = self._state_components(candidate)
                    # Synthetic selectors may shift groups, but must not latch or lock.
                    if components.persistent != baseline.persistent:
                        continue
                    for modifier in reversed(chord):
                        _ = self._common.xkb_state_update_key(candidate, modifier, 0)
                    if self._state_components(candidate) != baseline:
                        continue
                    for modifier in chord:
                        _ = self._common.xkb_state_update_key(candidate, modifier, 1)
                    self._collect_candidates(keymap, candidate, chord, plans, conflicts)
        return plans, conflicts

    def _collect_candidates(
        self,
        keymap: CData,
        state: CData,
        modifiers: tuple[X11Keycode, ...],
        plans: dict[str, KeyStroke],
        conflicts: set[str],
    ) -> None:
        depressed = self._common.xkb_state_serialize_mods(state, 1)
        for key in self._keycodes(keymap):
            if key in modifiers:
                continue
            literal = self._literal(state, key)
            if len(literal) != 1:
                continue
            consumed = self._common.xkb_state_key_get_consumed_mods2(state, key, 0)
            # XKB consumed masks contain real modifiers; virtual aliases are not extra keys.
            if depressed & 0xFF & ~consumed:
                conflicts.add(literal)
                continue
            before = self._state_components(state)
            _ = self._common.xkb_state_update_key(state, key, 1)
            during = self._state_components(state)
            _ = self._common.xkb_state_update_key(state, key, 0)
            if during != before or self._state_components(state) != before:
                self._restore_state(state, before)
                continue
            plan = KeyStroke(modifiers=modifiers, key=X11Keycode(key))
            previous = plans.get(literal)
            if previous is None or (len(modifiers), key, modifiers) < (
                len(previous.modifiers),
                previous.key,
                previous.modifiers,
            ):
                plans[literal] = plan

    def close(self) -> None:
        """Release the owned xkbcommon context without closing XCB."""
        if self._closed:
            return

        self._closed = True
        self._common.xkb_context_unref(self._context)

    def __enter__(self) -> Self:
        """Return this keyboard boundary for scoped use."""
        self._ensure_open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Release the xkbcommon context."""
        self.close()

    def _ensure_open(self) -> None:
        if self._closed:
            msg = "XKB keyboard boundary is closed"
            raise XkbClosedError(msg)
