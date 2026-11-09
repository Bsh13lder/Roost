"""Owner, 2026-11-04: "it asks too much, when it replies it looks a little afraid, and sometimes it speaks much more
than necessary." The prompt's reply rules ask for Grok's voice: confident, short, result first, a source only where it
matters, no disclaimers, at most one offer, no repeats; the honesty rules stay."""

from __future__ import annotations

from roost.bots.models import Avatar, Bot, BotStatus
from roost.bots.templates import CHIEF, LIFE_ADMIN, RESEARCHER
from roost.computer_use.texts import CHECK_TEXT
from roost.talk.chat_feel import (
    DONE_RULE, FIRST_LINE_RULE, LENGTH_RULE, LINK_RULE, OFFER_RULE, SOURCE_RULE, TONE_RULE, chat_feel_section,
)
from roost.talk.instructions import build_instructions

_BOT = Bot(
    id="bot-1", user_id="user-1", name="Gela", job="helps with anything", instructions="",
    avatar=Avatar("round", "#22c55e", "none"), template_id=None, status=BotStatus.RESTING, model_override=None,
    created_at="2026-10-13T00:00:00+00:00", updated_at="2026-10-13T00:00:00+00:00",
)
# What the owner saw in Gela's replies and does not want asked for anywhere in the prompt.
_AFRAID_ASKS = (
    "Name the page you read", "say which page each fact came from", "offer more instead", "Say what a link is in "
    "your sentence", "say exactly what you saved", "says who found what",
)


def test_the_new_rules_reach_a_typed_run():
    prompt = build_instructions(_BOT, origins=("your message",))
    for rule in (TONE_RULE, SOURCE_RULE, OFFER_RULE):
        assert rule in chat_feel_section() and rule in prompt


def test_no_rule_asks_for_provenance_sentences_or_default_offers():
    texts = (build_instructions(_BOT), build_instructions(_BOT, outside_content=True),
             CHIEF.instructions, LIFE_ADMIN.instructions, RESEARCHER.instructions)
    for text in texts:
        for words in _AFRAID_ASKS:
            assert words not in text, words


def test_the_tone_rule_forbids_hedges_and_repeats_but_not_failures():
    for words in ("confident", "I haven't checked", "I sent nothing", "Don't repeat", "failed"):
        assert words in TONE_RULE, words


def test_a_source_is_named_only_where_it_matters_and_once_as_a_link():
    for words in ("only when", "once", "[Wizz Air](", "I read"):
        assert words in SOURCE_RULE, words
    assert "[" in LINK_RULE and "bare" in LINK_RULE


def test_at_most_one_offer_and_never_by_default():
    assert "at most one" in OFFER_RULE and "obvious next step" in OFFER_RULE
    assert "Do you want me to" in OFFER_RULE      # the habit named, so the model knows what to drop
    assert "offer more" not in LENGTH_RULE


def test_the_first_line_stays_for_the_working_words_and_never_joins_the_answer():
    """The code depends on it: the first step streams live into the reply bubble, and the web and chat list cut an
    "On it: …" lead as the working words (chat_feel.shown_reply, web/src/lib/onItLead.ts)."""
    assert "On it:" in FIRST_LINE_RULE
    assert "no tool" in FIRST_LINE_RULE and "never" in FIRST_LINE_RULE.lower()


def test_the_honesty_rules_stay():
    assert "done only once you checked" in DONE_RULE
    assert "failed" in DONE_RULE
    assert "confirmation" in CHECK_TEXT and "done" in CHECK_TEXT


# Owner addition, 2026-11-04: "when we agree on something, just do it, don't bother me, don't ask questions before
# everything. Short 'let me look' and then do it."

def test_a_clear_request_is_done_with_a_named_default_not_a_question():
    from roost.talk.chat_feel import DO_IT_RULE
    for words in ("clarifying", "sensible default", "a few words", "risky", "can't be undone"):
        assert words in DO_IT_RULE, words


def test_the_working_lead_is_a_few_words():
    assert "a few words" in FIRST_LINE_RULE


def test_ask_choice_is_only_for_a_choice_that_blocks_or_is_risky():
    from roost.talk.tool_catalog import ASK_CHOICE_SPEC
    text = ASK_CHOICE_SPEC.description
    assert "can't be undone" in text and "sensible default" in text and "confirm" in text


def test_note_question_is_preferred_over_asking():
    from roost.questions.tool_specs import NOTE_QUESTION_SPEC
    assert "instead of asking" in NOTE_QUESTION_SPEC.description


def test_full_auto_tells_the_bot_to_act_not_ask():
    from roost.approvals.models import BotApproval
    from roost.talk.instructions import FULL_AUTO_LINE
    full = build_instructions(_BOT, approval=BotApproval("auto_edit", frozenset(), auto_review=True))
    plain = build_instructions(_BOT, approval=BotApproval("auto_edit", frozenset(), auto_review=False))
    assert FULL_AUTO_LINE in full and FULL_AUTO_LINE not in plain
    assert "act" in FULL_AUTO_LINE and "don't ask" in FULL_AUTO_LINE
    asks = build_instructions(_BOT, approval=BotApproval("ask", frozenset(), auto_review=True))
    assert FULL_AUTO_LINE not in asks   # Ask every time keeps its cards
