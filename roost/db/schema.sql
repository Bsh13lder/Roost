-- Roost database schema — the shared contract every Night-1 task builds
-- against (docs/plans/2026-10-13-roost-night1-walking-skeleton.md).
--
-- `users` and `sessions` are Task 1's carry-over, unchanged. `bots`,
-- `threads`, `messages`, `events` and `audit` are Task 2's addition.
-- FROZEN: this file is schema version 0, the baseline the deployed
-- gateway created. Never edit a statement here; every change since is a
-- versioned, additive migration in roost/db/migrations.py.
--
-- Every user-content column listed in the contract as encrypted (e.g.
-- bots.name, messages.body) is encrypted at the application layer
-- (enc:v1, per-user DEK) before it ever reaches this schema — SQLite
-- just sees TEXT either way. Every table scoped to a user carries a
-- plaintext user_id column so every query can (and must) filter by it.

CREATE TABLE IF NOT EXISTS users (
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

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS bots (
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
    updated_at TEXT NOT NULL,
    UNIQUE(user_id, name_key)
);

CREATE TABLE IF NOT EXISTS threads (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    title TEXT,
    kind TEXT NOT NULL DEFAULT 'chat',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user','bot','activity','system')),
    body TEXT NOT NULL,
    tainted INTEGER NOT NULL DEFAULT 0,
    seq INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    bot_id TEXT,
    action TEXT NOT NULL,
    decision TEXT NOT NULL,
    detail TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_bots_user ON bots(user_id);
CREATE INDEX IF NOT EXISTS idx_threads_bot ON threads(user_id, bot_id);
CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(user_id, thread_id, seq);
CREATE INDEX IF NOT EXISTS idx_events_user ON events(user_id, seq);
