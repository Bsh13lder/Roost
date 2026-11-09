"""The richer repeat rule (Amendment T): "every other Monday", "every 3 days", "every! week" (from completion).

A 5-field cron can't say these, so the rule is a small validated JSON object kept in the task's existing
``recurring`` text (no new column): ``{"v":1,"every":2,"unit":"week","weekday":0,"from_completion":false}``.
A plain cron stays a plain cron; ``is_rule`` tells them apart. ``weekday`` is Monday=0 and only a week rule
has one. The dates are pure: ``next_day`` gives the day after a reference day."""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Literal

from dateutil.relativedelta import relativedelta
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, ValidationError

from roost.constants import REPEAT_RULE_MAX_EVERY

RULE_VERSION = 1
BAD_RULE_TEXT = "That repeat rule is not valid: use every 1 to {limit} days, weeks or months."
_DAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_DAYS_PER_WEEK = 7
_UNIT_WORD = {"day": "day", "week": "week", "month": "month"}


class RepeatRule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    v: Literal[1] = RULE_VERSION
    every: StrictInt = Field(ge=1, le=REPEAT_RULE_MAX_EVERY)
    unit: Literal["day", "week", "month"]
    weekday: StrictInt | None = Field(default=None, ge=0, le=6)
    from_completion: StrictBool = False

    def model_post_init(self, __context: object) -> None:
        if self.weekday is not None and self.unit != "week":
            raise ValueError("Only a weekly rule has a weekday.")


def is_rule(text: str | None) -> bool:
    return bool(text) and text.lstrip().startswith("{")


def parse_rule(text: str) -> RepeatRule:
    """The rule in ``text``; ``ValueError`` with a plain sentence when it is not a valid one."""
    try:
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("not an object")
        return RepeatRule.model_validate(data)
    except (ValueError, ValidationError, TypeError) as exc:
        raise ValueError(BAD_RULE_TEXT.format(limit=REPEAT_RULE_MAX_EVERY)) from exc


def rule_json(rule: RepeatRule) -> str:
    """The canonical text stored in ``recurring``."""
    return json.dumps(rule.model_dump(), separators=(",", ":"))


def next_day(rule: RepeatRule, reference: date) -> date:
    """The day of the occurrence after ``reference`` (the old due, or the completion day)."""
    if rule.unit == "day":
        return reference + timedelta(days=rule.every)
    if rule.unit == "month":
        return reference + relativedelta(months=rule.every)
    if rule.weekday is None:
        return reference + timedelta(weeks=rule.every)
    base = reference + timedelta(weeks=rule.every - 1)
    ahead = (rule.weekday - base.weekday() - 1) % _DAYS_PER_WEEK + 1      # strictly after base, 1..7 days
    return base + timedelta(days=ahead)


def readable_rule(rule: RepeatRule) -> str:
    unit = _UNIT_WORD[rule.unit]
    if rule.weekday is not None:
        day = _DAY_NAMES[rule.weekday]
        words = (f"every {day}" if rule.every == 1 else f"every other {day}" if rule.every == 2
                 else f"every {rule.every} weeks on {day}")
    elif rule.every == 1:
        words = f"every {unit}"
    elif rule.every == 2:
        words = f"every other {unit}"
    else:
        words = f"every {rule.every} {unit}s"
    return f"{words}, when done" if rule.from_completion else words
