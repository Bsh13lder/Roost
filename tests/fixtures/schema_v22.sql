-- Roost schema version 22, frozen by the approvals and Mac folders plan Task 1 (schema.sql + migrations 1-22).
-- The live ~/Roost/data/roost.db runs this schema at the start of this plan. Never edit.

CREATE TABLE users (
    id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    encryption_salt TEXT NOT NULL,
    encrypted_dek TEXT,
    password_encrypted_dek TEXT,
    recovery_encrypted_dek TEXT,
    display_name TEXT,
    settings TEXT NOT NULL DEFAULT '{}',
    role TEXT NOT NULL DEFAULT 'user',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE bots (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    name_key TEXT NOT NULL,
    job TEXT NOT NULL,
    instructions TEXT NOT NULL,
    avatar TEXT NOT NULL,
    template_id TEXT,
    status TEXT NOT NULL DEFAULT 'resting',
    model_override TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL, off_duty INTEGER NOT NULL DEFAULT 0, is_primary INTEGER NOT NULL DEFAULT 0, notify INTEGER NOT NULL DEFAULT 1, group_label TEXT, pinned INTEGER NOT NULL DEFAULT 0, pinned_at TEXT, effort TEXT,
    UNIQUE(user_id, name_key)
);

CREATE TABLE threads (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    title TEXT,
    kind TEXT NOT NULL DEFAULT 'chat',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
, peer_bot_id TEXT REFERENCES bots(id) ON DELETE SET NULL);

CREATE TABLE messages (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user','bot','activity','system')),
    body TEXT NOT NULL,
    tainted INTEGER NOT NULL DEFAULT 0,
    seq INTEGER NOT NULL,
    created_at TEXT NOT NULL
, kind TEXT NOT NULL DEFAULT 'text', author_bot_id TEXT);

CREATE TABLE events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    bot_id TEXT,
    action TEXT NOT NULL,
    decision TEXT NOT NULL,
    detail TEXT,
    created_at TEXT NOT NULL
, reason TEXT, tainted INTEGER NOT NULL DEFAULT 0);

CREATE INDEX idx_bots_user ON bots(user_id);

CREATE INDEX idx_threads_bot ON threads(user_id, bot_id);

CREATE INDEX idx_messages_thread ON messages(user_id, thread_id, seq);

CREATE INDEX idx_events_user ON events(user_id, seq);

CREATE TABLE work_items (
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
, link_scope TEXT);

CREATE INDEX idx_work_items_queue ON work_items(user_id, bot_id, state);

CREATE INDEX idx_work_items_parent ON work_items(user_id, parent_item_id);

CREATE TABLE runs (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    thread_id TEXT NOT NULL,
    outcome TEXT,
    started_at TEXT NOT NULL,
    ended_at TEXT
);

CREATE INDEX idx_runs_bot_day ON runs(user_id, bot_id, started_at);

CREATE UNIQUE INDEX idx_bots_one_primary ON bots(user_id) WHERE is_primary = 1;

CREATE INDEX idx_threads_peer ON threads(user_id, bot_id, peer_bot_id);

