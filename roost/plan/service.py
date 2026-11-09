"""``PlanService``: the one door to a bot's Plan, for the routes and the bot's tools.

- The user's writes (``put_text``, ``patch_item``) are compare-and-swap on the revision they read, and clear the
  taint of every line they changed (the user wrote that text).
- The bot's writes (``bot_add``, ``bot_update``, ``bot_complete``) are read-modify-write by item id with up to two
  retries, so they never touch the user's other lines. A tainted run adds the item's id to ``item_taint``. Each
  counts against ``PLAN_WRITES_PER_RUN``, and one "Updated plan · n items" line is posted per run.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Mapping

from roost.bots.store import BotStore
from roost.constants import PLAN_PROMPT_ITEMS, PLAN_WRITES_PER_RUN
from roost.events.hub import EventHub
from roost.plan import grammar
from roost.plan.grammar import PlanDoc, PlanItem, PlanRefused
from roost.plan.models import Plan, PromptItems
from roost.plan.store import PlanStore
from roost.records.revision import RevisionConflict
from roost.routines.reports import post_routine_note
from roost.timezones import local_tz
from roost.talk.store import TalkStore

CAP_TEXT = "I've changed the Plan enough in this run."
NO_SUCH_ITEM = "There is no such item in the Plan."
BAD_MARKUP = "That text uses Plan markup I can't keep. Reword it."
NOTE_LINE = "Updated plan · {n} items"
BOT_RETRIES = 2
MAX_RUN_COUNTERS = 500
ACTIVE = ("planned", "on_it")

Clock = Callable[[], datetime]
PATCH_FIELDS = frozenset({"status", "text", "date", "time", "tags"})


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class _RunCount:
    __slots__ = ("writes", "ids")

    def __init__(self) -> None:
        self.writes = 0
        self.ids: set[str] = set()


def _checked(item: PlanItem) -> PlanItem:
    """Refuse an item whose text would not read back the same (markup, a newline, an empty text)."""
    text = item.text.strip()
    if not text or "\n" in item.text or "\r" in item.text:
        raise PlanRefused(BAD_MARKUP if text else "An item needs some text.")
    item = replace(item, text=" ".join(text.split()))
    for tag in item.tags:
        if not grammar._TAG.fullmatch(tag):
            raise PlanRefused(f"“{tag}” is not a tag. Tags look like #home.")
    for kind, value in (("date", item.date), ("scheduled", item.scheduled), ("time", item.time)):
        if value is not None and not grammar._valid("time" if kind == "time" else "date", value):
            raise PlanRefused("Dates look like 2026-10-23 and times like 10:07.")
    back = grammar.parse(grammar.render_item(item) + "\n").items
    if len(back) != 1 or replace(back[0], line_no=0) != replace(item, line_no=0):
        raise PlanRefused(BAD_MARKUP)
    return item


def _reparse(lines: list[str | PlanItem]) -> PlanDoc:
    return grammar.parse("\n".join(grammar.render_item(x) if isinstance(x, PlanItem) else x for x in lines))


def _insert_at(lines: list[str | PlanItem]) -> int:
    end = next((n for n, x in enumerate(lines) if x == grammar.ARCHIVE_HEADING), len(lines))
    while end > 0 and lines[end - 1] == "":
        end -= 1
    return end


class PlanService:
    def __init__(self, store: PlanStore, events: EventHub, bots: BotStore, talk: TalkStore | None = None,
                 *, clock: Clock = _utc_now) -> None:
        self._store = store
        self._events = events
        self._bots = bots
        self._talk = talk
        self._clock = clock
        self._runs: dict[str, _RunCount] = {}

    def _today(self) -> date:
        return self._clock().astimezone(local_tz()).date()

    async def _plan(self, user_id: str, bot_id: str) -> Plan | None:
        if await self._bots.get(user_id, bot_id) is None:
            return None
        return await self._store.get_or_create(user_id, bot_id)

    async def _changed(self, plan: Plan) -> None:
        await self._events.publish(plan.user_id, {"type": "plan_changed", "bot_id": plan.bot_id,
                                                  "revision": plan.revision})

    # ----- reads -----

    async def read(self, user_id: str, bot_id: str) -> Plan | None:
        """``None``: the bot is not the user's. The Plan is made empty on first open."""
        return await self._plan(user_id, bot_id)

    async def items(self, user_id: str, bot_id: str) -> tuple[tuple[PlanItem, bool], ...] | None:
        plan = await self._plan(user_id, bot_id)
        if plan is None:
            return None
        return tuple((i, i.id in plan.item_taint) for i in grammar.parse(plan.content).items)

    async def items_for_prompt(self, user_id: str, bot_id: str) -> PromptItems | None:
        """Today's and tomorrow's open items. Tainted ones are only counted, never shown."""
        plan = await self._plan(user_id, bot_id)
        if plan is None:
            return None
        today = self._today()
        window = {today.isoformat(), (today + timedelta(days=1)).isoformat()}
        due = [i for i in grammar.parse(plan.content).items if i.status in ACTIVE and i.date in window]
        due.sort(key=lambda i: (i.date, i.time or "99:99"))
        clean = [i for i in due if i.id not in plan.item_taint]
        return PromptItems(tuple(clean[:PLAN_PROMPT_ITEMS]), len(due) - len(clean))

    # ----- the user's writes -----

    async def put_text(self, user_id: str, bot_id: str, content: str, *, base_revision: int) -> Plan | None:
        plan = await self._plan(user_id, bot_id)
        if plan is None:
            return None
        if base_revision != plan.revision:
            raise RevisionConflict(plan)
        grammar.check_limits(content)
        doc = grammar.parse(content)
        grammar.check_limits(content, doc)
        doc = grammar.normalise(grammar.assign_ids(doc), self._today())
        text = grammar.render(doc)
        grammar.check_limits(text, doc)
        saved = await self._store.save(user_id, bot_id, text, _carried_taint(plan, doc), base_revision)
        await self._changed(saved)
        return saved

    async def patch_item(self, user_id: str, bot_id: str, item_id: str, base_revision: int,
                         changes: Mapping[str, Any]) -> Plan | None:
        """``None``: no such bot or item. ``PlanRefused``: a change that cannot be kept."""
        plan = await self._plan(user_id, bot_id)
        if plan is None:
            return None
        if base_revision != plan.revision:
            raise RevisionConflict(plan)
        doc = grammar.parse(plan.content)
        found = next((i for i in doc.items if i.id == item_id), None)
        if found is None:
            return None
        edited = self._edit(found, changes)
        new_doc = _reparse([edited if x is found else x for x in doc.lines])
        saved = await self._store.save(user_id, bot_id, grammar.render(new_doc), plan.item_taint - {item_id},
                                       base_revision)
        await self._changed(saved)
        return saved

    def _edit(self, item: PlanItem, changes: Mapping[str, Any]) -> PlanItem:
        unknown = set(changes) - PATCH_FIELDS
        if unknown:
            raise PlanRefused("That change isn't allowed.")
        edited = item
        if "text" in changes:
            edited = replace(edited, text=str(changes["text"]))
        for field in ("date", "time"):
            if field in changes:
                edited = replace(edited, **{field: changes[field] or None})
        if "tags" in changes:
            edited = replace(edited, tags=tuple(changes["tags"] or ()))
        edited = _checked(edited)
        if "status" in changes:
            if changes["status"] not in grammar.STATUSES:
                raise PlanRefused("A status is planned, on_it, done or dropped.")
            edited = grammar.apply_status(edited, changes["status"], self._today())
        return edited

    # ----- the bot's writes -----

    def _spend(self, run_key: str) -> _RunCount:
        count = self._runs.get(run_key)
        if count is None:
            if len(self._runs) >= MAX_RUN_COUNTERS:
                self._runs = dict(list(self._runs.items())[MAX_RUN_COUNTERS // 2:])
            count = self._runs[run_key] = _RunCount()
        if count.writes >= PLAN_WRITES_PER_RUN:
            raise PlanRefused(CAP_TEXT)
        return count

    async def _modify(self, user_id: str, bot_id: str, run_key: str, tainted: bool,
                      change: Callable[[PlanDoc], tuple[list[str | PlanItem], str]]) -> str:
        """Read, change one item by id, archive old items, save; retry a lost race twice. Returns the item id."""
        count = self._spend(run_key)
        plan = await self._plan(user_id, bot_id)
        if plan is None:
            raise PlanRefused("There is no such bot.")
        for attempt in range(BOT_RETRIES + 1):
            lines, item_id = change(grammar.parse(plan.content))
            doc = grammar.archive_old(_reparse(lines), self._today())
            text = grammar.render(doc)
            grammar.check_limits(text, doc)
            taint = plan.item_taint | {item_id} if tainted else plan.item_taint
            try:
                saved = await self._store.save(user_id, bot_id, text, taint, plan.revision)
            except RevisionConflict as conflict:
                if attempt == BOT_RETRIES:
                    raise PlanRefused("The Plan changed while I was writing. Read it again and retry.") from conflict
                plan = conflict.current
                continue
            count.writes += 1
            count.ids.add(item_id)
            await self._changed(saved)
            return item_id
        raise PlanRefused("The Plan changed while I was writing. Read it again and retry.")

    async def bot_add(self, user_id: str, bot_id: str, *, text: str, run_key: str, tainted: bool,
                      date: str | None = None, time: str | None = None, tags: tuple[str, ...] = ()) -> PlanItem:
        fresh = _checked(PlanItem(id=None, status="planned", text=text, tags=tuple(tags), date=date, time=time))
        made: list[PlanItem] = []

        def add(doc: PlanDoc) -> tuple[list[str | PlanItem], str]:
            item = replace(fresh, id=grammar.new_id({i.id for i in doc.items if i.id}))
            lines = list(doc.lines)
            lines.insert(_insert_at(lines), item)
            made[:] = [item]
            return lines, item.id

        await self._modify(user_id, bot_id, run_key, tainted, add)
        return made[0]

    async def bot_update(self, user_id: str, bot_id: str, item_id: str, changes: Mapping[str, Any], *,
                         run_key: str, tainted: bool) -> PlanItem:
        if changes.get("status") == "done":
            raise PlanRefused("Use plan_complete to finish an item.")
        made: list[PlanItem] = []

        def update(doc: PlanDoc) -> tuple[list[str | PlanItem], str]:
            found = _find(doc, item_id)
            edited = self._edit(found, changes)
            made[:] = [edited]
            return [edited if x is found else x for x in doc.lines], item_id

        await self._modify(user_id, bot_id, run_key, tainted, update)
        return made[0]

    async def bot_complete(self, user_id: str, bot_id: str, item_id: str, *, note: str | None, run_key: str,
                           tainted: bool) -> PlanItem:
        made: list[PlanItem] = []

        def complete(doc: PlanDoc) -> tuple[list[str | PlanItem], str]:
            found = _find(doc, item_id)
            done = grammar.apply_status(found, "done", self._today())
            lines = [done if x is found else x for x in doc.lines]
            if note and note.strip():
                sub = _checked(PlanItem(id=grammar.new_id({i.id for i in doc.items if i.id}), status="planned",
                                        text=note, indent=1))
                lines.insert(lines.index(done) + 1, grammar.apply_status(sub, "done", self._today()))
            made[:] = [done]
            return lines, item_id

        await self._modify(user_id, bot_id, run_key, tainted, complete)
        return made[0]

    # ----- the per-run note -----

    async def flush_run_note(self, user_id: str, bot_id: str, thread_id: str | None, run_key: str | None) -> None:
        """Post the run's one "Updated plan · n items" line (if it wrote any) and forget the run."""
        count = self._runs.pop(run_key, None) if run_key else None
        if count is None or not count.ids or self._talk is None or thread_id is None:
            return
        await post_routine_note(self._talk, self._events, user_id, thread_id, bot_id, "updated", "plan",
                                text=NOTE_LINE.format(n=len(count.ids)))


def _find(doc: PlanDoc, item_id: str) -> PlanItem:
    found = next((i for i in doc.items if i.id == item_id), None)
    if found is None:
        raise PlanRefused(NO_SUCH_ITEM)
    return found


def _carried_taint(old: Plan, doc: PlanDoc) -> frozenset[str]:
    """Taint survives only on lines the user left exactly as they were."""
    before = {i.id: grammar.render_item(replace(i, line_no=0)) for i in grammar.parse(old.content).items if i.id}
    after = {i.id: grammar.render_item(replace(i, line_no=0)) for i in doc.items if i.id}
    return frozenset(i for i in old.item_taint if i in after and before.get(i) == after[i])
