"""The words routines put in a chat: slot lines, activity lines and failure Report headlines.

Times are local, as hh:mm. Nothing here reads the clock or the database."""

from __future__ import annotations

from datetime import datetime

from roost.constants import REPORT_HEADLINE_MAX
from roost.timezones import local_tz

QUIET_VERB = "quiet"
_ELLIPSIS = "…"


def _hhmm(moment: datetime) -> str:
    return moment.astimezone(local_tz()).strftime("%H:%M")


def slot_line(slot_at: datetime, now: datetime, *, late: bool) -> str:
    """The line under a routine's instructions: when it was planned and when it really runs."""
    if late:
        return f"Planned {_hhmm(slot_at)}, running at {_hhmm(now)} (late)."
    return f"Planned {_hhmm(slot_at)}, running now."


def missed_note(count: int, first: datetime, last: datetime) -> str:
    return f"Missed {count} runs, {_hhmm(first)} to {_hhmm(last)}, while Roost was off."


def activity_line(verb: str, name: str) -> str:
    """"Created routine · Morning news" and its kin. ``verb`` is created, updated, paused or ran."""
    if verb == "ran":
        return f"Ran routine · {name} · nothing new"
    return f"{verb.capitalize()} routine · {name}"


def clip(text: str, limit: int = REPORT_HEADLINE_MAX) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + _ELLIPSIS


def headline(kind: str, name: str, host: str = "") -> str:
    """A failure Report's headline. ``kind`` is missed, held, skipped, error, stuck or expired."""
    text = {
        "missed": f"Missed: {name}",
        "held": f"Held: {name}",
        "skipped": f"Skipped: {name}",
        "error": f"Didn't finish: {name}",
        "stuck": f"Stuck: {name} on {host}" if host else f"Stuck: {name}",
        "expired": f"Waited for you: {name}",
    }[kind]
    return clip(text)


def paused_for_cap(cap: int) -> str:
    return f"Paused my routines: I've used today's {cap} runs. They start again after midnight."


def paused_for_reserve(reset: str) -> str:
    return f"Paused my routines: the usage limit is nearly used up; I'll start again at {reset}."


STILL_GOING = "the last run was still going"
STILL_WAITING = "still waiting for you"
OFF_DUTY_NOTE = "Off duty"

FOLDED_LINE = "More reports this hour than the limit; this one is in the log"
STOPPED_NOTE = "Stopped"
UNFINISHED_TEXT = "The run ended before it finished."
STUCK_TEXT = "I couldn't go on and need your help."
EMPTY_REPLY_TEXT = "The run finished with nothing to say."

# Amendment R1: an errored run is tried once more; the second error is the failure, with a next step.
RETRY_NOTE = "Retried once"
UNFINISHED_TWICE_TEXT = (
    "It failed twice in a row, so I stopped. Next step: open the run log to see what went wrong, "
    "then run it again or change the routine."
)
EXPIRED_NOTE = "Waited for you"


def expired_text(what: str) -> str:
    """The failure Report of a run whose Ask card nobody answered in time. An unanswered card counts as no."""
    step = what.strip() or "a step"
    return (f"I skipped “{clip(step, 200)}” because you didn't answer in time. "
            "I took that as a no and won't ask again for this run.")


def overlap_note(name: str) -> str:
    """The one quiet line a routine leaves per local day when a slot is skipped because the last run was going."""
    return f"Skipped a run of {name} · the last run was still going"
