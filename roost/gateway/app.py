"""FastAPI application factory — the Night-1 gateway.

``create_app`` builds a fully wired, self-contained Roost gateway: loads
(or accepts) a ``RoostConfig``, mounts the auth router, and reserves the
``app.state`` slots later tasks' routers read from. Each call produces
an independent app instance — nothing it sets up is module-global state
shared across instances (see ``roost/gateway/auth.py``'s docstring for
why that matters for rate limiters specifically).

Night-1's Task 2 only had auth + the database; Task 3 added the real
``BotStore``/``ActivityBoard`` (``roost/bots/``) and its router. Task 4
added ``TalkStore`` (``roost/talk/store.py``) and its router. Task 9
added the real ``DeskFactory`` (``roost/desk/``) and its router. Task 11
adds the real ``EventHub`` (``roost/events/hub.py``), its WebSocket
router, and the real ``TurnRunner`` (``roost/talk/runner.py``) on
``app.state.turns`` — ``POST /api/threads/{id}/messages`` (``roost/
gateway/routes/threads.py``) has called ``await request.app.state.turns
.start(...)`` unconditionally since Task 4; only the instance behind
that slot changes here.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from roost.approvals.executor import ApprovedCalls
from roost.talk.new_site import PageOpens
from roost.computer_use.reruns import ScreenReruns
from roost.computer_use.session import ComputerUseLease
from roost.computer_use.steps import ComputerSteps
from roost.lessons.service import LessonService
from roost.lessons.signals import LessonSignals
from roost.lessons.steps import LessonSteps
from roost.talk.run_steps import RunStepsLog
from roost.approvals.service import ApprovalService
from roost.approvals.sessions import SessionOks
from roost.approvals.store import ApprovalStore
from roost.approvals.wiring import ApprovalWiring
from roost.bots.main_bot import ensure_main_bots
from roost.bots.status import ActivityBoard
from roost.bots.store import BotStore
from roost.config import RoostConfig, load_config
from roost.constants import (
    LOGIN_RATE_LIMIT_PER_IP,
    LOGIN_RATE_LIMIT_PER_USERNAME,
    LOGIN_RATE_WINDOW_S,
    LOGIN_USERNAME_WINDOW_S,
    REGISTER_RATE_LIMIT_PER_IP,
    REGISTER_RATE_WINDOW_S,
)
from roost.db.connection import close_pool, init_db
from roost.desk import DeskFactory
from roost.desk.control import ControlLock
from roost.desk.main_browser import make_main_browser
from roost.documents.service import DocumentService
from roost.documents.store import DocumentStore
from roost.events.hub import EventHub
from roost.models_check.start import start_model_check, stop_model_check
from roost.models_check.store import SeenModelStore
from roost.gateway.auth import RateLimiter, auth_router
from roost.gateway.routes.timezone import timezone_router
from roost.gateway.routes.approvals import approvals_router
from roost.media.store import ChatMediaStore
from roost.gateway.routes.bot_picture import bot_picture_router
from roost.gateway.routes.media import media_router
from roost.gateway.routes.bots import bots_router
from roost.gateway.routes.chats import chats_router
from roost.gateway.routes.comments import comments_router
from roost.gateway.routes.dates import dates_router
from roost.gateway.routes.desk import desk_router
from roost.gateway.routes.workspace import workspace_router
from roost.gateway.routes.documents import documents_router
from roost.gateway.routes.events import events_router
from roost.gateway.live_socket import LiveViewers
from roost.gateway.routes.health import health_router
from roost.gateway.routes.journal import journal_router
from roost.gateway.routes.live import live_router
from roost.gateway.routes.mac import mac_router
from roost.gateway.routes.memories import memories_router
from roost.gateway.routes.models import models_router
from roost.gateway.routes.money import money_router
from roost.gateway.routes.money_edit import money_edit_router
from roost.gateway.routes.money_line import money_line_router
from roost.gateway.routes.money_recurring import money_recurring_router
from roost.gateway.routes.money_range import money_range_router
from roost.gateway.routes.money_reports import money_reports_router
from roost.gateway.routes.day_notes import day_notes_router
from roost.gateway.routes.notes import notes_router
from roost.gateway.routes.profile import profile_router
from roost.gateway.routes.projects import projects_router
from roost.gateway.routes.rooms import rooms_router
from roost.gateway.routes.plan import plan_router
from roost.gateway.routes.routine_asks import routine_asks_router
from roost.gateway.routes.routines import routines_router
from roost.gateway.routes.standing import standing_router
from roost.gateway.routes.routines_hub import routines_hub_router
from roost.gateway.routes.skill_proposals import skill_proposals_router
from roost.gateway.routes.instruction_changes import instruction_changes_router
from roost.gateway.routes.instruction_proposals import instruction_proposals_router
from roost.gateway.routes.skills import skills_router
from roost.gateway.routes.teach import teach_router
from roost.gateway.routes.connectors import connector_requests_router, connectors_router
from roost.gateway.routes.mobile import mobile_router
from roost.gateway.routes.my_turn import my_turn_router
from roost.gateway.routes.usage import usage_router
from roost.gateway.routes.static import mount_static_if_built
from roost.gateway.routes.stuck import stuck_router
from roost.gateway.routes.vault import vault_router
from roost.gateway.routes.apps import apps_router
from roost.signin.check import SignInCheck
from roost.signin.service import SignInService
from roost.gateway.routes.vault_export import vault_export_router
from roost.vault.service import VaultService
from roost.work.queue import WorkQueue
from roost.vault.store import VaultStore
from roost.gateway.routes.task_detail import detail_router
from roost.gateway.routes.task_steps import steps_router
from roost.gateway.routes.task_views import task_views_router
from roost.gateway.routes.task_offline import offline_router
from roost.gateway.routes.tasks import tasks_router
from roost.gateway.routes.team import team_router
from roost.gateway.routes.templates import templates_router
from roost.gateway.routes.threads import threads_router
from roost.gateway.routes.voice import speak_lock_for, voice_router
from roost.gateway.routes.voice_live import voice_live_router
from roost.gateway.routes.work import work_router
from roost.voice.calls import CallRegistry
from roost.voice.client import make_voice
from roost.voice.context import HearHints
from roost.voice.correct import SpeechCorrector
from roost.voice.speak_ahead import SpeakAhead
from roost.voice.spoken import SpeechCache
from roost.voice.tasks import TrackedTasks
from roost.llm.registry import make_model, make_worker_model
from roost.mac.files import make_mac_files
from roost.mac.grant_service import GrantService, GrantSync
from roost.mac.grants import GrantStore
from roost.mac.limits import MacLimits
from roost.mac.undo import MacUndo
from roost.choices.decisions import DecisionBook
from roost.memory.hooks import MemoryHooks
from roost.money.expense_store import ExpenseStore
from roost.money.project_store import ProjectStore
from roost.money.service import MoneyService
from roost.day_notes.service import DayNoteService
from roost.day_notes.store import DayNoteStore
from roost.journal.runs import JournalRuns
from roost.journal.service import JournalService
from roost.journal.store import JournalStore
from roost.day_notes.service import madrid_today
from roost.vault_export.exporter import VaultExporter
from roost.vault_export.scheduler import ExportScheduler
from roost.vault_export.sources import ExportSources
from roost.vault_export.store import VaultExportStore
from roost.notes.service import NoteService
from roost.notes.store import NoteStore
from roost.projects.service import ProjectService
from roost.rooms.service import RoomService
from roost.plan.service import PlanService
from roost.plan.store import PlanStore
from roost.routines.hooks import RoutineHooks
from roost.routines.hub import RoutinesHub
from roost.routines.launcher import RoutineLauncher
from roost.questions.service import QuestionService
from roost.questions.store import QuestionStore
from roost.routines.proposals import ProposalService, ProposalStore
from roost.routines.runs import RoutineRunStore
from roost.routines.service import RoutineService
from roost.routines.start import start_scheduler, stop_scheduler
from roost.routines.watch import build_watch_checker
from roost.routines.watch_store import WatchStore
from roost.routines.store import RoutineStore
from roost.skills.proposals import SkillProposalService, SkillProposalStore
from roost.instruction_proposals.changes import InstructionChanges
from roost.instruction_proposals.service import InstructionProposalService
from roost.instruction_proposals.store import InstructionProposalStore
from roost.skills.service import SkillService
from roost.skills.store import SkillStore
from roost.teach.service import TeachService
from roost.teach.store import TeachStore
from roost.connectors.http import ConnectorClient
from roost.connectors.requests import ConnectorRequestService, ConnectorRequestStore
from roost.connectors.service import ConnectorService
from roost.connectors.store import ConnectorStore
from roost.usage.store import TokenUsageStore
from roost.usage.reading import NoUsageSource
from roost.rooms.store import RoomStore
from roost.signin.secret_entry import SecretEntry
from roost.payments.cards import CardStore
from roost.vault.passwords import VaultPasswordStore
from roost.gateway.routes.vault_passwords import vault_passwords_router
from roost.payments.entry import PayEntry
from roost.gateway.routes.payments import payments_router
from roost.stuck.service import StuckService
from roost.stuck.store import StuckStore
from roost.talk.domain_tools import build_domain_tools
from roost.programs.tools import ProgramLimits
from roost.standing.service import PermissionService
from roost.standing.store import PermissionStore
from roost.talk.gate import Gate
from roost.talk.mentions import MentionRouter
from roost.talk.runner import TurnRunner
from roost.talk.store import TalkStore
from roost.tasks.comment_service import CommentService
from roost.tasks.comment_store import CommentStore
from roost.tasks.service import TaskService
from roost.tasks.step_service import StepService
from roost.tasks.store import TaskStore
from roost.timezones import load_local_tz


def create_app(config: RoostConfig | None = None) -> FastAPI:
    """Build the Roost gateway app, wired with ``config`` (or a loaded default)."""
    resolved_config = config if config is not None else load_config()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # The primary init path on a real server boot. Starlette's
        # TestClient, used WITHOUT `with TestClient(app) as c:`, never
        # runs this at all — ensure_initialized() calls inside the auth
        # routes are the fallback for that case (see connection.py).
        await init_db(resolved_config)
        # The install's time zone: the account's own (owner, 2026-11-09), before anything reads a day or a clock.
        await load_local_tz(resolved_config)
        # Your Mac: the keeper learns the shared folders now and again every few seconds.
        app.state.grant_sync.start()
        # A bot left ON_IT across a restart has no live run to resume
        # into — see BotStore.reset_on_boot's docstring. Passing
        # app.state.events lets it publish a real `bot_status` RESTING
        # frame for each bot it resets, so a client across the restart
        # (or a resumed replay) sees the reset instead of a stale on_it.
        await app.state.bots.reset_on_boot(app.state.events)
        # Stuck flow R9: a bot whose Stuck card is still open shows Stuck again
        # (after reset_on_boot, which moved an interrupted On it bot to Resting).
        await app.state.turns.restore_stuck_on_boot()
        await app.state.turns.restore_asking_on_boot()
        # The Sign-in card: a "No, this time" site whose task ended while Roost was down is cleared now.
        await app.state.signin.sweep_on_boot()
        # S1 D4: every account has its main bot from the start (stars a Chief, or creates one).
        await ensure_main_bots(resolved_config, app.state.bots)
        # Spec §4.2 / step 5: re-queue what the old process was working on,
        # note interrupted calls, then let every bot with queued work drain.
        await app.state.turns.recover_on_boot()
        await app.state.turns.resume_all()
        app.state.model_check_task = start_model_check(resolved_config, app.state.seen_models)
        # Routines: the one scheduler, started after the queue has resumed and stopped before the pool closes.
        app.state.scheduler_task = start_scheduler(app.state)
        app.state.vault_export_scheduler.start()
        try:
            yield
        finally:
            await app.state.vault_export_scheduler.stop()
            await app.state.grant_sync.stop()
            await stop_model_check(app.state.model_check_task)
            await stop_scheduler(app.state.scheduler_task)
            await app.state.mentions.close()
            await app.state.speak_ahead.close()
            await app.state.voice_tasks.close()
            await app.state.voice.aclose()
            await close_pool()

    app = FastAPI(title="Roost", lifespan=lifespan)

    app.state.config = resolved_config
    app.state.model_check_task = None
    app.state.scheduler_task = None

    # Rate limiters live on app.state (constructed fresh per create_app()
    # call), never as module globals — see roost/gateway/auth.py. Scripted
    # mode (E2E only, never production) is exempt — see RateLimiter.disabled.
    _e2e = resolved_config.model_mode == "scripted"
    app.state.login_limiter = RateLimiter(LOGIN_RATE_LIMIT_PER_IP, LOGIN_RATE_WINDOW_S, disabled=_e2e)
    app.state.login_username_limiter = RateLimiter(LOGIN_RATE_LIMIT_PER_USERNAME, LOGIN_USERNAME_WINDOW_S, disabled=_e2e)
    app.state.register_limiter = RateLimiter(REGISTER_RATE_LIMIT_PER_IP, REGISTER_RATE_WINDOW_S, disabled=_e2e)

    app.state.bots = BotStore(resolved_config)
    app.state.activity_board = ActivityBoard()
    app.state.seen_models = SeenModelStore(resolved_config)
    app.state.talk = TalkStore(resolved_config)
    app.state.media = ChatMediaStore(resolved_config)   # chat pictures (owner, 2026-11-05)
    app.state.routine_store = RoutineStore(resolved_config, app.state.talk)
    app.state.routine_runs = RoutineRunStore(resolved_config)
    app.state.watch_store = WatchStore(resolved_config)     # "Only run when the page changes": the last snapshots
    app.state.desks = DeskFactory(resolved_config)
    app.state.events = EventHub(resolved_config)
    app.state.skills = SkillService(SkillStore(resolved_config), app.state.events, app.state.bots)
    app.state.skill_proposals = SkillProposalService(
        SkillProposalStore(resolved_config), app.state.skills, app.state.talk, app.state.events)
    app.state.instruction_proposals = InstructionProposalService(
        InstructionProposalStore(resolved_config), app.state.bots, app.state.talk, app.state.events)
    app.state.instruction_changes = InstructionChanges(
        app.state.bots, app.state.talk, app.state.events, resolved_config)
    # Connectors: a service's HTTP API with the user's key, which no route returns.
    app.state.connectors = ConnectorService(ConnectorStore(resolved_config), app.state.bots)
    app.state.voice = make_voice(resolved_config)          # the Mac's voice service (roost/voice/)
    app.state.voice_cache = SpeechCache()
    app.state.voice_hearing = {}                           # one hearing at a time per user (its lock)
    app.state.voice_speak_locks = {}                       # one spoken part at a time per user
    app.state.voice_tasks = TrackedTasks()                 # warm-ups and pre-made lines nobody waits for
    app.state.voice_warmed_at = float("-inf")              # the last warm a call kicked (monotonic)
    app.state.calls = CallRegistry()                       # call mode (§3): which threads are in a call
    # Correct my English (§4): a spoken message's correction, by the worker model, in the background.
    app.state.token_usage = TokenUsageStore(resolved_config)   # token usage: per bot, day, kind and model
    app.state.connector_client = ConnectorClient()
    app.state.connector_requests = ConnectorRequestService(
        ConnectorRequestStore(resolved_config), app.state.connectors, app.state.talk, app.state.events)
    app.state.tasks = TaskService(TaskStore(resolved_config), app.state.events)
    # Redesign P3: a task's steps and comments, behind the same doors as the bots' tools.
    app.state.steps = StepService(TaskStore(resolved_config), ExpenseStore(resolved_config),
                                  CommentStore(resolved_config), app.state.events)
    app.state.comments = CommentService(CommentStore(resolved_config), TaskStore(resolved_config), app.state.events)
    app.state.money = MoneyService(ProjectStore(resolved_config), ExpenseStore(resolved_config), app.state.events)
    app.state.notes = NoteService(NoteStore(resolved_config), app.state.events)
    app.state.day_notes = DayNoteService(DayNoteStore(resolved_config), app.state.events)
    app.state.documents = DocumentService(DocumentStore(resolved_config), app.state.events)
    # Projects hub (P1, H10): the Projects tab and a project's page. Stores hold no state, so these
    # instances share the database with the money, task, note and document services above.
    app.state.projects = ProjectService(
        ProjectStore(resolved_config), ExpenseStore(resolved_config), TaskStore(resolved_config),
        NoteStore(resolved_config), DocumentStore(resolved_config), app.state.bots, app.state.events,
    )
    app.state.rooms = RoomStore(resolved_config)
    app.state.control = ControlLock()
    # Teach a task: you show a bot a task on its Linux computer; the worker drafts a skill proposal from the steps.
    app.state.teach = TeachService(TeachStore(resolved_config), app.state.skill_proposals, app.state.talk,
                                   app.state.control, make_worker_model(resolved_config),
                                   usage=app.state.token_usage)
    app.state.cu_leases = ComputerUseLease()     # C3: one screen loop per computer, in memory like the control lock
    app.state.lesson_signals = LessonSignals()   # lessons (L1): what went wrong in a run, until it ends
    app.state.vault_store = VaultStore(resolved_config)
    app.state.live_viewers = LiveViewers()
    app.state.stuck = StuckStore(resolved_config)
    app.state.memory_hooks = MemoryHooks(
        resolved_config, app.state.talk, app.state.events, worker=make_worker_model(resolved_config),
    )
    app.state.memories = app.state.memory_hooks.service
    # Voice tuning D1: the names and site names a transcription and its correction read first, per user and bot.
    app.state.hear_hints = HearHints(app.state.bots, app.state.memories, app.state.talk, app.state.vault_store)
    # Correct what I say (voice tuning D3; §4 before it): before the send for the composer, or in the background.
    app.state.english = SpeechCorrector(app.state.talk, app.state.events, app.state.bots,
                                        make_worker_model(resolved_config), app.state.voice_tasks,
                                        usage=app.state.token_usage, hints=app.state.hear_hints)
    app.state.decisions = DecisionBook(app.state.memories)
    # Your Mac (approval modes + folders): the seam to the keeper (the fake in fake mode) and the grants.
    app.state.mac_files = make_mac_files(resolved_config)
    grant_store = GrantStore(resolved_config)
    app.state.grant_store = grant_store
    app.state.grants = GrantService(grant_store, app.state.bots, app.state.mac_files)
    # Approval modes: a bot that must ask parks its run on an Ask card (approvals/); "Yes" runs the stored call.
    app.state.approvals = ApprovalStore(resolved_config)
    app.state.session_oks = SessionOks()
    app.state.grants.set_revoke_hook(lambda user_id, grant_id: app.state.session_oks.end_for_grant(user_id, grant_id))
    app.state.mac_limits = MacLimits()
    # The Plan: one service, so the bot's tools and the after-run note share their per-run counters.
    app.state.plan = PlanService(PlanStore(resolved_config), app.state.events, app.state.bots, app.state.talk)
    # The Bot Journal: the bots' tools, the routes and each run's line share one service.
    app.state.journal = JournalService(JournalStore(resolved_config), app.state.events)
    app.state.journal_runs = JournalRuns(app.state.journal)
    # Programs: one workspace lock per bot, shared by the program tools and Wipe workspace.
    app.state.program_limits = ProgramLimits()
    _wire_apps(app, resolved_config)
    domain = build_domain_tools(resolved_config, app.state.events, mac_files=app.state.mac_files,
                                grants=app.state.grants, sessions=app.state.session_oks,
                                limits=app.state.mac_limits, plan=app.state.plan,
                                skills=app.state.skills, journal=app.state.journal_runs, desks=app.state.desks,
                                connectors=app.state.connectors, connector_client=app.state.connector_client,
                                connector_requests=app.state.connector_requests,
                                program_limits=app.state.program_limits, apps=app.state.apps)
    app.state.usage = NoUsageSource()      # no way to read the usage limit yet: the full-limit switch stays off
    app.state.question_store = QuestionStore(resolved_config)
    app.state.questions = QuestionService(
        app.state.question_store, app.state.talk, app.state.events, decisions=app.state.decisions)
    # Standing permissions: what an approved routine may post, send or submit without asking again.
    app.state.standing = PermissionService(PermissionStore(resolved_config))
    app.state.routine_hooks = RoutineHooks(
        app.state.talk, app.state.events, app.state.routine_runs, app.state.routine_store,
        answers=app.state.questions.answers_for_routine, permissions=PermissionStore(resolved_config),
        watches=app.state.watch_store,
    )
    # The Sign-in card: Open sign-in, the "No, this time" clear after the task, and Sign out.
    app.state.signin = SignInService(app.state.stuck, app.state.vault_store, app.state.bots, app.state.desks,
                                     app.state.control, WorkQueue(resolved_config), app.state.approvals)
    # Lessons (L2): a run of your own chat that went wrong offers at most one Skill card, from trusted text only.
    app.state.lesson_steps = LessonSteps()
    app.state.events.add_listener(app.state.lesson_steps.listen)
    app.state.lessons = LessonService(
        signals=app.state.lesson_signals, steps=app.state.lesson_steps, skills=app.state.skills,
        proposals=app.state.skill_proposals, worker=make_worker_model(resolved_config),
        approvals=app.state.approvals, queue=WorkQueue(resolved_config))
    app.state.turns = TurnRunner(
        resolved_config, app.state.bots, app.state.talk, app.state.events,
        app.state.desks, make_model(resolved_config), app.state.activity_board,
        rooms=app.state.rooms, control=app.state.control, stuck=app.state.stuck,
        memory=app.state.memory_hooks, seen_models=app.state.seen_models,
        approvals=ApprovalWiring(app.state.approvals, app.state.session_oks, app.state.mac_limits, app.state.grants),
        domain=domain, decisions=app.state.decisions, routines=app.state.routine_hooks,
        vault=app.state.vault_store, usage=app.state.usage, plan=app.state.plan, cu_leases=app.state.cu_leases,
        token_usage=app.state.token_usage,
        skills=app.state.skills, signin=app.state.signin, calls=app.state.calls, lessons=app.state.lessons,
        lesson_signals=app.state.lesson_signals,
    )
    # Speak-ahead: a call reply is spoken sentence by sentence as it streams (roost/voice/speak_ahead.py).
    app.state.speak_ahead = SpeakAhead(
        app.state.events, app.state.bots, app.state.voice, app.state.voice_cache, app.state.calls,
        speak_lock_for=lambda user_id: speak_lock_for(app.state.voice_speak_locks, user_id))
    app.state.events.add_listener(app.state.speak_ahead.listen)
    app.state.routine_hooks.attach(app.state.turns, app.state.approvals, app.state.bots)
    app.state.watch_checker = build_watch_checker(app.state)
    app.state.questions.attach(app.state.turns)
    app.state.connector_requests.attach(app.state.turns)
    app.state.vault = VaultService(app.state.vault_store, app.state.talk, app.state.events, app.state.turns)
    app.state.routines = RoutineService(
        app.state.routine_store, app.state.routine_runs, app.state.bots, app.state.talk, app.state.events,
        RoutineLauncher(app.state.talk, app.state.turns, app.state.routine_runs, app.state.events), app.state.turns,
        watches=app.state.watch_store,
    )
    # @bot in a bot's chat: your message handed to another of your bots, its answer back in the same chat.
    app.state.mentions = MentionRouter(app.state.talk, app.state.events, app.state.turns)
    app.state.routines_hub = RoutinesHub(
        app.state.routines, app.state.routine_store, app.state.routine_runs, app.state.bots)
    app.state.proposals = ProposalService(
        ProposalStore(resolved_config), app.state.routine_store, app.state.talk, app.state.events,
        writer=app.state.routines, standing=app.state.standing)
    app.state.mac_undo = MacUndo(app.state.talk, app.state.events, app.state.grants, app.state.mac_files)
    app.state.approval_service = ApprovalService(
        app.state.approvals, app.state.talk, app.state.events, app.state.turns,
        ApprovedCalls(app.state.turns.domain, Gate(resolved_config), app.state.talk, app.state.events,
                      screen=ScreenReruns(resolved_config, app.state.bots, app.state.desks, Gate(resolved_config),
                                          app.state.events, app.state.cu_leases, app.state.control,
                                          signals=app.state.lesson_signals),
                      pages=PageOpens(app.state.bots, app.state.desks)),
        app.state.session_oks, decisions=app.state.decisions,
    )
    app.state.room_service = RoomService(app.state.bots, app.state.talk, app.state.rooms, app.state.turns)
    # Stuck flow (Task 7): the card's buttons. Built after `turns`, which `/clear` queues continue items on.
    # The main Brave seam is the fake in fake mode and the keeper otherwise (R8).
    app.state.main_browser = make_main_browser(resolved_config)
    app.state.stuck_service = StuckService(
        app.state.stuck, app.state.talk, app.state.events, app.state.turns,
        app.state.control, app.state.main_browser, app.state.vault,
        signed_in=SignInCheck(app.state.bots, app.state.desks),
    )
    # Vault: passwords (owner, 2026-11-08): your site logins, sealed; the model never sees one.
    app.state.vault_passwords = VaultPasswordStore(resolved_config)
    # B3: the Sign-in card's masked field types your password or code into the box; a password is kept only when
    # you ask (Save in Vault).
    app.state.secret_entry = SecretEntry(
        app.state.stuck, app.state.stuck_service, app.state.bots, app.state.desks, app.state.control,
        app.state.cu_leases, Gate(resolved_config), vault=app.state.vault_passwords,
    )
    # The Pay card (owner, 2026-11-05): your card into the page's card boxes, then the stored Pay click; Vault: cards.
    app.state.payment_cards = CardStore(resolved_config)
    app.state.pay_entry = PayEntry(
        app.state.approval_service, app.state.talk, app.state.bots, app.state.desks, app.state.control,
        app.state.cu_leases, Gate(resolved_config), app.state.payment_cards, today=madrid_today,
    )

    app.state.grant_sync = GrantSync(grant_store, app.state.mac_files)
    # The Obsidian export: one pass at a time per user, debounced after changes, through the keeper's file API.
    app.state.vault_export_store = VaultExportStore(resolved_config)
    app.state.vault_exporter = VaultExporter(
        app.state.vault_export_store, ExportSources(resolved_config), app.state.mac_files, grant_store,
        app.state.events, today=madrid_today)
    app.state.vault_export_scheduler = ExportScheduler(app.state.vault_exporter.run)
    app.state.events.add_listener(app.state.vault_export_scheduler.listener)
    app.state.computer_steps = ComputerSteps()        # the computer card: each bot's current run's steps
    app.state.events.add_listener(app.state.computer_steps.listen)
    app.state.run_steps = RunStepsLog()              # the activity pill: each bot's current run's steps
    app.state.events.add_listener(app.state.run_steps.listen)

    app.include_router(health_router)
    app.include_router(payments_router)
    app.include_router(vault_passwords_router)
    app.include_router(auth_router)
    app.include_router(timezone_router)
    app.include_router(bots_router)
    app.include_router(bot_picture_router)
    app.include_router(media_router)
    app.include_router(models_router)
    app.include_router(voice_router)
    app.include_router(voice_live_router)
    app.include_router(work_router)
    app.include_router(team_router)
    app.include_router(templates_router)
    app.include_router(offline_router)
    app.include_router(tasks_router)
    app.include_router(task_views_router)
    app.include_router(steps_router)
    app.include_router(detail_router)
    app.include_router(comments_router)
    app.include_router(dates_router)
    app.include_router(money_router)
    app.include_router(money_line_router)
    app.include_router(money_edit_router)
    app.include_router(money_recurring_router)
    app.include_router(money_reports_router)
    app.include_router(money_range_router)
    app.include_router(projects_router)
    app.include_router(notes_router)
    app.include_router(day_notes_router)
    app.include_router(journal_router)
    app.include_router(documents_router)
    app.include_router(threads_router)
    app.include_router(memories_router)
    app.include_router(desk_router)
    app.include_router(workspace_router)
    app.include_router(events_router)
    app.include_router(live_router)
    app.include_router(rooms_router)
    app.include_router(profile_router)
    app.include_router(chats_router)
    app.include_router(routines_hub_router)
    app.include_router(routines_router)
    app.include_router(standing_router)
    app.include_router(plan_router)
    app.include_router(routine_asks_router)
    app.include_router(usage_router)
    app.include_router(stuck_router)
    app.include_router(vault_router)
    app.include_router(apps_router)
    app.include_router(vault_export_router)
    app.include_router(approvals_router)
    app.include_router(mac_router)
    app.include_router(skills_router)
    app.include_router(skill_proposals_router)
    app.include_router(teach_router)
    app.include_router(instruction_proposals_router)
    app.include_router(instruction_changes_router)
    app.include_router(connectors_router)
    app.include_router(connector_requests_router)
    app.include_router(my_turn_router)
    app.include_router(mobile_router)
    # Task 12 (web): serves web/dist at "/" with SPA fallback, but only
    # once it's actually been built (roost/gateway/routes/static.py) —
    # mounted last so it never shadows an /api/* route above.
    mount_static_if_built(app)
    return app


def _wire_apps(app: FastAPI, config: RoostConfig) -> None:
    """Install an app: the bots' card tools, the Computer tab's list, and the reinstall after a fresh start."""
    from roost.apps.boot import AppReinstaller
    from roost.apps.keeper import make_app_keeper
    from roost.apps.service import AppService
    from roost.apps.store import AppStore

    app.state.app_keeper = make_app_keeper(config)
    app.state.apps = AppService(config, AppStore(config), app.state.app_keeper, app.state.bots, app.state.desks)
    app.state.app_reinstaller = AppReinstaller(app.state.apps)
    app.state.desks.set_boot_hook(app.state.app_reinstaller.on_fresh)
