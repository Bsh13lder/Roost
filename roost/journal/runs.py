"""``JournalRuns`` — the one line a run that did work leaves in its bot's journal.

``DomainTools`` tells it about every domain step (``stepped``); it keeps the activity words of the steps
that wrote something (a ``write_create`` or ``write_change`` step that was not refused), per run. After the
run, ``finish_run`` appends one line built from them ("Added a task ×2, saved a note"), with no model call.
A step with no run (an approved call after your Yes) gets its line at once. The journal's own tools never
count. A failed append is logged and dropped: the journal never breaks a run."""

from __future__ import annotations

import logging

from roost.journal.markdown import run_line
from roost.journal.service import JournalService
from roost.talk.domain_tools import RecordContext
from roost.talk.outcome import ToolOutcome

log = logging.getLogger(__name__)

_WRITE_KINDS = frozenset({"write_create", "write_change"})
_REFUSED = ("Refused", "Not saved", "Blocked", "Not done")
JOURNAL_TOOLS = frozenset({"journal_append", "journal_read"})


def _did_work(name: str, outcome: ToolOutcome) -> bool:
    from roost.talk.tool_catalog import CATALOG   # local: the catalog imports every domain package

    tool = CATALOG.get(name)
    if tool is None or tool.kind not in _WRITE_KINDS or name in JOURNAL_TOOLS or outcome.failed:
        return False
    return outcome.created or not outcome.text.startswith(_REFUSED)


class JournalRuns:
    def __init__(self, journal: JournalService) -> None:
        self._journal = journal
        self._runs: dict[str, tuple[str, tuple[str, ...]]] = {}   # run id -> (bot name, activity words)

    @property
    def journal(self) -> JournalService:
        return self._journal

    async def stepped(self, name: str, activity: str, ctx: RecordContext, outcome: ToolOutcome) -> None:
        if not _did_work(name, outcome):
            return
        if ctx.run_id is None:
            await self._write(ctx.user_id, ctx.bot_id, ctx.bot_name or "", (activity,))
            return
        bot_name, steps = self._runs.get(ctx.run_id, (ctx.bot_name or "", ()))
        self._runs = {**self._runs, ctx.run_id: (bot_name, (*steps, activity))}

    async def finish_run(self, user_id: str, bot_id: str, run_id: str | None) -> None:
        """Append the run's line (if it did work) and forget the run."""
        if run_id is None or run_id not in self._runs:
            return
        bot_name, steps = self._runs[run_id]
        self._runs = {key: value for key, value in self._runs.items() if key != run_id}
        await self._write(user_id, bot_id, bot_name, steps)

    async def _write(self, user_id: str, bot_id: str, bot_name: str, steps: tuple[str, ...]) -> None:
        line = run_line(steps)
        if line is None:
            return
        try:
            await self._journal.append(user_id, bot_id, bot_name, line)
        except Exception as exc:   # the type only: never the text
            log.warning("a run's journal line was not written: %s", type(exc).__name__)
