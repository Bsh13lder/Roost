"""Fast pages, slice 4: a box whose own label says search (WhatsApp's "Search or start a new chat", a plain textbox
or contenteditable with no searchbox role, no type=search and no form) takes the bot's own short search words with
no card. Enter in such a box is unchanged (only a structural search box makes Enter browsing), so a box merely named
"Search" can't send anything without your Yes. Gela's Francis run, end to end, in four steps."""

from __future__ import annotations

import html
from dataclasses import replace

import pytest

from roost.approvals.floor import floor_of
from roost.approvals.texts import PARKED_TEXT
from roost.computer_use.commit_words import commit_class, is_search_box, takes_search_words
from roost.computer_use.models import ActResolution, Box
from roost.config import load_config
from roost.db.connection import init_db
from roost.desk.fake_chats import APPOINTMENT_LINE, FAKE_CHATS
from roost.desk.page_targets import target_from_ax

from cu_run_helpers import make_cu_rig, run_step

_BOX = Box(20, 70, 380, 36)
_EDITABLE = {"name": "editable", "value": {"value": "richtext"}}


def _ax(role: str, name: str, *props: dict) -> dict:
    return {"role": {"value": role}, "name": {"value": name}, "backendDOMNodeId": 7, "properties": list(props)}


def _box(role: str, name: str, *props: dict, tag: str = "div", **extra):
    return target_from_ax(_ax(role, name, *props), _BOX, {"tag": tag, **extra})


def test_a_box_named_search_is_search_named():
    assert _box("textbox", "Search or start a new chat", _EDITABLE).search_named
    assert _box("textbox", "Buscar un chat o iniciar uno nuevo", _EDITABLE).search_named
    assert _box("textbox", "", tag="input", input_type="text", field_names="q Filter results").search_named
    assert not _box("textbox", "Type a message", _EDITABLE).search_named
    assert not _box("textbox", "Search", _EDITABLE, {"name": "multiline", "value": {"value": True}}).search_named
    assert not _box("textbox", "Search notes", tag="textarea").search_named
    assert not _box("button", "Search").search_named


def _typing(target, text: str = "Francis", *, approved: bool = False, flags=frozenset()) -> ActResolution:
    return ActResolution("type", "https://web.whatsapp.test/", "web.whatsapp.test", target, (210, 88), "", "",
                         "browsing", text_ok=approved, text_flags=flags)


def test_own_short_words_go_into_a_search_named_box_with_no_card():
    box = _box("textbox", "Search or start a new chat", _EDITABLE)
    assert takes_search_words(box) and not is_search_box(box)
    assert floor_of(_typing(box), typed_chars=7) is None
    assert floor_of(_typing(box, flags=frozenset({"contact"})), typed_chars=7) == "contact"
    assert floor_of(_typing(box), typed_chars=500) is None


def test_own_words_into_a_composer_need_no_card_either():
    # Owner, 2026-11-03: typing never asks; what sends it does (the Send card).
    composer = _box("textbox", "Type a message", _EDITABLE)
    assert not takes_search_words(composer)
    assert floor_of(_typing(composer), typed_chars=7) is None


def test_enter_in_a_box_named_search_is_browsing_too():
    # Owner, 2026-11-03: Enter in a box whose own label says search is browsing; a message box keeps its card.
    named = _box("textbox", "Search or start a new chat", _EDITABLE)
    assert commit_class(named, key="Enter") == "browsing"
    assert commit_class(_box("textbox", "Type a message", _EDITABLE), key="Enter") == "unknown"
    structural = replace(named, searchish=True)
    assert commit_class(structural, key="Enter") == "browsing"


# -- Gela's Francis run ---------------------------------------------------------------------------------------


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


async def test_the_francis_run_takes_four_steps(cfg):
    rig = await make_cu_rig(cfg, "When is my appointment with the dentist? Look in WhatsApp.", screen=FAKE_CHATS)
    runner = rig.tool_runner()
    looked = html.unescape(await run_step(runner, "look", picture=False))
    assert '[1] field "Search or start a new chat"' in looked
    typed = await run_step(runner, "type", index=1, text="Francis", expect="the Francis chat shows")
    assert runner.parked is None and rig.page.state_name == "found"
    assert '[2] row "Francis Dentist"' in html.unescape(typed)
    await run_step(runner, "click", index=2, expect="the chat opens")
    assert rig.page.state_name == "chat"
    found = await run_step(runner, "read_text", area=2, find="appointment")
    assert html.escape(APPOINTMENT_LINE, quote=True) in found
    assert [verb for verb, _, _ in rig.desk.inputs] == ["move", "click", "move", "click"]   # the words went in as a paste


async def test_typing_your_own_words_into_the_chat_composer_needs_no_card(cfg):
    rig = await make_cu_rig(cfg, "When is my appointment?", screen=FAKE_CHATS)
    rig.page.state_name = "chat"
    runner = rig.tool_runner()
    await run_step(runner, "look", picture=False)
    assert await run_step(runner, "type", index=4, text="Is it Thursday?", expect="typed") != PARKED_TEXT
    assert runner.parked is None