CREATE TABLE rooms (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            coordinator_bot_id TEXT REFERENCES bots(id) ON DELETE SET NULL,
            thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

CREATE TABLE room_members (
            room_id TEXT NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
            bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            added_at TEXT NOT NULL,
            PRIMARY KEY (room_id, bot_id)
        );

CREATE INDEX idx_rooms_user ON rooms(user_id);

CREATE INDEX idx_room_members_bot ON room_members(user_id, bot_id);

CREATE TABLE bot_roles (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    role_id TEXT NOT NULL,
    added_at TEXT NOT NULL,
    PRIMARY KEY (bot_id, role_id)
);

CREATE INDEX idx_bot_roles_user ON bot_roles(user_id, role_id);

CREATE TABLE tasks (
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
, project_id TEXT REFERENCES money_projects(id) ON DELETE SET NULL, allocated_budget TEXT, starred INTEGER NOT NULL DEFAULT 0, estimate TEXT);

CREATE INDEX idx_tasks_user_status ON tasks(user_id, status, due_date);

CREATE INDEX idx_tasks_user_reminder ON tasks(user_id, reminder_at);

CREATE TABLE money_projects (
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
, color TEXT, start_date TEXT, due_date TEXT, monthly_budget TEXT, lead_bot_id TEXT REFERENCES bots(id) ON DELETE SET NULL, pinned INTEGER NOT NULL DEFAULT 0, pinned_at TEXT);

CREATE UNIQUE INDEX idx_money_projects_key ON money_projects(user_id, name_key) WHERE deleted_at IS NULL;

CREATE TABLE money_expenses (
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
, step_id TEXT, is_favorite INTEGER NOT NULL DEFAULT 0, recurring_id TEXT, occurrence TEXT, kind TEXT NOT NULL DEFAULT 'expense' CHECK (kind IN ('expense', 'income')));

CREATE INDEX idx_money_expenses_month ON money_expenses(user_id, spent_at);

CREATE INDEX idx_money_expenses_project ON money_expenses(user_id, project_id);

CREATE TABLE money_topups (
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
, topup_id TEXT);

CREATE INDEX idx_money_topups_project ON money_topups(user_id, project_id);

CREATE TABLE notes (
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
, project_id TEXT REFERENCES money_projects(id) ON DELETE SET NULL);

CREATE INDEX idx_notes_user_updated ON notes(user_id, updated_at);

CREATE INDEX idx_notes_user_title ON notes(user_id, title_key);

CREATE TABLE documents (
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
, project_id TEXT REFERENCES money_projects(id) ON DELETE SET NULL);

CREATE INDEX idx_documents_user ON documents(user_id, kind, updated_at);

CREATE TABLE stuck_cards (
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
);

CREATE UNIQUE INDEX idx_stuck_cards_one_open ON stuck_cards(user_id, bot_id) WHERE state = 'open';

CREATE INDEX idx_stuck_cards_user ON stuck_cards(user_id, state, created_at);

CREATE INDEX idx_tasks_user_project ON tasks(user_id, project_id);

CREATE INDEX idx_notes_user_project ON notes(user_id, project_id);

CREATE INDEX idx_documents_user_project ON documents(user_id, project_id);

CREATE TABLE task_comments (
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
);

CREATE INDEX idx_task_comments_task ON task_comments(user_id, task_id, created_at);

CREATE TABLE memories (
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
);

CREATE UNIQUE INDEX idx_memories_fingerprint ON memories(user_id, scope, fingerprint);

CREATE INDEX idx_memories_scope ON memories(user_id, scope, archived_at);

CREATE TABLE chat_summaries (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    upto_message_id TEXT NOT NULL,
    upto_created_at TEXT NOT NULL,
    text TEXT NOT NULL,                   -- enc:v2, AAD chat_summaries:text
    created_at TEXT NOT NULL
);

CREATE INDEX idx_chat_summaries_thread ON chat_summaries(user_id, thread_id, created_at);

CREATE TABLE money_recurring (
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
);

CREATE INDEX idx_money_recurring_project ON money_recurring(user_id, project_id);

CREATE INDEX idx_money_recurring_due ON money_recurring(user_id, next_due);

CREATE UNIQUE INDEX idx_money_expenses_occurrence ON money_expenses(user_id, recurring_id, occurrence) WHERE recurring_id IS NOT NULL;

CREATE TABLE import_links (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source TEXT NOT NULL,                 -- 'lazyclaw'
    kind TEXT NOT NULL,                   -- project | task | comment | topup | expense | recurring
    old_id TEXT NOT NULL,                 -- the id in the source system
    new_id TEXT NOT NULL,                 -- the Roost row it became
    run_id TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    PRIMARY KEY (user_id, source, kind, old_id)
);

CREATE INDEX idx_import_links_run ON import_links(user_id, source, run_id);

CREATE INDEX idx_import_links_new ON import_links(user_id, source, kind, new_id);

CREATE TABLE seen_models (
    model_id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    first_seen_at TEXT NOT NULL
);

CREATE TABLE model_notice_dismissals (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    model_id TEXT NOT NULL,
    dismissed_at TEXT NOT NULL,
    PRIMARY KEY (user_id, model_id)
);

CREATE TABLE day_notes (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    day TEXT NOT NULL,                       -- "YYYY-MM-DD", a Madrid day (plaintext: a date)
    author_kind TEXT NOT NULL CHECK (author_kind IN ('user', 'bot')),
    bot_id TEXT REFERENCES bots(id) ON DELETE SET NULL,
    text TEXT NOT NULL,                      -- enc:v2, AAD day_notes:text
    created_at TEXT NOT NULL,
    tainted INTEGER NOT NULL DEFAULT 0       -- a bot wrote it after reading web content
);

CREATE INDEX idx_day_notes_user_day ON day_notes(user_id, day);
