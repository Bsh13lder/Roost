"""The Stuck flow's words (design §2, R6, R7): the exact line for every branch."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import get_args

import pytest

from roost.desk.stuck import BlockReason
from roost.stuck.models import CardState, StuckCard
from roost.stuck.texts import (
    GIVE_UP_LINE, REASON_WORDS, already_waiting_line, blocked_line, continue_text, stuck_line,
    stuck_message_body, stuck_status_line,
)

REQUEST = "buy two tickets for Friday"
CARD = StuckCard(
    id="card-1", user_id="u1", bot_id="bot-1", thread_id="t1", work_item_id="item-0", reason="login",
    url="https://shop.example/checkout?step=2", note="", request=REQUEST, suggest_main_browser=False,
    tainted=False, main_opened=False, state=CardState.OPEN, answer_item_id=None,
    created_at="2026-10-14T08:00:00+00:00", closed_at=None,
)


def test_every_reason_has_its_words():
    assert dict(REASON_WORDS) == {
        "challenge": "a check that I'm human", "login": "a sign-in page", "code": "a code check",
        "refused": "the site refusing me", "asked": "something only you can do",
    }
    assert set(REASON_WORDS) == set(get_args(BlockReason))


def test_the_card_host_is_the_urls_host_and_empty_without_a_url():
    assert CARD.host == "shop.example"
    assert replace(CARD, url="").host == ""


@pytest.mark.parametrize(("reason", "line"), [
    ("challenge", "I'm stuck on shop.example: a check that I'm human. Take control to clear it, then give it back."),
    ("login", "I'm stuck on shop.example: a sign-in page. Take control to clear it, then give it back."),
    ("code", "I'm stuck on shop.example: a code check. Take control to clear it, then give it back."),
    ("refused", "I'm stuck on shop.example: the site refusing me. Take control to clear it, then give it back."),
])
def test_the_stuck_line_names_the_site_and_what_stopped_the_bot(reason, line):
    assert stuck_line(replace(CARD, reason=reason)) == line


def test_a_bot_that_asked_quotes_its_reason_with_the_site():
    card = replace(CARD, reason="asked", note="approve the payment of 40 euros")
    assert stuck_line(card) == (
        "I need your help on shop.example: approve the payment of 40 euros. "
        "Take control to clear it, then give it back."
    )


def test_a_bot_that_asked_without_a_page_still_quotes_its_reason():
    card = replace(CARD, reason="asked", url="", note="approve the payment of 40 euros")
    assert stuck_line(card) == (
        "I need your help: approve the payment of 40 euros. Take control to clear it, then give it back."
    )


def test_a_reason_that_ends_its_own_sentence_gets_no_second_full_stop():
    card = replace(CARD, reason="asked", url="", note="  approve the payment.  ")
    assert stuck_line(card) == "I need your help: approve the payment. Take control to clear it, then give it back."


@pytest.mark.parametrize("ending", ["?", "!"])
def test_a_reason_that_ends_in_a_question_or_exclamation_mark_gets_no_full_stop(ending):
    card = replace(CARD, reason="asked", url="", note=f"  can you approve the payment{ending}  ")
    assert stuck_line(card) == (
        f"I need your help: can you approve the payment{ending} Take control to clear it, then give it back."
    )


def test_the_bot_can_suggest_the_main_brave():
    card = replace(CARD, reason="challenge", suggest_main_browser=True)
    assert stuck_line(card) == (
        "I'm stuck on shop.example: a check that I'm human. Take control to clear it, then give it back. "
        "I think this needs your main Brave."
    )


def test_the_blocked_line_says_what_was_not_finished():
    assert blocked_line("shop.example", REQUEST) == (
        "Blocked: shop.example keeps stopping me. I didn't finish: buy two tickets for Friday. "
        "Take control and do it yourself, or tell me another way."
    )


def test_the_already_waiting_line_names_the_open_cards_site_and_what_was_not_finished():
    assert already_waiting_line("shop.example", "pay the bill at bank.example") == (
        "I'm already waiting on you for shop.example, so I stopped here. "
        "I didn't finish: pay the bill at bank.example"
    )


def test_the_already_waiting_line_without_a_site():
    assert already_waiting_line("", REQUEST) == (
        "I'm already waiting on you, so I stopped here. I didn't finish: buy two tickets for Friday"
    )


def test_the_give_up_line():
    assert GIVE_UP_LINE == "OK, I stopped that task."


def test_the_continue_text_after_the_user_cleared_the_block():
    assert continue_text(CARD) == (
        "I cleared the block on shop.example. Read the page again and carry on with: buy two tickets for Friday"
    )


def test_the_continue_text_after_the_main_brave_does_not_ask_for_the_page_again():
    """R13: the user did the step in their own Brave, so the bot carries on without re-reading that page."""
    assert continue_text(replace(CARD, main_opened=True)) == (
        "I did this step in my own browser on shop.example. Don't read that page again; "
        "carry on with the rest of: buy two tickets for Friday. If you can't, tell me exactly what's left."
    )


def test_the_main_brave_continue_text_keeps_the_requests_own_full_stop():
    card = replace(CARD, main_opened=True, request="buy two tickets for Friday.")
    assert continue_text(card) == (
        "I did this step in my own browser on shop.example. Don't read that page again; "
        "carry on with the rest of: buy two tickets for Friday. If you can't, tell me exactly what's left."
    )


@pytest.mark.parametrize("ending", ["?", "!"])
def test_a_request_that_ends_in_a_question_or_exclamation_mark_gets_no_full_stop(ending):
    card = replace(CARD, main_opened=True, request=f"can you buy two tickets{ending}")
    assert continue_text(card) == (
        "I did this step in my own browser on shop.example. Don't read that page again; "
        f"carry on with the rest of: can you buy two tickets{ending} If you can't, tell me exactly what's left."
    )


def test_the_continue_text_when_the_card_had_no_page_does_not_speak_the_models_note_for_you():
    """The bot's own note is its words, not the user's: the user's line is fixed."""
    card = replace(CARD, reason="asked", url="", note="approve the payment.")
    assert continue_text(card) == "I did what you asked. Carry on with: buy two tickets for Friday"
    assert "approve the payment" not in continue_text(card)


