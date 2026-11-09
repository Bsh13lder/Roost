# Roost Routines and Plan (P0–P3), Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. The SDD workspace is `.superpowers/sdd/2026-10-22-roost-routines/` (`contract.md`, one `task-N-brief.md` per task, `progress.md`).

**Goal:** Bots work on a schedule while you are away, and keep a Plan you can see. A **routine** (a name, instructions and a schedule, with an on/off switch in the bot's Info tab) wakes its bot at Madrid times. Each run happens in the routine's own run log, under the same gate, taint and caps as your chat, and its final reply arrives in the bot's chat as a **Report**. A bot may propose routines, but only with your OK (an Ask card). When it is unsure about something that isn't urgent, it picks a safe default, writes the question in its **question book**, and keeps working. Every bot keeps a **Plan**: one sealed Markdown file in the Obsidian Tasks markup. The bot writes it and you can edit it, and it shows as a Calendar and a Kanban in a new **Plan** tab. The same scheduler also sends the task reminders that are stored today but never fire, the end-of-day summary, and **budget alert** Reports. A bot you tell to "use the full limit" may run past its daily cap, routines included, but never into the last 10% of the subscription.

**Architecture:**
- **Storage (schema v25, one migration "routines and plan"):**
  - routines: `routines`, `routine_runs`, `routine_proposals`;
  - the question book: `bot_questions`;
  - the Plan: `bot_plans`;
  - what was already sent: `reminder_sends` and `budget_alerts`;
  - one new column: `bots.full_limit_until`.
- **`roost/routines/`:**
  - `schedule.py` (pure: `times` and `cron`, `next_after`, `readable`, jitter, missed slots);
  - `models.py`, `store.py` (`RoutineStore`) and `runs.py` (`RoutineRunStore`);
  - `launcher.py` (queues a `routine` work item in the routine's run-log thread);
  - `scheduler.py` (`RoutineScheduler`: one asyncio task, an injectable clock, its jobs);
  - `reports.py` (Reports and quiet lines), `hooks.py` (`RoutineHooks`: the runner's after-run pass and the Ask deadline), `service.py` (`RoutineService`);
  - `proposals.py` (`ProposalStore`), `tool_specs.py` and `tools.py` (the bot's routine tools);
  - `system_reports.py` (reminders, the end-of-day summary, budget alerts: Reports with no model run).
- **`roost/questions/`** is the question book (`store.py`, `service.py`, `tool_specs.py`, `tools.py`). **`roost/plan/`** is the Plan (`grammar.py` pure, `store.py`, `service.py`, `prompt.py`, `tool_specs.py`, `tools.py`). **`roost/usage/reading.py`** is the usage reading port behind "use the full limit".
- **Runs:**
  - The scheduler never runs a model. It queues a `routine` item, and the bot's own drain loop runs it.
  - `claim_batch` takes your messages and card answers before routine items.
  - `TurnRunner._run_batch` calls `RoutineHooks.after_run` for a routine batch, which posts the Report, closes the slot and posts failure Reports.
  - Memory capture already skips routine runs.
- **Routes:** routines (`roost/gateway/routes/routines.py`), proposals and questions (`routine_asks.py`), the Plan (`plan.py`), and the full limit and usage (`usage.py`).
- **The web:**
  - Info tab: a Routines card (list, switch, editor with Times and Custom, History, Run now) and the full-limit switch, plus the question book.
  - Chat: Report messages, quiet routine lines and routine Ask cards.
  - My turn: open questions and routine proposals.
  - A new **Plan** tab: Calendar, Kanban and Edit as text, built as a lazy chunk on the Board's `CalendarGrid` and `useKanbanDrag`.
  - A read-only run-log page.

**Tech Stack:** no new dependency. Server: Python 3.12 (uv), FastAPI, pydantic 2, aiosqlite, `croniter` (already a dependency) and `zoneinfo`, tested with pytest. Web: Vite, React 19 and TypeScript, using `react-day-picker` (already a dependency), the `web/src/ui/` kit and `tokens.css`, tested with vitest, Testing Library and Playwright.

**Design (binding):** `docs/plans/2026-10-20-roost-routines-plan-design.md`, including its "User decisions (2026-10-20)" (D1–D4), which override §7. Hand-offs folded in:
- `docs/plans/2026-10-20-roost-tasks-money-polish-design.md` §9: reminders, the end-of-day summary and budget alerts;
- `.superpowers/sdd/2026-10-20-roost-tasks-money/progress.md`;
- `docs/plans/2026-10-20-roost-computers-2-design.md` D6: the full limit and the 10% reserve.

**Scope:**
- **In:** the design's P0–P3, plus the parts named above: reminders, the end-of-day summary, budget alerts and the full limit (design P4, pulled in because D3 is decided).
- **Out:** P5 and decision **D4**, the two-way Obsidian sync. It depends on the Mac folders feature (`docs/plans/2026-10-21-roost-mac-folders-design.md`). The `bot_plans.export_enabled` column is created here (default 0) and nothing reads it.

> **Status (2026-10-22): ready to execute once v23 and v24 have landed.** It was written against `night-1` at `f40a8fc`, where the latest migration is v22 (day notes). v23 (approval modes and Mac folders) and v24 (Computers) are planned to land first. The code was not pre-written. Each task gives exact files, test names, the shapes that matter and the commit, and the implementer writes the code test-first.

## Global Constraints

- **Path guard, first in every task:**
  - `git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel` must print `/Users/blckit/Desktop/Code_Projects/roost`.
  - `git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current` must print `night-1`.
  - If either check fails, stop.
- **Where you may edit:**
  - Only under `/Users/blckit/Desktop/Code_Projects/roost`, and never its `roost-ui/` folder (it is the user's).
  - `/Users/blckit/Desktop/Code_Projects/lazyclaw` is never opened or touched.
- **The live Roost is never touched:**
  - Never stop, restart, rebuild or call `roost-gateway-1` (`127.0.0.1:18800`), the keeper (`127.0.0.1:18801`) or `~/Roost/data`.
  - Any script or probe that imports `roost` runs with `ROOST_DATA_DIR` and `ROOST_DESKS_DIR` set to a fresh `mktemp -d`.
  - Run Playwright as `ROOST_DESKS_DIR=$(mktemp -d) make e2e`. It starts its own throwaway gateway. Never point a test at 18800.
- **Clean room (spec §10.3):** never open, fetch or search for the open-dot repos, `~/Roost-review/` or `~/.claude/projects/**`. No browser MCP tools, no subagents for searching.
- **Licences:** no new dependency, and `web/tests/licenseGate.test.ts` stays green.
- **Disk guard:** before `make e2e`, run `df -g /System/Volumes/Data | awk 'NR==2{print $4}'`. If fewer than 8 GB are free, stop and report.
- **Schema:**
  - **v25** is one additive, idempotent migration, frozen against `tests/fixtures/schema_v24.sql`. Task 1 writes that fixture **before** `roost/db/migrations.py` changes.
  - **Gate:** Task 1 starts only when `latest_version() == 24`. If v23 (approval modes and Mac folders) or v24 (Computers) hasn't landed, the implementer stops, and **the controller reassigns the number at build time**: the next free version, written into this plan, the contract and every brief that names it.
- **Data rules (CLAUDE.md):**
  - Every user-content column is `enc:v2` with the per-user DEK and `user_aad(user_id, "<table>:<column>")`, with the AADs listed in the Shared Contract.
  - Plaintext is allowed only for ids, timestamps, states, flags, `builtin`, `level`, `budget`, `month`, `slot_at` and `fire_at`.
  - Every query on user data names `user_id` in its `WHERE`. A background job first lists users (`SELECT id FROM users`, as `ensure_main_bots` does) and then queries per user.
  - Another user's routine, run, proposal, question, plan or bot is **404**, never the object. A body id the user doesn't own is **422** "No such bot.".
- **No LLM in tests:** use `ScriptedModel` and `ScriptedTeamModel`; `tests/conftest.py` forces `ROOST_MODEL=scripted`. The scheduler is tested with a **fake clock** (`Clock = Callable[[], datetime]`), never with sleeps.
- **Logging:** a scheduler or Report failure logs `user_id`, `bot_id`, `routine_id` and the exception's **type name** only. Never `exc_info`, never the exception's message, never routine, plan, question or message text.
- **Tests:** tests first (red, then green), with ≥80% line coverage on new code (`uv run pytest --cov=roost --cov-fail-under=80`). Web tests run in jsdom.
- **Code rules:**
  - Files ≤800 lines (typically 200–400), functions under 50 lines.
  - Frozen dataclasses and tuples; new objects in React state.
  - Pydantic at every boundary: `extra="forbid"` on HTTP bodies, `extra="ignore"` on tool arguments.
  - Plain-sentence refusals (422) and "Try again" for a lost race (409).
  - No magic values: server numbers in `roost/constants.py`, web numbers in `web/src/components/routines/constants.ts` and `web/src/components/plan/constants.ts`.
- **Tokens and bundle:**
  - No colour or font size outside `web/src/styles/tokens.css` (`web/tests/tokens.test.ts`).
  - The Plan tab is a **lazy chunk**. The entry stays within `web/bundle-budget.json` (`npm run size`).
  - The web reads the server's parse of the Plan; it never parses the Markdown itself.
- **Dark only (V4), and the vocabulary** (the CLAUDE.md table, `tests/test_vocabulary.py`):
  - Report, Ask cards, Parked run, Work queue, My turn, Off duty, Profile;
  - the tabs **Info · Plan · Documents · Computer · Links** (D1).
- **Git:**
  - Commit after each task's green tests.
  - Stage files **by name** (never `git add -A`, `-a` or `.`).
  - Conventional messages, with **no Co-Authored-By or any AI attribution line**.
- **Commands:**
  - Prefix every command with `cd /Users/blckit/Desktop/Code_Projects/roost &&`.
  - One file: `ROOST_DATA_DIR=$(mktemp -d) ROOST_DESKS_DIR=$(mktemp -d) uv run pytest tests/<file>.py -q`. The suite: the same with no path.
  - Web: `cd web && npx vitest run tests/<file>`, `npm test`, `npm run build && npm run size`.

## Design meets code

1. **Schema version.**
   - The design said v17. Numbers since then: v17 tasks and money, v18 import links, v19 pins, v20 models, v21 income, v22 day notes.
   - The controller's plan is v23 for approval modes and Mac folders, and v24 for Computers, so this plan is **v25**.
   - Task 1 stops if `latest_version() != 24`.
2. **Ask cards come from the approval-modes step (v23).**
   - Today the gate only says `do` or `never`. The `ask` verdict, the generic Ask card, parking a run and the `card_answer` resume all come with approval modes. This plan **does not build a second Ask-card system**.
   - It needs exactly one seam from it, used in Task 8: a deadline for a card opened by a routine run, and a callback when that card expires.
   - Task 8 checks for the seam first: `grep -n '"ask"' roost/talk/gate.py`, then the card store approval modes built.
   - If the seam is missing, Task 8 stops and reports. Every other task can still be built.
3. **Routine proposals are our own small card.**
   - `propose_routine`, `propose_routine_change` and a `pause_routine` from a tainted run never write a routine. They store a sealed **proposal** and post a `routine_proposal` card (role `bot`) in the bot's chat.
   - **Approve** (`POST /api/routine-proposals/{id}/approve`) makes the server write the routine. The model never does, so no run has to wait or resume.
   - The card looks like the other Ask cards (it reuses their web component if approval modes made one) and shows in My turn.
   - Design §3.4 makes a "routine write" a hard-floor row. This card *is* that ask, so no approval mode can relax it.
4. **Routine tools in a tainted run.**
   - D3's gate rule would refuse `propose_routine_change` and `pause_routine` (both `write_change`) in a tainted run. The design says a tainted run *proposes* and the card is marked instead.
   - So `ToolDef` gains `allowed_when_tainted: bool = False`, and `judge` skips D3's tainted-change and tainted-create-cap rules for such a tool. It still audits, and it still refuses names outside the run's allowlist.
   - The flag is set on exactly these tools: the routine tools (Task 9) and the plan tools (Task 14). The Plan is the bot's own diary, and the design says "do it, in any run" (design §4.3), with `PLAN_WRITES_PER_RUN` as its own cap.
   - `pause_routine` in a tainted run becomes a pause **proposal**. In a clean run it just pauses.
5. **The run-log thread.**
   - Each routine owns one thread with `kind='routine'`, made with the routine.
   - Thread lists, Earlier conversations and `main_thread` leave it out: `list_for_bot` changes `kind != 'room'` to `kind NOT IN ('room', 'routine')`, and `main_thread` already takes only `kind='chat'`.
   - The web opens it read-only at `/bots/:botId/routines/:routineId/log`.
6. **How a routine run gets its instructions.**
   - A work item's body never reaches the model (`turn.py`). So the launcher first posts a **`routine` message** in the run-log thread (role `user`, `author_bot_id` NULL), holding the routine's instructions and the slot line ("Planned 10:07, running at 14:22 (late)."). It then queues the item.
   - `routine` joins `_MODEL_KINDS`.
   - `_user_started` and `_may_open_cards` already exclude `WorkKind.ROUTINE`, so a routine run can't create bots and gets R5's loud `Blocked:` result instead of a Stuck card.
   - `_newest_user_text` reads only `kind='text'`, so the memory section ignores the routine message.
7. **Reports reach the model.**
   - A `report` message (role `bot`, in the bot's **main chat**) has the body JSON `ReportBody`.
   - `report` joins `_MODEL_KINDS`, and `_history` turns it into the text `"Report ({source}): {headline}\n\n{text}"`, so "about that report…" works. Its `tainted` flag carries over, as any bot reply's does.
   - `routine_note`, `question_note` and `routine_proposal` are UI only and never reach the model.
8. **Which Report is for which run.**
   - A routine run's state lives in `routine_runs` and is linked by `work_item_id`.
   - `RoutineHooks.after_run(user_id, batch, result, outcome)` runs only when every item of the batch is `WorkKind.ROUTINE`, called from `TurnRunner._after_run` next to the memory hook.
   - The scheduler's reconcile step closes rows whose work item is `dropped`: a Stop gives `skipped` with "Stopped", and Retire this bot cascades.
   - It also closes rows whose item is `done` with no finish (a crash between complete and after-run): `error`.
9. **Message-first claims.**
   - `claim_batch` orders by `CASE kind WHEN 'message' THEN 0 WHEN 'card_answer' THEN 0 WHEN 'routine' THEN 2 ELSE 1 END, rowid`.
   - It takes `exclude_kinds: frozenset[WorkKind] = frozenset()`, used for the 10% reserve (item 13).
   - `_leading_same_thread` still groups only the leading rows of one thread.
10. **Missed runs.**
    - A slot more than `ROUTINE_LATE_GRACE_SECONDS` late counts as missed.
    - All the missed slots of one routine in one tick become **one** `routine_runs` row with state `missed`, `missed_count = n`, `slot_at` the first missed slot, and a sealed note ("Missed 3 runs, 10:07 to 20:07, while Roost was off.").
    - The routine then **runs once**, in a second row (state `queued`) whose `slot_at` is the newest missed slot. Its slot line says it is late.
    - `next_run_at` is then the next slot after *now*, so a backlog never piles up.
11. **Jitter** is `int(sha256(f"{routine_id}|{slot_at}").hexdigest()[:8], 16) % (ROUTINE_JITTER_SECONDS + 1)` seconds, added to `next_run_at`, never to `slot_at`. So `slot_at` stays the user's minute, and the jitter is deterministic.
12. **The question book (D2).**
    - The tool is `note_question(question, default_choice, why?)` (`write_create`). A tainted run may call it under the shared tainted-create cap, and its row is `tainted`. It also has its own caps: `QUESTIONS_PER_RUN_MAX` and `QUESTIONS_OPEN_PER_BOT_MAX`.
    - The bot posts a quiet `question_note` line in the run's thread ("Picked: weekly, not daily · in your question book").
    - **Answering** (`POST /api/questions/{id}/answer`) seals the answer and posts **your** message in the bot's main chat ("About your question “…”: <answer>"). It then queues a `message` item with `ORIGIN_YOU`, exactly as the tasks-money P5 assignment does, so the bot adapts in a normal run.
    - Routine runs list that routine's last `QUESTION_ANSWERS_IN_PROMPT` answers in their instructions.
    - Urgent or risky questions are not a tool: the gate asks (approval modes), and item 2's deadline applies.
13. **The full limit (D3, D6).**
    - **The setting:** `bots.full_limit_until` (UTC ISO; NULL means off). It is set only through `PUT /api/bots/{id}/full-limit` from the Profile, and no tool writes it. It lasts until the reading's `resets_at`. With a reading but no reset time, it lasts until the next Madrid midnight.
    - **The reading:** `roost/usage/reading.py` defines `UsageReading(remaining_fraction: float, resets_at: datetime | None)` and the `UsageSource` protocol, whose `read()` returns a reading or `None`.
      - If v24 or C0 built a usage reading (`grep -rn "remaining\|rate_limit" roost/llm roost/usage 2>/dev/null`), Task 12 adapts it.
      - Otherwise it ships `NoUsageSource` (always `None`). The switch is then disabled with "Roost can't read your usage limit yet, so this stays off.", and the full limit never applies. That is the safe default: the reserve can't be checked without a reading.
    - **In the runner:** `_next_batch` lets a bot past `DAILY_RUN_CAP` only when its full limit is on and a reading shows more than `USAGE_RESERVE_FRACTION` left. When a reading shows ≤ the reserve, routine items are never claimed (`exclude_kinds={ROUTINE}`), and your own messages still run under the normal cap.
    - **In the scheduler:** a due slot is `held` when the bot is at its cap without an active full limit, or when the reading is inside the reserve. One Report per bot per reset window says "Paused my routines: the usage limit is nearly used up; I'll start again at <reset, Madrid>." At the plain daily cap, one Report per Madrid day says "Paused my routines: I've used today's {cap} runs. They start again after midnight."
14. **Reminders.**
    - `tasks.reminder_at` is plaintext UTC and indexed (`idx_tasks_user_reminder`). `pre_reminders` holds negative offsets against `reminder_at` (`roost/tasks/reminders.py` `parse_offset_against`).
    - **The fire times** of an open, not-deleted task are `reminder_at` plus each offset.
    - **The ledger:** `reminder_sends` is unique on `(user_id, task_id, fire_at)`, so a changed `reminder_at` fires again and a repeat never does.
    - **Lateness:** a fire time more than `REMINDER_LATE_GRACE_SECONDS` late is recorded `missed = 1`. All of a tick's missed ones become one "While Roost was off, these reminders passed: …" Report.
    - **Where:** the Report goes to the task's owner bot when `owner` is a bot id, else to the main bot.
15. **The end-of-day summary** is a **built-in routine** (`routines.builtin = 'day_summary'`, no model run).
    - It is seeded on the main bot, **off**, at `DAY_SUMMARY_DEFAULT_TIME` (21:00), the first time the scheduler sees the user, and the user switches it on in Info.
    - When due, the scheduler posts `render_day_summary(build_day_summary(...))` as a Report (`source="day_summary"`) and records the slot `done`.
    - It can't be deleted or proposed, only switched and re-timed. Its instructions are empty and its editor hides that field.
16. **Budget alerts.**
    - Every `BUDGET_ALERT_EVERY_TICKS` ticks, for each user's open projects, the job reads the numbers through `ProjectService` (which runs the repeating-charge catch-up first).
    - For each of the monthly limit and the total budget whose tone is `warn` or `over`, it inserts into `budget_alerts` (`project_id`, `budget` `month|total`, `level` `warn|over`, `month` `YYYY-MM`). That table is unique, and a new row means: post one Report (`source="budget"`) from the project's lead bot, else the main bot.
    - "Once per month" holds for both budgets: a total budget still over next month is said once more. Going straight to `over` records `warn` too, so there is no second Report for the lower level.

## Review Focus

Two security reviews (progress.md places them).

**(a) Routine runs without the user present: trust, taint and the approval policy.** Reviewed after Batch C (Tasks 8–10), with Task 4's launcher and Task 6's Reports.
1. **Starting taint.**
   - A `tainted` routine starts its run tainted.
   - A clean routine that loads a tainted Plan item, question or memory turns tainted.
   - A routine saved from a proposal made in a tainted run keeps `tainted = 1`.
   - Tests: `test_a_tainted_routine_starts_its_run_tainted` and `test_a_clean_routine_turns_tainted_on_a_tainted_plan_item` (Task 8).
2. **Nobody watching.**
   - The routine section says no one is watching live.
   - `create_bot` is never offered, memory capture never runs, and a block is a loud `Blocked:` result with no Stuck card.
   - Tests: `test_a_routine_run_never_creates_bots_or_captures_memory` and `test_a_routine_run_that_meets_a_wall_reports_it` (Task 8).
3. **Ask cards from a routine run.**
   - They expire at `min(next_run_at, now + ROUTINE_ASK_MAX_WAIT_HOURS)`. The run then ends, the slot is `expired`, and the Report names what was skipped.
   - A new slot while the card waits is `skipped` ("the last run was still waiting for you").
   - Tests: `test_an_unanswered_card_expires_at_the_next_slot` and `test_a_slot_is_skipped_while_a_card_waits` (Task 8).
4. **A routine changing routines.**
   - No tool writes a routine. Every proposal needs the user's Approve.
   - A proposal from a routine run is marked "A routine asked to change a routine". One from a tainted run is marked "This run read outside content".
   - Approving one names the routine's owner bot and `user_id`, and another user's proposal is 404.
   - Tests: `test_no_tool_writes_a_routine`, `test_a_tainted_proposal_is_marked_and_saved_tainted` and `test_another_users_proposal_is_404` (Task 9).
5. **The full limit can't be set by a model.**
   - No tool, no proposal and no question can change `full_limit_until`. Only `PUT /api/bots/{id}/full-limit` (RequireOrigin) can.
   - Tests: `test_no_tool_can_turn_on_the_full_limit` and `test_routines_never_start_inside_the_reserve` (Task 12).
6. **The question book.**
   - An answer becomes the user's own message (ORIGIN_YOU, untainted, because you typed it).
   - A question from a tainted run is shown with the "from web content" mark and never reaches a clean run's prompt as instructions (it is quoted data).
   - Tests: `test_an_answer_is_your_message_and_queues_a_run` and `test_a_tainted_question_is_quoted_and_marked` (Task 10).
7. **`allowed_when_tainted`** is on exactly the routine and plan tools.
   - Test: `test_only_routine_and_plan_tools_skip_the_tainted_rule` (Task 9).

**(b) The scheduler's resource limits.** Reviewed after Batch B (Tasks 4–7), with Task 11's jobs when they land (the reviewer re-reads `system_reports.py` at the end of Batch D).
1. **One owner.** One scheduler task per gateway, started in the lifespan after `resume_all()` and cancelled on shutdown. A tick that overruns `SCHEDULER_TICK_TIMEOUT_SECONDS` is cut and logged, and the next tick starts fresh. Test: `test_a_slow_tick_is_cut_and_the_next_one_runs` (Task 5).
2. **No double fire.** Every slot is a CAS on `next_run_at`, plus the `routine_runs` unique `(user_id, routine_id, slot_at)`. Test: `test_two_ticks_at_once_fire_a_slot_once` (Task 5).
3. **Bounded work per tick.**
   - At most `ROUTINE_TICK_MAX_FIRES` routine fires and `REMINDERS_PER_TICK_MAX` reminders per tick; the rest wait for the next tick.
   - At most `ROUTINES_PER_BOT_MAX` and `ROUTINES_PER_USER_MAX` routines, and `ROUTINE_PROPOSALS_OPEN_PER_BOT_MAX` open proposals.
   - A cron is refused if two fires come closer than `ROUTINE_MIN_INTERVAL_MINUTES`.
   - `REPORTS_PER_BOT_PER_HOUR` limits Reports.
   - Tests: `test_a_tick_fires_at_most_the_cap` (Task 5), `test_cron_closer_than_fifteen_minutes_is_refused` (Task 2), `test_the_routine_caps_are_422` (Task 7), `test_reports_past_the_hourly_cap_fold_into_the_run_log` (Task 6).
4. **Isolation.** One routine's exception, or a user's DEK failure, never stops the tick for others. It is logged with ids and the type name only. Test: `test_one_broken_routine_never_stops_the_others` (Task 5).
5. **Never a backlog.** Sleep through n slots and you get one `missed` row and one run. Off duty records `skipped` with no item. The daily cap gives `held`. Tests in Task 5.
6. **Retention.** `routine_runs` older than `RUN_LOG_RETENTION_DAYS` are pruned once per Madrid day, and so are `reminder_sends` older than `REMINDER_LOOKBACK_HOURS` × 2. Test: `test_old_runs_are_pruned` (Task 3).

---

## Shared Contract (every task uses these exact names)

### Schema v25 (Task 1)

```sql
CREATE TABLE IF NOT EXISTS routines (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,   -- its run-log thread, kind 'routine'
    name TEXT NOT NULL,                  -- enc:v2, AAD routines:name
    instructions TEXT NOT NULL,          -- enc:v2, AAD routines:instructions ('' sealed for a built-in)
    schedule TEXT NOT NULL,              -- enc:v2, AAD routines:schedule (Schedule JSON)
    builtin TEXT,                        -- NULL | 'day_summary' (no model run)
    enabled INTEGER NOT NULL DEFAULT 1,
    tainted INTEGER NOT NULL DEFAULT 0,
    created_by TEXT NOT NULL CHECK (created_by IN ('user', 'bot')),
    next_run_at TEXT,                    -- UTC ISO, jitter included; NULL when disabled
    last_run_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_routines_due ON routines(user_id, enabled, next_run_at);
CREATE INDEX IF NOT EXISTS idx_routines_bot ON routines(user_id, bot_id);
CREATE TABLE IF NOT EXISTS routine_runs (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    routine_id TEXT NOT NULL REFERENCES routines(id) ON DELETE CASCADE,
    bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    slot_at TEXT NOT NULL,               -- the planned Madrid time, as UTC ISO (no jitter)
    work_item_id TEXT,
    state TEXT NOT NULL CHECK (state IN ('queued','running','done','missed','skipped','held','expired','error')),
    missed_count INTEGER NOT NULL DEFAULT 0,
    note TEXT,                           -- enc:v2, AAD routine_runs:note
    started_at TEXT,
    finished_at TEXT,
    created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_routine_runs_slot ON routine_runs(user_id, routine_id, slot_at, state);
CREATE INDEX IF NOT EXISTS idx_routine_runs_routine ON routine_runs(user_id, routine_id, created_at);
CREATE INDEX IF NOT EXISTS idx_routine_runs_item ON routine_runs(user_id, work_item_id);
CREATE TABLE IF NOT EXISTS routine_proposals (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    routine_id TEXT REFERENCES routines(id) ON DELETE CASCADE,   -- NULL: a new routine
    action TEXT NOT NULL CHECK (action IN ('create','change','pause')),
    payload TEXT NOT NULL,               -- enc:v2, AAD routine_proposals:payload (ProposalPayload JSON)
    tainted INTEGER NOT NULL DEFAULT 0,
    from_routine INTEGER NOT NULL DEFAULT 0,
    state TEXT NOT NULL CHECK (state IN ('open','approved','declined','expired')),
    thread_id TEXT NOT NULL,
    message_id TEXT,
    created_at TEXT NOT NULL,
    decided_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_routine_proposals_open ON routine_proposals(user_id, state, created_at);
CREATE TABLE IF NOT EXISTS bot_questions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    routine_id TEXT REFERENCES routines(id) ON DELETE SET NULL,
    thread_id TEXT NOT NULL,
    question TEXT NOT NULL,              -- enc:v2, AAD bot_questions:question
    default_choice TEXT NOT NULL,        -- enc:v2, AAD bot_questions:default_choice
    why TEXT,                            -- enc:v2, AAD bot_questions:why
    answer TEXT,                         -- enc:v2, AAD bot_questions:answer
    tainted INTEGER NOT NULL DEFAULT 0,
    state TEXT NOT NULL CHECK (state IN ('open','answered','dismissed')),
    created_at TEXT NOT NULL,
    answered_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_bot_questions_open ON bot_questions(user_id, state, bot_id, created_at);
CREATE TABLE IF NOT EXISTS bot_plans (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    content TEXT NOT NULL,               -- enc:v2, AAD bot_plans:content
    item_taint TEXT NOT NULL,            -- enc:v2, AAD bot_plans:item_taint (JSON list of item ids)
    revision INTEGER NOT NULL DEFAULT 1,
    export_enabled INTEGER NOT NULL DEFAULT 0,   -- P5 (out of scope): nothing reads it yet
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_bot_plans_bot ON bot_plans(user_id, bot_id);
CREATE TABLE IF NOT EXISTS reminder_sends (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    fire_at TEXT NOT NULL,               -- UTC ISO
    missed INTEGER NOT NULL DEFAULT 0,
    sent_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_reminder_sends_once ON reminder_sends(user_id, task_id, fire_at);
CREATE TABLE IF NOT EXISTS budget_alerts (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    project_id TEXT NOT NULL REFERENCES money_projects(id) ON DELETE CASCADE,
    budget TEXT NOT NULL CHECK (budget IN ('month','total')),
    level TEXT NOT NULL CHECK (level IN ('warn','over')),
    month TEXT NOT NULL,                 -- YYYY-MM, Madrid
    sent_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_budget_alerts_once ON budget_alerts(user_id, project_id, budget, level, month);
-- AddColumn("bots", "full_limit_until", "TEXT")   -- UTC ISO; NULL: off
```

`idx_routine_runs_slot` includes `state` so a slot can hold its `missed` row and its one catch-up run. The scheduler's CAS on `next_run_at` is what stops a double fire. The index is the second lock.

### Constants (`roost/constants.py`, section "Routines and Plan")

| Name | Value | Name | Value |
|---|---|---|---|
| `ROUTINE_MAX_TIMES` | 12 | `ROUTINE_MIN_INTERVAL_MINUTES` | 15 |
| `ROUTINE_CRON_CHECK_FIRES` | 50 | `ROUTINE_TICK_SECONDS` | 30 |
| `ROUTINE_JITTER_SECONDS` | 90 | `ROUTINE_LATE_GRACE_SECONDS` | 600 |
| `ROUTINE_TICK_MAX_FIRES` | 50 | `SCHEDULER_TICK_TIMEOUT_SECONDS` | 20 |
| `ROUTINES_PER_BOT_MAX` | 20 | `ROUTINES_PER_USER_MAX` | 100 |
| `ROUTINE_NAME_MAX` | 80 | `ROUTINE_INSTRUCTIONS_MAX` | 4000 |
| `ROUTINE_PREVIEW_COUNT` | 5 | `ROUTINE_CARD_PREVIEW_COUNT` | 3 |
| `ROUTINE_RUNS_PAGE` | 50 | `RUN_LOG_RETENTION_DAYS` | 90 |
| `ROUTINE_ASK_MAX_WAIT_HOURS` | 24 | `ROUTINE_PROPOSALS_OPEN_PER_BOT_MAX` | 5 |
| `REPORT_HEADLINE_MAX` | 80 | `REPORT_TEXT_MAX_CHARS` | 8000 |
| `REPORT_QUIET_SENTINEL` | `"[nothing new]"` | `REPORTS_PER_BOT_PER_HOUR` | 6 |
| `QUESTION_MAX_CHARS` | 500 | `QUESTION_ANSWER_MAX_CHARS` | 1000 |
| `QUESTIONS_PER_RUN_MAX` | 3 | `QUESTIONS_OPEN_PER_BOT_MAX` | 20 |
| `QUESTION_ANSWERS_IN_PROMPT` | 5 | `REMINDER_LATE_GRACE_SECONDS` | 21600 |
| `REMINDER_LOOKBACK_HOURS` | 48 | `REMINDER_LOOKAHEAD_DAYS` | 8 |
| `REMINDERS_PER_TICK_MAX` | 100 | `DAY_SUMMARY_DEFAULT_TIME` | `"21:00"` |
| `BUDGET_ALERT_EVERY_TICKS` | 10 | `USAGE_RESERVE_FRACTION` | 0.10 |
| `PLAN_MAX_BYTES` | 262144 | `PLAN_MAX_ITEMS` | 2000 |
| `PLAN_ARCHIVE_DAYS` | 60 | `PLAN_WRITES_PER_RUN` | 20 |
| `PLAN_PROMPT_ITEMS` | 15 | `PLAN_ID_LENGTH` | 6 |

### Names

- **`roost/routines/schedule.py`:**
  - `TimesSchedule(kind="times", days: tuple[int, ...] (1=Mon … 7=Sun), times: tuple[str, ...] ("HH:MM"))`.
  - `CronSchedule(kind="cron", expr: str)`.
  - `Schedule = Annotated[TimesSchedule | CronSchedule, Field(discriminator="kind")]`.
  - Functions:
    - `parse_schedule(raw: Mapping) -> Schedule` (raises `ScheduleRefused(text)`);
    - `next_after(schedule, after_utc) -> datetime` (UTC, minute precision, no jitter);
    - `upcoming(schedule, after_utc, count) -> tuple[datetime, ...]`;
    - `readable(schedule) -> str`;
    - `jitter_seconds(routine_id, slot_at) -> int`;
    - `slots_between(schedule, after_utc, until_utc, limit) -> tuple[datetime, ...]`.
- **`roost/routines/models.py`:**
  - `Routine` and `RoutineDraft(bot_id, name, instructions, schedule, created_by, tainted=False, builtin=None, enabled=True)`;
  - `RoutinePatch(changes: Mapping)`;
  - `RoutineRun`, with `RunState = Literal[...]`;
  - `ProposalPayload(name, instructions, schedule)` (pydantic);
  - `Proposal`;
  - `ReportBody(source: Literal["routine","reminder","day_summary","budget","system"], headline, text, routine_id=None, run_id=None, log_thread_id=None, tainted=False)`.
- **Stores and services:**
  - `RoutineStore`: `create`, `get`, `list_for_bot`, `count_for_bot`, `count_for_user`, `update`, `delete`, `due`, `claim_slot`, `set_enabled`, `builtin_for`.
    - `due(user_id, now) -> tuple[Routine, ...]` returns enabled routines with `next_run_at <= now`, oldest first.
    - `claim_slot(user_id, routine_id, old_next, new_next, last_run_at) -> bool` is the CAS.
  - `RoutineRunStore`: `record`, `set_state`, `for_item`, `open_for_routine`, `list_for_routine`, `prune`, `recent_reports`.
  - `RoutineLauncher.launch(user_id, routine, slot_at, *, late, now) -> RoutineRun`.
  - `RoutineScheduler(config, *, clock, launcher, runs, routines, turns, bots, usage, jobs)`, with `tick()`, `loop()`, `start_scheduler(app_state) -> asyncio.Task` and `stop_scheduler(task)`.
  - `RoutineHooks`:
    - `after_run(user_id, batch, result, outcome)`;
    - `ask_deadline(user_id, items, now) -> datetime | None`;
    - `on_ask_expired(user_id, work_item_id, what)`;
    - `prompt_section(user_id, items) -> str | None`.
  - `RoutineService` (the one door for routes and tools): `list`, `create`, `update`, `delete`, `set_enabled`, `run_now`, `runs`, `preview`.
  - `post_report(talk, events, user_id, bot_id, body: ReportBody) -> Message | None` returns `None` when folded by the hourly cap. `post_routine_note(talk, events, user_id, thread_id, bot_id, verb, name)`.
  - `ProposalStore` and `ProposalService`: `propose`, `approve`, `decline`, `list_open`.
  - `QuestionStore` and `QuestionService`: `note`, `list`, `answer`, `dismiss`, `answers_for_routine`.
- **The Plan:** `PlanItem(id, status, text, tags, date, time, done_on, dropped_on, scheduled, indent, line_no)` and `PlanDoc(lines, items, unreadable)`.
  - `grammar.py`: `parse(text) -> PlanDoc`, `render(doc) -> str`, `canonical(text, today) -> str`, `assign_ids(doc, taken) -> PlanDoc`, `apply_status(item, status, today) -> PlanItem`, `archive_old(doc, today) -> PlanDoc`.
  - `PlanStore`: `get_or_create`, `save` (CAS).
  - `PlanService`: `read`, `put_text`, `patch_item`, `bot_add`, `bot_update`, `bot_complete`, `items_for_prompt`.
- **Usage:** `UsageReading`, `UsageSource`, `NoUsageSource`, `full_limit_active(bot, reading, now) -> bool`, `in_reserve(reading) -> bool`.
- **Work:** `routine_origin(name) -> str` returns `f"routine {name}"`. `WorkQueue.claim_batch(..., exclude_kinds=frozenset())`.
- **Tools:**
  - routines: `list_routines` (read), `propose_routine` (write_create), `propose_routine_change` (write_change), `pause_routine` (write_change);
  - questions: `note_question` (write_create);
  - the Plan: `plan_read` (read), `plan_add` (write_create), `plan_update` (write_change), `plan_complete` (write_change).
  - `ToolDef.allowed_when_tainted` is set on the routine and plan tools only.

### Message kinds (added to `MessageKind`)

| Kind | Role | Body | Reaches the model |
|---|---|---|---|
| `routine` | user | the routine's instructions + "\n\n" + slot line | yes (run-log thread) |
| `report` | bot | `ReportBody` JSON | yes, as `"Report ({source}): {headline}\n\n{text}"` |
| `routine_note` | activity | `{"routine_id", "verb", "name"}` | no |
| `routine_proposal` | bot | `{"proposal_id"}` | no |
| `question_note` | activity | `{"question_id", "default_choice"}` | no |

### Texts (`roost/routines/texts.py`, `roost/questions/texts.py`)

- **Slot lines:** `"Planned {hh:mm}, running now."` and `"Planned {hh:mm}, running at {hh:mm} (late)."`
- **Missed note:** `"Missed {n} runs, {first} to {last}, while Roost was off."`
- **Activity lines:**
  - `"Created routine · {name}"`, `"Updated routine · {name}"`, `"Paused routine · {name}"`;
  - `"Ran routine · {name} · nothing new"`;
  - `"Updated plan · {n} items"`.
- **Failure Report headlines:**
  - `"Missed: {name}"`, `"Held: {name}"`, `"Skipped: {name}"`;
  - `"Didn't finish: {name}"` (error, time cap or step cap);
  - `"Stuck: {name} on {host}"`;
  - `"Waited for you: {name}"` (expired).
- **Paused Reports:**
  - `"Paused my routines: the usage limit is nearly used up; I'll start again at {reset}."`
  - `"Paused my routines: I've used today's {cap} runs. They start again after midnight."`
- **Proposal card marks:** `"A routine asked to change a routine."` and `"This run read outside content."`
- **Answer message:** `"About your question “{question}”: {answer}"`
- **Full-limit refusal:** `"Roost can't read your usage limit yet, so this stays off."`
- **Refusals (422):**
  - `"A routine needs a name."`
  - `"Pick at least one day and one time."`
  - `"Times look like 10:07."`
  - `"Up to {ROUTINE_MAX_TIMES} times a day."`
  - `"That schedule runs more often than every {ROUTINE_MIN_INTERVAL_MINUTES} minutes."`
  - `"That custom schedule isn't valid."`
  - `"This bot already has {ROUTINES_PER_BOT_MAX} routines."`
  - `"You already have {ROUTINES_PER_USER_MAX} routines."`
  - `"The end-of-day summary can be switched off, not deleted."`
- **Conflict (409):** `"It's still running."`

### HTTP (all writes are `RequireOrigin`; every route takes `CurrentUser`)

| Route | Body → result |
|---|---|
| `GET /api/bots/{bot_id}/routines` | → `{routines: RoutineOut[]}` (`id, name, instructions, schedule, words, enabled, builtin, tainted, created_by, next_run_at, last_run_at, last_state`) |
| `POST /api/bots/{bot_id}/routines` | `RoutineIn{name, instructions, schedule, enabled=true}` → 201 `RoutineOut` |
| `PATCH /api/routines/{id}` | `RoutinePatchIn{name?, instructions?, schedule?, enabled?}` (an empty patch is 422) → `RoutineOut` |
| `DELETE /api/routines/{id}` | → 204 (a built-in is 422) |
| `POST /api/routines/{id}/run-now` | → 202 `{run: RoutineRunOut}` (409 "It's still running.") |
| `GET /api/routines/{id}/runs?before=` | → `{runs: RoutineRunOut[]}` (`id, slot_at, state, missed_count, note, started_at, finished_at, report_message_id`) |
| `POST /api/routines/preview` | `{schedule}` → `{words, next: string[]}` (Madrid ISO, `ROUTINE_PREVIEW_COUNT`), no write |
| `GET /api/routine-proposals?state=open` | → `{proposals: ProposalOut[]}` (`id, bot_id, action, routine_id, payload, words, next, diff, tainted, from_routine, created_at`) |
| `POST /api/routine-proposals/{id}/approve` / `decline` | → `ProposalOut` (409 when not open) |
| `GET /api/questions?state=open&bot_id=` | → `{questions: QuestionOut[]}` |
| `POST /api/questions/{id}/answer` | `{answer}` → `QuestionOut` · `POST /api/questions/{id}/dismiss` → `QuestionOut` |
| `GET /api/bots/{bot_id}/plan` | → `{content, revision, items: PlanItemOut[], unreadable: int}` |
| `PUT /api/bots/{bot_id}/plan` | `{content, base_revision}` → the same shape (409 + the current copy) |
| `PATCH /api/bots/{bot_id}/plan/items/{item_id}` | `{base_revision, status?, text?, date?, time?, tags?}` → the same shape (409 + current) |
| `GET /api/usage` | → `{readable: bool, remaining_fraction: float \| null, resets_at: string \| null}` |
| `PUT /api/bots/{bot_id}/full-limit` | `{on: bool}` → `BotOut` (gains `full_limit_until`; 422 with the refusal text when there is no reading) |

**Frames:**
- `routines_changed {bot_id}`
- `routine_run {routine_id, run_id, state}`
- `proposals_changed {bot_id}`
- `questions_changed {bot_id}`
- `plan_changed {bot_id, revision}`
- `bot_updated` for the full limit
- `message`, as today, for every new message kind

---

## Tasks

Batches:
- **A** (1–3): schema, schedules, stores;
- **B** (4–7): launcher, scheduler, Reports, routes;
- **C** (8–10): trust, proposals, the question book;
- **D** (11–12): no-model Reports, the full limit;
- **E** (13–14): Plan grammar, Plan server;
- **F** (15–17): the web;
- **G** (18): E2E and docs.

See `progress.md`.

### Task 1: Schema v25 (routines and plan), v24 frozen first

Design §2; Design meets code 1. One additive migration, `Migration(25, "routines and plan", …)`, plus the constants.

**Files:**
- Create: `tests/fixtures/schema_v24.sql` (Step 2a, before any other change) and `tests/test_migrations_v24.py`.
- Modify: `roost/db/migrations.py` and `roost/constants.py`.

- [ ] **Step 1: Path guard and gate.** Run the path guard. Then run `… uv run python -c "from roost.db.migrations import latest_version as v; print(v())"`. Expected: `24`. Any other number: stop, and report "Schema is v<N>, not v24: the controller reassigns this plan's number." Also stop if `tests/fixtures/schema_v24.sql` already exists.
- [ ] **Step 2a: Freeze v24.** Use the memory plan's Task 1 script with `14→24` and the header "frozen by routines Task 1". It runs in a `mktemp -d`. Expected: `grep -c routines tests/fixtures/schema_v24.sql` prints `0`.
- [ ] **Step 2b: Failing tests** in `tests/test_migrations_v24.py`, seeded from the v24 fixture with one user, bot, thread, task and project:
  - `test_v25_adds_the_routine_and_plan_tables_and_keeps_every_row`: `latest_version() == 25`, the exact columns of each new table, `bots.full_limit_until` present, and the row counts kept.
  - `test_a_slot_can_hold_a_missed_row_and_one_run`: the same `(routine_id, slot_at)` with states `missed` and `queued` is allowed, and two `queued` rows raise `sqlite3.IntegrityError`.
  - `test_reminders_and_budget_alerts_are_sent_once`: duplicate rows in either ledger raise `IntegrityError`.
  - `test_one_plan_per_bot`.
  - `test_retiring_a_bot_drops_its_routines_runs_questions_proposals_and_plan`.
  - `test_migration_25_is_idempotent`.
- [ ] **Step 3: Red.** Then implement: the table strings, the `Migration(25, …)` with the comment `# Routines and Plan (P0-P3). v23 approval modes + Mac folders, v24 Computers.`, and the constants table.
- [ ] **Step 4: Green.** `… uv run pytest tests/test_migrations_v24.py tests/test_migrations.py -q`.
- [ ] **Commit:** `git add tests/fixtures/schema_v24.sql tests/test_migrations_v24.py roost/db/migrations.py roost/constants.py && git commit -m "feat: schema v25 adds routines, runs, proposals, questions, plans and send ledgers, v24 frozen first"`

### Task 2: Schedules: Madrid times, cron, DST, jitter and missed slots (pure)

Design §3.1, §3.2 (jitter, missed); Design meets code 10–11.

**Files:**
- Create: `roost/routines/__init__.py`, `roost/routines/schedule.py` and `tests/test_routine_schedule.py`.

**Shapes:**
- `next_after` works in `MADRID_TZ`.
  - **`times`:** walk the Madrid days from `after`'s day for up to 8 days and take each listed day's times in order. A time that doesn't exist on that day (spring forward) becomes the first valid minute after it. A time that happens twice (fall back) is taken once, at its **first** occurrence (`fold=0`). Return the first instant strictly after `after_utc`.
  - **`cron`:** `croniter(expr, after_madrid)` gives local fires. Normalise each: a nonexistent local time moves forward, and an ambiguous one takes `fold=0` and skips the repeat.
- `parse_schedule` refuses with the contract texts: an empty name, empty days or times, a bad `HH:MM`, more than `ROUTINE_MAX_TIMES`, an invalid cron, or two of the next `ROUTINE_CRON_CHECK_FIRES` fires closer than `ROUTINE_MIN_INTERVAL_MINUTES`. Duplicate times are folded and the times are sorted.
- `readable`:
  - `times`: "Every day at 10:07, 15:07 and 20:07", "Weekdays at 09:00", "Mon, Wed and Fri at 18:30";
  - `cron`: "Custom: next 21 Oct 10:00, 22 Oct 10:00 and 23 Oct 10:00" (`upcoming`, 3).

**Tests** (fixed instants; nothing reads the wall clock):
- `test_every_day_three_times_gives_the_next_one`;
- `test_weekdays_skip_the_weekend`;
- `test_spring_forward_0230_fires_at_0300_on_2026_03_29`;
- `test_fall_back_0230_fires_once_on_2026_10_25`;
- `test_cron_follows_madrid_wall_clock_across_dst`;
- `test_cron_closer_than_fifteen_minutes_is_refused`;
- `test_bad_times_and_too_many_times_are_refused_with_plain_text`;
- `test_jitter_is_deterministic_and_within_bounds`;
- `test_slots_between_lists_every_missed_slot_up_to_the_limit`;
- `test_readable_words_for_times_and_cron`.

- [ ] Red → green: `… uv run pytest tests/test_routine_schedule.py -q`.
- [ ] **Commit:** `git add roost/routines/__init__.py roost/routines/schedule.py tests/test_routine_schedule.py && git commit -m "feat: routine schedules in Madrid time with DST rules, cron limits, jitter and missed slots"`

### Task 3: Routine and run stores (sealed, scoped, CAS)

Design §2, §3.2; Review (b) 2 and 6.

**Files:**
- Create: `roost/routines/models.py`, `roost/routines/store.py`, `roost/routines/runs.py`, `tests/test_routine_store.py` and `tests/test_routine_runs_store.py`.

**Shapes:**
- **Sealing:** `name`, `instructions` and `schedule` (JSON of the pydantic model) are sealed with `user_aad(user_id, "routines:<column>")`. `note` is sealed with `routine_runs:note`.
- **Creating a routine:** `create` also makes its run-log thread (`TalkStore.create_thread(..., kind="routine", title=name)`) in the same call, and sets `next_run_at = next_after(schedule, now) + jitter` when the routine is enabled.
- **`claim_slot`:** `UPDATE routines SET next_run_at = ?, last_run_at = ?, updated_at = ? WHERE id = ? AND user_id = ? AND next_run_at = ?`, true when `rowcount == 1`.
- **`set_enabled(False)`** sets `next_run_at = NULL`. `set_enabled(True)` computes the next slot from *now*, so turning a routine back on never replays a slot.
- **`RoutineRunStore`:**
  - `record(user_id, routine, slot_at, state, *, note=None, missed_count=0, work_item_id=None)`;
  - `open_for_routine` returns the `queued` or `running` rows;
  - `prune(user_id, before)` deletes rows created before `RUN_LOG_RETENTION_DAYS`;
  - `recent_reports(user_id, bot_id, since)` counts the Reports for the hourly cap. It reads `messages` with `kind='report'` and `author_bot_id`.

**Tests:**
- `test_create_seals_every_text_column` (raw row starts `enc:v2`);
- `test_create_makes_a_routine_thread`;
- `test_due_is_scoped_by_user`;
- `test_claim_slot_is_a_compare_and_swap`;
- `test_disable_clears_next_run_and_enable_never_replays`;
- `test_another_users_routine_is_none`;
- `test_open_for_routine_sees_queued_and_running`;
- `test_old_runs_are_pruned`;
- `test_a_run_note_is_sealed`.

- [ ] Red → green.
- [ ] **Commit:** `git add roost/routines/models.py roost/routines/store.py roost/routines/runs.py tests/test_routine_store.py tests/test_routine_runs_store.py && git commit -m "feat: routine and run stores, sealed and scoped, with a compare-and-swap slot claim"`

### Task 4: Routine work items: message-first claims and the launcher

Design §1, §3.2 (concurrency), §3.3 (origin); Design meets code 5, 6, 9.

**Files:**
- Create: `roost/routines/launcher.py`, `roost/routines/texts.py`, `tests/test_routine_launcher.py` and `tests/test_work_queue_priority.py`.
- Modify:
  - `roost/work/models.py`: `routine_origin`, and the module docstring;
  - `roost/work/queue.py`: the `claim_batch` order and `exclude_kinds`;
  - `roost/talk/store.py`: the `MessageKind` additions, and `kind NOT IN ('room','routine')` in both list queries;
  - `roost/talk/turn.py`: `routine` and `report` in `_MODEL_KINDS`, plus the `report` rendering in `_history`.

**Shapes:**
- `RoutineLauncher.launch` posts the `routine` message in `routine.thread_id`, then calls `TurnRunner.submit(user_id, WorkDraft(bot_id, thread_id, WorkKind.ROUTINE, origin=routine_origin(name), body=name, tainted=routine.tainted))`. It records the `routine_runs` row as `queued` with `work_item_id`.
- On Off duty, `submit` already posts a notice. The launcher is never called for an Off duty bot (Task 5 decides that first).

**Tests:**
- `test_your_message_claims_before_an_older_routine_item`;
- `test_card_answers_also_go_first`;
- `test_excluded_kinds_are_never_claimed`;
- `test_launch_posts_the_instructions_and_queues_a_routine_item`;
- `test_a_tainted_routine_queues_a_tainted_item`;
- `test_routine_threads_never_show_in_the_thread_list_or_as_the_main_chat`;
- `test_a_report_reaches_the_model_as_text` (ScriptedModel captures the request turns);
- `test_routine_notes_and_proposals_never_reach_the_model`.

- [ ] Red → green, plus `tests/test_work_queue.py tests/test_work_runner.py tests/test_main_thread.py`.
- [ ] **Commit:** `git add roost/routines/launcher.py roost/routines/texts.py roost/work/models.py roost/work/queue.py roost/talk/store.py roost/talk/turn.py tests/test_routine_launcher.py tests/test_work_queue_priority.py && git commit -m "feat: routine work items run in their own log thread, after your messages"`

### Task 5: The scheduler (injectable clock, missed runs, skips, holds, limits)

Design §3.2; Design meets code 8, 10, 11; Review (b) 1–5.

**Files:**
- Create: `roost/routines/scheduler.py`, `roost/routines/start.py` (`start_scheduler` and `stop_scheduler`, in the `models_check/start.py` pattern) and `tests/test_routine_scheduler.py`.
- Modify: `roost/gateway/app.py` (start after `resume_all()`, stop before `close_pool()`; `app.state.scheduler_task`), and `roost/talk/runner.py` (a public `runs_today(user_id, bot_id) -> int` and `limit_state(user_id, bot) -> LimitState` that Task 12 extends; for now `at_cap = count >= DAILY_RUN_CAP`).

**Shapes:**
- `tick()`: for each user id, wrapped in `asyncio.timeout(SCHEDULER_TICK_TIMEOUT_SECONDS)` around the whole tick, run `_fire_due(user)`, then `_reconcile(user)`, then the jobs (Task 11 adds them; empty here). Fires are counted across users up to `ROUTINE_TICK_MAX_FIRES`.
- `_fire_one(routine, now)`, decided in this order:
  1. Compute the slots in `(last_run_at or created_at, now]` with `slots_between`, and split them into on-time and missed (`> ROUTINE_LATE_GRACE_SECONDS` late).
  2. CAS `next_run_at` to `next_after(schedule, now) + jitter`. If it loses, stop: another tick took it.
  3. Bot Off duty: one `skipped` row ("Off duty"), with no item.
  4. `open_for_routine` not empty: `skipped` ("the last run was still going", or "still waiting for you" when it is parked).
  5. `limit_state.at_cap` (or inside the reserve, Task 12): `held`, plus the paused Report once (Task 6's `post_report`).
  6. Otherwise: one `missed` row if any slot was missed, then `launcher.launch(slot = newest slot, late = slot < now - grace)`.
- Built-in routines (`builtin` set) are handed to the job registry (Task 11) instead of the launcher.
- The loop: `while True: await tick(); await asyncio.sleep(ROUTINE_TICK_SECONDS)`. Every exception per user or per routine is caught and logged with ids and the type name.

**Tests** (fake clock, real stores in the temp data dir, ScriptedModel):
- `test_a_due_routine_queues_one_item`;
- `test_two_ticks_at_once_fire_a_slot_once` (`asyncio.gather(tick(), tick())`);
- `test_sleeping_through_three_slots_gives_one_missed_row_and_one_run`;
- `test_off_duty_records_skipped_and_queues_nothing`;
- `test_a_slot_is_skipped_while_the_last_run_is_going`;
- `test_held_at_the_daily_cap_with_one_report`;
- `test_a_tick_fires_at_most_the_cap`;
- `test_one_broken_routine_never_stops_the_others`;
- `test_a_slow_tick_is_cut_and_the_next_one_runs`;
- `test_the_gateway_starts_and_stops_the_scheduler` (TestClient lifespan).

- [ ] Red → green.
- [ ] **Commit:** `git add roost/routines/scheduler.py roost/routines/start.py roost/gateway/app.py roost/talk/runner.py tests/test_routine_scheduler.py && git commit -m "feat: the routine scheduler with a fake-clock tick, missed runs, skips, holds and limits"`

### Task 6: Reports and the after-run pass

Design §3.5; Design meets code 7, 8.

**Files:**
- Create: `roost/routines/reports.py`, `roost/routines/hooks.py` and `tests/test_routine_reports.py`.
- Modify: `roost/talk/runner.py` (a `routines: RoutineHooks | None = None` constructor argument; `_after_run` calls `routines.after_run` for an all-`ROUTINE` batch before the memory hook; `_execute` stays the error boundary), `roost/gateway/app.py` (wire `RoutineHooks`), and `roost/routines/scheduler.py` (`_reconcile`).

**Shapes:**
- `after_run` maps the result to the run's state:
  - `outcome == "done"` with no block → `done`;
  - a block → `error`, with the Stuck headline;
  - `time_cap`, `step_cap` or `error` → `error`;
  - `stopped` or `interrupted` → `skipped` ("Stopped").
- **The Report:**
  - The headline is the reply's first non-empty line, with Markdown `#` removed and cut to `REPORT_HEADLINE_MAX`.
  - The text is the reply, cut to `REPORT_TEXT_MAX_CHARS`.
  - `log_thread_id` is the routine's thread, and `tainted` is `result.tainted`.
  - A reply exactly `REPORT_QUIET_SENTINEL` (after strip) posts only `routine_note` "Ran routine · {name} · nothing new" in the main chat.
- **The hourly cap:** past `REPORTS_PER_BOT_PER_HOUR`, the Report is not posted. One `routine_note` line goes in the run-log thread instead ("More reports this hour than the limit; this one is in the log"), and a failure still posts.
- **Failure Reports** (missed, held, skipped while waiting, expired, error or stuck) always post, never folded.
- **Frames:** Reports publish a `message` frame and a `routine_run` frame.

**Tests:**
- `test_the_final_reply_becomes_a_report_in_the_main_chat`;
- `test_the_quiet_sentinel_posts_only_a_line`;
- `test_a_tainted_run_gives_a_marked_report`;
- `test_reports_past_the_hourly_cap_fold_into_the_run_log`;
- `test_failures_always_report`;
- `test_a_stopped_routine_run_is_closed_as_skipped` (reconcile);
- `test_a_non_routine_run_never_reports`.

- [ ] Red → green, plus `tests/test_work_runner.py`.
- [ ] **Commit:** `git add roost/routines/reports.py roost/routines/hooks.py roost/routines/scheduler.py roost/talk/runner.py roost/gateway/app.py tests/test_routine_reports.py && git commit -m "feat: a routine run's final reply is a Report in the bot's chat, failures always report"`

### Task 7: RoutineService and the routine routes

Design §3.6; HTTP table; Review (b) 3.

**Files:**
- Create: `roost/routines/service.py`, `roost/gateway/routes/routines.py` and `tests/test_routines_api.py`.
- Modify: `roost/gateway/app.py` (`app.state.routines` and the router).

**Shapes:**
- The pydantic bodies use `extra="forbid"`. `schedule` goes through `parse_schedule` and `ScheduleRefused` gives 422.
- Every write publishes `routines_changed` and posts the `routine_note` line in the bot's main chat ("Created routine · …" and so on; Delete posts none).
- `run_now` records a slot at `now`, to the second, so it never collides with a scheduled minute in `idx_routine_runs_slot`, and launches it. It returns 409 when `open_for_routine` is not empty, and it **does** count against the daily cap (held → 409 "Daily limit reached.").
- A built-in routine can be patched in `schedule` and `enabled` only. Any other field gives 422.
- The bot is looked up with `user.id` first. Another user's bot gives 404.

**Tests:**
- `test_create_list_patch_and_delete`;
- `test_bad_schedules_are_422_with_plain_text`;
- `test_the_routine_caps_are_422`;
- `test_preview_gives_words_and_the_next_five_madrid_times`;
- `test_run_now_queues_and_a_second_run_now_is_409`;
- `test_runs_page_by_before`;
- `test_every_write_needs_the_origin`;
- `test_every_write_publishes_routines_changed_and_a_quiet_line`;
- `test_another_users_routines_runs_and_bots_are_404`;
- `test_a_builtin_cannot_be_deleted_or_renamed`.

- [ ] Red → green.
- [ ] **Commit:** `git add roost/routines/service.py roost/gateway/routes/routines.py roost/gateway/app.py tests/test_routines_api.py && git commit -m "feat: routine routes: create, edit, switch, run now, history and schedule preview"`

**SECURITY REVIEW (b) here, at the end of Batch B** (Review Focus (b)).

### Task 8: Trust in a routine run (taint, nobody watching, Ask-card deadline)

Design §3.3; Design meets code 2, 6; Review (a) 1–3.

**Files:**
- Create: `tests/test_routine_trust.py`.
- Modify:
  - `roost/talk/instructions.py`: `routine_section(name, slot_line, answers)` and a `routine=` parameter on `build_instructions`;
  - `roost/talk/turn.py`: `_prepare` passes `inputs.routine_section`;
  - `roost/talk/turn.py` `RunInputs`: `routine_section: str | None = None`;
  - `roost/talk/runner.py`: `_inputs` asks `RoutineHooks.prompt_section`;
  - `roost/routines/hooks.py`: `prompt_section`, `ask_deadline` and `on_ask_expired`;
  - **the approval-modes Ask-card opener and its expiry path**, at the file Step 1 finds.

**Step 1 (stop check):** `grep -n '"ask"' roost/talk/gate.py`, then find where an `ask` verdict opens a card and parks the run. If there is no `ask` verdict or no expiry path, **stop**, and report "Approval modes' Ask cards are missing; Task 8 waits for them." Do not build a card system.

**Shapes:**
- **`routine_section`:**
  - It says: "This run is the routine “{name}”, started by its schedule. Nobody is watching live: if a step needs the user's OK, the Ask card waits until this routine's next run. For a question that isn't urgent, pick a safe default, say which one you picked, call note_question, and carry on. Your final reply becomes a Report in your chat. Reply exactly [nothing new] when there is nothing to report."
  - It then gives the slot line and the routine's last answers, each `_escape_tags`-quoted as data.
- **`ask_deadline`:** for a batch of `ROUTINE` items it returns `min(routine.next_run_at, now + ROUTINE_ASK_MAX_WAIT_HOURS)`, otherwise `None` (the chat keeps approval modes' own rule).
- **`on_ask_expired`:** sets the slot to `expired` and posts the "Waited for you" failure Report naming the skipped step, which is the card's one-line summary.
- While a card waits, the run row stays `running`, so Task 5's skip-while-going covers "still waiting for you". The scheduler tells the two apart by whether there is an open card for the work item.

**Tests:**
- `test_a_tainted_routine_starts_its_run_tainted`;
- `test_a_clean_routine_turns_tainted_on_a_tainted_plan_item` (once Task 14 lands, the test stubs a tainted `ToolOutcome` from a domain handler);
- `test_the_routine_section_says_nobody_is_watching_and_quotes_answers`;
- `test_a_routine_run_never_creates_bots_or_captures_memory`;
- `test_a_routine_run_that_meets_a_wall_reports_it` (Blocked result, no Stuck card, a Stuck Report);
- `test_an_unanswered_card_expires_at_the_next_slot`;
- `test_a_slot_is_skipped_while_a_card_waits`;
- `test_a_chat_card_keeps_its_own_deadline`.

- [ ] Red → green, plus `tests/test_instructions.py tests/test_stuck_runs.py tests/test_memory_capture.py`.
- [ ] **Commit:** `git add roost/talk/instructions.py roost/talk/turn.py roost/talk/runner.py roost/routines/hooks.py tests/test_routine_trust.py <the approval-modes file(s) Step 1 found, by name> && git commit -m "feat: routine runs start with their routine's taint, say nobody is watching, and their Ask cards wait until the next run"`

### Task 9: The bot's routine tools and routine proposal cards

Design §3.4; Design meets code 3, 4; Review (a) 4, 7.

**Files:**
- Create: `roost/routines/proposals.py` (`ProposalStore`, `ProposalService`), `roost/routines/tool_specs.py`, `roost/routines/tools.py` (`RoutineTools`), `roost/gateway/routes/routine_asks.py` (the proposal routes; Task 10 adds the questions), `tests/test_routine_tools.py` and `tests/test_routine_proposals_api.py`.
- Modify: `roost/talk/tool_def.py` (`allowed_when_tainted`), `roost/talk/gate.py` (`judge` skips the D3 rules for it), `roost/talk/tool_catalog.py` (`*ROUTINE_TOOL_DEFS`), `roost/talk/domain_tools.py` (`RoutineTools`), `roost/gateway/app.py`, and `tests/test_every_bot_tools.py` (the catalog count).

**Shapes:**
- `list_routines` lists only its own routines: name, words, on/off and the next run in Madrid time. The result is quoted data.
- **`propose_routine` and `propose_routine_change`:**
  - Validate with `ProposalPayload` and `parse_schedule`, and check the caps (`ROUTINES_PER_BOT_MAX`, `ROUTINE_PROPOSALS_OPEN_PER_BOT_MAX`).
  - Store the proposal sealed, with `tainted = ctx.tainted` and `from_routine` true when the run's items are `ROUTINE` (`RecordContext` gains `from_routine: bool = False`).
  - Post the `routine_proposal` card message in the run's thread, and also in the main chat when the run is a routine's.
  - Publish `proposals_changed`, and return "Asked the user to approve “{name}”. It starts only after they say yes."
- **`pause_routine`:** in a clean run it pauses and posts "Paused routine · …". In a tainted run it becomes a `pause` proposal.
- **Approve:**
  - `create`: `RoutineService.create(created_by="bot", tainted=proposal.tainted)`.
  - `change`: patch, and the routine's `tainted |= proposal.tainted`.
  - `pause`: `set_enabled(False)`.
  - Approve then posts the quiet line, and the proposal becomes `approved`. Decline: `declined`.
- **`ProposalOut`** carries `words` and `next` (`ROUTINE_CARD_PREVIEW_COUNT` Madrid times), and for a change a field-by-field `diff` (`[{field, before, after}]`).

**Tests:**
- `test_no_tool_writes_a_routine`;
- `test_propose_posts_a_card_and_approve_creates_the_routine`;
- `test_a_change_card_shows_the_diff`;
- `test_a_tainted_proposal_is_marked_and_saved_tainted`;
- `test_a_routine_run_proposal_is_marked`;
- `test_pause_just_pauses_in_a_clean_run_and_asks_in_a_tainted_one`;
- `test_list_routines_shows_only_its_own`;
- `test_only_routine_and_plan_tools_skip_the_tainted_rule` (the catalog flags must equal exactly the routine tool names plus `plan_add`, `plan_update` and `plan_complete`; until Task 14 lands, the test lists the plan names as expected-to-come and asserts a subset);
- `test_another_users_proposal_is_404`;
- `test_approving_twice_is_409`.

- [ ] Red → green, plus `tests/test_gate.py tests/test_every_bot_tools.py`.
- [ ] **Commit:** `git add roost/routines/proposals.py roost/routines/tool_specs.py roost/routines/tools.py roost/gateway/routes/routine_asks.py roost/talk/tool_def.py roost/talk/gate.py roost/talk/tool_catalog.py roost/talk/domain_tools.py roost/gateway/app.py tests/test_routine_tools.py tests/test_routine_proposals_api.py tests/test_every_bot_tools.py && git commit -m "feat: bots propose routines through Ask cards; only your Approve writes one"`

### Task 10: The question book (D2)

Decision D2; Design meets code 12; Review (a) 6.

**Files:**
- Create: `roost/questions/__init__.py`, `store.py`, `service.py`, `texts.py`, `tool_specs.py`, `tools.py`, `tests/test_question_book.py` and `tests/test_questions_api.py`.
- Modify: `roost/gateway/routes/routine_asks.py` (the question routes), `roost/talk/tool_catalog.py`, `roost/talk/domain_tools.py`, `roost/routines/hooks.py` (`answers_for_routine` in `prompt_section`), `roost/gateway/app.py`, and `tests/test_every_bot_tools.py`.

**Shapes:**
- `note_question(question, default_choice, why?)` uses `ToolText` fields capped at `QUESTION_MAX_CHARS`.
- It refuses past `QUESTIONS_PER_RUN_MAX` ("I've noted enough questions in this run; I'll carry on with the defaults.") or `QUESTIONS_OPEN_PER_BOT_MAX`.
- It stores the row with `routine_id` (when the run is a routine's) and `tainted`, posts the `question_note` line, publishes `questions_changed`, and returns "Noted. Carry on with: {default_choice}."
- **Answer:** seal the answer, then `talk.add_message(role="user", kind="text", body=answer_text)` in the main chat, then queue `TurnRunner.submit(WorkDraft(kind=MESSAGE, origin=ORIGIN_YOU, tainted=False, message_id=…))`. Answering a question that isn't open gives 409.
- **Dismiss:** close the question with no message.
- **`GET /api/questions`** with no `bot_id` returns all of the user's open questions, for My turn.

**Tests:**
- `test_a_question_is_stored_sealed_with_a_quiet_line`;
- `test_the_per_run_and_open_caps`;
- `test_an_answer_is_your_message_and_queues_a_run`;
- `test_a_tainted_question_is_quoted_and_marked`;
- `test_routine_runs_see_their_last_answers`;
- `test_dismiss_closes_without_a_message`;
- `test_another_users_questions_are_404`;
- `test_every_write_needs_the_origin`.

- [ ] Red → green.
- [ ] **Commit:** `git add roost/questions/__init__.py roost/questions/store.py roost/questions/service.py roost/questions/texts.py roost/questions/tool_specs.py roost/questions/tools.py roost/gateway/routes/routine_asks.py roost/talk/tool_catalog.py roost/talk/domain_tools.py roost/routines/hooks.py roost/gateway/app.py tests/test_question_book.py tests/test_questions_api.py tests/test_every_bot_tools.py && git commit -m "feat: the question book: bots note non-urgent questions with a default, your answer comes back as your message"`

**SECURITY REVIEW (a) here, at the end of Batch C** (Review Focus (a); Task 12's item 5 is checked again at the end of Batch D).

### Task 11: Reports with no model run: reminders, the end-of-day summary, budget alerts

Hand-off §9; Design meets code 14–16; Review (b) 3.

**Files:**
- Create: `roost/routines/system_reports.py` (`ReminderJob`, `DaySummaryJob`, `BudgetAlertJob`, `jobs_for(app_state) -> tuple[Job, ...]`), `tests/test_reminder_job.py`, `tests/test_day_summary_job.py` and `tests/test_budget_alert_job.py`.
- Modify:
  - `roost/routines/scheduler.py`: the job registry; a `day_summary` built-in goes to `DaySummaryJob.fire`;
  - `roost/routines/store.py`: `ensure_day_summary(user_id, main_bot_id)`, which seeds the built-in, off;
  - `roost/tasks/day_summary.py`: `render_day_summary` if no text renderer is exported yet. Read the file first; it has `_section` and `_spent_lines`;
  - `roost/tasks/store.py`: `reminders_between(user_id, start, end) -> tuple[Task, ...]`, for open, not-deleted tasks with `reminder_at` in range.

**Shapes:**
- **`ReminderJob.run(user_id, now)`:**
  - Window: `now - REMINDER_LOOKBACK_HOURS` to `now + REMINDER_LOOKAHEAD_DAYS`.
  - Fire times: `reminder_at` and every `parse_offset_against(offset, reminder_at)`. Keep those `<= now`, then `INSERT OR IGNORE` into `reminder_sends`; only a new row (`rowcount == 1`) posts.
  - A fire time within the grace period gives a Report "Reminder: {title}" whose text has the due in Madrid words. Late ones gather into one Report.
  - At most `REMINDERS_PER_TICK_MAX`.
  - The recipient bot is the owner when it is a bot id and still exists, else the main bot.
- **`DaySummaryJob.fire(user_id, routine, slot)`:** `build_day_summary(user_id, madrid_today(slot), …)` becomes a Report headed "Your day, {day}", and the slot is recorded `done`.
- **`BudgetAlertJob.run(user_id, now)`** runs every `BUDGET_ALERT_EVERY_TICKS`-th tick. For each open project, `ProjectService` detail gives `numbers` (monthly and total `BudgetLine`). For each line with tone `warn` or `over`, it inserts the level's row, plus `warn` too when it is `over`. A new `over` row posts "Over budget: {project}" (otherwise "Near the budget: {project}"), with spent / budget / percent in the project's currency and a deep link `/board/projects/{id}`. It comes from `lead_bot_id`, else the main bot.

**Tests:**
- `test_a_reminder_fires_once_at_its_time`;
- `test_advance_reminders_fire_before_it`;
- `test_a_changed_reminder_fires_again`;
- `test_done_and_deleted_tasks_never_remind`;
- `test_reminders_missed_while_off_come_as_one_report`;
- `test_an_assigned_task_reminds_through_its_bot`;
- `test_reminders_are_scoped_by_user`;
- `test_the_day_summary_is_seeded_off_on_the_main_bot`;
- `test_the_day_summary_posts_when_on`;
- `test_crossing_warn_then_over_reports_each_once_a_month`;
- `test_straight_to_over_reports_once`;
- `test_a_new_month_reports_again`;
- `test_budget_alerts_read_repeating_charges`.

- [ ] Red → green.
- [ ] **Commit:** `git add roost/routines/system_reports.py roost/routines/scheduler.py roost/routines/store.py roost/tasks/day_summary.py roost/tasks/store.py tests/test_reminder_job.py tests/test_day_summary_job.py tests/test_budget_alert_job.py && git commit -m "feat: reminders fire, the end-of-day summary and budget alerts arrive as Reports"`

### Task 12: Use the full limit (D3, D6) and the 10% reserve

Design §3.2 "Usage cap"; Design meets code 13; Review (a) 5.

**Files:**
- Create: `roost/usage/__init__.py`, `roost/usage/reading.py`, `roost/gateway/routes/usage.py`, `tests/test_usage_reading.py` and `tests/test_full_limit.py`.
- Modify: `roost/bots/models.py` and `roost/bots/store.py` (`full_limit_until`, `set_full_limit`), `roost/bots/service.py` (`bot_out` gains `full_limit_until`), `roost/talk/runner.py` (`limit_state` and `_next_batch`), `roost/routines/scheduler.py` (held in the reserve, the paused Report once per reset window), and `roost/gateway/app.py` (`app.state.usage`, the router).

**Step 1:** `grep -rn "remaining\|rate_limit\|usage" roost/llm roost/computers 2>/dev/null | head`. If v24 or C0 gives a reading, write `SdkUsageSource` against it. Otherwise only `NoUsageSource`.

**Shapes:**
- `LimitState(count, at_cap, full_limit, in_reserve, reading)`.
- `_next_batch`:
  - when `at_cap and not (full_limit and reading and not in_reserve)`, call `_hit_daily_limit`;
  - when `in_reserve`, claim with `exclude_kinds={WorkKind.ROUTINE}`.
- The `PUT` with `on: true` and no reading gives 422 with the refusal text. With `on: true`, `full_limit_until` is the reading's `resets_at`, or the next Madrid midnight.

**Tests:**
- `test_without_a_reading_the_switch_is_refused`;
- `test_full_limit_lets_a_bot_run_past_its_daily_cap`;
- `test_full_limit_ends_at_the_reset`;
- `test_routines_never_start_inside_the_reserve`;
- `test_your_messages_still_run_inside_the_reserve`;
- `test_the_paused_report_is_posted_once_per_reset_window`;
- `test_no_tool_can_turn_on_the_full_limit` (no catalog tool's schema names it; the setting changes only through the route);
- `test_another_users_bot_is_404`.

- [ ] Red → green, plus `tests/test_work_runner.py tests/test_routine_scheduler.py`.
- [ ] **Commit:** `git add roost/usage/__init__.py roost/usage/reading.py roost/gateway/routes/usage.py roost/bots/models.py roost/bots/store.py roost/bots/service.py roost/talk/runner.py roost/routines/scheduler.py roost/gateway/app.py tests/test_usage_reading.py tests/test_full_limit.py && git commit -m "feat: use the full limit per bot until the reset, routines included, never into the last 10%"`

### Task 13: The Plan grammar (pure, lenient read, canonical write)

Design §4.1.

**Files:**
- Create: `roost/plan/__init__.py`, `roost/plan/grammar.py`, `tests/test_plan_grammar.py` and `tests/fixtures/plan/` (`obsidian_tasks.md`, `user_order.md`, `odd_lines.md`, `canonical.md`).

**Shapes:**
- **The grammar** is exactly design §4.1.
  - Statuses: `" "` planned, `"/"` on_it, `"x"` done, `"-"` dropped.
  - Fields: `⏰ HH:MM`, `📅`, `⏳`, `✅`, `❌` dates, and `🆔 [a-z0-9]{6}`. Tags are `#[A-Za-z0-9_/-]+`.
  - Indent `""`, two spaces, four spaces or a tab (one subtask level).
  - CRLF is read as LF.
- **Canonical writer:** `desc ⏰ HH:MM #tags 📅 date ⏳ date ✅ date ❌ date 🆔 id`.
- **Unknown emoji fields** (`🔁`, `⏫`) stay in `desc`.
- **Unreadable lines:** an invalid date or time makes the line `other`, counted in `unreadable` and kept byte for byte.
- **`apply_status`:**
  - `done` adds `✅ today` when missing;
  - `dropped` adds `❌ today`;
  - leaving either state clears its date.
- **`assign_ids`** gives a fresh `[a-z0-9]{6}` (`secrets.choice`) to every item without one, avoiding `taken`.
- **`archive_old`** moves done or dropped items older than `PLAN_ARCHIVE_DAYS` under a final `## Archive` heading, which it creates once.
- **Limits:** `PLAN_MAX_BYTES` and `PLAN_MAX_ITEMS` raise `PlanRefused("The Plan is too long. Archive or remove some items.")`.

**Tests** (tables, because `hypothesis` is not a dependency):
- `test_round_trip_is_the_canonical_form`;
- `test_other_lines_survive_byte_for_byte`;
- `test_both_field_orders_parse_the_same`;
- `test_obsidian_tasks_fixture_parses_every_field`;
- `test_unknown_emoji_fields_stay_in_the_text`;
- `test_bad_dates_make_a_line_unreadable_not_lost`;
- `test_status_rules_add_and_clear_done_and_dropped_dates`;
- `test_ids_are_assigned_once_and_unique`;
- `test_one_subtask_level_with_spaces_or_a_tab`;
- `test_archive_moves_old_finished_items`;
- `test_limits_refuse_with_plain_text`.

- [ ] Red → green.
- [ ] **Commit:** `git add roost/plan/__init__.py roost/plan/grammar.py tests/test_plan_grammar.py tests/fixtures/plan/obsidian_tasks.md tests/fixtures/plan/user_order.md tests/fixtures/plan/odd_lines.md tests/fixtures/plan/canonical.md && git commit -m "feat: the Plan grammar reads Obsidian Tasks lines leniently and writes them in a canonical order"`

### Task 14: The Plan on the server: store, CAS, routes, tools, prompt slice, per-item taint

Design §4.2–§4.4; Design meets code 4.

**Files:**
- Create: `roost/plan/models.py`, `store.py`, `service.py`, `prompt.py`, `tool_specs.py`, `tools.py`, `roost/gateway/routes/plan.py`, `tests/test_plan_store.py`, `tests/test_plan_api.py`, `tests/test_plan_tools.py` and `tests/test_plan_prompt.py`.
- Modify: `roost/talk/tool_catalog.py`, `roost/talk/domain_tools.py`, `roost/talk/instructions.py` (a `plan=` section), `roost/talk/turn.py` (`_prepare` loads `PlanService.items_for_prompt`; it taints nothing because only clean items are shown), `roost/talk/runner.py` (`_after_run` calls `PlanService.flush_run_note`), `roost/gateway/app.py`, `tests/test_every_bot_tools.py`, and `tests/test_routine_tools.py` (the exact `allowed_when_tainted` set).

**Shapes:**
- **The store:** `content` is sealed with `bot_plans:content`, and `item_taint` with `bot_plans:item_taint` (a JSON list). `save(user_id, bot_id, content, item_taint, base_revision)` is `UPDATE … WHERE user_id = ? AND bot_id = ? AND revision = ?`, raising `RevisionConflict(current)` on 0 rows.
- **The service:**
  - `put_text` parses, assigns ids, takes the canonical form and saves. Lines the user changed clear their ids from `item_taint` (compare by id: a changed rendered line means the user wrote it).
  - `patch_item` changes one item by id and clears its taint.
  - `bot_*` tools are a read-modify-write by id with up to 2 retries on a conflict, adding the id to `item_taint` when `ctx.tainted`. They run `archive_old` on every bot write.
- **The tools:**
  - `plan_read(from?, to?, status?, tag?)` returns the items quoted as data, with `ToolOutcome.tainted` true when any returned item is tainted.
  - `plan_add`, `plan_update` and `plan_complete` share a per-run counter, keyed by `RecordContext` run id, up to `PLAN_WRITES_PER_RUN` ("I've changed the Plan enough in this run.").
  - One `routine_note`-style line "Updated plan · {n} items" per run: the service counts per run id and the after-run pass posts it. For a non-routine run, `TurnRunner._after_run` calls `PlanService.flush_run_note`.
  - A bot may change only its own Plan: the tools take no `bot_id`.
- **The prompt:** "Your Plan for today and tomorrow" lists up to `PLAN_PROMPT_ITEMS` clean items, escaped, plus "{n} more from outside content; use plan_read".
- **The routes** follow the HTTP table, publishing `plan_changed`. A 409 body is `{"detail": "…", "current": PlanOut}`, as notes do.

**Tests:**
- `test_the_plan_is_sealed_and_made_on_first_open`;
- `test_a_stale_revision_is_409_with_the_current_copy`;
- `test_a_bot_write_never_clobbers_the_users_other_lines`;
- `test_bot_writes_from_a_tainted_run_mark_only_those_items`;
- `test_a_user_edit_clears_that_items_taint`;
- `test_plan_read_taints_the_run_only_for_a_tainted_item`;
- `test_plan_tools_work_in_a_tainted_run_up_to_the_cap`;
- `test_the_prompt_shows_today_and_tomorrow_clean_items_only`;
- `test_one_updated_plan_line_per_run`;
- `test_patch_an_item_by_id`;
- `test_another_users_plan_and_items_are_404`;
- `test_every_write_needs_the_origin`;
- `test_only_routine_and_plan_tools_skip_the_tainted_rule` (now exact).

- [ ] Red → green, plus `tests/test_gate.py tests/test_instructions.py`.
- [ ] **Commit:** `git add roost/plan/models.py roost/plan/store.py roost/plan/service.py roost/plan/prompt.py roost/plan/tool_specs.py roost/plan/tools.py roost/gateway/routes/plan.py roost/talk/tool_catalog.py roost/talk/domain_tools.py roost/talk/instructions.py roost/talk/turn.py roost/talk/runner.py roost/gateway/app.py tests/test_plan_store.py tests/test_plan_api.py tests/test_plan_tools.py tests/test_plan_prompt.py tests/test_every_bot_tools.py tests/test_routine_tools.py && git commit -m "feat: every bot keeps a sealed Plan with revision checks, plan tools, a prompt slice and per-item taint"`

### Task 15: Web: Routines in Info, and the full-limit switch

Decision D1; design §3.6; Design meets code 13, 15.

**Files:**
- Create:
  - `web/src/api/routines.ts` and `web/src/api/usage.ts`;
  - `web/src/components/routines/`: `RoutinesCard.tsx`, `RoutineRow.tsx`, `RoutineEditor.tsx`, `ScheduleFields.tsx` (Times: weekday chips plus a time list; Custom: cron plus the live preview of the next 5 times through `POST /api/routines/preview`, debounced), `RoutineHistory.tsx` (a Sheet) and `constants.ts`;
  - `web/src/components/profile/FullLimitSwitch.tsx` and `web/src/styles/routines.css`;
  - tests: `web/tests/RoutinesCard.test.tsx`, `web/tests/RoutineEditor.test.tsx` and `web/tests/FullLimitSwitch.test.tsx`.
- Modify: `web/src/components/profile/InfoTab.tsx` (drop "Routines come in a later update."; add `RoutinesCard` and `FullLimitSwitch`), `web/src/api/types.ts` (`BotOut.full_limit_until`), `web/src/styles/styles.css` (import `routines.css` once), and `web/src/store/live.ts` (`routines_changed` reloads the card).

**Shapes:**
- **A row** shows the name, the words, "Next: Wed 21 Oct 10:07" (Madrid), the `ui/Switch`, and a `ui/Menu` with Run now, Edit, History and Delete (Delete is hidden for the built-in and asks first).
- **The built-in** shows "End-of-day summary" with its time only.
- **A tainted routine** shows the "from web content" mark.
- **History** lists the runs with their state words: Done · Missed · Skipped · Held · Waited for you · Didn't finish. A run with a Report links to it.
- **The full-limit switch:** "Use the full limit until it resets". When on, "On until {reset, Madrid}"; when `GET /api/usage` is unreadable, it is disabled with the refusal text.

**Tests:**
- `shows routines with words, next run and switch`;
- `switching off calls PATCH and shows the new state`;
- `run now and delete ask first and call the routes`;
- `the editor switches Times and Custom and shows the live preview`;
- `a bad schedule shows the server's sentence`;
- `the built-in hides delete and instructions`;
- `full limit is disabled without a reading`;
- `full limit shows until when on`.

- [ ] Red → green: `cd web && npx vitest run tests/RoutinesCard.test.tsx tests/RoutineEditor.test.tsx tests/FullLimitSwitch.test.tsx`, then `npm test`.
- [ ] **Commit:** `git add web/src/api/routines.ts web/src/api/usage.ts web/src/components/routines/RoutinesCard.tsx web/src/components/routines/RoutineRow.tsx web/src/components/routines/RoutineEditor.tsx web/src/components/routines/ScheduleFields.tsx web/src/components/routines/RoutineHistory.tsx web/src/components/routines/constants.ts web/src/components/profile/FullLimitSwitch.tsx web/src/components/profile/InfoTab.tsx web/src/api/types.ts web/src/styles/routines.css web/src/styles/styles.css web/src/store/live.ts web/tests/RoutinesCard.test.tsx web/tests/RoutineEditor.test.tsx web/tests/FullLimitSwitch.test.tsx && git commit -m "feat: routines in the Info tab with switches, an editor with a live preview, history, and the full-limit switch"`

### Task 16: Web: Reports, quiet lines, routine Ask cards, the question book, My turn, the run log

Design §3.5; Design meets code 3, 5, 12.

**Files:**
- Create:
  - `web/src/api/questions.ts` and `web/src/api/proposals.ts`;
  - `web/src/components/chat/ReportMessage.tsx` (headline, Markdown body through `Markdown.tsx`, "Open run log", the "from web content" mark), `RoutineNoteLine.tsx` (also draws `question_note`) and `RoutineAskCard.tsx` (name, words, next 3, instructions or diff, the marks, Approve / Decline; reuses the approval-modes Ask card component if one exists);
  - `web/src/components/questions/QuestionBook.tsx` (in Info under Routines: open questions, each with its default, Answer (a text field) and Dismiss);
  - `web/src/pages/RoutineLog.tsx` (read-only, the existing thread-messages API and `MessageList`);
  - tests: `web/tests/ReportMessage.test.tsx`, `web/tests/RoutineAskCard.test.tsx`, `web/tests/QuestionBook.test.tsx` and `web/tests/RoutineLog.test.tsx`.
- Modify: `web/src/components/MessageRow.tsx` (dispatch the new kinds), `web/src/pages/Home.tsx` (My turn adds open questions and routine proposals, loaded on their own like the Stuck cards, with Retry), `web/src/App.tsx` (route `/bots/:botId/routines/:routineId/log`), `web/src/components/profile/InfoTab.tsx` (`QuestionBook`), `web/src/store/live.ts` (`questions_changed`, `proposals_changed`), and `web/tests/Home.test.tsx`.

**Tests:**
- `a report shows its headline, body and run-log link`;
- `a tainted report wears the mark`;
- `quiet lines draw as activity`;
- `approve and decline call the routes and the card settles`;
- `a change card shows before and after`;
- `answering posts and the question leaves the book`;
- `my turn lists questions and proposals and survives a failed load`;
- `the run log is read-only`.

- [ ] Red → green, then `npm test`.
- [ ] **Commit:** `git add web/src/api/questions.ts web/src/api/proposals.ts web/src/components/chat/ReportMessage.tsx web/src/components/chat/RoutineNoteLine.tsx web/src/components/chat/RoutineAskCard.tsx web/src/components/questions/QuestionBook.tsx web/src/pages/RoutineLog.tsx web/src/components/MessageRow.tsx web/src/pages/Home.tsx web/src/App.tsx web/src/components/profile/InfoTab.tsx web/src/store/live.ts web/tests/ReportMessage.test.tsx web/tests/RoutineAskCard.test.tsx web/tests/QuestionBook.test.tsx web/tests/RoutineLog.test.tsx web/tests/Home.test.tsx && git commit -m "feat: Reports and routine Ask cards in chat, the question book, and both in My turn"`

### Task 17: Web: the Plan tab (Calendar and Kanban as a lazy chunk, Edit as text)

Decision D1; design §4.5.

**Files:**
- Create:
  - `web/src/api/plan.ts`;
  - `web/src/components/plan/`:
    - `PlanTab.tsx` (the small entry: `lazy(() => import("./PlanView"))` with a quiet fallback);
    - `PlanView.tsx` (the chunk: a `ui/Segmented` with Calendar · Kanban · Text, and the "N lines couldn't be read" note);
    - `PlanCalendar.tsx` (reuses `board/calendar/CalendarGrid`, `monthCells` and `CalendarToolbar`: a dot per day with items and that day's list below, sorted by `⏰`, with "No date" for undated items);
    - `PlanKanban.tsx` (columns Planned / On it / Done, with Dropped behind a toggle; reuses `board/kanban/useKanbanDrag`; a card's menu has Move to… for keyboards and touch);
    - `PlanText.tsx` (a textarea; Save sends `PUT` with `base_revision`; a 409 shows the newer copy with "Use theirs" or "Keep mine", as notes do);
    - `planColumns.ts` and `constants.ts`;
  - `web/src/styles/plan.css`, imported by `PlanView.tsx` only, so it stays in the chunk;
  - tests: `web/tests/PlanView.test.tsx`, `web/tests/PlanKanban.test.tsx` and `web/tests/PlanCalendar.test.tsx`.
- Modify: `web/src/components/panel/panelTabs.ts` (`"plan"` between `info` and `documents`, label "Plan"), `web/src/components/panel/BotPanel.tsx` (`plan: ({ bot }) => <PlanTab bot={bot} />`), `web/tests/BotPanel.test.tsx` (the five tabs in order), `web/tests/bundleGuard.test.ts` (PlanView is not in the entry), and `web/src/store/live.ts` (`plan_changed` reloads it when the revision is newer).

**Shapes:**
- Drag and Move to… call `PATCH /api/bots/{id}/plan/items/{item_id}` with `base_revision` and `status`.
- A 409 reloads the Plan and shows a Toast: "The Plan changed; try again."

**Tests:**
- `the tabs are Info, Plan, Documents, Computer, Links`;
- `the plan loads as its own chunk`;
- `the calendar marks days with items and lists the day sorted by time`;
- `undated items sit in No date`;
- `drag moves a card and sends the item's id and revision`;
- `move to works from the keyboard`;
- `dropped hides behind the toggle`;
- `edit as text saves and a conflict shows the newer copy`;
- `unreadable lines are counted`.

- [ ] Red → green, then `npm test && npm run build && npm run size`.
- [ ] **Commit:** `git add web/src/api/plan.ts web/src/components/plan/PlanTab.tsx web/src/components/plan/PlanView.tsx web/src/components/plan/PlanCalendar.tsx web/src/components/plan/PlanKanban.tsx web/src/components/plan/PlanText.tsx web/src/components/plan/planColumns.ts web/src/components/plan/constants.ts web/src/styles/plan.css web/src/components/panel/panelTabs.ts web/src/components/panel/BotPanel.tsx web/src/store/live.ts web/tests/PlanView.test.tsx web/tests/PlanKanban.test.tsx web/tests/PlanCalendar.test.tsx web/tests/BotPanel.test.tsx web/tests/bundleGuard.test.ts && git commit -m "feat: the Plan tab with a Calendar, a Kanban and Edit as text, loaded as its own chunk"`

### Task 18: E2E, docs and the full checks

**Files:**
- Create: `web/e2e/routines.spec.ts`.
- Modify: `web/e2e/fixtures/team-script.json` (the scripted reply for a routine run and a `plan_add` call), `web/e2e/profile.spec.ts` (five tabs), `CLAUDE.md`, and `tests/test_docs.py`.

**E2E** (on the scripted gateway; the disk guard runs first):
1. Make a routine in Info (Times, today's next minute), then Run now. A Report appears in the chat, "Open run log" shows the run, and History shows Done.
2. The scripted bot proposes a routine. The card shows in the chat and in My turn. Approve, and the routine is listed.
3. The scripted bot notes a question. It shows in My turn. Answer it, and your message appears in the chat.
4. The Plan tab: the scripted `plan_add` item shows in the Kanban. Drag it to Done, and the Calendar shows it on its day. Edit as text, then Save.
5. A task with a reminder one minute ago gets a "Reminder:" Report after one scheduler tick. The scripted gateway sets `ROUTINE_TICK_SECONDS` through a scripted-mode override, `config.scheduler_tick_seconds`, used only when `model_mode == "scripted"`.

**Docs:**
- In CLAUDE.md's Documentation Map, add this plan and the design.
- Add a Routines and Plan paragraph to Architecture: the scheduler only queues, the run-log thread, Reports, proposals, the question book, the full limit and reserve, reminders, the day summary, budget alerts, and the Plan's grammar, CAS and per-item taint.
- Change the vocabulary row to "Info · Plan · Documents · Computer · Links", and add rows for **Report**, **question book** and **use the full limit**.
- `tests/test_docs.py` checks these.

- [ ] Full checks:
  - `… uv run pytest --cov=roost --cov-fail-under=80 -q`;
  - `cd web && npm test && npm run build && npm run size`;
  - `ROOST_DESKS_DIR=$(mktemp -d) make e2e`.
- [ ] **Commit:** `git add web/e2e/routines.spec.ts web/e2e/fixtures/team-script.json web/e2e/profile.spec.ts CLAUDE.md tests/test_docs.py <the scripted-tick override files, by name> && git commit -m "test: routines, proposals, questions, reminders and the Plan end to end; docs: Routines and Plan in CLAUDE.md"`

## Choices this plan made (open for the user)

1. **No second Ask-card system.** Routine runs use the approval-modes Ask cards (v23) and add only their deadline. Routine proposals are a small card of their own, applied by the server on Approve. If approval modes later offers a card registry, the proposal card can move into it.
2. **The deadline (D2)** for an Ask card from a routine run is `min(next slot, 24 h)`, from the design's D2 (b) wording.
3. **Answering a question** posts your answer as your own message and starts a normal run, so the bot adapts at once. Routine runs also see their routine's last answers.
4. **The end-of-day summary** is a built-in routine on the main bot, **off** by default at 21:00. Switching it on is one tap in Info.
5. **Budget alerts are checked every 5 minutes**, not on each expense write. A total budget that is still over is said once a month, matching "once per month".
6. **The full limit with no usage reading stays off**, with the switch disabled and saying why, because the 10% reserve can't be checked without a reading. It lasts until the reading's reset, or Madrid midnight when the reading gives no reset time.
7. **Reminders** go to the task's bot when one is assigned, else to the main bot. Ones that passed while Roost was off arrive as one Report.
8. **Vocabulary clash:** approval modes (Mac folders design D1) names a **"Plan mode"** with a **"Plan card"**, and this plan adds the bot's **Plan** tab. Both are kept as approved, but one may want a new name, for example "Preview mode". The user should decide this before approval modes' web lands.
