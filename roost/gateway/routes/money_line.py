"""``POST /api/money/parse``: how the server reads an expense quick line (Task 6).

It changes nothing; the web adds the expense from this reading. A project's page passes ``project_id``.
Another user's project reads as a project that is gone."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Request
from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from roost.constants import MAX_RECORD_ID_LENGTH, QUICK_LINE_MAX_LENGTH
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.money.expense_line import ExpenseKind, expense_line_out, read_expense_line

money_line_router = APIRouter(prefix="/api/money", tags=["money"])


BAD_DEFAULT_DAY_TEXT = "default_day must be a day like 2026-10-21."
_DAY_CHARS = len("YYYY-MM-DD")


def _iso_day(value: str) -> str:
    """A real calendar day written exactly ``YYYY-MM-DD`` (``fromisoformat`` alone also reads other forms)."""
    try:
        day = date.fromisoformat(value)
    except ValueError:
        raise ValueError(BAD_DEFAULT_DAY_TEXT) from None
    if day.isoformat() != value:
        raise ValueError(BAD_DEFAULT_DAY_TEXT)
    return value


DefaultDay = Annotated[str, Field(min_length=_DAY_CHARS, max_length=_DAY_CHARS), AfterValidator(_iso_day)]


class ExpenseLineIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(max_length=QUICK_LINE_MAX_LENGTH)
    project_id: str | None = Field(default=None, max_length=MAX_RECORD_ID_LENGTH)    # a project page's own
    skip: list[Literal["amount", "project", "date", "star", "vendor", "repeat"]] = Field(
        default_factory=list, max_length=len(ExpenseKind))
    default_day: DefaultDay | None = None     # the day of a line that names none (the money calendar's "+")


@money_line_router.post("/parse", dependencies=[RequireOrigin])
async def parse_expense_line(body: ExpenseLineIn, request: Request, user: CurrentUser) -> dict[str, Any]:
    line = await read_expense_line(request.app.state.projects, user.id, body.text, project_id=body.project_id,
                                   skip=frozenset(body.skip), default_day=body.default_day)
    return expense_line_out(line)