@pytest.mark.parametrize("how", ["try_again", "gave_back"])
def test_the_continue_text_without_a_page_is_the_same_for_both_buttons(how):
    card = replace(CARD, reason="asked", url="", note="approve the payment.")
    assert continue_text(card, how) == "I did what you asked. Carry on with: buy two tickets for Friday"


def test_try_again_has_its_own_words():
    assert continue_text(CARD, "try_again") == (
        "Try again on shop.example. Read the page again and carry on with: buy two tickets for Friday"
    )


def test_give_it_back_keeps_its_words_and_is_the_default():
    gave_back = "I cleared the block on shop.example. Read the page again and carry on with: buy two tickets for Friday"
    assert continue_text(CARD, "gave_back") == continue_text(CARD) == gave_back


def test_a_step_done_in_the_main_brave_keeps_its_words_whichever_button_was_pressed():
    """R13 wins: the bot must not read that page again."""
    done = continue_text(replace(CARD, main_opened=True))
    assert continue_text(replace(CARD, main_opened=True), "try_again") == done
    assert done.startswith("I did this step in my own browser on shop.example.")


def test_the_card_message_body_is_the_card_as_json():
    card = replace(CARD, suggest_main_browser=True)
    assert json.loads(stuck_message_body(card)) == {
        "card_id": "card-1", "bot_id": "bot-1", "reason": "login", "host": "shop.example",
        "url": "https://shop.example/checkout?step=2", "note": "", "suggest_main_browser": True,
        "line": ("I'm stuck on shop.example: a sign-in page. Take control to clear it, then give it back. "
                 "I think this needs your main Brave."),
        "sign_in": False, "secret_field": None,
    }


def test_a_sign_in_cards_line_says_roost_never_sees_your_password():
    card = replace(CARD, sign_in=True, note="to see your tickets")
    body = json.loads(stuck_message_body(card))
    assert body["sign_in"] is True
    assert body["line"] == ("shop.example's sign-in page is open on my computer (to see your tickets). Take control, "
                            "type your email and password, then press I'm done. Roost never sees your password.")


def test_a_sign_in_cards_status_line_waits_calmly_and_never_says_stuck():
    card = replace(CARD, sign_in=True, url="https://accounts.google.com/v3/signin/identifier?continue=x", note="to read")
    assert stuck_status_line(card) == "Waiting for you to sign in to accounts.google.com."
    assert "Stuck" not in stuck_status_line(card)


def test_a_sign_in_card_with_no_host_still_waits():
    assert stuck_status_line(replace(CARD, sign_in=True, url="")) == "Waiting for you to sign in."
