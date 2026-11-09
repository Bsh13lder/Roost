"""The chat's first second: On it with words and the placeholder bubble go
out before anything loads, and the prompt rules that shape a reply's feel."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from roost.bots.models import BotStatus
from roost.bots.status import ActivityBoard
from roost.bots.store import BotStore
from roost.constants import FIRST_LINE_ACTIVITY
from roost.events.hub import EventHub
from roost.timezones import zone_city

# The "On it: …" lead stays: the first step streams live into the reply bubble, and the web and the chat list cut that
# lead as the working words (shown_reply below, web/src/lib/onItLead.ts), so it must never carry the answer.
FIRST_LINE_RULE = (
    "When you will use a tool, start with one line of a few words that says what you are starting on, before any "
    "tool (for example: \"On it: let me look.\" or \"On it: checking your Upwork inbox.\"). Say it once, never in your answer, and put your final "
    "answer in a new paragraph. When you need no tool, skip it and just answer."
)
# Owner, 2026-11-01 ("make it smooth like Grok"); 2026-11-04: these lines are the activity pill's notes, never bubbles.
PROGRESS_RULE = (
    "On a task with several stages, say in one short line what you found or what you are about to do before "
    "the next stage, like a person narrating (for example: \"Search is done. I'm picking the Acme job because "
    "it fits your rate.\"). Keep each line to one short sentence, skip it for quick steps, and do not repeat "
    "these lines in your final answer."
)
# Owner, 2026-10-25: replies were far too long for a chat. 2026-11-04: "it speaks much more than necessary".
LENGTH_RULE = (
    "Keep replies short, like a chat message: the answer first, in as few words as it takes, then at most a few "
    "short lines (about 80 words). Use a list only for three or more items, at most five. Leave out what the user "
    "didn't ask for, unless they ask for detail, a full list or a document."
)
# Owner, 2026-11-04: "when it replies it looks a little afraid" (Gela: "I sent nothing and changed nothing.").
TONE_RULE = (
    "Sound confident and plain, like a capable friend: state the result, not how you got it. No hedges or "
    "disclaimers such as \"I haven't checked again\", \"I sent nothing and changed nothing\" or \"I checked the "
    "tool's replies\"; say a limit only when something failed or is uncertain in a way that changes what the user "
    "does. Don't repeat the user's words or what you already said."
)
SOURCE_RULE = (
    "Name a source only when it matters (a price, a fact from a web page the user may want to check), once, as a "
    "short link on the words, like [Wizz Air](https://wizzair.com). Never write a sentence about it such as "
    "\"I read this on …\". "
    # Owner, 2026-11-05: a bot posted a table copied from a comparison site as if the bus company had shown it.
    "Give only results you read yourself on the real site; when a number came from elsewhere (a search result, a "
    "comparison site), say where it came from."
)
OFFER_RULE = (
    "End when the answer is done. Offer at most one next step, and only when there is an obvious next step; "
    "never close with \"Do you want me to …?\" or \"Tell me which one …\" by habit."
)
DONE_RULE = (
    "Say done only once you checked it worked (you read it back, or the tool said so). "
    "Otherwise say drafted, waiting or blocked, and say plainly when something failed."
)
# The install's zone by its place (owner, 2026-11-09): "Madrid time ... 12:16 Madrid", "New York time ...".
TIME_RULE_TEMPLATE = "Write times in {city} time with the label, like 12:16 {city}."
LINK_RULE = "Put a link on the words it belongs to, like [the booking page](url); never a bare or long address."

# Owner, 2026-11-03: "the bot just does what you ask"; 2026-11-04: "when we agree on something, just do it, don't
# bother me, don't ask questions before everything".
DO_IT_RULE = (
    "When the user asks you to do something, do it yourself with your tools, start to finish. Don't ask leave for "
    "ordinary steps and don't hand them steps to do; Roost shows a card on its own where one is needed. When the "
    "request is clear or the user already agreed, act now: no clarifying questions and no \"shall I?\" first. "
    "Pick a sensible default for any detail they left out and name it in a few words in your answer (for "
    "example: \"Booked for 13 Dec, 2 people; stopped at payment.\"). When a detail you can't pick for them is "
    "missing (the date, the names, how many people), ask one short question instead of guessing or searching for "
    "it again and again. Ask only when you truly can't go on, or when the choice is risky or can't be undone."
)

_RULES = (
    FIRST_LINE_RULE, PROGRESS_RULE, LENGTH_RULE, TONE_RULE, SOURCE_RULE, OFFER_RULE, DONE_RULE, DO_IT_RULE,
)


# Owner, 2026-10-27: the opening "On it: …" line is the working robot's words while a bot works, never part of the
# answer a chat shows (web/src/lib/onItLead.ts reads it the same way).
_ON_IT_LEAD = re.compile(r"^\s*On it\s*[:,—-]\s*([^\n]*)(?:\n+|$)", re.IGNORECASE)


def shown_reply(text: str) -> str:
    """A bot reply without its "On it: …" opening line; the line's words alone when nothing follows it."""
    found = _ON_IT_LEAD.match(text)
    if found is None:
        return text
    return text[found.end():].lstrip() or found.group(1).strip()


def without_on_it(text: str) -> str:
    """``text`` without an "On it: …" opening line, and nothing when that line is all it holds."""
    found = _ON_IT_LEAD.match(text)
    return (text if found is None else text[found.end():]).strip()


def on_it_only(text: str) -> bool:
    """True when ``text`` says nothing past an "On it: …" line: working words, never a bubble of its own."""
    return not without_on_it(text)


def chat_feel_section() -> str:
    """The chat-feel rules, one paragraph of the system prompt."""
    return "\n".join((*_RULES, time_rule(), LINK_RULE))


def time_rule() -> str:
    """How the bot writes a time: in the install's zone, labelled with its place (read at call time)."""
    return TIME_RULE_TEMPLATE.format(city=zone_city())


def placeholder_message_out(message_id: str, thread_id: str, bot_id: str) -> dict[str, Any]:
    """The empty-bodied ``MessageOut`` shape Ruling 15's pre-announcement
    ``message`` frame carries — ``seq`` is a sentinel (nothing is persisted yet)."""
    return {
        "id": message_id, "thread_id": thread_id, "role": "bot", "body": "", "tainted": False,
        "seq": 0, "created_at": datetime.now(timezone.utc).isoformat(), "kind": "text", "author_bot_id": bot_id,
    }


async def publish_status(
    events: EventHub, bots: BotStore, user_id: str, bot_id: str, status: BotStatus, current_activity: str | None,
) -> None:
    await bots.set_status(user_id, bot_id, status)
    await events.publish(user_id, {
        "type": "bot_status", "bot_id": bot_id, "status": status.value, "activity": current_activity,
    })


async def announce_start(
    *, events: EventHub, bots: BotStore, activity: ActivityBoard, user_id: str, bot_id: str,
    thread_id: str, reply_id: str,
) -> None:
    """On it with words, then the placeholder bubble, before any load."""
    if activity.get(bot_id) is None:
        activity.set(bot_id, FIRST_LINE_ACTIVITY)
    await publish_status(events, bots, user_id, bot_id, BotStatus.ON_IT, activity.get(bot_id))
    await events.publish(user_id, {
        "type": "message", "thread_id": thread_id, "message": placeholder_message_out(reply_id, thread_id, bot_id),
    })
