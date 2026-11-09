-- Synthetic subset of LazyClaw's schema (lazyclaw/db/schema.sql + connection.py column
-- migrations applied). Test fixture only; holds no real data.
CREATE TABLE users (
    id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
    encryption_salt TEXT NOT NULL, encrypted_dek TEXT, display_name TEXT,
    settings TEXT DEFAULT '{}', password_encrypted_dek TEXT, recovery_encrypted_dek TEXT, role TEXT NOT NULL DEFAULT 'user',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE tasks (
    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, title TEXT NOT NULL, description TEXT,
    category TEXT, priority TEXT NOT NULL DEFAULT 'medium', status TEXT NOT NULL DEFAULT 'todo',
    owner TEXT NOT NULL DEFAULT 'user', due_date TEXT, reminder_at TEXT, reminder_job_id TEXT,
    recurring TEXT, tags TEXT, nag_count INTEGER DEFAULT 0, created_at TEXT DEFAULT (datetime('now')),
    completed_at TEXT, last_error TEXT, attempt_count INTEGER NOT NULL DEFAULT 0,
    last_attempted_at TEXT, trace_session_id TEXT, lazybrain_note_id TEXT, pre_reminders TEXT,
    allocated_budget REAL, recur_until TEXT, steps TEXT, nag_fired_at TEXT,
    reminder_offset_minutes INTEGER, progress_log TEXT, comments TEXT, check_every TEXT,
    progress_template_id TEXT, nudge_sent_at TEXT, last_pulse_fired_at TEXT,
    updated_at TEXT, deleted_at TEXT
);
CREATE TABLE projects (
    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, name TEXT NOT NULL, name_key TEXT NOT NULL,
    budget REAL DEFAULT 0, currency TEXT NOT NULL DEFAULT 'EUR', status TEXT NOT NULL DEFAULT 'active',
    description TEXT, lazybrain_note_id TEXT, start_date TEXT, due_date TEXT,
    created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now')),
    deleted_at TEXT, color TEXT, is_favorite INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE project_expenses (
    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, project_id TEXT NOT NULL, task_id TEXT,
    subtask_id TEXT, amount REAL NOT NULL DEFAULT 0, currency TEXT NOT NULL DEFAULT 'EUR',
    description TEXT, vendor TEXT, notes TEXT, spent_at TEXT, status TEXT NOT NULL DEFAULT 'posted',
    recurring_expense_id TEXT, lazybrain_note_id TEXT, created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')), deleted_at TEXT, is_favorite INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE recurring_expenses (
    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, project_id TEXT NOT NULL, task_id TEXT,
    amount REAL NOT NULL DEFAULT 0, currency TEXT NOT NULL DEFAULT 'EUR', description TEXT,
    vendor TEXT, cron_expression TEXT NOT NULL, job_id TEXT, next_run TEXT, last_charged_at TEXT,
    status TEXT NOT NULL DEFAULT 'active', created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE budget_entries (
    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, project_id TEXT NOT NULL, amount REAL NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'EUR', source TEXT, kind TEXT NOT NULL DEFAULT 'credit',
    created_at TEXT DEFAULT (datetime('now')), updated_at TEXT, deleted_at TEXT
);
