# LazyClaw → Roost: tasks and money migration (M4, part 1) — plan

**Status:** plan for review. No real data was opened to write it; it is built from LazyClaw's source
(`lazyclaw/db/schema.sql`, `db/connection.py`, `tasks/store.py`, `budgets/store.py`,
`budgets/settings.py`, `crypto/*`) and Roost's (`roost/db/migrations.py` up to v17, the task and
money stores). **In scope:** tasks (steps, comments, reminders, repeats), projects (LazyClaw
`projects`, which absorb categories), expenses, top-ups, recurring expenses. **Out:** memories,
LazyBrain notes, documents, contacts, vault, chats.

**Decided earlier:** projects hub design P1–P8 and H1–H16 (one project holds tasks and money, a
total and/or monthly budget, only the project's currency counts, General holds loose expenses);
spec §9.1–9.2 (ids preserved, decrypt → verify → re-encrypt, read-back through the stores, taint
on rows the user can't be proven to have written). The money maths are Roost's
(`roost/projects/numbers.py`), not LazyClaw's: nothing from LazyClaw's sums is copied.

## 0. Facts found

- **LazyClaw DB:** SQLite (aiosqlite, WAL), `config.database_dir / "lazyclaw.db"`, `DATABASE_DIR`
  defaulting to `./data`; compose bind-mounts `./data:/app/data`, so the live file is
  `/Users/blckit/Desktop/Code_Projects/lazyclaw/data/lazyclaw.db` (path only; not opened). `.env`
  could override `DATABASE_DIR`; the user confirms the path at run time.
- **Account: not imported.** `MORNING.md` §5: "Your old LazyClaw account was **not** imported", and
  the Q1c step-0 export never ran. Roost's account came from `/api/auth/register` (new id, salt and
  DEK), and Roost's secret is `ROOST_SERVER_SECRET` or a generated `~/Roost/data/server.secret`,
  not LazyClaw's `SERVER_SECRET`. Roost's `key_manager` also dropped the legacy NULL-DEK branch.
  So **LazyClaw ciphertext cannot be read with Roost's key**; the spec's "if you said no to Q1c"
  path applies (old-id → new-id user map).
- **LazyClaw encryption:** every task and money text field is `enc:v1` (AES-GCM, **no AAD**) under
  the user's DEK: tasks `title, description, category, tags, steps, comments` (+ `progress_log`);
  projects `name, description`; expenses `description, vendor, notes`; recurring
  `description, vendor`; budget_entries `source`. `decrypt_field` passes a non-`enc:` value through
  as plaintext, and returns `"[encrypted]"` on failure. Amounts, budgets, dates, status are
  plaintext; **amounts are `REAL`**.
- **Projects ⇄ tasks in LazyClaw** join by name: `tasks.category` (encrypted) casefolded equals
  `projects.name_key` (a **plaintext** casefold name). Roost has `tasks.project_id` and an HMAC
  `name_key`.
- **LazyClaw's sums** add every posted expense across currencies (`SUM(amount)`), so a mixed-currency
  project's "spent" differs in Roost (P4). `budget` includes top-ups (same meaning as Roost), but an
  opening budget given at create time has no ledger row, so Σ entries ≠ budget is normal there.

## 1. Field-by-field mapping

Ids are kept (LazyClaw uuids); `user_id` becomes the Roost user's id; every text field is
`enc:v2` with `user_aad(new_user_id, "<table>:<column>")`; LazyClaw `datetime('now')` stamps
(`YYYY-MM-DD HH:MM:SS`, UTC) become ISO UTC with `+00:00`.

**Tasks** (`tasks` → `tasks`)

| LazyClaw | Roost | Note |
|---|---|---|
| title, description, tags (JSON), steps (JSON `{id,title,done,created_at?,completed_at?}`) | same columns | same shapes (`roost/tasks/steps.py` was harvested from them); steps re-normalised by Roost's `steps.py` |
| category | `project_id` if its casefold matches a live project's `name_key`, and `category` NULL; else `category` stays as the **list** | phantom categories (<3 tasks) stay lists |
| priority `low/medium/high/urgent`, status `todo/in_progress/done/cancelled/failed`, owner | same | an unknown value stops the run (anomaly) |
| due_date, reminder_at, pre_reminders, recurring (cron), recur_until | same | copied as stored (naive = local wall clock, as Roost reads them); `validate_cron` must pass |
| allocated_budget REAL | `allocated_budget` enc:v2 decimal | kept only when the task gets a project (H11); else dropped and listed |
| comments (JSON `{id,ts,author,text,subtask_id}`) | `task_comments` rows: body enc:v2, `step_id` ← subtask_id, author `user` or the main bot's id | `agent` comments tainted |
| created_at, completed_at, updated_at, deleted_at | same | soft-deleted tasks are **not** imported (counted) |
| `owner='agent'` | `tainted=1` | spec §9.2 |
| — | `starred=0`, `estimate=NULL`, `created_by_bot=NULL` | v17 columns have no LazyClaw source |
| reminder_job_id, nag_count, nag_fired_at, reminder_offset_minutes, last_error, attempt_count, last_attempted_at, trace_session_id, lazybrain_note_id, progress_log, check_every, progress_template_id, nudge_sent_at, last_pulse_fired_at | **lost** | scheduler/pulse state; Roost's scheduler (M3) fires from `reminder_at`. progress_log entries are counted in the report |

**Projects** (`projects` → `money_projects`)

| LazyClaw | Roost | Note |
|---|---|---|
| name, description | enc:v2; `name_key` = HMAC(new DEK, folded name) | the plaintext `name_key` is dropped |
| budget REAL (0 default) | `budget` enc:v2 decimal; 0 with no ledger rows → NULL (no budget) | |
| — | `monthly_budget` NULL | LazyClaw had none |
| currency, status `active/archived`, start_date, due_date | same | currency must be 3 upper-case letters |
| color (any hex) | nearest of `PROJECT_COLORS`, NULL → first | changed |
| `name_key='general'` | Roost's existing General (H2): its id is mapped, not inserted | merged |
| is_favorite, lazybrain_note_id | **lost** | Roost has no project star |
| deleted_at set | not imported; its live expenses go to General (H9) | |

**Top-ups** (`budget_entries` → `money_topups`): amount REAL → signed enc decimal, currency,
source, kind `credit/edit`, `topup_id` NULL (LazyClaw edits are budget edits = Roost's "Budget set"),
deleted_at kept as history. Then **H4's invariant** `budget == Σ live rows`: any gap (an opening
budget) becomes one `edit` row "Opening budget (from LazyClaw)" dated the project's `created_at`.
An entry in another currency than its project is an anomaly.

**Expenses** (`project_expenses` → `money_expenses`): amount REAL → enc decimal (must be > 0), currency
(NULL → the project's, H7), description, vendor, notes, `spent_at` (NULL → the `created_at` date,
listed), status `posted/void`, `is_favorite`, `task_id` (must resolve to an imported task, else
NULL + listed), `step_id` ← subtask_id (must be one of the task's steps, else NULL: LazyClaw's own
demotion rule), `recurring_id` ← recurring_expense_id with `occurrence` = the `spent_at` date (a
second row on the same occurrence keeps `recurring_id` NULL, listed). `lazybrain_note_id` lost;
soft-deleted expenses not imported.

**Recurring** (`recurring_expenses` → `money_recurring`): amount, currency, description, vendor
copied; `cron_expression` → `cadence`+`anchor_day`: `M H D * *` → monthly on D, `M H * * W` →
weekly on W, `M H D Mo *` → yearly; any other cron is listed and **not** imported.
`next_due` = the first occurrence strictly after `max(last_charged_at, import day)`, so Roost's
lazy catch-up never backfills a charge LazyClaw already made. `task_id`, `job_id`, `next_run` lost;
`status='paused'` rules are imported with `deleted_at` = import time (kept, not charging).

**Currency and money rules:** an amount is `Decimal(repr(value))` (never `Decimal(float)`), then
quantised to cents; if that changes the value by more than 0.000001 it is an anomaly. Money is never
summed across currencies, in the report or in Roost.

## 2. Decryption path

1. The script reads LazyClaw's `SERVER_SECRET` with `getpass` (or `--old-secret-env NAME`), never
   from argv, never logged, never written. It never reads LazyClaw's `.env` itself.
2. From the **snapshot**, it takes the one users row (chosen by `--old-username`; more than one user
   without it stops the run), and unwraps the old DEK with a harvested copy of LazyClaw's
   `get_user_dek`: PBKDF2(secret + old_id, salt, 600k) → `unwrap_dek`; when `encrypted_dek` is
   NULL, the legacy `derive_server_key` (100k, fixed salt). Nothing is written back.
3. A **strict** decrypt: any failure, or the value `[encrypted]`, stops the run with the row id;
   `enc:v2` values are tried with the obvious AADs, a plain value is accepted and counted.
4. The Roost DEK comes from Roost's own `get_user_dek(new_user_id)`. Both keys live in `bytearray`s
   zeroed on exit. The Roost account, password and `server.secret` are untouched.

## 3. Reading LazyClaw safely (one host script)

- `mkdtemp()` dir, `chmod 0700`; the snapshot file is created 0600.
- Source opened as `file:<path>?mode=ro` (URI, **never** `immutable=1`, which would skip the WAL);
  `src.backup(dst)` (SQLite online backup API) copies a consistent view. The containers keep
  running; no `docker` call; nothing is written to LazyClaw (no pragma, no checkpoint, no VACUUM).
- Then on the copy: `PRAGMA integrity_check` must say `ok`, and a second backup's per-table counts
  must equal the first (Docker Desktop's bind mount gives no lock guarantee across host and VM).
- Every later step reads only the copy; it is deleted when the run ends (`--keep-snapshot` keeps
  it 0600 for the 30-day window, §4.7).

## 4. Dry run first (the default)

`uv run python -m roost.migrate.lazyclaw --source <db> --old-username <u>` without `--apply`
writes nothing to Roost and prints:
- counts per kind (tasks by status, steps, comments, projects active/archived, top-ups, expenses
  posted/void, recurring), and what is skipped (soft-deleted rows, lost fields, progress_log entries);
- per project and **per currency**: budget, Σ live top-ups, spent (LazyClaw way and Roost way side by
  side), remaining; plus totals per currency;
- 5 samples per kind with titles cut to 24 characters;
- anomalies: unmatched task/step links, float drift, zero or negative amounts, unknown enum values,
  non-convertible crons, a budget gap, timezone in settings ≠ Europe/Madrid, name clashes with
  Roost projects, tainted vs clean counts.

The report is shown to the user; `--apply` runs only after the user's "yes" to that report.

## 5. The import (`--apply`)

- First an online backup of `~/Roost/data/roost.db` to `~/Roost/backups/pre-lazyclaw-<ts>.db`
  (0700 / 0600); the gateway is stopped (or in maintenance) while it runs.
- One `BEGIN IMMEDIATE` transaction for every row; any error rolls back all of it.
- A new table `import_links(user_id, source='lazyclaw', kind, old_id, new_id, run_id, imported_at)`,
  unique on `(user_id, source, kind, old_id)`: a re-run skips what is linked, so it is idempotent.
  It is also the "imported from LazyClaw" mark: the API adds `imported_from: "lazyclaw"` and the web
  shows a small "from LazyClaw" label (no text is written into the user's descriptions).
- Every insert includes the Roost `user_id`; every lookup is `WHERE user_id = ?`.
- After commit: every row is read back through `TaskStore`, `ProjectStore`, `ExpenseStore`,
  `TopupStore` and the recurring store (no `[encrypted]`, every link resolves), and
  `numbers.py`'s results are compared with the dry run's Roost-way totals.
- **Undo:** `--undo <run_id>` deletes, in one transaction, exactly the rows linked to that run (and
  the opening-budget rows), restores the General project's budget, and refuses when a linked row
  was changed after import unless `--force`; the pre-import backup is the last resort.

## 6. Tasks (TDD; tests use synthetic LazyClaw-shaped fixtures only)

`tests/fixtures/lazyclaw_shape.sql` holds the LazyClaw DDL subset (users, tasks, projects,
project_expenses, recurring_expenses, budget_entries, with the column migrations applied);
`tests/migrate/lazyclaw_factory.py` builds a temp DB with a test secret and `enc:v1` values. The
tripwire refuses any path under `lazyclaw/data` or `~/Roost` in tests.

1. **Old keys** — `roost/migrate/lazyclaw/old_crypto.py` (harvest header): unwrap, legacy branch,
   strict decrypt. Tests: wrapped and NULL-DEK users, wrong secret, `[encrypted]`/tamper stops.
2. **Snapshot** — `source.py`: ro URI, online backup, 0700/0600, integrity and double-count check,
   no writes (the source's bytes and mtime are unchanged in the test). Tests on a WAL fixture.
3. **Money values** — `values.py`: float → Decimal, currency check, cron → cadence, next_due,
   colour to palette, timestamp normalising. Pure; table tests incl. 0.1+0.2 and 1e-9 drift.
4. **Mapping** — `mapping.py`: frozen `Imported*` dataclasses for every row kind, category →
   project/list, step and task links, General merge, opening-budget gap, taint. Pure tests.
5. **Dry run** — `report.py` + `__main__.py`: counts, per-currency totals, truncated samples,
   anomalies. Test: the report on a fixture matches fixed numbers and holds no full title.
6. **Schema + writer** — migration (next free version; v18–v20 are reserved, so v21 today) adds
   `import_links`; `writer.py` inserts in one transaction through store-level `insert_imported`
   helpers. Tests: ciphertext on disk with Roost AADs, user scoping, idempotent re-run, rollback
   on a failing row, H4 invariant holds.
7. **Read-back and Roost numbers** — after commit, store read-back and `numbers.py` totals equal
   the dry run. Test: mixed currencies, void, archived, removed step.
8. **Undo** — `undo.py`: run-scoped delete, edited-row refusal, `--force`. Tests.
9. **Label** — `imported_from` on task/project/expense wire models and the small web label
   (vitest). Coverage ≥ 80 % on `roost/migrate/`.

The real run (orchestrator, with the user): dry run → user reads the report → "yes" → `--apply`.

## 7. Open questions for the user

1. **LazyClaw keeps running after the import?** Its reminders and recurring expenses would fire
   twice once Roost's scheduler runs. Recommended: right after the import, pause recurring
   expenses and reminders in LazyClaw (or retire it).
2. **Roost's current tasks and money rows:** the hub design said "test data, wiped first". Is
   that still true, or must the import keep them (name clashes are then reported, not merged)?
3. **Taint on money:** LazyClaw has no author column on projects, expenses and top-ups. Spec §9.2
   says taint what can't be proven yours; that marks all of them. Import money clean instead?
4. **Reading while LazyClaw runs** (asked by this task) differs from spec §9.1 (stop the stack
   for ~2 minutes). Is the online read-only backup with the double check acceptable?

## User decisions (2026-10-20)

1. **LazyClaw is stopped fully after the import.** Roost never touches LazyClaw's containers. The final report gives the user the exact steps to stop it themselves.
2. **Roost's current tasks, expenses and projects are test data.** `--apply` first clears them for this user, inside the same transaction and after the Roost DB backup. It deletes the user's tasks, steps, comments, expenses, top-ups, recurring rows and every project except General. Notes and documents are left alone. The dry run reports how many rows the wipe would remove.
3. **Imported money and tasks are trusted** (`tainted = 0`). Every imported row still shows the "from LazyClaw" label.
4. **Reading LazyClaw:** the live, read-only online backup with the double count check, as planned (Q4).
5. **Schema:** `import_links` takes the next free version at build time (v21 after v17–v20).
