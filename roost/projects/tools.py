"""The project tools (projects hub §3, H2–H4, H15): every bot reads, creates
and changes the user's projects through ``ProjectService``.

- Pydantic arguments, a refusal sentence instead of a guess, and record text
  escaped by its producer (``roost.projects.format``).
- A project is named exact-or-ask (``roost.projects.refs``): ``get_project``
  may read a near miss; nothing else ever lands on one.
- A new project records its bot and the run's taint. A reply that echoes a
  web-made project, or sums a web-made expense, carries that taint (M1 D3).
- Top-ups change an existing budget (H4), so the gate refuses them in a run
  that read a web page. Deleting a project is never a tool: only the Board
  does it, after a confirmation (design §3)."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from roost.bots.store import BotStore, normalize_bot_name
from roost.money.amounts import optional_amount, parse_amount
from roost.money.format import escape, money
from roost.money.models import Project, ProjectDraft
from roost.projects.format import project_brief, project_list_text, project_page_text
from roost.projects.refs import required_project
from roost.projects.service import ProjectRefusal, ProjectService
from roost.projects.tool_args import (
    AddTopupArgs, CreateProjectArgs, EditTopupArgs, ListProjectsArgs, ProjectRefArgs, TopupRefArgs,
    UpdateProjectArgs, optional_day, project_changes, read_color,
)
from roost.talk.domain_tools import RecordContext
from roost.talk.outcome import ToolOutcome

_ACTIVITY = {
    "list_projects": "checking your projects", "get_project": "looking at a project",
    "create_project": "creating a project", "update_project": "updating a project",
    "add_topup": "adding a top-up", "edit_topup": "changing a top-up", "undo_topup": "undoing a top-up",
}
GONE_TEXT = "Refused: that project is gone."
# None from the store: not one of the user's credits on a live project. An undone credit is the
# store's TopUpUndone, a ValueError that run() turns into "Refused: That top-up was undone already."
NO_TOPUP_TEXT = "Refused: there is no top-up with that id."
NOTHING_TO_CHANGE_TEXT = "Refused: update_project needs something to change."
NO_SUCH_BOT_TEXT = "None of your bots is called “{name}”."


def _budget_sentence(project: Project) -> str:
    name = escape(project.name)
    if project.budget is None:
        return f"“{name}” has no total budget now."
    return f"The total budget of “{name}” is now {money(project.budget, project.currency)}."


class ProjectTools:
    names = frozenset(_ACTIVITY)

    def __init__(self, service: ProjectService, bots: BotStore) -> None:
        self._service = service
        self._bots = bots

    def activity(self, name: str) -> str:
        return _ACTIVITY[name]

    async def run(self, name: str, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        handlers = {
            "list_projects": self._list, "get_project": self._get, "create_project": self._create,
            "update_project": self._update, "add_topup": self._add_topup, "edit_topup": self._edit_topup,
            "undo_topup": self._undo_topup,
        }
        try:
            return await handlers[name](arguments, ctx)
        except ValidationError:
            return ToolOutcome(f"Refused: {name} got arguments it can't use; see its description.")
        except ValueError as exc:
            return ToolOutcome(f"Refused: {escape(str(exc))}")

    async def _list(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = ListProjectsArgs.model_validate(arguments)
        listing = await self._service.listing(ctx.user_id, include_archived=args.include_archived)
        tainted = listing.web_money or any(project.tainted for project, _, _ in listing.rows)
        return ToolOutcome(project_list_text(listing.rows, include_archived=args.include_archived), tainted=tainted)

    async def _get(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        ref = ProjectRefArgs.model_validate(arguments).project
        found = await required_project(self._service, ctx.user_id, ref, change=False)
        if isinstance(found, ToolOutcome):
            return found
        detail = await self._service.detail(ctx.user_id, found.id)
        if detail is None:
            return ToolOutcome(GONE_TEXT)
        return ToolOutcome(project_page_text(detail), tainted=detail.tainted)

    async def _create(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = CreateProjectArgs.model_validate(arguments)
        draft = ProjectDraft(
            name=args.name.strip(), currency=args.currency, budget=optional_amount(args.budget),
            monthly_budget=optional_amount(args.monthly_budget), color=read_color(args.color),
            start_date=optional_day(args.start_date), due_date=optional_day(args.due_date),
            lead_bot_id=await self._lead_bot_id(ctx.user_id, args.lead_bot),
        )
        project = await self._service.create(ctx.user_id, draft, created_by_bot=ctx.bot_id, tainted=ctx.tainted)
        return ToolOutcome(f"Created project {project_brief(project)}.", created=True, tainted=project.tainted)

    async def _update(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = UpdateProjectArgs.model_validate(arguments)
        found = await required_project(self._service, ctx.user_id, args.project, change=True)
        if isinstance(found, ToolOutcome):
            return found
        changes = project_changes(args)
        if args.lead_bot is not None:
            changes = {**changes, "lead_bot_id": await self._lead_bot_id(ctx.user_id, args.lead_bot)}
        if not changes:
            return ToolOutcome(NOTHING_TO_CHANGE_TEXT)
        project = await self._service.update(ctx.user_id, found.id, changes)
        if project is None:
            return ToolOutcome(GONE_TEXT)
        return ToolOutcome(f"Updated: {project_brief(project)}.", tainted=project.tainted)

    async def _add_topup(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = AddTopupArgs.model_validate(arguments)
        amount = parse_amount(args.amount)
        found = await required_project(self._service, ctx.user_id, args.project, change=True)
        if isinstance(found, ToolOutcome):
            return found
        topup = await self._service.add_topup(ctx.user_id, found.id, amount, args.source,
                                              created_by_bot=ctx.bot_id, tainted=ctx.tainted)
        if topup is None:
            return ToolOutcome(GONE_TEXT)
        done = f"Added a {money(topup.amount, topup.currency)} top-up (id={topup.id})"
        return await self._budget_now(ctx.user_id, done, topup.project_id)

    async def _edit_topup(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = EditTopupArgs.model_validate(arguments)
        amount = parse_amount(args.amount)
        topup = await self._service.edit_topup(ctx.user_id, args.topup.strip(), amount)
        if topup is None:
            return ToolOutcome(NO_TOPUP_TEXT)
        done = f"Changed the top-up to {money(amount, topup.currency)}"
        return await self._budget_now(ctx.user_id, done, topup.project_id)

    async def _undo_topup(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        ref = TopupRefArgs.model_validate(arguments).topup.strip()
        topup = await self._service.undo_topup(ctx.user_id, ref)
        if topup is None:
            return ToolOutcome(NO_TOPUP_TEXT)
        return await self._budget_now(ctx.user_id, "Undid the top-up and its changes", topup.project_id)

    async def _budget_now(self, user_id: str, done: str, project_id: str) -> ToolOutcome:
        """A top-up reply: what was done, and the project's total budget now."""
        project = await self._service.resolve(user_id, project_id, change=False)
        if isinstance(project, ProjectRefusal):
            return ToolOutcome(f"{done}.")
        return ToolOutcome(f"{done}. {_budget_sentence(project)}", tainted=project.tainted)

    async def _lead_bot_id(self, user_id: str, name: str | None) -> str | None:
        """H15: the lead is one of the user's own bots, by id or name; '' is none."""
        wanted = (name or "").strip().lstrip("@")
        if not wanted:
            return None
        key = normalize_bot_name(wanted)
        bots = await self._bots.list(user_id)
        found = next((bot for bot in bots if bot.id == wanted or normalize_bot_name(bot.name) == key), None)
        if found is None:
            raise ValueError(NO_SUCH_BOT_TEXT.format(name=wanted))
        return found.id
