"""Versioned, additive schema migrations over the Night-1 baseline.

``schema.sql`` is the frozen baseline (schema version 0: what the first
deployed gateway created in ``~/Roost/data/roost.db``). Every change since
is a ``Migration`` here, applied in order by ``apply_migrations`` and
recorded in SQLite's own ``PRAGMA user_version``. Rules, because a real
account lives in that file:

- additive only: new tables, new indexes, new nullable or defaulted
  columns — never a DROP, a rename or a table rebuild; a backfill
  ``INSERT OR IGNORE ... SELECT`` into a table the same migration creates
  is allowed;
- idempotent: ``CREATE ... IF NOT EXISTS`` and ``AddColumn`` (which checks
  ``PRAGMA table_info`` first), so re-running a step can never fail;
- atomic: one migration is one transaction together with its
  ``user_version`` bump; on any error it is rolled back and
  ``MigrationError`` is raised (``init_db`` backs the file up first).
"""


from __future__ import annotations

import aiosqlite

from roost.constants import TIMEZONE_LEGACY
from roost.db.migration_types import AddColumn, Migration, MigrationError, Step
from roost.db.migration_sql import (
    _APPROVAL_CARDS,
    _BOT_APPS,
    _ROUTINE_PERMISSIONS,
    _BACKFILL_WEB_ROLE,
    _BOT_PLANS,
    _BOT_QUESTIONS,
    _BOT_JOURNALS,
    _CONNECTOR_REQUESTS,
    _CONNECTORS,
    _BOT_ROLES,
    _BOT_SKILL_OFF,
    _BUDGET_ALERTS,
    _CHAT_SUMMARIES,
    _DAY_NOTES,
    _DOCUMENTS,
    _IMPORT_LINKS,
    _INSTRUCTION_PROPOSALS,
    _MAC_FILE_MARKS,
    _MAC_GRANTS,
    _MEMORIES,
    _MODEL_DISMISSALS,
    _MONEY_EXPENSES,
    _MONEY_PROJECTS,
    _MONEY_RECURRING,
    _MONEY_TOPUPS,
    _NOTES,
    _REMINDER_SENDS,
    _ROUTINES,
    _ROUTINE_PROPOSALS,
    _ROUTINE_RUNS,
    _RUNS,
    _SEEN_MODELS,
    _SITE_LOGINS,
    _SKILLS,
    _SKILL_PROPOSALS,
    _STUCK_CARDS,
    _TASKS,
    _TASK_COMMENTS,
    _TEACH_SESSIONS,
    _VAULT_EXPORTS,
    _WORK_ITEMS,
)

__all__ = ["AddColumn", "Migration", "MigrationError", "Step"]

