"""The project tools' arguments (projects hub §3, H5, H15, H16): pydantic at
the tool boundary, plus the readers that turn a model's text into a project
field. Free text is ``ToolText``: a copy of an escaped tool result is stored
plain. On ``update_project`` a null leaves a field as it is, and '' clears a
date, the lead bot or the monthly limit."""

from __future__ import annotations

from datetime import date
from types import MappingProxyType
from typing import Any, Callable, Mapping

from pydantic import BaseModel, ConfigDict, Field

from roost.constants import (
    DEFAULT_CURRENCY, DEFAULT_PROJECT_COLOR, MAX_BOT_NAME_LENGTH, MAX_CATEGORY_NAME_LENGTH,
    MAX_DUE_TEXT_LENGTH, MAX_RECORD_ID_LENGTH, PROJECT_COLORS, PROJECT_STATUSES, TOPUP_SOURCE_MAX_CHARS,
)
from roost.money.amounts import optional_amount
from roost.money.currency import CurrencyCode, OptionalCurrencyCode
from roost.money.models import COLOR_TEXT       # Task 2's sentence: the palette, listed
from roost.records.tool_text import ToolText

Amount = str | int | float
DAY_TEXT = "“{value}” is not a day like 2026-10-14."
_ACTIVE, _ARCHIVED = PROJECT_STATUSES


class ListProjectsArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    include_archived: bool = False


class ProjectRefArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    project: ToolText = Field(min_length=1, max_length=MAX_CATEGORY_NAME_LENGTH)


class CreateProjectArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: ToolText = Field(min_length=1, max_length=MAX_CATEGORY_NAME_LENGTH)
    currency: CurrencyCode = DEFAULT_CURRENCY
    budget: Amount | None = None
    monthly_budget: Amount | None = None
    color: str | None = None                       # checked against the palette by read_color
    start_date: str | None = Field(default=None, max_length=MAX_DUE_TEXT_LENGTH)
    due_date: str | None = Field(default=None, max_length=MAX_DUE_TEXT_LENGTH)
    lead_bot: ToolText | None = Field(default=None, max_length=MAX_BOT_NAME_LENGTH)


class UpdateProjectArgs(ProjectRefArgs):
    name: ToolText | None = Field(default=None, min_length=1, max_length=MAX_CATEGORY_NAME_LENGTH)
    color: str | None = None
    start_date: str | None = Field(default=None, max_length=MAX_DUE_TEXT_LENGTH)
    due_date: str | None = Field(default=None, max_length=MAX_DUE_TEXT_LENGTH)
    lead_bot: ToolText | None = Field(default=None, max_length=MAX_BOT_NAME_LENGTH)
    monthly_budget: Amount | None = None
    archived: bool | None = None
    currency: OptionalCurrencyCode = None


class AddTopupArgs(ProjectRefArgs):
    amount: Amount
    source: ToolText | None = Field(default=None, max_length=TOPUP_SOURCE_MAX_CHARS)


class TopupRefArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    topup: str = Field(min_length=1, max_length=MAX_RECORD_ID_LENGTH)


class EditTopupArgs(TopupRefArgs):
    amount: Amount


def read_color(value: str | None) -> str:
    """A colour from the fixed palette (H16); none given is the default one."""
    if value is None:
        return DEFAULT_PROJECT_COLOR
    color = value.strip().lower()
    if color not in PROJECT_COLORS:
        raise ValueError(COLOR_TEXT)
    return color


def optional_day(value: str | None) -> str | None:
    """A day like 2026-10-14; ``None`` or '' is no day."""
    text = (value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise ValueError(DAY_TEXT.format(value=text)) from exc


def _name(value: str) -> str:
    return value.strip()


def _status(archived: bool) -> str:
    return _ARCHIVED if archived else _ACTIVE


def _same(value: Any) -> Any:
    return value


# update_project's argument → (ProjectService.update's field, its reader). The lead bot is
# read by the tools themselves: naming it needs the user's bots.
_READERS: Mapping[str, tuple[str, Callable[[Any], Any]]] = MappingProxyType({
    "name": ("name", _name), "color": ("color", read_color), "start_date": ("start_date", optional_day),
    "due_date": ("due_date", optional_day), "monthly_budget": ("monthly_budget", optional_amount),
    "archived": ("status", _status), "currency": ("currency", _same),
})


def project_changes(args: UpdateProjectArgs) -> dict[str, object]:
    """The fields the call set, read into ``ProjectService.update``'s changes."""
    given = args.model_dump(include=args.model_fields_set & set(_READERS))
    return {_READERS[key][0]: _READERS[key][1](value) for key, value in given.items() if value is not None}
