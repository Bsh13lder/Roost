"""DomainTools fills in the bot's name (for its bot: tag) and tells an observer about every step."""

from __future__ import annotations

from typing import Any

from roost.talk.domain_tools import DomainTools, RecordContext
from roost.talk.outcome import ToolOutcome


class _Echo:
    names = frozenset({"echo"})

    def activity(self, name: str) -> str:
        return "adding a thing"

    async def run(self, name: str, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        return ToolOutcome(f"name={ctx.bot_name}", created=True)


class _Seen:
    def __init__(self) -> None:
        self.steps: list[tuple[str, str, str | None, str]] = []

    async def stepped(self, name: str, activity: str, ctx: RecordContext, outcome: ToolOutcome) -> None:
        self.steps.append((name, activity, ctx.bot_name, outcome.text))


async def _names(user_id: str, bot_id: str) -> str | None:
    return {"b1": "Ana"}.get(bot_id)


async def test_run_and_execute_fill_the_bot_name_and_tell_the_observer():
    seen = _Seen()
    tools = DomainTools((_Echo(),), names=_names, observer=seen)
    ctx = RecordContext(user_id="u", bot_id="b1", tainted=False)
    assert (await tools.run("echo", {}, ctx)).text == "name=Ana"
    assert (await tools.execute("echo", {}, ctx)).text == "name=Ana"
    assert seen.steps == [("echo", "adding a thing", "Ana", "name=Ana")] * 2


async def test_an_unknown_bot_gets_an_empty_name_and_a_given_name_is_kept():
    tools = DomainTools((_Echo(),), names=_names)
    assert (await tools.run("echo", {}, RecordContext(user_id="u", bot_id="gone", tainted=False))).text == "name="
    given = RecordContext(user_id="u", bot_id="b1", tainted=False, bot_name="Kept")
    assert (await tools.run("echo", {}, given)).text == "name=Kept"


async def test_without_a_resolver_the_context_is_untouched():
    assert (await DomainTools((_Echo(),)).run("echo", {}, RecordContext("u", "b1", False))).text == "name=None"
