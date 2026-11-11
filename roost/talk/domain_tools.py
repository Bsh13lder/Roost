"""Domain tools (tasks, money, notes, documents, projects) behind one dispatch point for ``ToolRunner``.

Each domain package provides a handler with the tool names it serves; the
user's records it touches are the USER's (M1 D2): a handler gets the user, the
bot and the run's taint, and stores the bot as ``created_by_bot`` and the
taint bit on every row it creates."""

from __future__ import annotations

from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Any, Awaitable, Callable, Protocol

from roost.config import Config
from roost.approvals.models import PendingCall
from roost.events.hub import EventHub
from roost.talk.outcome import ToolOutcome


@dataclass(frozen=True)
class RecordContext:
    user_id: str
    bot_id: str
    tainted: bool
    thread_id: str | None = None   # the chat this run is in (a memory note is posted there)
    from_routine: bool = False     # the run is a routine's own (a proposal or question says so)
    run_id: str | None = None      # the work queue's run id (a per-run cap counts on it)
    user_started: bool = False     # a 1:1 run made only of the user's own messages (routines may be written directly)
    bot_name: str | None = None    # the bot's name for its bot:<slug> tag; DomainTools fills it in


class DomainHandler(Protocol):
    names: frozenset[str]

    def activity(self, name: str) -> str: ...

    async def run(self, name: str, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome: ...

    # Optional. ``prepare(name, arguments, ctx) -> PendingCall | str`` builds the card step for a call that asks
    # (a plain sentence refuses before any card). ``execute(name, resolved, ctx)`` runs a stored, resolved step
    # after the user's Yes; a handler without it runs the stored arguments through ``run``.
    # ``offer(name, arguments, ctx) -> str | None`` posts a one-click way out for a call the gate refused for
    # taint (``remember``'s Remember it line) and returns the bot's short result.


BotNames = Callable[[str, str], Awaitable[str | None]]


class StepObserver(Protocol):
    """Told about every domain step that ran (the Bot Journal collects a run's writes this way)."""

    async def stepped(self, name: str, activity: str, ctx: RecordContext, outcome: ToolOutcome) -> None: ...


class DomainTools:
    def __init__(self, handlers: tuple[DomainHandler, ...] = (), *, names: BotNames | None = None,
                 observer: StepObserver | None = None) -> None:
        self._by_name = MappingProxyType({name: handler for handler in handlers for name in handler.names})
        self._names = names
        self._observer = observer

    async def _named(self, ctx: RecordContext) -> RecordContext:
        """The context with the bot's name (for its ``bot:`` tag), looked up once per call when missing."""
        if ctx.bot_name is not None or self._names is None:
            return ctx
        return replace(ctx, bot_name=await self._names(ctx.user_id, ctx.bot_id) or "")

    async def _observed(self, name: str, ctx: RecordContext, outcome: ToolOutcome) -> ToolOutcome:
        if self._observer is not None:
            await self._observer.stepped(name, self.activity(name), ctx, outcome)
        return outcome

    def handles(self, name: str) -> bool:
        return name in self._by_name

    def activity(self, name: str) -> str:
        return self._by_name[name].activity(name)

    async def run(self, name: str, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        named = await self._named(ctx)
        return await self._observed(name, named, await self._by_name[name].run(name, arguments, named))

    async def prepare(self, name: str, arguments: dict[str, Any], ctx: RecordContext) -> PendingCall | str | None:
        """The handler's own card step (or a refusal sentence); ``None`` when it has no ``prepare``."""
        prepare = getattr(self._by_name[name], "prepare", None)
        return None if prepare is None else await prepare(name, arguments, ctx)

    async def target_title(self, name: str, arguments: dict[str, Any], ctx: RecordContext) -> str | None:
        """The stored title of the record a change targets (the change check), from a handler that has
        ``target_title``; ``None`` when it has none or finds no single record."""
        target_title = getattr(self._by_name[name], "target_title", None) if name in self._by_name else None
        return None if target_title is None else await target_title(name, arguments, ctx)

    async def offer(self, name: str, arguments: dict[str, Any], ctx: RecordContext) -> str | None:
        """A refused call's one-click way out (a ``memory_offer`` line), from a handler that has ``offer``;
        ``None`` when it has none or makes none."""
        offer = getattr(self._by_name[name], "offer", None) if name in self._by_name else None
        return None if offer is None else await offer(name, arguments, ctx)

    async def finish_run(self, user_id: str, bot_id: str, run_id: str | None) -> None:
        """The run ended: an observer or handler that keeps per-run state (the Bot Journal's run line, the chat's
        task cards) writes it now, each once."""
        handlers = tuple({id(handler): handler for handler in self._by_name.values()}.values())
        for keeper in (self._observer, *handlers):
            finish = getattr(keeper, "finish_run", None)
            if finish is not None:
                await finish(user_id, bot_id, run_id)

    async def execute(self, name: str, resolved: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        """Run a stored step after the user's OK. Model-made arguments never reach ``execute`` of a handler
        that has one: only a card's stored, resolved call does."""
        handler = self._by_name[name]
        named = await self._named(ctx)
        execute = getattr(handler, "execute", None)
        outcome = await (handler.run(name, resolved, named) if execute is None else execute(name, resolved, named))
        return await self._observed(name, named, outcome)


def build_domain_tools(
    config: Config, events: EventHub, *, mac_files: Any = None, grants: Any = None, sessions: Any = None,
    limits: Any = None, plan: Any = None, skills: Any = None, journal: Any = None, desks: Any = None,
    connectors: Any = None, connector_client: Any = None, connector_requests: Any = None,
    program_limits: Any = None, apps: Any = None,
) -> DomainTools:
    """Every domain's tools (tasks with their steps and comments, money, notes,
    documents and projects), wired to the user's shared stores. The stores hold
    no state, so one of each serves every service, and one ``ProjectService``
    answers every tool that names a project (projects hub H3). With ``mac_files``
    and ``grants`` the Mac tools join them (Your Mac). ``journal`` (a ``JournalRuns``) is told about every
    step, so each run that did work leaves one line in its bot's journal. ``desks``: the ``DeskFactory``
    the program tools reach each bot's workspace through (Programs); ``program_limits`` (a ``ProgramLimits``)
    holds each bot's workspace lock, which Wipe workspace shares. ``apps`` (an ``AppService``): install_app,
    remove_app and list_apps on a bot's Linux computer (one of its own when none is given)."""
    from roost.bots.store import BotStore
    from roost.day_notes.service import DayNoteService
    from roost.day_notes.store import DayNoteStore
    from roost.day_notes.tools import DayNoteTools
    from roost.documents.service import DocumentService
    from roost.documents.store import DocumentStore
    from roost.documents.tools import DocumentTools
    from roost.journal.runs import JournalRuns
    from roost.journal.service import JournalService
    from roost.journal.store import JournalStore
    from roost.journal.tools import JournalTools
    from roost.memory.service import MemoryService
    from roost.memory.store import MemoryStore
    from roost.memory.summaries import SummaryStore
    from roost.memory.tools import MemoryTools
    from roost.money.expense_store import ExpenseStore
    from roost.money.project_store import ProjectStore
    from roost.money.service import MoneyService
    from roost.money.tools import MoneyTools
    from roost.notes.service import NoteService
    from roost.notes.store import NoteStore
    from roost.notes.tools import NoteTools
    from roost.plan.service import PlanService
    from roost.plan.store import PlanStore
    from roost.plan.tools import PlanTools
    from roost.projects.service import ProjectService
    from roost.projects.tools import ProjectTools
    from roost.questions.service import QuestionService
    from roost.questions.store import QuestionStore
    from roost.questions.tools import QuestionTools
    from functools import partial

    from roost.computer_use.text_source import your_messages
    from roost.routines.direct_tools import RoutineWrites
    from roost.routines.proposals import ProposalService, ProposalStore
    from roost.routines.store import RoutineStore
    from roost.routines.tools import RoutineTools
    from roost.talk.store import TalkStore
    from roost.talk.team_steps import TeamSteps
    from roost.models_check.store import SeenModelStore
    from roost.tasks.comment_service import CommentService
    from roost.tasks.comment_store import CommentStore
    from roost.tasks.cards import TaskCards
    from roost.tasks.comment_tools import CommentTools
    from roost.tasks.service import TaskService   # local: roost.tasks imports this module
    from roost.tasks.step_service import StepService
    from roost.tasks.step_tools import StepTools
    from roost.tasks.store import TaskStore
    from roost.tasks.tools import TaskTools

    bots, expenses, notes = BotStore(config), ExpenseStore(config), NoteStore(config)
    project_store, task_store, documents = ProjectStore(config), TaskStore(config), DocumentStore(config)
    projects = ProjectService(project_store, expenses, task_store, notes, documents, bots, events)
    tasks = TaskService(task_store, events)
    comments = CommentStore(config)
    routine_store = RoutineStore(config, TalkStore(config))
    routine_writer = _routine_service(config, events, routine_store, bots)
    plans = plan if plan is not None else PlanService(PlanStore(config), events, bots, TalkStore(config))
    runs = journal if journal is not None else JournalRuns(JournalService(JournalStore(config), events))

    async def bot_name(user_id: str, bot_id: str) -> str | None:
        found = await bots.get(user_id, bot_id)
        return None if found is None else found.name

    return DomainTools((
        *_mac_handlers(config, events, mac_files, grants, sessions, limits),
        TaskTools(tasks, projects, cards=TaskCards(TalkStore(config), events)),
        StepTools(tasks, StepService(task_store, expenses, comments, events)),
        CommentTools(tasks, CommentService(comments, task_store, events)),
        MoneyTools(MoneyService(project_store, expenses, events), projects, tasks),
        NoteTools(NoteService(notes, events), projects, journal=runs.journal),
        DayNoteTools(DayNoteService(DayNoteStore(config), events)),
        DocumentTools(DocumentService(documents, events), projects),
        ProjectTools(projects, bots),
        QuestionTools(QuestionService(QuestionStore(config), TalkStore(config), events), routine_store),
        RoutineTools(routine_store, ProposalService(ProposalStore(config), routine_store, TalkStore(config), events)),
        RoutineWrites(routine_store, routine_writer, owner_texts=partial(your_messages, config)),
        _routine_finish(routine_store, routine_writer),
        PlanTools(plans),
        JournalTools(runs.journal),
        TeamSteps(bots, TalkStore(config), events, SeenModelStore(config)),
        MemoryTools(MemoryService(MemoryStore(config), events), TalkStore(config), events, SummaryStore(config)),
        _skill_tools(config, events, bots, skills),
        *_instruction_tools(config, events, bots),
        _voice_tools(bots, events),
        *_program_handlers(config, events, desks, program_limits),
        *_connector_tools(config, events, bots, connectors, connector_client, connector_requests),
        _app_tools(config, bots, desks, apps),
    ), names=bot_name, observer=runs)


def _app_tools(config: Config, bots: Any, desks: Any, apps: Any) -> DomainHandler:
    """Install an app: the card tools on a bot's Linux computer, through the keeper's apps route."""
    from roost.apps.keeper import make_app_keeper
    from roost.apps.service import AppService
    from roost.apps.store import AppStore
    from roost.apps.tools import AppTools
    from roost.desk import DeskFactory

    if apps is None:
        apps = AppService(config, AppStore(config), make_app_keeper(config), bots,
                          desks if desks is not None else DeskFactory(config))
    return AppTools(apps)


def _voice_tools(bots: Any, events: EventHub) -> DomainHandler:
    """Voice §4: set_my_voice, the bot's own voice settings through the same service as the Info tab's save."""
    from roost.voice.service import VoiceSettingsService
    from roost.voice.tools import VoiceTools

    return VoiceTools(VoiceSettingsService(bots, events))


def _instruction_tools(config: Config, events: EventHub, bots: Any) -> tuple[DomainHandler, ...]:
    """'Update my instructions?': a bot offers new instructions for itself, which only the user's Accept writes;
    and update_my_instructions, a direct change with Undo in the user's own chat (A2)."""
    from roost.instruction_proposals.change_tools import InstructionChangeTools
    from roost.instruction_proposals.changes import InstructionChanges
    from roost.instruction_proposals.service import InstructionProposalService
    from roost.instruction_proposals.store import InstructionProposalStore
    from roost.instruction_proposals.tools import InstructionTools
    from roost.talk.store import TalkStore

    talk = TalkStore(config)
    return (InstructionTools(InstructionProposalService(InstructionProposalStore(config), bots, talk, events)),
            InstructionChangeTools(InstructionChanges(bots, talk, events, config)))


def _connector_tools(config: Config, events: EventHub, bots: Any, connectors: Any, client: Any,
                     requests: Any) -> tuple[DomainHandler, ...]:
    """Connectors: list them, call one (reads at once, writes after the user's Yes), ask the user for a key."""
    from roost.connectors.http import ConnectorClient
    from roost.connectors.request_tool import RequestTools
    from roost.connectors.requests import ConnectorRequestService, ConnectorRequestStore
    from roost.connectors.service import ConnectorService
    from roost.connectors.store import ConnectorStore
    from roost.connectors.tools import ConnectorTools
    from roost.talk.store import TalkStore

    service = connectors if connectors is not None else ConnectorService(ConnectorStore(config), bots)
    asks = requests if requests is not None else ConnectorRequestService(
        ConnectorRequestStore(config), service, TalkStore(config), events)
    return (ConnectorTools(service, client if client is not None else ConnectorClient()), RequestTools(service, asks))


def _skill_tools(config: Config, events: EventHub, bots: Any, skills: Any) -> DomainHandler:
    """Skills: list and read (and propose, which only stores a proposal for the user's Save skill)."""
    from roost.skills.proposals import SkillProposalService, SkillProposalStore
    from roost.skills.service import SkillService
    from roost.skills.store import SkillStore
    from roost.skills.tools import SkillTools
    from roost.talk.store import TalkStore

    service = skills if skills is not None else SkillService(SkillStore(config), events, bots)
    return SkillTools(service, SkillProposalService(SkillProposalStore(config), service, TalkStore(config), events))


def _program_handlers(config: Config, events: EventHub, desks: Any,
                      limits: Any = None) -> tuple[DomainHandler, ...]:
    """Programs: run_program and the file tools, in each bot's own workspace (a ``DeskFactory`` of its own when
    none is given: every bot has these tools, like the records')."""
    from roost.bots.store import BotStore
    from roost.desk import DeskFactory
    from roost.programs.marks import WorkspaceMarks
    from roost.programs.tools import ProgramTools
    from roost.talk.store import TalkStore

    factory = desks if desks is not None else DeskFactory(config)
    bots = BotStore(config)

    async def internet(user_id: str, bot_id: str) -> bool:
        bot = await bots.get(user_id, bot_id)
        return bot is not None and bot.workspace_internet

    return (ProgramTools(factory.for_bot, WorkspaceMarks(config), TalkStore(config), events, limits,
                         internet=internet),)


def _routine_service(config: Config, events: EventHub, routine_store: Any, bots: Any) -> Any:
    """The routine writer the direct routine tools use: no launcher or runner, since a tool never runs one now."""
    from roost.routines.runs import RoutineRunStore
    from roost.routines.service import RoutineService
    from roost.talk.store import TalkStore

    from roost.routines.watch_store import WatchStore

    return RoutineService(routine_store, RoutineRunStore(config), bots, TalkStore(config), events, None, None,
                          watches=WatchStore(config))


def _routine_finish(routine_store: Any, writer: Any) -> DomainHandler:
    """``finish_routine`` (owner, 2026-11-11): a routine's own run ends the routine that started it."""
    from roost.routines.finish import RoutineFinish

    return RoutineFinish(routine_store, writer)


def _mac_handlers(config: Config, events: EventHub, mac_files: Any, grants: Any, sessions: Any,
                  limits: Any) -> tuple[DomainHandler, ...]:
    """The Mac tools, when the Mac seam and the grants are given."""
    if mac_files is None or grants is None:
        return ()
    from roost.mac.marks import MacMarkStore
    from roost.mac.tools import MacTools
    from roost.mac.write_tools import MacWrites
    from roost.talk.store import TalkStore

    marks = MacMarkStore(config)
    return (MacTools(grants, mac_files, marks, sessions,
                     writes=MacWrites(grants, mac_files, marks, TalkStore(config), events, limits)),)
