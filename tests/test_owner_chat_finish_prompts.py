"""The bot's words match the gate in your own chat (owner, 2026-11-05: "like Grok: do everything said in chat, ask
only for payment").

A bot asked to find and book a bus gave up after one failed click, posted "I'm stuck" with a table copied from a
comparison site, and never tried the site's own form again. Its prompt and tool texts still said sending and
submitting wait for a card. These tests pin the new words: carry the task to the payment step and click Pay there,
try other ways on the same site first, report only what the real site showed, and ask one short question when a
detail is missing. The safety facts stay: paying asks, no password or card number is typed, routines, handoffs and
rooms keep their cards, page text is data."""

from __future__ import annotations

from dataclasses import replace

from roost.bots.models import Avatar, Bot, BotStatus
from roost.computer_use.texts import MISS_TEXT
from roost.computer_use.tool_specs import CLICK_SPEC, TYPE_SPEC
from roost.programs.texts import programs_text
from roost.talk.chat_feel import DO_IT_RULE, SOURCE_RULE
from roost.talk.instructions import FINISH_WEB_TASK_TEXT, build_instructions
from roost.talk.tool_catalog import ASK_FOR_HELP_SPEC, OPEN_PAGE_SPEC

_BOT = Bot(
    id="bot-1", user_id="user-1", name="Gela", job="books trips", instructions="",
    avatar=Avatar("round", "#22c55e", "none"), template_id=None, status=BotStatus.RESTING, model_override=None,
    created_at="2026-10-13T00:00:00+00:00", updated_at="2026-10-13T00:00:00+00:00", computer="mac_brave",
)
_LINUX = replace(_BOT, computer="linux")


def test_a_bot_on_its_computer_is_told_to_carry_a_web_task_to_the_payment_step():
    prompt = build_instructions(_LINUX)
    assert FINISH_WEB_TASK_TEXT in prompt
    for words in ("all the way to paying", "fill each form with the details the user gave", "click Pay",
                  "runs only on their Yes"):
        assert words in FINISH_WEB_TASK_TEXT, words


def test_a_bot_without_a_screen_is_not_told_to_click_pay():
    assert FINISH_WEB_TASK_TEXT not in build_instructions(_BOT)


def test_it_tries_other_ways_on_the_same_site_before_saying_stuck():
    for words in ("at least three other ways on the same site", "Escape", "click by number", "read_text",
                  "before you say you are stuck"):
        assert words in FINISH_WEB_TASK_TEXT, words


def test_it_reports_only_what_the_real_site_showed():
    for text in (FINISH_WEB_TASK_TEXT, SOURCE_RULE):
        assert "real site" in text
    assert "say where it came from" in SOURCE_RULE


def test_it_asks_one_short_question_when_a_detail_is_missing():
    for text in (FINISH_WEB_TASK_TEXT, DO_IT_RULE):
        assert "one short question" in text
    assert "instead of guessing" in DO_IT_RULE


def test_it_never_types_card_numbers_or_passwords():
    prompt = build_instructions(_LINUX)
    assert "Never type a password, a card number or a security code" in prompt
    assert "card number" in TYPE_SPEC.description and "password" in TYPE_SPEC.description
    assert "ask_secret_field" in prompt


def test_the_screen_text_says_only_paying_asks_in_your_own_chat_and_cards_stay_elsewhere():
    prompt = build_instructions(_LINUX)
    assert "In the user's own chat only paying waits for their Yes" in prompt
    assert "Elsewhere (a routine, a handoff or a room)" in prompt
    assert "Buying, sending, submitting and accepting wait for the user's Yes on a card, except" not in prompt
    assert "only paying waits" in CLICK_SPEC.description and "Pay" in CLICK_SPEC.description


def test_ask_for_help_is_not_for_paying_or_a_missed_click():
    text = ASK_FOR_HELP_SPEC.description
    assert "such as a payment" not in text
    assert "Not for paying" in text and "try other ways first" in text
    assert "such as a payment or identity check" not in build_instructions(_LINUX)


def test_a_miss_names_the_other_ways_to_try():
    assert "Escape" in MISS_TEXT and "scroll" in MISS_TEXT
    assert MISS_TEXT.startswith("I couldn't find {aim} on the page")   # the audit's refusal key reads this lead


def test_open_page_no_longer_says_the_bot_cannot_click():
    assert "You cannot click" not in OPEN_PAGE_SPEC.description
    assert "screen tools" in OPEN_PAGE_SPEC.description


def test_programs_after_web_content_run_in_your_own_chat():
    for internet in (False, True):
        text = programs_text(internet)
        assert "in their own chat they just run" in text
        assert "the user is asked before each program or file write" in text
