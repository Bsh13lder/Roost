"""SQL for the schema migrations (see ``roost/db/migrations.py``)."""

from __future__ import annotations

_WORK_ITEMS = """
CREATE TABLE IF NOT EXISTS work_items (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('message','routine','trigger','handoff','card_answer','room_post')),
    origin TEXT NOT NULL,
    body TEXT NOT NULL,
    tainted INTEGER NOT NULL DEFAULT 0,
    depth INTEGER NOT NULL DEFAULT 0,
    parent_item_id TEXT,
    message_id TEXT,
    state TEXT NOT NULL DEFAULT 'queued' CHECK (state IN ('queued','claimed','done','dropped')),
    lease_until TEXT,
    run_id TEXT,
    inflight TEXT,
    result TEXT,
    result_tainted INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)"""

_RUNS = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    thread_id TEXT NOT NULL,
    outcome TEXT,
    started_at TEXT NOT NULL,
    ended_at TEXT
)"""

_BOT_ROLES = """
CREATE TABLE IF NOT EXISTS bot_roles (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    role_id TEXT NOT NULL,
    added_at TEXT NOT NULL,
    PRIMARY KEY (bot_id, role_id)
)"""

# Every bot that exists before roles keeps what it could do: open and read
# pages. INSERT OR IGNORE on the primary key keeps the step idempotent.
_BACKFILL_WEB_ROLE = (
    "INSERT OR IGNORE INTO bot_roles (user_id, bot_id, role_id, added_at) "
    "SELECT user_id, id, 'web', strftime('%Y-%m-%dT%H:%M:%f', 'now') || '+00:00' FROM bots"
)

# Column names and meanings follow LazyClaw's tasks table (lazyclaw/db/schema.sql
# + its column migrations) so M4 can import them. User content is enc:v2.
_TASKS = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT,
    category TEXT,
    priority TEXT NOT NULL DEFAULT 'medium',
    status TEXT NOT NULL DEFAULT 'todo',
    owner TEXT NOT NULL DEFAULT 'user',
    due_date TEXT,
    reminder_at TEXT,
    pre_reminders TEXT,
    recurring TEXT,
    recur_until TEXT,
    tags TEXT,
    steps TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    deleted_at TEXT,
    created_by_bot TEXT REFERENCES bots(id) ON DELETE SET NULL,
    tainted INTEGER NOT NULL DEFAULT 0
)"""

# Column names follow LazyClaw's budgets tables (projects / project_expenses /
# budget_entries) so M4 can import them. Amounts and budgets are encrypted
# decimal strings (never floats, never plaintext).
_MONEY_PROJECTS = """
CREATE TABLE IF NOT EXISTS money_projects (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    name_key TEXT NOT NULL,
    budget TEXT,
    currency TEXT NOT NULL DEFAULT 'EUR',
    status TEXT NOT NULL DEFAULT 'active',
    description TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT,
    created_by_bot TEXT REFERENCES bots(id) ON DELETE SET NULL,
    tainted INTEGER NOT NULL DEFAULT 0
)"""

_MONEY_EXPENSES = """
CREATE TABLE IF NOT EXISTS money_expenses (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    project_id TEXT NOT NULL REFERENCES money_projects(id) ON DELETE CASCADE,
    task_id TEXT,
    amount TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'EUR',
    description TEXT,
    vendor TEXT,
    notes TEXT,
    spent_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'posted',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT,
    created_by_bot TEXT REFERENCES bots(id) ON DELETE SET NULL,
    tainted INTEGER NOT NULL DEFAULT 0
)"""

_MONEY_RECURRING = """
CREATE TABLE IF NOT EXISTS money_recurring (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    project_id TEXT NOT NULL REFERENCES money_projects(id) ON DELETE CASCADE,
    amount TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'EUR',
    description TEXT,
    vendor TEXT,
    cadence TEXT NOT NULL,
    anchor_day TEXT NOT NULL,
    next_due TEXT NOT NULL,
    ends_on TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT,
    created_by_bot TEXT REFERENCES bots(id) ON DELETE SET NULL,
    tainted INTEGER NOT NULL DEFAULT 0
)"""

_MONEY_TOPUPS = """
CREATE TABLE IF NOT EXISTS money_topups (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    project_id TEXT NOT NULL REFERENCES money_projects(id) ON DELETE CASCADE,
    amount TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'EUR',
    source TEXT,
    kind TEXT NOT NULL DEFAULT 'credit' CHECK (kind IN ('credit','edit')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT,
    created_by_bot TEXT REFERENCES bots(id) ON DELETE SET NULL,
    tainted INTEGER NOT NULL DEFAULT 0
)"""

