"""The money tools' arguments (M1 D7; projects hub H1, H5, H6, H11) — pydantic
at the tool boundary. Free text is ``ToolText``: a copy of an escaped tool
result is stored plain. ``roost.money.tools`` imports every model here, so
they are importable from there too."""

from __future__ import annotations

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from roost.constants import (
    MAX_CATEGORY_NAME_LENGTH, MAX_DUE_TEXT_LENGTH, MAX_EXPENSE_NOTE_LENGTH, MAX_RECORD_ID_LENGTH,
    MAX_TASK_TAGS, MAX_TASK_TITLE_LENGTH,
)
from roost.money.currency import OptionalCurrencyCode
from roost.records.tool_text import ToolText

Amount = str | int | float
# Projects hub H1: the argument is `project`. `extra="ignore"` would silently drop
# the old `category`, landing the money in General, so both names are read;
# `project` wins when a model sends both.
PROJECT_ARG = AliasChoices("project", "category")


class LogExpenseArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    amount: Amount
    project: ToolText | None = Field(default=None, validation_alias=PROJECT_ARG, max_length=MAX_CATEGORY_NAME_LENGTH)
    note: ToolText | None = Field(default=None, max_length=MAX_EXPENSE_NOTE_LENGTH)
    vendor: ToolText | None = Field(default=None, max_length=MAX_EXPENSE_NOTE_LENGTH)
    currency: OptionalCurrencyCode = None   # None: the project's (H7)
    spent_at: str | None = Field(default=None, max_length=MAX_DUE_TEXT_LENGTH)
    task: ToolText | None = Field(default=None, max_length=MAX_TASK_TITLE_LENGTH)
    step: ToolText | None = Field(default=None, max_length=MAX_TASK_TITLE_LENGTH)
    starred: bool = False
    income: bool = False                    # money received: stored as money in, never as spending
    tags: list[ToolText] = Field(default_factory=list, max_length=MAX_TASK_TAGS)


class MonthArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    month: str | None = Field(default=None, max_length=7)
    project: ToolText | None = Field(default=None, validation_alias=PROJECT_ARG, max_length=MAX_CATEGORY_NAME_LENGTH)


class ListExpensesArgs(MonthArgs):
    offset: int = Field(default=0, ge=0)


class ExpenseRefArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    expense: str = Field(min_length=1, max_length=MAX_RECORD_ID_LENGTH)


class UpdateExpenseArgs(ExpenseRefArgs):
    """A null leaves a field as it is. ``task`` '' unlinks the task and its
    step; ``step`` '' unlinks the step."""

    amount: Amount | None = None
    project: ToolText | None = Field(default=None, validation_alias=PROJECT_ARG, max_length=MAX_CATEGORY_NAME_LENGTH)
    note: ToolText | None = Field(default=None, max_length=MAX_EXPENSE_NOTE_LENGTH)
    spent_at: str | None = Field(default=None, max_length=MAX_DUE_TEXT_LENGTH)
    task: ToolText | None = Field(default=None, max_length=MAX_TASK_TITLE_LENGTH)
    step: ToolText | None = Field(default=None, max_length=MAX_TASK_TITLE_LENGTH)
    starred: bool | None = None
    void: bool | None = None


class SetBudgetArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    project: ToolText = Field(validation_alias=PROJECT_ARG, min_length=1, max_length=MAX_CATEGORY_NAME_LENGTH)
    amount: Amount                    # '' clears the total budget (H5)
