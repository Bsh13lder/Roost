"""``send_helpers``' arguments and the refusal texts, apart from the tools so ``ToolRunner`` can use them
without importing the code that imports it."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from roost.constants import HELPER_TASK_MAX_CHARS, MAX_HELPERS_AT_ONCE, MAX_HELPERS_PER_RUN

HELPERS_RUN_CAP_TEXT = f"Refused: at most {MAX_HELPERS_PER_RUN} helpers in one run."
NO_NESTED_HELPERS_TEXT = "Refused: a helper can't send helpers."
BAD_HELPERS_ARGS_TEXT = (
    f"Refused: send 1 to {MAX_HELPERS_AT_ONCE} helpers at once, each with a task of up to "
    f"{HELPER_TASK_MAX_CHARS} characters."
)
NO_HELPERS_TEXT = "Refused: helpers are not available in this run."
ANNOUNCE_TASK_CHARS = 60


class HelperSpec(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    task: str = Field(min_length=1, max_length=HELPER_TASK_MAX_CHARS)
    model: Literal["haiku", "sonnet"] = "haiku"


class SendHelpersArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")

    helpers: list[HelperSpec] = Field(min_length=1, max_length=MAX_HELPERS_AT_ONCE)


def sending_line(args: SendHelpersArgs) -> str:
    """The parent's activity: ``sending 2 helpers to <first task, up to 60 characters>``."""
    count = len(args.helpers)
    first = " ".join(args.helpers[0].task.split())[:ANNOUNCE_TASK_CHARS]
    return f"sending {count} {'helper' if count == 1 else 'helpers'} to {first}"
