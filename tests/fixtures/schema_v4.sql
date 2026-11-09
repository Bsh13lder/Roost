-- Roost schema version 4, frozen by M1 Task 1 (schema.sql + migrations 1-4).
-- The live ~/Roost/data/roost.db runs this schema at the start of M1. Never edit.

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
    updated_at TEXT NOT NULL, off_duty INTEGER NOT NULL DEFAULT 0, is_primary INTEGER NOT NULL DEFAULT 0,
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
);

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
);

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
