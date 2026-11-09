"""``ask_choice``: park the run on an options card, or say why it can't."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from roost.approvals.models import PendingCall
from roost.choices.decisions import DecisionBook
from roost.choices.models import choice_step, parse_choice_args
from roost.choices.texts import ALREADY_DECIDED_TEXT, BAD_CHOICE_ARGS_TEXT, CHOICE_NOT_HERE_TEXT, NOTE_QUESTION_CLAUSE
from roost.timezones import local_tz


def _madrid_date(iso: str) -> str:
    return datetime.fromisoformat(iso).astimezone(local_tz()).strftime("%Y-%m-%d")


async def park_choice(
    arguments: Mapping[str, Any], *, cards: bool, tainted: bool, decisions: DecisionBook | None,
    user_id: str, bot_id: str, has_question_book: bool,
) -> PendingCall | str:
    """The card's one step, or a plain sentence for the model (no card opens)."""
    args = parse_choice_args(dict(arguments))
    if args is None:
        return BAD_CHOICE_ARGS_TEXT
    if not cards:
        text = CHOICE_NOT_HERE_TEXT.format(safe=args.options[args.safe])
        return text + (NOTE_QUESTION_CLAUSE if has_question_book else "") + "."
    if decisions is not None:
        earlier = await decisions.find(user_id, bot_id, args.question)
        if earlier is not None and not earlier.reusable(tainted_run=tainted):
            return choice_step(args, earlier=earlier.answer)
        if earlier is not None:
            return ALREADY_DECIDED_TEXT.format(date=_madrid_date(earlier.decided_at), answer=earlier.answer)
    return choice_step(args)
