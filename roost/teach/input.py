"""What one input message from your control socket means for a teach recording. Pure.

``read_input`` reads only the shape of an input: a pointer press (buttons going from none to some, the wheel
ignored), the first key after a click or Tab ("typing into the field"), Enter, Tab and Escape by name, and
Ctrl+V as a paste. Which character was typed is never returned and never kept: a key's keysym is looked at only
to tell a character from a control key."""

from __future__ import annotations

import struct
from dataclasses import dataclass, replace

from roost.desk.rfb import RfbMessage

_BUTTONS = 0b111                         # left, middle, right; 8 and 16 are the wheel
_ENTER = frozenset({0xff0d, 0xff8d})
_TAB = frozenset({0xff09, 0xfe20})       # Tab, ISO_Left_Tab (Shift+Tab)
_ESCAPE = 0xff1b
_BACKSPACE_DELETE = frozenset({0xff08, 0xffff})
_MODIFIERS = range(0xffe1, 0xffef)       # Shift, Control, Caps, Meta, Alt, Super, Hyper (left and right)
_SHORTCUT_MODIFIERS = frozenset({0xffe3, 0xffe4, 0xffe7, 0xffe8, 0xffe9, 0xffea, 0xffeb, 0xffec, 0xffed, 0xffee})
_KEYPAD_TYPING = range(0xffaa, 0xffba)   # keypad * + , - . / and 0-9
_UNICODE_BASE = 0x01000000
_FUNCTION_KEYS = 0xff00
_PASTE_KEYS = frozenset({ord("v"), ord("V")})


@dataclass(frozen=True)
class InputState:
    buttons: int = 0                     # the pointer buttons held after the last pointer message
    held: frozenset[int] = frozenset()   # modifier keysyms held
    typing_open: bool = True             # the next character opens a "typed into" step


@dataclass(frozen=True)
class Press:
    x: int                               # screen pixels
    y: int


@dataclass(frozen=True)
class Typing:
    pass


@dataclass(frozen=True)
class NamedKey:
    name: str                            # "Enter", "Tab" or "Escape"


@dataclass(frozen=True)
class Paste:
    pass


Intent = Press | Typing | NamedKey | Paste


def _key_fields(message: RfbMessage) -> tuple[bool, int] | None:
    data = message.data
    if message.kind == "key" and len(data) >= 8:
        down, keysym = struct.unpack(">B2xI", data[1:8])
        return bool(down), keysym
    if message.kind == "qemu_key" and len(data) >= 12:
        down, keysym = struct.unpack(">HI", data[2:8])
        return bool(down), keysym
    return None


def _is_character(keysym: int) -> bool:
    return (keysym < _FUNCTION_KEYS or keysym >= _UNICODE_BASE or keysym in _KEYPAD_TYPING
            or keysym in _BACKSPACE_DELETE)


def _pointer(message: RfbMessage, state: InputState) -> tuple[InputState, Intent | None]:
    if len(message.data) < 6:
        return state, None
    mask, x, y = struct.unpack(">BHH", message.data[1:6])
    buttons = mask & _BUTTONS
    pressed = state.buttons == 0 and buttons != 0
    if pressed:
        return replace(state, buttons=buttons, typing_open=True), Press(x, y)
    return replace(state, buttons=buttons), None


def _named(keysym: int) -> str:
    if keysym in _ENTER:
        return "Enter"
    if keysym in _TAB:
        return "Tab"
    return "Escape" if keysym == _ESCAPE else ""


def _key(down: bool, keysym: int, state: InputState) -> tuple[InputState, Intent | None]:
    if keysym in _MODIFIERS:
        held = state.held | {keysym} if down else state.held - {keysym}
        return replace(state, held=frozenset(held)), None
    if not down:
        return state, None
    if name := _named(keysym):
        return replace(state, typing_open=True), NamedKey(name)
    if state.held & _SHORTCUT_MODIFIERS:
        return state, (Paste() if keysym in _PASTE_KEYS else None)
    if _is_character(keysym) and state.typing_open:
        return replace(state, typing_open=False), Typing()
    return state, None


def read_input(message: RfbMessage, state: InputState) -> tuple[InputState, Intent | None]:
    """The new state and what this message adds to the recording (``None``: nothing)."""
    if message.kind == "pointer":
        return _pointer(message, state)
    fields = _key_fields(message)
    if fields is None:
        return state, None
    return _key(*fields, state)
