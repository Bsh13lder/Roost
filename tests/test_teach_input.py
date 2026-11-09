"""Reading your control socket's input while teaching: presses, the first key in a field, named keys, a paste."""

from __future__ import annotations

import struct

from roost.desk.rfb import RfbMessage
from roost.teach.input import InputState, NamedKey, Paste, Press, Typing, read_input

CTRL = 0xffe3


def pointer(mask: int, x: int = 10, y: int = 20) -> RfbMessage:
    return RfbMessage("pointer", struct.pack(">BBHH", 5, mask, x, y), True)


def key(keysym: int, down: bool = True) -> RfbMessage:
    return RfbMessage("key", struct.pack(">BBxxI", 4, int(down), keysym), True)


def qemu(keysym: int, down: bool = True) -> RfbMessage:
    return RfbMessage("qemu_key", struct.pack(">BBHII", 255, 0, int(down), keysym, 30), True)


def run(messages, state: InputState | None = None):
    state = state or InputState()
    intents = []
    for message in messages:
        state, intent = read_input(message, state)
        if intent is not None:
            intents.append(intent)
    return state, intents


def test_a_press_is_recorded_once_until_the_buttons_go_up():
    _, intents = run([pointer(0, 1, 1), pointer(1, 30, 40), pointer(1, 31, 41), pointer(0, 31, 41),
                      pointer(4, 50, 60), pointer(0, 50, 60)])
    assert intents == [Press(30, 40), Press(50, 60)]


def test_scroll_wheel_is_not_a_press():
    _, intents = run([pointer(8), pointer(0), pointer(16), pointer(0)])
    assert intents == []


def test_only_the_first_key_after_a_click_says_typing():
    _, intents = run([pointer(1), pointer(0), key(ord("h")), key(ord("h"), False), key(ord("i")),
                      key(0xff08)])
    assert intents == [Press(10, 20), Typing()]


def test_tab_enter_and_escape_are_named_and_tab_opens_a_new_field():
    _, intents = run([key(ord("a")), key(0xff09), key(ord("b")), key(0xff0d), key(0xff8d), key(0xff1b),
                      key(0xfe20)])
    assert intents == [Typing(), NamedKey("Tab"), Typing(), NamedKey("Enter"), NamedKey("Enter"),
                       NamedKey("Escape"), NamedKey("Tab")]


def test_shortcuts_are_not_typing_but_ctrl_v_is_a_paste():
    state, intents = run([pointer(1), pointer(0), key(CTRL), key(ord("c")), key(ord("v"))])
    assert intents == [Press(10, 20), Paste()]
    state, intents = run([key(CTRL, False), key(ord("x"))], state)
    assert intents == [Typing()]


def test_arrows_and_key_ups_say_nothing():
    _, intents = run([key(0xff51), key(0xff52), key(ord("a"), False), key(0xffe1), key(0xffe1, False)])
    assert intents == []


def test_qemu_keys_read_like_key_events():
    _, intents = run([qemu(ord("z")), qemu(0xff0d), qemu(ord("q"), False)])
    assert intents == [Typing(), NamedKey("Enter")]


def test_unicode_and_keypad_keys_count_as_typing():
    _, intents = run([key(0x01000439)])
    assert intents == [Typing()]
    _, intents = run([key(0xffb5)])
    assert intents == [Typing()]


def test_other_messages_say_nothing():
    cut = RfbMessage("cut_text", struct.pack(">BxxxI", 6, 3) + b"abc", True)
    request = RfbMessage("update_request", struct.pack(">BBHHHH", 3, 0, 0, 0, 1, 1), False)
    short = RfbMessage("pointer", b"\x05", True)
    _, intents = run([cut, request, short])
    assert intents == []