MIGRATIONS: tuple[Migration, ...] = (
    Migration(1, "work queue", (
        _WORK_ITEMS,
        "CREATE INDEX IF NOT EXISTS idx_work_items_queue ON work_items(user_id, bot_id, state)",
        "CREATE INDEX IF NOT EXISTS idx_work_items_parent ON work_items(user_id, parent_item_id)",
        _RUNS,
        "CREATE INDEX IF NOT EXISTS idx_runs_bot_day ON runs(user_id, bot_id, started_at)",
        AddColumn("messages", "kind", "TEXT NOT NULL DEFAULT 'text'"),
        AddColumn("messages", "author_bot_id", "TEXT"),
        AddColumn("bots", "off_duty", "INTEGER NOT NULL DEFAULT 0"),
    )),
    Migration(2, "main bot", (
        AddColumn("bots", "is_primary", "INTEGER NOT NULL DEFAULT 0"),
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_bots_one_primary ON bots(user_id) WHERE is_primary = 1",
    )),
    Migration(3, "handoff threads", (
        AddColumn("threads", "peer_bot_id", "TEXT REFERENCES bots(id) ON DELETE SET NULL"),
        "CREATE INDEX IF NOT EXISTS idx_threads_peer ON threads(user_id, bot_id, peer_bot_id)",
    )),
    Migration(4, "rooms", (
        """CREATE TABLE IF NOT EXISTS rooms (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            coordinator_bot_id TEXT REFERENCES bots(id) ON DELETE SET NULL,
            thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS room_members (
            room_id TEXT NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
            bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            added_at TEXT NOT NULL,
            PRIMARY KEY (room_id, bot_id)
        )""",
        "CREATE INDEX IF NOT EXISTS idx_rooms_user ON rooms(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_room_members_bot ON room_members(user_id, bot_id)",
    )),
    Migration(5, "bot roles", (
        _BOT_ROLES,
        "CREATE INDEX IF NOT EXISTS idx_bot_roles_user ON bot_roles(user_id, role_id)",
        _BACKFILL_WEB_ROLE,
    )),
    Migration(6, "gate provenance", (
        AddColumn("audit", "reason", "TEXT"),
        AddColumn("audit", "tainted", "INTEGER NOT NULL DEFAULT 0"),
        AddColumn("work_items", "link_scope", "TEXT"),
    )),
    Migration(7, "tasks", (
        _TASKS,
        "CREATE INDEX IF NOT EXISTS idx_tasks_user_status ON tasks(user_id, status, due_date)",
        "CREATE INDEX IF NOT EXISTS idx_tasks_user_reminder ON tasks(user_id, reminder_at)",
    )),
    Migration(8, "money", (
        _MONEY_PROJECTS,
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_money_projects_key ON money_projects(user_id, name_key) "
        "WHERE deleted_at IS NULL",
        _MONEY_EXPENSES,
        "CREATE INDEX IF NOT EXISTS idx_money_expenses_month ON money_expenses(user_id, spent_at)",
        "CREATE INDEX IF NOT EXISTS idx_money_expenses_project ON money_expenses(user_id, project_id)",
        _MONEY_TOPUPS,
        "CREATE INDEX IF NOT EXISTS idx_money_topups_project ON money_topups(user_id, project_id)",
    )),
    Migration(9, "notes", (
        _NOTES,
        "CREATE INDEX IF NOT EXISTS idx_notes_user_updated ON notes(user_id, updated_at)",
        "CREATE INDEX IF NOT EXISTS idx_notes_user_title ON notes(user_id, title_key)",
    )),
    Migration(10, "documents", (
        _DOCUMENTS,
        "CREATE INDEX IF NOT EXISTS idx_documents_user ON documents(user_id, kind, updated_at)",
    )),
    Migration(11, "bot notify", (
        # S1.10: tell the user when this bot finishes or needs them. Plaintext flag, default on.
        AddColumn("bots", "notify", "INTEGER NOT NULL DEFAULT 1"),
    )),
    Migration(12, "stuck cards", (
        _STUCK_CARDS,
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_stuck_cards_one_open ON stuck_cards(user_id, bot_id) "
        "WHERE state = 'open'",
        "CREATE INDEX IF NOT EXISTS idx_stuck_cards_user ON stuck_cards(user_id, state, created_at)",
    )),
    # Projects hub: money_projects is the project (P8). Every step is an added nullable or
    # defaulted column, or an index. Status values are plaintext on columns with no CHECK:
    # money_projects.status active|archived, money_expenses.status posted|void, tasks.status gains failed.
    Migration(13, "projects hub", (
        AddColumn("money_projects", "color", "TEXT"),
        AddColumn("money_projects", "start_date", "TEXT"),
        AddColumn("money_projects", "due_date", "TEXT"),
        AddColumn("money_projects", "monthly_budget", "TEXT"),          # enc:v2 decimal string
        AddColumn("money_projects", "lead_bot_id", "TEXT REFERENCES bots(id) ON DELETE SET NULL"),
        AddColumn("money_expenses", "step_id", "TEXT"),
        AddColumn("money_expenses", "is_favorite", "INTEGER NOT NULL DEFAULT 0"),
        AddColumn("money_topups", "topup_id", "TEXT"),
        AddColumn("tasks", "project_id", "TEXT REFERENCES money_projects(id) ON DELETE SET NULL"),
        AddColumn("tasks", "allocated_budget", "TEXT"),                   # enc:v2 decimal string
        AddColumn("notes", "project_id", "TEXT REFERENCES money_projects(id) ON DELETE SET NULL"),
        AddColumn("documents", "project_id", "TEXT REFERENCES money_projects(id) ON DELETE SET NULL"),
        "CREATE INDEX IF NOT EXISTS idx_tasks_user_project ON tasks(user_id, project_id)",
        "CREATE INDEX IF NOT EXISTS idx_notes_user_project ON notes(user_id, project_id)",
        "CREATE INDEX IF NOT EXISTS idx_documents_user_project ON documents(user_id, project_id)",
    )),
    # Redesign P3. Live control's site_logins, planned as v14 before this, takes v15.
    Migration(14, "task comments", (
        _TASK_COMMENTS,
        "CREATE INDEX IF NOT EXISTS idx_task_comments_task ON task_comments(user_id, task_id, created_at)",
    )),
    # Memory and endless chat. Live control's site_logins, last planned as v15, takes v16.
    Migration(15, "memory", (
        _MEMORIES,
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_memories_fingerprint ON memories(user_id, scope, fingerprint)",
        "CREATE INDEX IF NOT EXISTS idx_memories_scope ON memories(user_id, scope, archived_at)",
        _CHAT_SUMMARIES,
        "CREATE INDEX IF NOT EXISTS idx_chat_summaries_thread ON chat_summaries(user_id, thread_id, created_at)",
    )),
    # Polish R1. Live control's site_logins, last planned as v16, takes v17.
    Migration(16, "bot groups", (
        AddColumn("bots", "group_label", "TEXT"),   # enc:v2, AAD bots:group_label; NULL: no label
    )),
    # Tasks & Money polish (controller amendment S: v16 R1, v17 this, v18 models, v19 site_logins, v20 routines).
    Migration(17, "tasks and money polish", (
        AddColumn("tasks", "starred", "INTEGER NOT NULL DEFAULT 0"),
        AddColumn("tasks", "estimate", "TEXT"),     # enc:v2, AAD tasks:estimate, minutes as text
        _MONEY_RECURRING,                           # amount, description, vendor, cadence are enc:v2
        "CREATE INDEX IF NOT EXISTS idx_money_recurring_project ON money_recurring(user_id, project_id)",
        "CREATE INDEX IF NOT EXISTS idx_money_recurring_due ON money_recurring(user_id, next_due)",
        AddColumn("money_expenses", "recurring_id", "TEXT"),
        AddColumn("money_expenses", "occurrence", "TEXT"),
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_money_expenses_occurrence "
        "ON money_expenses(user_id, recurring_id, occurrence) WHERE recurring_id IS NOT NULL",
    )),
    # LazyClaw migration: which rows came from LazyClaw (the "from LazyClaw" mark) and which run made them (undo).
    Migration(18, "import links", (
        _IMPORT_LINKS,
        "CREATE INDEX IF NOT EXISTS idx_import_links_run ON import_links(user_id, source, run_id)",
        "CREATE INDEX IF NOT EXISTS idx_import_links_new ON import_links(user_id, source, kind, new_id)",
    )),
    # Polish R1 follow-up: pinned bots. Plaintext flag and time (not user content); the main bot counts as pinned in code.
    Migration(19, "pinned bots", (
        AddColumn("bots", "pinned", "INTEGER NOT NULL DEFAULT 0"),
        AddColumn("bots", "pinned_at", "TEXT"),     # when it was pinned: the pin order
    )),
    # Models & helpers (controller amendment S5). Settings and public facts: plaintext.
    Migration(20, "models and helpers", (
        AddColumn("bots", "effort", "TEXT"),        # low | medium | high | max; NULL: the model's default
        _SEEN_MODELS,
        _MODEL_DISMISSALS,
    )),
    # Money income (controller amendment S6). Plaintext: the kind is not user content. Old rows stay expenses.
    Migration(21, "money income", (
        AddColumn("money_expenses", "kind", "TEXT NOT NULL DEFAULT 'expense' CHECK (kind IN ('expense', 'income'))"),
    )),
    # Board redesign G7 (controller amendment S6): day notes and pinned projects.
    Migration(22, "day notes and project pins", (
        _DAY_NOTES,
        "CREATE INDEX IF NOT EXISTS idx_day_notes_user_day ON day_notes(user_id, day)",
        AddColumn("money_projects", "pinned", "INTEGER NOT NULL DEFAULT 0"),
        AddColumn("money_projects", "pinned_at", "TEXT"),     # when it was pinned; NULL: not pinned
        )),
    # Approval modes and Your Mac (P0-P1). Computers, planned as v19, takes v24; Routines, planned as v17, takes v25.
    Migration(23, "approvals and mac folders", (
        AddColumn("bots", "approval_mode",
                  "TEXT NOT NULL DEFAULT 'auto_edit' CHECK (approval_mode IN ('ask', 'auto_edit', 'plan'))"),
        AddColumn("bots", "approval_ask_topics", "TEXT NOT NULL DEFAULT '[\"files\"]'"),
        _MAC_GRANTS,
        "CREATE INDEX IF NOT EXISTS idx_mac_grants_user ON mac_grants(user_id, revoked_at)",
        _APPROVAL_CARDS,
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_approval_cards_one_open ON approval_cards(user_id, bot_id) "
        "WHERE state = 'open'",
        "CREATE INDEX IF NOT EXISTS idx_approval_cards_user ON approval_cards(user_id, state, created_at)",
        _MAC_FILE_MARKS,
    )),
    # Computers (C1 + C2). Amendment S7: bots.computer defaults to Mac Brave for new and old bots; the Linux
    # computer is opt-in per bot until the user has tested it. Routines, planned for v24, takes v25.
    Migration(24, "computers", (
        AddColumn("bots", "computer",
                  "TEXT NOT NULL DEFAULT 'mac_brave' CHECK (computer IN ('linux', 'mac_brave'))"),
        _SITE_LOGINS,
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_site_logins_one ON site_logins(user_id, bot_id, host_key)",
        "CREATE INDEX IF NOT EXISTS idx_site_logins_bot ON site_logins(user_id, bot_id, updated_at)",
    )),
    # Routines and Plan (P0-P3). v23 approval modes + Mac folders, v24 Computers.
    Migration(25, "routines and plan", (
        _ROUTINES,
        "CREATE INDEX IF NOT EXISTS idx_routines_due ON routines(user_id, enabled, next_run_at)",
        "CREATE INDEX IF NOT EXISTS idx_routines_bot ON routines(user_id, bot_id)",
        _ROUTINE_RUNS,
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_routine_runs_slot ON routine_runs(user_id, routine_id, slot_at, state)",
        "CREATE INDEX IF NOT EXISTS idx_routine_runs_routine ON routine_runs(user_id, routine_id, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_routine_runs_item ON routine_runs(user_id, work_item_id)",
        _ROUTINE_PROPOSALS,
        "CREATE INDEX IF NOT EXISTS idx_routine_proposals_open ON routine_proposals(user_id, state, created_at)",
        _BOT_QUESTIONS,
        "CREATE INDEX IF NOT EXISTS idx_bot_questions_open ON bot_questions(user_id, state, bot_id, created_at)",
        _BOT_PLANS,
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_bot_plans_bot ON bot_plans(user_id, bot_id)",
        _REMINDER_SENDS,
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_reminder_sends_once ON reminder_sends(user_id, task_id, fire_at)",
        _BUDGET_ALERTS,
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_budget_alerts_once ON budget_alerts(user_id, project_id, budget, level, month)",
        AddColumn("bots", "full_limit_until", "TEXT"),     # UTC ISO; NULL: the full limit is off
    )),
    # Skills: the user's saved how-tos (sealed), per-bot off switches and bot proposals. C3 takes no migration.
    Migration(26, "skills", (
        _SKILLS,
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_skills_name ON skills(user_id, name_key)",
        _BOT_SKILL_OFF,
        _SKILL_PROPOSALS,
        "CREATE INDEX IF NOT EXISTS idx_skill_proposals_open ON skill_proposals(user_id, state, created_at)",
    )),
    # The Sign-in card (docs/plans/2026-10-22-roost-signin.md): a Linux bot's sign-in Stuck card, and whether
    # each Vault login is kept on the computer or cleared after the task (an item id, plaintext).
    Migration(27, "sign-in card", (
        AddColumn("stuck_cards", "sign_in", "INTEGER NOT NULL DEFAULT 0"),
        AddColumn("site_logins", "kept", "INTEGER NOT NULL DEFAULT 1"),
        AddColumn("site_logins", "clear_after_item_id", "TEXT"),
        "CREATE INDEX IF NOT EXISTS idx_site_logins_pending ON site_logins(user_id, bot_id, kept)",
    )),
    # Teach a task: the sealed step log of a bot you are teaching, one per bot.
    Migration(28, "teach", (
        _TEACH_SESSIONS,
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_teach_sessions_bot ON teach_sessions(user_id, bot_id)",
    )),
    # Replies: a message may quote one earlier message of its thread (the quote sealed, its taint kept), and a bot
    # offers a change to its own instructions on a card (the proposal sealed). Only the user's Accept writes it.
    Migration(29, "replies and instruction proposals", (
        AddColumn("messages", "reply_to", "TEXT"),              # a message id in the same thread; NULL: no reply
        AddColumn("messages", "reply_quote", "TEXT"),           # enc:v2, messages:reply_quote
        AddColumn("messages", "reply_tainted", "INTEGER NOT NULL DEFAULT 0"),
        _INSTRUCTION_PROPOSALS,
        "CREATE INDEX IF NOT EXISTS idx_instruction_proposals_open "
        "ON instruction_proposals(user_id, state, created_at)",
    )),
    # Obsidian track: tags on what a bot writes, the Bot Journal, the one-way vault export.
    Migration(30, "obsidian", (
        AddColumn("money_expenses", "tags", "TEXT"),      # enc:v2, money_expenses:tags (JSON list)
        AddColumn("memories", "tags", "TEXT"),            # enc:v2, memories:tags (JSON list)
        AddColumn("money_projects", "vault_export", "INTEGER NOT NULL DEFAULT 0"),
        _BOT_JOURNALS,
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_bot_journals_day ON bot_journals(user_id, bot_id, day)",
        _VAULT_EXPORTS,
    )),
    # Connectors: a service's HTTP API with the user's key, which no route returns (docs/plans/2026-10-22-roost-connectors.md).
    Migration(31, "connectors", (
        _CONNECTORS,
        "CREATE INDEX IF NOT EXISTS idx_connectors_user ON connectors(user_id, created_at)",
        _CONNECTOR_REQUESTS,
        "CREATE INDEX IF NOT EXISTS idx_connector_requests_open ON connector_requests(user_id, state, created_at)",
    )),
    # Install an app: the Debian packages the owner said Yes to, per bot (docs/plans/2026-10-22-roost-install-app.md).
    Migration(32, "bot apps", (
        _BOT_APPS,
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_bot_apps_key ON bot_apps(user_id, bot_id, package_key)",
    )),
    # Standing permissions: what an approved routine may post, send or submit without asking again
    # (docs/plans/2026-10-23-roost-full-computer.md Step 2).
    Migration(33, "routine permissions", (
        _ROUTINE_PERMISSIONS,
        "CREATE INDEX IF NOT EXISTS idx_routine_permissions_routine ON routine_permissions(user_id, routine_id)",
    )),
    # Internet in the workspace (A4, docs/plans/2026-10-23-roost-signin-research-fixes.md): off by default.
    Migration(34, "workspace internet", (
        AddColumn("bots", "workspace_internet", "INTEGER NOT NULL DEFAULT 0"),
    )),
    # The Sign-in card's secret field: "password" or "code" on a card that shows a masked field, else NULL
    # (docs/plans/2026-10-23-roost-tabs-signin-flow.md B3). The value typed there is never stored anywhere.
    Migration(35, "secret field", (
        AddColumn("stuck_cards", "secret_field", "TEXT"),
    )),
    # Full auto (owner, 2026-10-25): a Fable reviewer may stand in for the card of a button Roost can't read, in
    # your own chat only. Off by default; the chat mode pill and the Info tab set it.
    Migration(36, "auto review", (
        AddColumn("bots", "auto_review", "INTEGER NOT NULL DEFAULT 0"),
    )),
    # Voice (docs/plans/2026-10-30-roost-voice.md): a bot's voice, tone, speed and Read replies aloud as JSON of fixed
    # ids and a number (no user words, like the avatar JSON); NULL reads as the defaults.
    Migration(37, "bot voice", (
        AddColumn("bots", "voice", "TEXT"),
    )),
    # Answer a Stuck card by typing (owner, 2026-11-02): v12's CHECK on stuck_cards.state allows only four states
    # and migrations are additive, so a card you answered in the chat is ``given_up`` with ``replied = 1``.
    Migration(38, "stuck card replied", (
        AddColumn("stuck_cards", "replied", "INTEGER NOT NULL DEFAULT 0"),
    )),
    # Token usage (docs/plans/2026-11-04-roost-token-usage.md): each model call's counts summed per user, bot
    # (NULL for a job with no bot), Madrid day, kind and model. Counts and model ids are metadata, not user
    # content, so they are plain. No FK on bot_id: a retired bot's history stays and reads as "Retired bot".
    Migration(39, "token usage", (
        """CREATE TABLE IF NOT EXISTS token_usage (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bot_id TEXT,
    day TEXT NOT NULL,                 -- YYYY-MM-DD, a Madrid day
    kind TEXT NOT NULL CHECK (kind IN ('chat','routine','handoff','room','helper','background')),
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens INTEGER NOT NULL DEFAULT 0,
    calls INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
)""",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_token_usage_key "
        "ON token_usage(user_id, IFNULL(bot_id, ''), day, kind, model)",
        "CREATE INDEX IF NOT EXISTS idx_token_usage_day ON token_usage(user_id, day)",
    )),
    # Only run when the page changes (owner, 2026-11-04, docs/plans/2026-11-04-roost-routine-watch.md): a routine's
    # watch (address and part sealed; NULL every_min: no watch) and the last snapshot Roost read, sealed, with a keyed
    # HMAC fingerprint; ids, flags, counts and times stay plaintext.
    Migration(40, "routine watch", (
        AddColumn("routines", "watch_url", "TEXT"),              # enc:v2, routines:watch_url
        AddColumn("routines", "watch_part", "TEXT"),             # enc:v2, routines:watch_part
        AddColumn("routines", "watch_every_min", "INTEGER"),
        """CREATE TABLE IF NOT EXISTS routine_watches (
    routine_id TEXT PRIMARY KEY REFERENCES routines(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    snapshot TEXT,
    fingerprint TEXT,
    change_text TEXT,
    change_run_id TEXT,
    blocked INTEGER NOT NULL DEFAULT 0,
    quiet_run_id TEXT,
    quiet_count INTEGER NOT NULL DEFAULT 0,
    checked_at TEXT,
    changed_at TEXT,
    updated_at TEXT NOT NULL
)""",
        "CREATE INDEX IF NOT EXISTS idx_routine_watches_user ON routine_watches(user_id, routine_id)",
    )),
    # Chat pictures (owner, 2026-11-05, docs/plans/2026-11-05-roost-chat-pictures.md): your uploads and a bot's
    # screenshots, re-encoded JPEGs sealed under chat_media:blob; a deleted thread (or bot) takes its pictures.
    Migration(41, "chat media", (
        """CREATE TABLE IF NOT EXISTS chat_media (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    message_id TEXT,
    mime TEXT NOT NULL DEFAULT 'image/jpeg',
    width INTEGER NOT NULL,
    height INTEGER NOT NULL,
    bytes INTEGER NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('you','bot')),
    group_label TEXT,
    blob TEXT NOT NULL,
    created_at TEXT NOT NULL
)""",
        "CREATE INDEX IF NOT EXISTS idx_chat_media_thread ON chat_media(user_id, thread_id, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_chat_media_message ON chat_media(user_id, message_id)",
    )),
    # Vault: cards (owner, 2026-11-05, docs/plans/2026-11-05-roost-pay-card.md P6): a saved payment card's number,
    # expiry, name, brand and last 4 sealed under payment_cards:<column>; number_key is a keyed HMAC of the
    # number, one row per card per user. The security code is never stored.
    Migration(42, "payment cards", (
        """CREATE TABLE IF NOT EXISTS payment_cards (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    number TEXT NOT NULL,
    number_key TEXT NOT NULL,
    exp TEXT NOT NULL,
    name TEXT NOT NULL,
    brand TEXT NOT NULL,
    last4 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_used_at TEXT,
    UNIQUE (user_id, number_key)
)""",
        "CREATE INDEX IF NOT EXISTS idx_payment_cards_user ON payment_cards(user_id, created_at)",
    )),
    # Offline tasks (owner, 2026-11-08, docs/plans/2026-11-08-roost-offline-tasks.md O5): the phone's own id for a
    # task it added offline, so a sync sent twice makes one task. A plain id, unique per user.
    Migration(43, "task client ids", (
        AddColumn("tasks", "client_id", "TEXT"),
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_client_id ON tasks(user_id, client_id) WHERE client_id IS NOT NULL",
    )),
    # Vault: passwords (owner, 2026-11-08, docs/plans/2026-11-08-roost-vault-passwords.md V1): a site login's host,
    # user name and password sealed under vault_passwords:<column>; host_key and username_key are keyed HMACs, one
    # row per site and user name per user. ``always`` is the owner's standing OK to fill it with no card.
    Migration(44, "vault passwords", (
        """CREATE TABLE IF NOT EXISTS vault_passwords (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    host TEXT NOT NULL,
    host_key TEXT NOT NULL,
    username TEXT NOT NULL,
    username_key TEXT NOT NULL,
    password TEXT NOT NULL,
    always INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_used_at TEXT,
    UNIQUE (user_id, host_key, username_key)
)""",
        "CREATE INDEX IF NOT EXISTS idx_vault_passwords_host ON vault_passwords(user_id, host_key)",
    )),
    # The account's time zone (owner, 2026-11-09, docs/plans/2026-11-09-roost-time-zone.md): an IANA name, plaintext
    # (a setting, not user content). An account from before v45 keeps Madrid, the zone Roost always used; a new one
    # starts NULL until the web app sends the zone it detected.
    Migration(45, "account time zone", (
        AddColumn("users", "timezone", "TEXT"),
        f"UPDATE users SET timezone = '{TIMEZONE_LEGACY}' WHERE timezone IS NULL",
    )),
)