# Column names and meanings follow LazyClaw's notes table (title, content, tags,
# pinned, title_key) so M4 can import the user's LazyBrain notes. Title, content
# and tags are enc:v2; title_key is HMAC(dek, folded title), never the title;
# revision is the compare-and-swap counter every content write bumps.
_NOTES = """
CREATE TABLE IF NOT EXISTS notes (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    title_key TEXT NOT NULL,
    content TEXT NOT NULL,
    tags TEXT,
    pinned INTEGER NOT NULL DEFAULT 0,
    revision INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT,
    created_by_bot TEXT REFERENCES bots(id) ON DELETE SET NULL,
    tainted INTEGER NOT NULL DEFAULT 0
)"""

# One encrypted blob per file (spec §4.7; LazyClaw's docs / sheets / pdf_files,
# whose `name` is `title` here): payload is the Univer snapshot JSON or the PDF's
# base64 bytes, enc:v2 under docs:payload / sheets:payload / pdf:payload; title
# and tags are enc:v2 (tags: reserved for M4's import of LazyClaw's document
# tags); revision is the compare-and-swap counter every save bumps.
_DOCUMENTS = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('doc','sheet','pdf')),
    title TEXT NOT NULL,
    payload TEXT NOT NULL,
    pages INTEGER,
    tags TEXT,
    revision INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT,
    created_by_bot TEXT REFERENCES bots(id) ON DELETE SET NULL,
    tainted INTEGER NOT NULL DEFAULT 0
)"""

# Stuck flow (Piece A): one row per Stuck card. url, note and request are enc:v2
# under stuck_cards:<column> (note is NULL when empty); ids, reason, state, flags
# and times are plaintext. A card goes with its bot and with its chat (CASCADE),
# so "Retire this bot" removes its cards. answer_item_id is the card_answer work
# item that /clear queued, which rung 4 looks the card up by.
_STUCK_CARDS = """
CREATE TABLE IF NOT EXISTS stuck_cards (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    work_item_id TEXT,
    reason TEXT NOT NULL CHECK (reason IN ('challenge','login','code','refused','asked')),
    url TEXT NOT NULL,                 -- enc:v2, AAD stuck_cards:url
    note TEXT,                         -- enc:v2, AAD stuck_cards:note (nullable)
    request TEXT NOT NULL,             -- enc:v2, AAD stuck_cards:request
    suggest_main_browser INTEGER NOT NULL DEFAULT 0,
    tainted INTEGER NOT NULL DEFAULT 0,
    main_opened INTEGER NOT NULL DEFAULT 0,
    state TEXT NOT NULL DEFAULT 'open' CHECK (state IN ('open','cleared','given_up','blocked')),
    answer_item_id TEXT,
    created_at TEXT NOT NULL,
    closed_at TEXT
)"""

# Redesign P3: comments on a task or one of its steps. ``author`` is "user" or a bot's id, with no
# foreign key, so a retired bot's comments stay. ``tainted`` marks a comment a bot wrote after reading
# outside content, as on every record. Deleting is soft; the task's row going takes its comments.
_TASK_COMMENTS = """
CREATE TABLE IF NOT EXISTS task_comments (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    step_id TEXT,                      -- one of the task's steps; NULL: the whole task
    author TEXT NOT NULL,              -- 'user', or the bot's id
    body TEXT NOT NULL,                -- enc:v2, AAD task_comments:body
    tainted INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    edited_at TEXT,
    deleted_at TEXT
)"""

_MEMORIES = """
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bot_id TEXT REFERENCES bots(id) ON DELETE CASCADE,   -- NULL: About you, shared by every bot
    scope TEXT NOT NULL,                  -- the bot's id, or '*' for About you (SQLite repeats NULLs in a unique index)
    kind TEXT NOT NULL,                   -- about_you | preference | fact | project | lesson
    text TEXT NOT NULL,                   -- enc:v2, AAD memories:text
    source TEXT NOT NULL,                 -- user | bot
    created_by_bot TEXT,                  -- the bot that saved it (source bot); no FK, like notes
    importance INTEGER NOT NULL DEFAULT 3,
    pinned INTEGER NOT NULL DEFAULT 0,
    tainted INTEGER NOT NULL DEFAULT 0,
    fingerprint TEXT NOT NULL,            -- hex HMAC-SHA256 under the memory key
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_recalled_at TEXT,
    archived_at TEXT
)
"""

_CHAT_SUMMARIES = """
CREATE TABLE IF NOT EXISTS chat_summaries (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    upto_message_id TEXT NOT NULL,
    upto_created_at TEXT NOT NULL,
    text TEXT NOT NULL,                   -- enc:v2, AAD chat_summaries:text
    created_at TEXT NOT NULL
)
"""

_SEEN_MODELS = """
CREATE TABLE IF NOT EXISTS seen_models (
    model_id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    first_seen_at TEXT NOT NULL
)
"""

_MODEL_DISMISSALS = """
CREATE TABLE IF NOT EXISTS model_notice_dismissals (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    model_id TEXT NOT NULL,
    dismissed_at TEXT NOT NULL,
    PRIMARY KEY (user_id, model_id)
)
"""

_DAY_NOTES = """
CREATE TABLE IF NOT EXISTS day_notes (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    day TEXT NOT NULL,                       -- "YYYY-MM-DD", a Madrid day (plaintext: a date)
    author_kind TEXT NOT NULL CHECK (author_kind IN ('user', 'bot')),
    bot_id TEXT REFERENCES bots(id) ON DELETE SET NULL,
    text TEXT NOT NULL,                      -- enc:v2, AAD day_notes:text
    created_at TEXT NOT NULL,
    tainted INTEGER NOT NULL DEFAULT 0       -- a bot wrote it after reading web content
)
"""

_IMPORT_LINKS = """
CREATE TABLE IF NOT EXISTS import_links (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source TEXT NOT NULL,                 -- 'lazyclaw'
    kind TEXT NOT NULL,                   -- project | task | comment | topup | expense | recurring
    old_id TEXT NOT NULL,                 -- the id in the source system
    new_id TEXT NOT NULL,                 -- the Roost row it became
    run_id TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    PRIMARY KEY (user_id, source, kind, old_id)
)"""

_MAC_GRANTS = """
CREATE TABLE IF NOT EXISTS mac_grants (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bot_id TEXT REFERENCES bots(id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    label TEXT NOT NULL,
    access TEXT NOT NULL CHECK (access IN ('read', 'read_write')),
    read_policy TEXT NOT NULL DEFAULT 'ask_each' CHECK (read_policy IN ('ask_each', 'ask_session')),
    is_vault INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    revoked_at TEXT
)
"""

_APPROVAL_CARDS = """
CREATE TABLE IF NOT EXISTS approval_cards (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    work_item_id TEXT,
    kind TEXT NOT NULL CHECK (kind IN ('ask', 'plan')),
    state TEXT NOT NULL CHECK (state IN ('open', 'approved', 'declined', 'edited', 'failed', 'expired')),
    steps TEXT NOT NULL,
    request TEXT NOT NULL,
    tainted INTEGER NOT NULL DEFAULT 0,
    session_offer INTEGER NOT NULL DEFAULT 0,
    answer_item_id TEXT,
    created_at TEXT NOT NULL,
    closed_at TEXT
)
"""

_SITE_LOGINS = """
CREATE TABLE IF NOT EXISTS site_logins (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    host TEXT NOT NULL,                -- enc:v2, AAD site_logins:host
    host_key TEXT NOT NULL,            -- HMAC(dek, normalised host): the unique key, never the host
    label TEXT NOT NULL,               -- enc:v2, AAD site_logins:label
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)"""

_MAC_FILE_MARKS = """
CREATE TABLE IF NOT EXISTS mac_file_marks (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    grant_id TEXT NOT NULL REFERENCES mac_grants(id) ON DELETE CASCADE,
    path_key TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    bot_id TEXT,
    written_tainted INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, grant_id, path_key)
)
"""

_ROUTINES = """
CREATE TABLE IF NOT EXISTS routines (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    instructions TEXT NOT NULL,
    schedule TEXT NOT NULL,
    builtin TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    tainted INTEGER NOT NULL DEFAULT 0,
    created_by TEXT NOT NULL CHECK (created_by IN ('user', 'bot')),
    next_run_at TEXT,
    last_run_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

_ROUTINE_RUNS = """
CREATE TABLE IF NOT EXISTS routine_runs (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    routine_id TEXT NOT NULL REFERENCES routines(id) ON DELETE CASCADE,
    bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    slot_at TEXT NOT NULL,
    work_item_id TEXT,
    state TEXT NOT NULL CHECK (state IN ('queued','running','done','missed','skipped','held','expired','error')),
    missed_count INTEGER NOT NULL DEFAULT 0,
    note TEXT,
    started_at TEXT,
    finished_at TEXT,
    created_at TEXT NOT NULL
)
"""

_ROUTINE_PROPOSALS = """
CREATE TABLE IF NOT EXISTS routine_proposals (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    routine_id TEXT REFERENCES routines(id) ON DELETE CASCADE,
    action TEXT NOT NULL CHECK (action IN ('create','change','pause')),
    payload TEXT NOT NULL,
    tainted INTEGER NOT NULL DEFAULT 0,
    from_routine INTEGER NOT NULL DEFAULT 0,
    state TEXT NOT NULL CHECK (state IN ('open','approved','declined','expired')),
    thread_id TEXT NOT NULL,
    message_id TEXT,
    created_at TEXT NOT NULL,
    decided_at TEXT
)
"""

_BOT_QUESTIONS = """
CREATE TABLE IF NOT EXISTS bot_questions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    routine_id TEXT REFERENCES routines(id) ON DELETE SET NULL,
    thread_id TEXT NOT NULL,
    question TEXT NOT NULL,
    default_choice TEXT NOT NULL,
    why TEXT,
    answer TEXT,
    tainted INTEGER NOT NULL DEFAULT 0,
    state TEXT NOT NULL CHECK (state IN ('open','answered','dismissed')),
    created_at TEXT NOT NULL,
    answered_at TEXT
)
"""

_BOT_PLANS = """
CREATE TABLE IF NOT EXISTS bot_plans (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    item_taint TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1,
    export_enabled INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

_REMINDER_SENDS = """
CREATE TABLE IF NOT EXISTS reminder_sends (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    fire_at TEXT NOT NULL,
    missed INTEGER NOT NULL DEFAULT 0,
    sent_at TEXT NOT NULL
)
"""

_BUDGET_ALERTS = """
CREATE TABLE IF NOT EXISTS budget_alerts (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    project_id TEXT NOT NULL REFERENCES money_projects(id) ON DELETE CASCADE,
    budget TEXT NOT NULL CHECK (budget IN ('month','total')),
    level TEXT NOT NULL CHECK (level IN ('warn','over')),
    month TEXT NOT NULL,
    sent_at TEXT NOT NULL
)
"""

# Skills (schema v26): the user's saved how-tos, per-bot switches and bot proposals.
_SKILLS = """
CREATE TABLE IF NOT EXISTS skills (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,            -- enc:v2, skills:name
    use_when TEXT NOT NULL,        -- enc:v2, skills:use_when
    body TEXT NOT NULL,            -- enc:v2, skills:body
    name_key TEXT NOT NULL,        -- HMAC-SHA256(skill sub-key of the DEK, fold_name(name)), hex
    origin TEXT NOT NULL CHECK (origin IN ('user','bot','file')),
    tainted INTEGER NOT NULL DEFAULT 0,
    created_by_bot TEXT REFERENCES bots(id) ON DELETE SET NULL,
    revision INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

_BOT_SKILL_OFF = """
CREATE TABLE IF NOT EXISTS bot_skill_off (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    skill_id TEXT NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, bot_id, skill_id)
)
"""

_SKILL_PROPOSALS = """
CREATE TABLE IF NOT EXISTS skill_proposals (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    skill_id TEXT REFERENCES skills(id) ON DELETE CASCADE,
    action TEXT NOT NULL CHECK (action IN ('create','change')),
    payload TEXT NOT NULL,         -- enc:v2, skill_proposals:payload (SkillProposalPayload JSON)
    base_revision INTEGER,         -- a change: the skill's revision when proposed
    tainted INTEGER NOT NULL DEFAULT 0,
    from_routine INTEGER NOT NULL DEFAULT 0,
    state TEXT NOT NULL CHECK (state IN ('open','saved','declined')),
    thread_id TEXT NOT NULL,
    message_id TEXT,
    created_at TEXT NOT NULL,
    decided_at TEXT
)
"""

# Teach a task (schema v28): one sealed step log per bot while you teach it; deleted once its proposal is made.
_TEACH_SESSIONS = """
CREATE TABLE IF NOT EXISTS teach_sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    steps TEXT NOT NULL,           -- enc:v2, teach_sessions:steps (a JSON list of TeachStep)
    step_count INTEGER NOT NULL DEFAULT 0,
    capped INTEGER NOT NULL DEFAULT 0,
    started_at TEXT NOT NULL
)
"""

_INSTRUCTION_PROPOSALS = """
CREATE TABLE IF NOT EXISTS instruction_proposals (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    payload TEXT NOT NULL,         -- enc:v2, instruction_proposals:payload (JSON {before, after, why})
    tainted INTEGER NOT NULL DEFAULT 0,
    from_routine INTEGER NOT NULL DEFAULT 0,
    state TEXT NOT NULL CHECK (state IN ('open','accepted','declined')),
    thread_id TEXT NOT NULL,
    message_id TEXT,
    created_at TEXT NOT NULL,
    decided_at TEXT
)
"""

_CONNECTORS = """
CREATE TABLE IF NOT EXISTS connectors (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,            -- enc:v2, connectors:name
    purpose TEXT NOT NULL,         -- enc:v2, connectors:purpose
    base_url TEXT NOT NULL,        -- enc:v2, connectors:base_url
    auth_style TEXT NOT NULL CHECK (auth_style IN ('bearer','header','query')),
    auth_name TEXT NOT NULL,       -- enc:v2, connectors:auth_name
    secret TEXT NOT NULL,          -- enc:v2, connectors:secret (write-only: no route ever returns it)
    secret_hint TEXT NOT NULL,     -- enc:v2, connectors:secret_hint
    allowed_prefixes TEXT NOT NULL, -- enc:v2, connectors:allowed_prefixes (JSON list)
    bot_ids TEXT,                  -- JSON list of bot ids; NULL: every bot
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

_CONNECTOR_REQUESTS = """
CREATE TABLE IF NOT EXISTS connector_requests (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    thread_id TEXT NOT NULL,
    service TEXT NOT NULL,         -- enc:v2, connector_requests:service
    base_url TEXT NOT NULL,        -- enc:v2, connector_requests:base_url
    why TEXT NOT NULL,             -- enc:v2, connector_requests:why
    auth_style TEXT NOT NULL CHECK (auth_style IN ('bearer','header','query')),
    auth_name TEXT NOT NULL,       -- enc:v2, connector_requests:auth_name
    tainted INTEGER NOT NULL DEFAULT 0,
    state TEXT NOT NULL CHECK (state IN ('open','saved','declined')),
    connector_id TEXT REFERENCES connectors(id) ON DELETE SET NULL,
    message_id TEXT,
    created_at TEXT NOT NULL,
    decided_at TEXT
)
"""

# Obsidian track (schema v30): the Bot Journal and the one-way vault export.
_BOT_JOURNALS = """
CREATE TABLE IF NOT EXISTS bot_journals (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    day TEXT NOT NULL,                 -- YYYY-MM-DD, a Madrid day
    content TEXT NOT NULL,             -- enc:v2, bot_journals:content (Obsidian Markdown)
    tainted INTEGER NOT NULL DEFAULT 0,
    revision INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

_VAULT_EXPORTS = """
CREATE TABLE IF NOT EXISTS vault_exports (
    user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    grant_id TEXT REFERENCES mac_grants(id) ON DELETE SET NULL,
    journals INTEGER NOT NULL DEFAULT 0,
    manifest TEXT,                     -- enc:v2, vault_exports:manifest ({path: sha256} JSON)
    last_result TEXT,                  -- a code: ok | partial | no_grant | away | failed
    last_written INTEGER NOT NULL DEFAULT 0,
    last_conflicts INTEGER NOT NULL DEFAULT 0,
    last_export_at TEXT,
    updated_at TEXT NOT NULL
)
"""

# Install an app (schema v32, docs/plans/2026-10-22-roost-install-app.md): the packages the owner said Yes to.
_BOT_APPS = """
CREATE TABLE IF NOT EXISTS bot_apps (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    package TEXT NOT NULL,             -- enc:v2, bot_apps:package
    package_key TEXT NOT NULL,         -- HMAC(sub-key of the DEK, package): the unique key, never the name
    tainted INTEGER NOT NULL DEFAULT 0, -- the card came from a run that read outside content
    installed_at TEXT NOT NULL
)
"""

# Standing permissions (schema v33, docs/plans/2026-10-23-roost-full-computer.md Step 2): what an approved routine
# may do without asking again. Only the owner's own click writes a row; a revoke takes effect at once.
_ROUTINE_PERMISSIONS = """
CREATE TABLE IF NOT EXISTS routine_permissions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    routine_id TEXT NOT NULL REFERENCES routines(id) ON DELETE CASCADE,
    host TEXT NOT NULL,                -- enc:v2, routine_permissions:host
    host_key TEXT NOT NULL,            -- HMAC(sub-key of the DEK, host): the lookup key, never the host
    action TEXT NOT NULL CHECK (action IN ('post','send','submit')),
    max_per_day INTEGER NOT NULL CHECK (max_per_day BETWEEN 1 AND 20),
    until TEXT NOT NULL,               -- YYYY-MM-DD, a Madrid day (the last day it holds)
    used_day TEXT,                     -- the Madrid day used_count counts
    used_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    revoked_at TEXT
)
"""
