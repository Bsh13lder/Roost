"""Constants for the LazyClaw importer (kept out of roost/constants.py on purpose)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

# --- old crypto (harvested from LazyClaw lazyclaw/crypto/encryption.py) ---
LEGACY_FIXED_SALT = b"lazyclaw-server-key-v1"
LEGACY_ITERATIONS = 100_000
ENC_V1_PREFIX = "enc:v1:"
ENC_V2_PREFIX = "enc:v2:"
ENC_PREFIX = "enc:"
UNREADABLE_MARKER = "[encrypted]"  # what LazyClaw's decrypt_field returns on failure

# --- snapshot ---
SNAPSHOT_DIR_PREFIX = "roost-lazyclaw-"
SNAPSHOT_FILE_NAME = "lazyclaw-snapshot.db"
DIR_MODE = 0o700
FILE_MODE = 0o600
COUNTED_TABLES = (
    "users", "tasks", "projects", "project_expenses", "recurring_expenses", "budget_entries",
)
SNAPSHOT_BUSY_TIMEOUT_S = 10.0
SNAPSHOT_COUNT_ATTEMPTS = 3

# --- money ---
CENT = Decimal("0.01")
DRIFT_LIMIT = Decimal("0.000001")
CURRENCY_LENGTH = 3
GENERAL_NAME_KEY = "general"
OPENING_BUDGET_SOURCE = "Opening budget (from LazyClaw)"

# --- recurring ---
CADENCE_MONTHLY = "monthly"
CADENCE_WEEKLY = "weekly"
CADENCE_YEARLY = "yearly"

# --- enums ---
TASK_PRIORITIES = frozenset({"low", "medium", "high", "urgent"})
TASK_STATUSES = frozenset({"todo", "in_progress", "done", "cancelled", "failed"})
TASK_OWNERS = frozenset({"user", "agent"})
PROJECT_STATUSES = frozenset({"active", "archived"})
EXPENSE_STATUSES = frozenset({"posted", "void"})
TOPUP_KINDS = frozenset({"credit", "edit"})
RECURRING_STATUSES = frozenset({"active", "paused"})

# --- report ---
SAMPLES_PER_KIND = 5
SAMPLE_TITLE_CHARS = 24
EXPECTED_TIMEZONE = "Europe/Madrid"
OLD_SECRET_PROMPT = "LazyClaw SERVER_SECRET (input hidden): "

# --- unlock by login password (LazyClaw crypto/recovery.py derive_password_wrapping_key) ---
PASSWORD_KDF_ITERATIONS = 100_000
OLD_PASSWORD_PROMPT = "LazyClaw password (input hidden): "
OLD_USERNAME_PROMPT = "LazyClaw username: "
UNLOCK_PASSWORD = "password"
UNLOCK_SERVER_SECRET = "server-secret"
# Columns tried, in order, for the one known ciphertext that proves a key.
VERIFY_COLUMNS = (
    ("tasks", "title"), ("projects", "name"), ("project_expenses", "description"),
    ("recurring_expenses", "description"), ("budget_entries", "source"),
)

# --- writing into Roost ---
IMPORT_SOURCE = "lazyclaw"
KIND_PROJECT = "project"
KIND_TASK = "task"
KIND_COMMENT = "comment"
KIND_TOPUP = "topup"
KIND_EXPENSE = "expense"
KIND_RECURRING = "recurring"
KIND_WIPE = "wipe"          # a lasting marker: this account was wiped once; undo never removes it
# Deleted first to last (children before parents) by undo.
UNDO_ORDER = (KIND_EXPENSE, KIND_RECURRING, KIND_COMMENT, KIND_TASK, KIND_TOPUP, KIND_PROJECT)
BACKUP_DIR_NAME = "backups"
BACKUP_PREFIX = "pre-lazyclaw-"
RUN_ID_PREFIX = "lazyclaw-"
APPLY_CONFIRM_PROMPT = "Type yes to wipe the rows listed above and import LazyClaw's: "
APPLY_NO_WIPE_PROMPT = "Type yes to import LazyClaw's rows (nothing is wiped): "

# --- running-process guards ---
ROOST_GATEWAY_PORT = 18800
ROOST_KEEPER_PORT = 18801
ROOST_PORTS = (ROOST_GATEWAY_PORT, ROOST_KEEPER_PORT)
LOOPBACK = "127.0.0.1"
PORT_PROBE_TIMEOUT_S = 0.5

# --- LazyClaw running? ---
LAZYCLAW_DEFAULT_PORT = 18789          # fallback when its source config cannot be read
LAZYCLAW_CONFIG_RELATIVE = Path("lazyclaw") / "config.py"
LAZYCLAW_PORT_PATTERN = r'os\.getenv\(\s*"PORT"\s*,\s*"(\d{2,5})"\s*\)'
LAZYCLAW_RUNNING_MESSAGE = "Stop LazyClaw first (its database is in use)."
LEFTOVER_WAL_HINT = ("If LazyClaw is already stopped (docker compose stop), its -wal file was just left behind: "
                     "run again with --lazyclaw-stopped.")
STAGE_FILE_NAME = "lazyclaw-stage.db"
# Schemas this tool was written and tested against: 18 (import_links) and 19 (bots.pinned) and 20 (bots.effort, seen_models,
# dismissals), 21 (money income) 22 (day notes, project pins) and 23 (approval modes, Mac folders); the last three touch no imported rows. Any other version is refused.
SUPPORTED_SCHEMA_VERSIONS = (18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48)   # 27-48: sign-in, teach, replies, tags/journal/export, connectors, bot apps, routine permissions, workspace internet, secret field, auto review, bot voice, stuck card replied, token usage, routine watch, chat media, payment cards, task client ids, vault passwords, account time zone, routine model, routine last error, finished routines; the importer writes none of them
SERVER_SECRET_FILE = "server.secret"
KEEPER_SECRET_FILE = "keeper.secret"
RESTORE_STEPS = ("stop Roost, delete roost.db-wal and roost.db-shm next to roost.db, then copy {backup} over "
                 "roost.db")
