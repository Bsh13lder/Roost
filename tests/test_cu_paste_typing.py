"""Owner, 2026-11-01 ("make it smooth like Grok"): ``type`` puts the whole text into the focused box at once (CDP
``Input.insertText`` on the bot's own page, never key by key), line breaks and tabs included, up to 5000
characters. A one-line box refuses text with line breaks (nothing is typed), so a line break can never act as Enter.
When the page can't take a paste (another frame, a lost focus), one-line text falls back to roost-input's typing;
text with line breaks is never sent as keys."""

from __future__ import annotations

import pytest

from roost.computer_use.runner import HELD_TEXT
from roost.computer_use.runner_typing import LINE_BREAKS_ONE_LINE_TEXT, NO_PASTE_TEXT
from roost.config import load_config
from roost.constants import CU_TYPE_MAX_CHARS
from roost.db.connection import init_db
from roost.desk.fake_cu import FakeScreenState, fake_target, script

from cu_run_helpers import make_cu_rig, step

_MESSAGE = "On www.upwork.com please apply to the React job with my cover letter"
_LETTER = ("Hello,\n\nI have built React apps for six years.\nI can start on Monday.\n\n"
           "Best regards,\n\tGela")
_TEXTAREA = fake_target("field", "Cover letter", 300, 200, width=600, height=200, tag="textarea")
_ONE_LINE = fake_target("field", "Your rate", 300, 460, width=200, tag="input")
_SUBMIT = fake_target("button", "Submit", 920, 600, width=80, tag="button")
APPLY = script([
    ("apply", FakeScreenState(url="https://www.upwork.com/apply", title="Apply",
                              targets=(_TEXTAREA, _ONE_LINE, _SUBMIT), text="Submit a proposal",
                              on_click={"Submit": "sent"})),
    ("sent", FakeScreenState(url="https://www.upwork.com/sent", title="Sent", targets=(), text="Sent")),
])


@pytest.fixture
async def rig():
    config = load_config()
    await init_db(config)
    return await make_cu_rig(config, _MESSAGE, screen=APPLY)


async def _focus(rig, label: str):
    cu = rig.computer()
    await step(cu, "look")
    await step(cu, "click", target={"text": label}, expect="the box is focused")
    return cu


async def test_a_cover_letter_with_paragraphs_goes_in_at_once(rig):
    cu = await _focus(rig, "Cover letter")
    done = await step(cu, "type", text=_LETTER, expect="the letter is in the box")
    assert await rig.page.box_text(_TEXTAREA.node_id) == _LETTER
    assert rig.page.pasted_lengths == (len(_LETTER),)
    assert rig.desk.typed_lengths == () and "type" not in [verb for verb, _, _ in rig.desk.inputs]
    assert "Careful" not in done.text and rig.page.state_name == "apply"     # a line break never submits


async def test_the_longest_text_goes_in_at_once(rig):
    cu = await _focus(rig, "Cover letter")
    longest = ("word " * (CU_TYPE_MAX_CHARS // 5))[:CU_TYPE_MAX_CHARS - 1] + "."
    done = await step(cu, "type", text=longest, expect="typed")
    assert len(longest) == CU_TYPE_MAX_CHARS == 5000
    assert rig.page.pasted_lengths == (CU_TYPE_MAX_CHARS,) and "Careful" not in done.text


async def test_a_paste_replaces_an_old_draft(rig):
    cu = await _focus(rig, "Cover letter")
    rig.page.fill_box("an old draft")
    await step(cu, "type", text=_LETTER, expect="the letter is in the box")
    assert await rig.page.box_text(_TEXTAREA.node_id) == _LETTER


async def test_a_lost_letter_is_pasted_again(rig):
    cu = await _focus(rig, "Cover letter")
    rig.page.lossy_typing = 1
    done = await step(cu, "type", text=_LETTER, expect="typed")
    assert await rig.page.box_text(_TEXTAREA.node_id) == _LETTER
    assert rig.page.pasted_lengths == (len(_LETTER), len(_LETTER)) and "Careful" not in done.text


async def test_a_one_line_box_refuses_line_breaks_and_types_nothing(rig):
    cu = await _focus(rig, "Your rate")
    rig.page.fill_box("40", _ONE_LINE.node_id)
    done = await step(cu, "type", text="45 per hour\nfixed", expect="typed")
    assert done.text.startswith(LINE_BREAKS_ONE_LINE_TEXT)
    assert await rig.page.box_text(_ONE_LINE.node_id) == "40"
    assert rig.page.pasted_lengths == () and rig.desk.typed_lengths == () and rig.page.state_name == "apply"


async def test_a_one_line_box_takes_one_line_by_paste(rig):
    cu = await _focus(rig, "Your rate")
    await step(cu, "type", text="45 per hour", expect="typed")
    assert await rig.page.box_text(_ONE_LINE.node_id) == "45 per hour"
    assert rig.page.pasted_lengths == (len("45 per hour"),) and rig.desk.typed_lengths == ()


async def test_no_paste_falls_back_to_typing_for_one_line_text(rig):
    cu = await _focus(rig, "Your rate")
    rig.page.paste_works = False
    await step(cu, "type", text="45 per hour", expect="typed")
    assert await rig.page.box_text(_ONE_LINE.node_id) == "45 per hour"
    assert rig.page.pasted_lengths == () and rig.desk.typed_lengths == (len("45 per hour"),)


async def test_no_paste_never_sends_line_breaks_as_keys(rig):
    cu = await _focus(rig, "Cover letter")
    rig.page.paste_works = False
    done = await step(cu, "type", text=_LETTER, expect="typed")
    assert done.text.startswith(NO_PASTE_TEXT)
    assert rig.desk.typed_lengths == () and await rig.page.box_text(_TEXTAREA.node_id) == ""


async def test_a_paste_waits_for_your_hands(rig, monkeypatch):
    cu = await _focus(rig, "Cover letter")
    held = {"now": None}
    real_decide = rig.gate.decide

    async def decide(*args, **kwargs):
        verdict = await real_decide(*args, **kwargs)
        held["now"] = object()            # you hold it from here on, with no new epoch
        return verdict

    monkeypatch.setattr(rig.gate, "decide", decide)
    monkeypatch.setattr(rig.control, "held", lambda bot_id: held["now"])
    done = await step(cu, "type", text=_LETTER, expect="typed")
    assert done.text == HELD_TEXT and rig.page.pasted_lengths == ()
    assert await rig.page.box_text(_TEXTAREA.node_id) == ""