def latest_version() -> int:
    return MIGRATIONS[-1].version if MIGRATIONS else 0


def pending(current: int) -> tuple[Migration, ...]:
    return tuple(m for m in MIGRATIONS if m.version > current)


async def schema_version(db: aiosqlite.Connection) -> int:
    row = await (await db.execute("PRAGMA user_version")).fetchone()
    return int(row[0])


async def _column_exists(db: aiosqlite.Connection, table: str, column: str) -> bool:
    rows = await (await db.execute(f"PRAGMA table_info({table})")).fetchall()
    return any(row[1] == column for row in rows)


async def _run_step(db: aiosqlite.Connection, step: Step) -> None:
    if isinstance(step, AddColumn):
        if not await _column_exists(db, step.table, step.column):
            await db.execute(f"ALTER TABLE {step.table} ADD COLUMN {step.column} {step.definition}")
        return
    await db.execute(step)


async def _apply_one(db: aiosqlite.Connection, migration: Migration) -> None:
    await db.execute("BEGIN IMMEDIATE")
    try:
        for step in migration.steps:
            await _run_step(db, step)
        await db.execute(f"PRAGMA user_version = {int(migration.version)}")
        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise MigrationError(
            f"Migration {migration.version} ({migration.name}) failed and was rolled back: {exc}"
        ) from exc


async def apply_migrations(db: aiosqlite.Connection) -> int:
    """Apply every pending migration in order; returns the new schema version."""
    for migration in pending(await schema_version(db)):
        await _apply_one(db, migration)
    return await schema_version(db)
