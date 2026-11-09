"""Owner, 2026-10-27: Gela's Russian message went in after the old Spanish draft, and one letter was lost. Typing now
replaces what a box holds and is read back (typed once more when it doesn't match); a Send card shows the message as
its box holds it, under "Send message"; and Yes sends only when the box still holds that same message."""

from __future__ import annotations

import pytest

from roost.computer_use.lines import SEND_TITLE
from roost.computer_use.runner_typing import DRAFT_CHANGED_TEXT, TYPED_WRONG_TEXT
from roost.config import load_config
from roost.db.connection import init_db
from roost.desk.box_text import same_text
from roost.desk.fake_cu import FakeScreenState, fake_target, script

from cu_run_helpers import make_cu_rig, step

_MESSAGE = "On web.whatsapp.com please write to the physio and ask for a new appointment"
_BOX = fake_target("field", "Type a message", 300, 600, width=600, tag="div")
_SEND = fake_target("button", "Send", 920, 600, width=60, tag="button")
CHAT = script([
    ("chat", FakeScreenState(url="https://web.whatsapp.com/", title="WhatsApp", targets=(_BOX, _SEND),
                             text="Buenos días", on_click={"Send": "sent"})),
    ("sent", FakeScreenState(url="https://web.whatsapp.com/", title="WhatsApp", targets=(_BOX, _SEND),
                             text="Sent")),
])
_RUSSIAN = "Здравствуйте, хочу записаться на новый приём. Какие дни и время у вас свободны?"


@pytest.fixture
async def rig():
    config = load_config()
    await init_db(config)
    return await make_cu_rig(config, _MESSAGE, screen=CHAT)


async def _focus_box(rig):
    cu = rig.computer()
    await step(cu, "look")
    await step(cu, "click", target={"text": "Type a message"}, expect="the box is focused")
    return cu


async def test_typing_replaces_an_old_draft(rig):
    cu = await _focus_box(rig)
    rig.page.fill_box("Hola, quisiera pedir una nueva cita.")
    done = await step(cu, "type", text=_RUSSIAN, expect="the Russian text is in the box")
    assert await rig.page.box_text(_BOX.node_id) == _RUSSIAN
    assert "Careful" not in done.text and rig.desk._screen_page.pasted_lengths == (len(_RUSSIAN),)


async def test_a_lost_letter_is_typed_again(rig):
    cu = await _focus_box(rig)
    rig.page.lossy_typing = 1
    done = await step(cu, "type", text=_RUSSIAN, expect="typed")
    assert await rig.page.box_text(_BOX.node_id) == _RUSSIAN
    assert rig.desk._screen_page.pasted_lengths == (len(_RUSSIAN), len(_RUSSIAN)) and "Careful" not in done.text


async def test_a_box_that_stays_wrong_tells_the_bot_not_to_send(rig):
    cu = await _focus_box(rig)
    rig.page.lossy_typing = 5
    done = await step(cu, "type", text="hola", expect="typed")
    assert done.text.startswith(TYPED_WRONG_TEXT.format(held=3, meant=4))
    assert rig.desk._screen_page.pasted_lengths == (4, 4)


async def test_the_send_card_shows_the_message_and_says_send_message(rig):
    cu = await _focus_box(rig)
    await step(cu, "type", text=_RUSSIAN, expect="typed")
    await step(cu, "look")
    asked = await step(cu, "click", target={"text": "Send"}, expect="the message is sent")
    card = asked.parked
    assert card is not None and card.title == SEND_TITLE
    assert {row.label: row.value for row in card.rows}["Type a message"] == _RUSSIAN       # the box's own label
    assert [(box.text, box.node) for box in card.drafts] == [(_RUSSIAN, _BOX.node_id)]


async def test_yes_sends_only_the_message_the_card_showed(rig):
    cu = await _focus_box(rig)
    await step(cu, "type", text="hola", expect="typed")
    await step(cu, "look")
    card = (await step(cu, "click", target={"text": "Send"}, expect="sent")).parked
    await cu.close()                                               # the asking run has ended
    rig.page.fill_box("hola y algo más", _BOX.node_id)            # the box changed before you said yes
    refused = await rig.computer("run-2").rerun(card)
    assert not refused.ok and refused.text == DRAFT_CHANGED_TEXT.format(label="Type a message")
    assert rig.page.state_name == "chat"
    rig.page.fill_box("hola", _BOX.node_id)
    sent = await rig.computer("run-3").rerun(card)
    assert sent.ok and rig.page.state_name == "sent"


async def test_a_card_with_an_empty_box_has_no_message_row(rig):
    cu = rig.computer()
    await step(cu, "look")
    card = (await step(cu, "click", target={"text": "Send"}, expect="sent")).parked
    assert card is not None and card.drafts == () and "Type a message" not in {row.label for row in card.rows}


def test_same_text_ignores_only_spacing_and_unicode_forms():
    assert same_text("hola  que\ntal\n", "hola que tal")
    assert same_text("Café", "Café")
    assert not same_text("Каие дни", "Какие дни")
