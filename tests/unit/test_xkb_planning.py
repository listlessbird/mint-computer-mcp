"""Exercise real libxkbcommon maps in memory without opening an X11 connection."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, cast, final

import pytest

from mint_computer_mcp.backend import (
    KeyboardStateConflictError,
    UnsupportedKeyError,
    UnsupportedTextInputError,
)
from mint_computer_mcp.domain.input import KeyName
from mint_computer_mcp.domain.x11 import ProtocolVersion
from mint_computer_mcp.native.x11 import xkb
from mint_computer_mcp.native.x11.xkb import XkbKeyboard, XkbSetup, ffi

if TYPE_CHECKING:
    from cffi import CData

    from mint_computer_mcp.native.x11.client import X11Client

ffi.cdef("""
    struct xkb_keymap *xkb_keymap_new_from_string(
        struct xkb_context *context, const char *string, int format, int flags);
""")


class Compiler(Protocol):
    def xkb_keymap_new_from_string(
        self, context: CData, string: bytes, format_: int, flags: int
    ) -> CData: ...


@final
class SnapshotLibrary:
    def __init__(self, layout: str, components: tuple[int, int, int, int, int, int]) -> None:
        self.common, _ = xkb._load_libraries()  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        self.compiler = cast("Compiler", ffi.dlopen("libxkbcommon.so.0"))
        self.layout = layout
        self.components = components
        self.snapshots = 0

    def xkb_x11_keymap_new_from_device(
        self, context: CData, connection: CData, device: int, flags: int
    ) -> CData:
        _ = connection, device, flags
        self.snapshots += 1
        source = (
            'xkb_keymap { xkb_keycodes { include "evdev+aliases(qwerty)" };'
            'xkb_types { include "complete" }; xkb_compat { include "complete" };'
            f'xkb_symbols {{ include "pc+{self.layout}+inet(evdev)" }}; }};'
        )
        keymap = self.compiler.xkb_keymap_new_from_string(context, source.encode(), 1, 0)
        assert keymap != ffi.NULL
        return keymap

    def xkb_x11_state_new_from_device(self, keymap: CData, connection: CData, device: int) -> CData:
        _ = connection, device
        state = self.common.xkb_state_new(keymap)
        assert state != ffi.NULL
        _ = self.common.xkb_state_update_mask(state, *self.components)
        return state


def keyboard(
    layout: str = "us", components: tuple[int, int, int, int, int, int] = (0, 0, 0, 0, 0, 0)
) -> tuple[XkbKeyboard, SnapshotLibrary]:
    library = SnapshotLibrary(layout, components)
    context = library.common.xkb_context_new(0)
    board = object.__new__(XkbKeyboard)
    board._initialize(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        client=cast("X11Client", object()),
        common=library.common,
        x11=cast("xkb._XkbX11Lib", cast("object", library)),  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        connection=ffi.NULL,
        context=context,
        setup=XkbSetup(version=ProtocolVersion(major=1, minor=0), device_id=1),
    )
    return board, library


def test_fresh_map_for_each_action_and_no_hidden_chord_modifiers() -> None:
    board, library = keyboard()
    with board:
        assert board.resolve_key_names((KeyName("plus"),)) == (21,)
        library.layout = "de"
        assert board.resolve_key_names((KeyName("plus"),)) == (35,)
        assert library.snapshots == 2
        with pytest.raises(UnsupportedKeyError):
            _ = board.resolve_key_names((KeyName("not_a_keysym"),))


def test_literal_case_symbols_and_special_characters() -> None:
    board, _ = keyboard()
    with board:
        lower, upper, plus, newline, tab = board.plan_text("aA+\n\t")
        assert lower.modifiers == ()
        assert upper.key == lower.key
        assert len(upper.modifiers) == 1
        assert plus.modifiers == ()  # The keypad plus needs no Shift.
        assert newline.key == 36
        assert tab.key == 23


def test_altgr_and_direct_unicode() -> None:
    board, _ = keyboard("de")
    with board:
        at = board.plan_text("@")[0]
        assert at.modifiers
    board, _ = keyboard("fr")
    with board:
        assert not board.plan_text("é")[0].modifiers


@pytest.mark.parametrize("components", [(0, 1, 0, 0, 0, 0), (0, 0, 0, 0, 1, 0)])
def test_latches_rejected(components: tuple[int, int, int, int, int, int]) -> None:
    board, _ = keyboard("us+de:2", components)
    with board, pytest.raises(KeyboardStateConflictError, match="latch"):
        _ = board.plan_text("a")


def test_caps_lock_and_user_shift_are_preserved() -> None:
    board, _ = keyboard(components=(0, 0, 2, 0, 0, 0))
    with board:
        upper, lower = board.plan_text("Aa")
        assert not upper.modifiers
        assert lower.modifiers
    board, _ = keyboard(components=(1, 0, 0, 0, 0, 0))
    with board:
        assert not board.plan_text("A")[0].modifiers
        with pytest.raises(KeyboardStateConflictError):
            _ = board.plan_text("a")


def test_control_held_rejected() -> None:
    board, _ = keyboard(components=(4, 0, 0, 0, 0, 0))
    with board, pytest.raises(KeyboardStateConflictError):
        _ = board.plan_text("a")


@pytest.mark.parametrize(
    ("text", "index", "codepoint"),
    [
        ("hello 世", 6, "4E16"),
        ("é", 0, "00E9"),
        ("\b", 0, "0008"),
    ],
)
def test_unsupported_text_reports_only_codepoint_and_index(
    text: str, index: int, codepoint: str
) -> None:
    board, _ = keyboard()
    with board, pytest.raises(UnsupportedTextInputError) as error:
        _ = board.plan_text(text)
    assert str(error.value) == f"unsupported codepoint U+{codepoint} at character index {index}"


def test_effective_group_controls_resolution_and_text() -> None:
    board, _ = keyboard("us+de:2", (0, 0, 0, 0, 0, 1))
    with board:
        assert board.resolve_key_names((KeyName("y"),)) == (52,)
        assert board.plan_text("y")[0].key == 52


def test_dead_key_sequence_is_not_planned() -> None:
    board, _ = keyboard("de")
    with board, pytest.raises(UnsupportedTextInputError, match=r"U\+00E9"):
        _ = board.plan_text("é")
