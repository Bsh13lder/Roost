# Roost Look & Feel Redesign, P3 Tasks Done Properly, Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tasks a person can really work with: steps (subtasks) the user and every bot can add, rename, tick, reorder and delete; comments on a task or a step; one drawer per task holding its details, schedule, steps, money, comments and where it came from; a quick-add line that turns `Call plumber tomorrow 9am #Renovation €200 !high` into chips before Enter; and structured task rows.

**Architecture:**
- **Steps** stay the encrypted JSON list on `tasks.steps` (M1) with stable ids. `roost/tasks/steps.py` gains one pure function per change (`with_step_added`, `with_step_renamed`, `with_step_done`, `with_step_moved`, `without_step`). `TaskStore.edit_steps` applies a change to the task's current steps in a compare-and-set on `updated_at`, retrying when someone else changed the task in between, so a bot's tick and the user's rename never undo each other. `StepService` (`roost/tasks/step_service.py`) is the one door for the tools and the routes; deleting a step clears `step_id` on its expenses and its comments, so they stay on the task.
- **Comments** are a new table, `task_comments` (schema **v14**), each body `enc:v2` under `task_comments:body`, with the author ("user" or a bot's id) and a taint bit. `CommentStore` and `CommentService` (`roost/tasks/comment_store.py`, `comment_service.py`) read and write them; only the user's own comments can be edited or deleted.
- **Tools:** `add_step` (write_create), `update_step`, `delete_step`, `move_step` (write_change), `add_comment` (write_create) and `list_comments` (read), in `roost/tasks/step_specs.py`, `step_tools.py` and `comment_tools.py`. They name a task and a step the way the money tools already do (`roost/money/expense_links.py`: exact or ask).
- **Routes:** `/api/tasks/{id}/steps…` (`roost/gateway/routes/task_steps.py`), `/api/tasks/{id}/comments` and `/api/comments/{id}` (`comments.py`), and `GET /api/tasks/{id}` (the drawer's task with its money) plus `POST /api/tasks/parse` (the quick-add line) in `task_detail.py`. `PATCH /api/tasks/{id}` learns the reminder and the repeat; `POST /api/money/expenses` learns a task and a step.
- **Quick typing:** the server reads the whole line (`roost/tasks/quick_line.py`): the `nl_time` rules for the date, `#project` (exact or ask), `€/$/£ amount` (the budget slice, which needs a project and its currency) and `!high` / `!low` / `!urgent` / `!medium`. The web asks it as you type and draws the chips from its answer; Enter reads the line once more and adds exactly what the server read.
- **The web:** task rows are structured (checkbox, title, chips for due, project and progress, actions on hover); a click opens the task drawer, a P1 `Sheet` in its own lazy chunk (`web/src/components/tasks/TaskDrawer.tsx`) with Details, Steps, Money, Comments and Activity. The Sheet first learns to give focus back to a menu's button when a menu item opened it, and to hold Selects, menus and date pickers without a focus fight (they draw inside its panel).

**Tech Stack:** The P1 and P2 stack, with no new dependency:
- Python 3.12 (uv), FastAPI, pydantic 2, aiosqlite; pytest.
- Vite, React 19 and TypeScript, tested with vitest + Testing Library and Playwright.
- The `@radix-ui/*` kit from P1 (`web/src/ui/`), `react-day-picker` behind the lazy calendar.

**Spec:** `docs/plans/2026-10-15-roost-look-and-feel-design.md`, section "P3 — Tasks done properly", and decisions V1 (Boxbot), V2 (P4 owns record cards), V3 (build order) and V4 (dark only); `docs/plans/2026-10-14-roost-projects-hub-design.md` H11 (task money, steps, budget slices). Where the design and the code disagree, the "Design meets code" list below says what this plan does.

> **Status (2026-10-20): ready to execute.** Written against `night-1` at `405492d`. The code was written and run on a throwaway worktree of that commit, and the plan was then generated from it by a script that replayed every Create, Find / Replace, Append and Delete block in order on a copy of `405492d` (each Find matched exactly once) and checked that the result equals the worktree, file for file (96 files). On that worktree: the v13 freeze and the v14 migration, every task's own pytest files, the full pytest suite (1,869 passed), the full vitest suite (637 tests in 98 files), `npm run build` and `npm run size` (entry about 204 KB of 257 KB gzip, the drawer its own `TaskDrawer-*.js` chunk) all passed; `playwright test --list` parses both specs. The red runs and the per-task commits were not replayed one by one, and the Playwright specs were not run (Task 15 runs them).

## Global Constraints

- **Path guard, first in every task:**
  - `git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel` must print `/Users/blckit/Desktop/Code_Projects/roost`.
  - `git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current` must print `night-1`.
  - If either check fails, stop.
- **Where you may edit:**
  - Edit only under `/Users/blckit/Desktop/Code_Projects/roost`, and never its `roost-ui/` folder (it is the user's).
  - `/Users/blckit/Desktop/Code_Projects/lazyclaw` is never touched: not `lazyclaw/data`, not its containers, not its `make` targets.
- **The live Roost is never touched:**
  - Never stop, restart, rebuild or call the Docker container `roost-gateway-1` (the live gateway on `127.0.0.1:18800`), the keeper (`127.0.0.1:18801`) or `~/Roost/data`.
  - Any script or probe that imports `roost` runs with `ROOST_DATA_DIR` and `ROOST_DESKS_DIR` set to a fresh `mktemp -d`, and never opens `~/Roost/data`. `uv run pytest` is safe on its own (`tests/conftest.py` repoints both before collection); the commands below set them anyway.
  - `make e2e` starts its own throwaway gateway with `ROOST_DATA_DIR=$(mktemp -d)`; run it as `ROOST_DESKS_DIR=$(mktemp -d) make e2e` so the desks are throwaway too. It picks port 5173 by itself while the live gateway holds 18800. Never point a test at 18800.
- **Clean room (spec §10.3):**
  - Roost's look is its own: no other product's art, mascots, icons or copy.
  - Never open, fetch or search for the open-dot repos, `~/Roost-review/` or `~/.claude/projects/**`. Do not use browser MCP tools.
- **Licences:** only MIT, Apache-2.0, BSD, ISC or MPL-2.0 dependencies. P3 adds none; `web/tests/licenseGate.test.ts` stays green.
- **Disk guard:** before `make e2e`, run `df -g /System/Volumes/Data | awk 'NR==2{print $4}'`. If it shows fewer than 8 GB free, stop and report.
- **Schema:** v14 is additive (one new table and its index), idempotent, and frozen against `tests/fixtures/schema_v13.sql`, which Task 3 writes **before** `roost/db/migrations.py` changes. Live control's plan named `site_logins` v14; it becomes v15 there.
- **Data rules (CLAUDE.md):**
  - Every user-content column is `enc:v2` with the per-user DEK and `user_aad(user_id, "<table>:<column>")`: a comment's body is `task_comments:body`; a step's title stays inside the encrypted `tasks:steps` JSON.
  - Every query on user data names `user_id` in its `WHERE`. Another user's task, step or comment id gives **404**, never the object.
  - Bot-written records carry the taint bit: a comment from a run that read outside content is stored `tainted`; a step a tainted run adds marks its task "from web content".
- **Tests:**
  - Tests first: red, then green.
  - At least 80% line coverage on new code (`uv run pytest --cov=roost --cov-fail-under=80`).
  - Tests never call a real LLM and never launch a real browser outside Playwright (`tests/conftest.py` forces scripted and fake). Web tests run in jsdom (`web/tests/setup.ts`).
  - P1's picker tests (`DatePicker`, `DateTimePicker`, `ExpenseAddForm`) load the lazy calendar and can pass vitest's 5 s limit while the Mac is very busy (load average above 15). If only those time out in a full `npm test`, run them alone; they pass. Any other failure is real.
- **Code rules:**
  - Files at most 800 lines (typically 200–400); functions under 50 lines.
  - No mutation of shared state: frozen dataclasses and tuples on the server, new objects in React state.
  - Pydantic validation at every HTTP and tool boundary (`extra="forbid"` on bodies, `extra="ignore"` on tool arguments).
  - Explicit error handling with user-friendly messages: a refused change says why in a plain sentence (422), a lost race says "Try again" (409), and the web shows the server's sentence through `ErrorNotice`.
  - No magic values: the server's numbers in `roost/constants.py`, the web's in `web/src/components/tasks/constants.ts`.
- **Tokens:** no colour and no font size is written anywhere in `web/src` but `web/src/styles/tokens.css` and the two colour-data files; `web/tests/tokens.test.ts` enforces it. Every new rule uses the tokens (`--space-*`, `--radius-*`, `--fs-*`, `--color-*`).
- **Bundle:** the main entry stays within `web/bundle-budget.json` (about 203 KB of 257 KB gzip at `405492d`). The drawer and everything only it uses (steps, money, comments, activity) are one lazy chunk; `web/tests/bundleGuard.test.ts` refuses a static import of it.
- **Dark only (V4):** no light theme in this round.
- **Vocabulary** (the CLAUDE.md table and `tests/test_vocabulary.py`): Board, Profile, "main bot", the statuses verbatim; a bot is a bot. Never "Category", "By category" or "categories" in `web/src` (a task's `category` is shown as its **List**).
- **Git:**
  - Commit after each task's green tests. Stage files **by name**, never `git add -A`, `-a` or `.`.
  - Messages are conventional, with **no Co-Authored-By or any AI attribution line** (CLAUDE.md overrides any default).
- **Commands:**
  - Prefix every command with `cd /Users/blckit/Desktop/Code_Projects/roost &&`.
  - `ROOST_DATA_DIR=$(mktemp -d) ROOST_DESKS_DIR=$(mktemp -d) uv run pytest tests/<file>.py -q` runs one file; the same with no path runs the suite.
  - `cd web && npx vitest run tests/<file>` runs one web test; `npm test` runs them all; `npm run build && npm run size` checks the types, the build and the entry chunk's budget.

## Design meets code

What the design says, what the code holds today, and what this plan does:

1. **"Schema: the next free version. Today that is v14; if live control's `site_logins` is built first, comments take v15".** Live control is not built; the latest migration is v13 (projects hub). Comments take **v14**; live control's plan renumbers `site_logins` to v15 when it runs.
2. **The `task_comments` columns** list no taint bit, but the design also says "bot comments carry the taint rules like any record". Every record stores its taint in a column, so the table gets `tainted INTEGER NOT NULL DEFAULT 0` beside the listed columns. `author` has no foreign key: a retired bot's comments stay, shown as "A retired bot".
3. **"Subtasks (steps)".** Steps already exist (M1): an encrypted JSON list on `tasks.steps` with ids, harvested from LazyClaw, written only by `add_task` and the completion cascade. P3 adds no schema: one pure function per change in `roost/tasks/steps.py`, written through a compare-and-set on `updated_at` (`TaskStore.edit_steps`), so two hands on one checklist never undo each other. A new step's id is `s-` and 12 hex digits; old ids are kept as they are.
4. **"Deleting a step that has expenses moves them to the task (`step_id` cleared)".** H11 already counts an expense whose step is gone at task level when reading. P3 also clears the `step_id` on those expenses (and on the step's comments), so no row is left naming a missing step, and says how many moved.
5. **"Budget slice, spent and left, per task and per step".** H11 gives a slice to a task only; a step has no budget of its own. The drawer shows the task's slice, spent and left, and **what is spent on each step** (`numbers.step_spent`, server-side). Step budgets are not added.
6. **`add_step` is write_create.** A tainted run may add a step (up to the run's create cap), but a step is a line inside the task's encrypted JSON with no taint bit of its own. So a step added by a tainted run marks **its task** "from web content" (Keep clears it, as for any record). `update_step`, `delete_step` and `move_step` are write_change: the gate refuses them in a tainted run.
7. **How a tool names a task and a step.** `update_task` looks only at open tasks; the step and comment tools use the money tools' rule instead (`roost/money/expense_links.py` `find_task` / `find_step`): any status, id or exact title or a unique part, never a near miss. A comment can be added to a finished task.
8. **"Reorder".** The tools and the route move a step to a place (`move_step` with `position`, 1 is first for a bot; the route's body is 0-based). The drawer has Move up and Move down on each step, which work from the keyboard; drag and drop is not in this round.
9. **"Own comments only".** Editing or deleting a bot's comment is **403** ("Only your own comments can be changed."); another user's comment is **404**, like every other id.
10. **"Due (DateTimePicker), reminder, repeat".** `PATCH /api/tasks/{id}` could not set a reminder or a repeat. It gains `reminder_at` (words or ISO on Madrid time, which must name a time; it resets the advance reminder to 30 minutes before; null clears both) and `recurring` (a cron, checked by `validate_cron`; null: no repeat). The drawer's Repeat offers Never, Every day, Every weekday, Every week and Every month, built from the due's day and time (09:00 when the due has none); a cron a bot set that matches none of them shows as "Custom" and is kept.
11. **"Parsing is client-side for the preview, and the server stays the authority".** One parser is enough: the server's. The web sends the line to `POST /api/tasks/parse` (250 ms after the last key) and draws the chips from the answer; Enter reads the line once more and adds exactly that reading. There is no second parser in the web to drift from the server's.
12. **The quick line's words.** `#project` needs an existing project, exact or ask (a unique part of a name is fine, a near miss is a question, a new name is never made, General is refused); `!high` and `!low`, plus `!urgent` and `!medium`; `€`, `$` and `£` before or after the amount, which must match the project's currency (the slice needs a project). The `nl_time` rules read numbers boldly ("Book 2 tickets" reads as the 2nd of the month), so every chip has a remove button: a removed chip's words stay in the title (the request's `skip`).
13. **The inline edit form** (`TaskEditForm`, P1) is replaced by the drawer: a row's title opens it, and the row's "Edit" button goes. `web/e2e/pickers.spec.ts` checks the due in the drawer instead.
14. **"The activity: made by a bot, from web content".** Roost keeps no change history for a task. The drawer's Activity shows who made it (a bot, by name, or you), when it was made, last changed and finished, and the "from web content" mark with Keep. A history of changes is not in this round.
15. **The Sheet focus bug (P1 review).** Opening a Sheet from a menu item left focus on the page body when it closed: the item is gone by the time the Sheet remembers its opener. `MenuItem` now puts focus on the menu's own button before it acts, so the Sheet remembers the button and gives focus back to it; an item that opens a dialog which focuses its own field keeps that focus, as before.
16. **A Select inside a Sheet.** P1 never put a Select or a date picker inside a Sheet, and it freezes the page: each Radix package carries its own copy of `@radix-ui/react-focus-scope`, so the Sheet's focus trap and the Select's pull focus from each other until the stack overflows (`RangeError`). The Sheet now hands its panel to the kit's overlays (`PortalContainer`), which draw inside it, so focus never leaves the Sheet. No dependency changes (Task 2).
17. **"Sept".** ICU spells September "Sept" in `en-GB`; P1's pickers already use a fixed month table (`web/src/ui/date/dates.ts`). The Board's day labels (`money.ts` `dayLabel`, `projects.ts` `dateLabel` and `momentDay`) move onto that table through one new helper, `dayText`.

## Review Focus

These are the input classes the design implies but the main tests do not exercise. The test for each one is added to the task named.

1. **Two hands on one checklist:** a bot ticks one step while the user renames another (or the same task changes in another tab).
   - Expected: both changes land; neither is undone; a change that keeps losing the race says "Try again" (409), never a 500 and never a silent loss.
   - Tests: Task 4, `test_two_step_changes_at_once_both_land` and `test_a_change_that_keeps_losing_the_race_says_try_again` (`tests/test_task_steps.py`).
2. **Deleting a step that has money and comments.**
   - Expected: the expenses and the comments stay on the task with `step_id` cleared; the task's spent is the same before and after; the reply says how many moved.
   - Tests: Task 4, `test_deleting_a_step_keeps_its_money_and_comments_on_the_task` (`tests/test_task_steps.py`), and Task 5, `test_deleting_a_step_says_its_money_stays_on_the_task` (`tests/test_step_comment_tools.py`).
3. **A quick line the reader could get wrong:** a typo in the project (`#Renovaton`), a money sign in another currency, an amount with no project, `#General`, a number read as a date ("Book 2 tickets").
   - Expected: never a silent wrong project or a slice in the wrong currency: the line shows the question or the problem and nothing is added until it is fixed; a removed chip's words go back into the title.
   - Tests: Task 8, `test_a_near_project_name_asks_and_a_foreign_sign_or_no_project_explains` and `test_a_project_page_passes_its_project_and_a_dismissed_date_stays_in_the_title` (`tests/test_quick_line.py`); Task 14, `it("a removed chip's words go back into the title, and the line is read again without it")` (`web/tests/QuickAdd.test.tsx`).
4. **A bot's comment written after reading a hostile page:** raw HTML, a script tag, a very long line.
   - Expected: the drawer shows it as plain text (no element made from it), marks it "from web content", and offers no Edit or Delete on it; the bot's own listing escapes it.
   - Tests: Task 5, `test_a_bot_comments_on_a_task_and_a_step_and_lists_them` (`tests/test_step_comment_tools.py`); Task 13, `it("shows a bot's web-made comment as plain text with its mark, and no Edit or Delete")` (`web/tests/CommentThread.test.tsx`).
5. **Another user's ids at every new door:** a task id, a step id, a comment id in a path; a task or project id in a body.
   - Expected: 404 for a path id (or 422 "No such task." for a body id), and never the other user's titles or text in the answer.
   - Tests: Task 6, `test_another_users_task_steps_and_comments_are_404` (`tests/test_steps_comments_api.py`); Task 7, `test_another_users_task_is_404_and_their_task_cannot_take_an_expense` (`tests/test_task_detail_api.py`); Task 8, `test_an_empty_line_or_another_users_project_is_not_ready` (`tests/test_quick_line.py`).

---

## Shared Contract (every task uses these exact names)

### Schema v14 (Task 3)

```sql
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
);
CREATE INDEX IF NOT EXISTS idx_task_comments_task ON task_comments(user_id, task_id, created_at);
```

`Migration(14, "task comments", (_TASK_COMMENTS, <the index>))`. `tests/fixtures/schema_v13.sql` is frozen first.

### Constants (`roost/constants.py`, Tasks section, after `TASK_LIST_LIMIT = 50`)

| Name | Value | Task |
|---|---|---|
| `MAX_STEP_TITLE_LENGTH` | `200` | 3 |
| `STEP_WRITE_ATTEMPTS` | `3` | 3 |
| `MAX_COMMENT_LENGTH` | `4000` | 3 |
| `COMMENT_LIST_LIMIT` | `200` | 3 |
| `COMMENT_TOOL_LIMIT` | `20` | 3 |
| `QUICK_LINE_MAX_LENGTH` | `300` | 8 |
| `QUICK_LINE_CURRENCIES` | `(("€", "EUR"), ("$", "USD"), ("£", "GBP"))` | 8 |

### Server names

| Name | Where | What |
|---|---|---|
| `TOO_EARLY_TEXT`, `_instant` | `roost/tasks/reminders.py` (Task 1) | an advance reminder before year 1 is a `ValueError`, not an `OverflowError` |
| `STEP_NOT_FOUND_TEXT = "That task has no such step."` | `roost/tasks/models.py` (Task 3) | shared by steps, comments and expenses |
| `TaskChange` gains `"commented"`; `publish_task_change(events, user_id, change, task_id)` | `roost/tasks/service.py` (Task 3) | the one `tasks_changed` frame |
| `TaskComment(id, user_id, task_id, step_id, author, body, tainted, created_at, edited_at)` + `.by_user`; `COMMENT_BY_USER = "user"`; `comment_body(text) -> str`; `comment_out(comment) -> dict`; `EMPTY_COMMENT_TEXT`, `LONG_COMMENT_TEXT` | `roost/tasks/comments.py` (Task 3) | |
| `CommentStore(config)`: `add(user_id, task_id, *, step_id, author, body, tainted) -> TaskComment \| None`, `list(user_id, task_id, *, limit)`, `get`, `edit(user_id, comment_id, body)`, `delete(user_id, comment_id) -> bool`, `unlink_step(user_id, task_id, step_id) -> int` | `roost/tasks/comment_store.py` (Task 3) | |
| `CommentService(comments, tasks: TaskStore, events)`: `list(user_id, task_id, *, limit=COMMENT_LIST_LIMIT) -> tuple \| None`, `add(user_id, task_id, body, *, step_id=None, author="user", tainted=False) -> TaskComment \| None`, `edit`, `delete`; `CommentNotYours(PermissionError)`, `NOT_YOURS_TEXT` | `roost/tasks/comment_service.py` (Task 3) | |
| `StepNotFound(LookupError)`, `step_title`, `with_step_added`, `with_step_renamed`, `with_step_done`, `with_step_moved`, `without_step`; `STEP_TITLE_TEXT`, `LONG_STEP_TEXT`, `TOO_MANY_STEPS_TEXT` | `roost/tasks/steps.py` (Task 4) | pure, ids kept |
| `TaskStore.edit_steps(user_id, task_id, edit, *, taint=False) -> Task \| None`; `StepsBusy(RuntimeError)`, `STEPS_BUSY_TEXT`; `_write(..., guard_params=())` | `roost/tasks/store.py` (Task 4) | compare-and-set on `updated_at` |
| `ExpenseStore.unlink_step(user_id, task_id, step_id) -> tuple[str, ...]` | `roost/money/expense_store.py` (Task 4) | the moved expense ids |
| `StepService(tasks: TaskStore, expenses: ExpenseStore, comments: CommentStore, events)`: `add(user_id, task_id, title, *, tainted=False)`, `rename`, `set_done(…, done)`, `move(…, position)` (0-based), `delete(…) -> StepRemoval \| None`; `StepRemoval(task, moved_expenses, moved_comments)` | `roost/tasks/step_service.py` (Task 4) | |
| `STEP_TOOL_DEFS`, `COMMENT_TOOL_DEFS` and the six specs | `roost/tasks/step_specs.py` (Task 5) | |
| `StepTools(tasks: TaskService, steps: StepService)`, `steps_text(task)`, `GONE_TEXT`, `NOTHING_TO_CHANGE_TEXT`; activities "adding a step", "changing a step", "deleting a step", "moving a step" | `roost/tasks/step_tools.py` (Task 5) | |
| `CommentTools(tasks: TaskService, comments: CommentService)`; activities "adding a comment", "reading comments" | `roost/tasks/comment_tools.py` (Task 5) | |
| `app.state.steps`, `app.state.comments`; `steps_router`, `comments_router` | `roost/gateway/{app,routes/task_steps,routes/comments}.py` (Task 6) | |
| `numbers.step_spent(task, expenses, currency) -> Mapping[str, Decimal]`; `MoneyService.for_task(user_id, task_id)`; `TaskPatchIn.reminder_at`, `.recurring`; `ExpenseIn.task_id`, `.step_id`, `NO_SUCH_TASK_TEXT`; `detail_router` with `GET /api/tasks/{id}` | Task 7 | |
| `due_from_parsed(parsed, text, tz)`; `QuickLine`, `LineWords`, `read_words`, `read_date`, `read_quick_line(projects, user_id, text, *, project_id=None, skip=frozenset())`, `quick_line_out`; `SLICE_CURRENCY_TEXT`, `NO_PROJECT_HERE_TEXT`, `PROJECT_GONE_TEXT`; `POST /api/tasks/parse` | `roost/tasks/{due,quick_line}.py`, `routes/task_detail.py` (Task 8) | |

### HTTP (every mutation needs the Origin; every route a login)

| Route | Body | Answer | Errors |
|---|---|---|---|
| `GET /api/tasks/{id}` | | `TaskDetailOut`: `task_out` + `money` (`{planned, spent, left, currency, steps: {step_id: spent}}` or `null`) + `expenses` (`expense_row`s) | 404 |
| `POST /api/tasks/{id}/steps` | `{title}` | 201 `TaskOut` | 404, 409, 422 |
| `PATCH /api/tasks/{id}/steps/{step_id}` | `{title?, done?}` (at least one) | `TaskOut` | 404, 409, 422 |
| `POST /api/tasks/{id}/steps/{step_id}/move` | `{position}` (0 is first) | `TaskOut` | 404, 409, 422 |
| `DELETE /api/tasks/{id}/steps/{step_id}` | | `TaskOut` + `moved_expenses`, `moved_comments` | 404, 409 |
| `GET /api/tasks/{id}/comments` | | `CommentOut[]`, oldest first | 404 |
| `POST /api/tasks/{id}/comments` | `{body, step_id?}` | 201 `CommentOut` | 404, 422 |
| `PATCH /api/comments/{id}` | `{body}` | `CommentOut` | 403 (a bot's), 404, 422 |
| `DELETE /api/comments/{id}` | | 204 | 403, 404 |
| `POST /api/tasks/parse` | `{text, project_id?, skip?: ("date"\|"project"\|"budget"\|"priority")[]}` | `QuickLineOut` | 422 |
| `PATCH /api/tasks/{id}` | gains `reminder_at`, `recurring` | as before | 422 |
| `POST /api/money/expenses` | gains `task_id`, `step_id` | as before; no project named → the task's | 422 "No such task." / "That task has no such step." / "A step needs its task: name the task too." |

`CommentOut`: `{id, task_id, step_id, author, body, tainted, created_at, edited_at}`. `QuickLineOut`: `{title, due_date, priority, project: {id, name, currency, color} | null, project_words, project_question, budget, budget_words, budget_problem, ready}`.

### Web names

| Name | Where (task) | What |
|---|---|---|
| `dayText(day, { weekday?, year? })` | `web/src/ui/date/dates.ts` (1) | "Tue 13 Oct", "13 Oct 2026", "Tue 13 Oct 2026" with the fixed month names |
| `MenuItem` focuses its menu's button before `onSelect`; `PortalContainer`, `usePortalContainer()`; `Sheet` provides its panel, `Select` / `Popover` / `Menu` draw into it | `web/src/ui/{Menu,Sheet,Select,Popover,portalContainer}.ts(x)` (2) | |
| `TaskDetailOut`, `TaskDetailMoneyOut`, `StepRemovalOut`, `CommentOut`, `QuickKind`, `QuickLineProjectOut`, `QuickLineOut`; `TasksChangedFrame.change` gains `"commented"` | `web/src/api/types.ts` (9) | |
| `getTask`, `addStep`, `updateStep`, `moveStep`, `deleteStep`, `parseQuickLine`; `TaskIn` gains `allocated_budget?`; `TaskPatchIn` gains `project_id`, `reminder_at`, `recurring`; `StepPatchIn`, `QuickLineIn` | `web/src/api/tasks.ts` (9) | |
| `listComments`, `addComment`, `editComment`, `deleteComment`; `CommentIn` | `web/src/api/comments.ts` (9) | |
| `ExpenseIn.task_id?`, `.step_id?` | `web/src/api/money.ts` (9) | |
| `MAX_STEP_TITLE = 200`, `MAX_COMMENT = 4000`, `MAX_QUICK_LINE = 300`, `QUICK_PARSE_DELAY_MS = 250`, `REPEAT_DEFAULT_TIME = "09:00"`, `TASK_PARAM = "task"`, `COMMENT_ROWS = 6` | `web/src/components/tasks/constants.ts` (9) | |
| `wallText(iso): string` | `web/src/ui/date/dates.ts` (10) | a UTC instant as Madrid's "YYYY-MM-DD HH:MM", the pickers' text |
| `MAX_LIST = 60` | `web/src/components/board/taskLimits.ts` (10) | a task's list |
| `StepProgress`, `stepProgress(steps): { done; total }`, `stepsText(steps): string \| null` ("2/5 steps") | `web/src/components/tasks/progress.ts` (10) | |
| `TaskRow` (rewritten): `{ task, currency?, money?, projectName?, completing, onComplete, onOpen, onFail, onKeep }` | `web/src/components/board/TaskRow.tsx` (10) | checkbox, title button, chips, hover actions |
| `useOpenTask(): { openId, open(taskId), close() }` | `web/src/components/tasks/useOpenTask.ts` (10) | the drawer's task in the URL (`?task=`) |
| `useProjects(enabled = true): readonly ProjectOut[]` | `web/src/components/tasks/useProjects.ts` (10) | live projects but General, reloaded on `money_changed` |
| `TaskDrawer` (default export) `{ taskId, onClose }` | `web/src/components/tasks/TaskDrawer.tsx` (10) | lazy chunk; loads `getTask` |
| `TaskDetailsForm` `{ task, onSaved }`, `changesOf(before, after)` | `web/src/components/tasks/TaskDetailsForm.tsx` (10) | replaces `TaskEditForm` |
| `RepeatKind`, `REPEAT_OPTIONS`, `CUSTOM_OPTION`, `repeatOf(cron)`, `cronFor(kind, due)` | `web/src/components/tasks/repeat.ts` (10) | |
| `StepList` `{ task, spent?, currency?, onChanged }`; `ChevronUpIcon` | `web/src/components/tasks/StepList.tsx`, `web/src/components/icons.tsx` (11) | |
| `TaskMoneyPanel` `{ task: TaskDetailOut, onChanged }`; `ExpenseAddForm` gains `task?: { id; steps }` | `web/src/components/tasks/TaskMoneyPanel.tsx`, `board/ExpenseAddForm.tsx` (12) | |
| `CommentThread` `{ task }`, `TaskActivity` `{ task, onChanged }`; `USER_AUTHOR`, `RETIRED_BOT`, `authorName(author, bots)`, `momentText(iso)` | `web/src/components/tasks/{CommentThread.tsx,TaskActivity.tsx,authors.ts}` (13) | |
| `useQuickLine(text, projectId, skip): { line, error }`, `QuickAdd` `{ projectId?, onAdded }`, `QuickChip`, `chipsOf(line)`, `taskInputOf(line)`, `blockerOf(line)` | `web/src/components/tasks/{useQuickLine.ts,QuickAdd.tsx,quickChips.ts}` (14) | replaces `TaskAddForm` |
| `web/src/styles/tasks.css` | (10–14) | rows, drawer, steps, comments, quick add; imported in `styles.css` after `board.css` |

### File structure

| File | Task | Responsibility |
|---|---|---|
| `roost/tasks/reminders.py`, `web/src/ui/date/dates.ts`, `web/src/components/board/money.ts`, `web/src/components/projects/projects.ts`, `tests/{test_task_time,test_tasks_api}.py`, `web/tests/{dates,money,projectsText}.test.ts` | 1 | leftovers: year 1 is a 422, no "Sept" |
| `web/src/ui/{Menu,Sheet,Select,Popover}.tsx`, `web/src/ui/portalContainer.ts`, `web/tests/sheetFocus.test.tsx` | 2 | Sheets with menus and pickers: focus back, overlays inside |
| `roost/db/migrations.py`, `tests/fixtures/schema_v13.sql`, `roost/constants.py`, `roost/tasks/{models,service,comments,comment_store,comment_service}.py`, `tests/{test_migrations_v13,test_task_comments}.py` | 3 | schema v14 and comments |
| `roost/tasks/{steps,store,step_service}.py`, `roost/money/expense_store.py`, `tests/test_task_steps.py` | 4 | steps, one change at a time |
| `roost/tasks/{step_specs,step_tools,comment_tools}.py`, `roost/talk/{tool_catalog,domain_tools}.py`, `web/src/lib/toolLines.ts`, `tests/test_step_comment_tools.py` | 5 | the bots' tools |
| `roost/gateway/routes/{task_steps,comments}.py`, `roost/gateway/app.py`, `tests/test_steps_comments_api.py` | 6 | steps and comments over HTTP |
| `roost/projects/numbers.py`, `roost/money/service.py`, `roost/tasks/due.py`, `roost/gateway/routes/{tasks,money,task_detail}.py`, `roost/gateway/app.py`, `tests/test_task_detail_api.py` | 7 | the drawer's data, the reminder and repeat, an expense for a task or a step |
| `roost/tasks/{due,quick_line}.py`, `roost/constants.py`, `roost/gateway/routes/task_detail.py`, `tests/test_quick_line.py` | 8 | the quick-add line |
| `web/src/api/{types,tasks,comments,money}.ts`, `web/src/components/tasks/constants.ts`, `web/tests/{tasksApi.test.ts,taskFixtures.ts}` | 9 | the web's data layer |
| `web/src/components/board/{TaskRow,TasksBoard}.tsx`, `web/src/components/board/{TaskEditForm.tsx (deleted),taskLimits.ts}`, `web/src/components/tasks/{progress,repeat,useOpenTask,useProjects}.ts`, `web/src/components/tasks/{TaskDrawer,TaskDetailsForm}.tsx`, `web/src/ui/date/dates.ts`, `web/src/styles/{tasks,board,projects}.css`, `web/src/styles.css`, `web/tests/{TasksBoard,TaskDrawer,repeat,dates,bundleGuard}.test.ts(x)` | 10 | structured rows and the drawer |
| `web/src/components/tasks/StepList.tsx`, `web/src/components/tasks/TaskDrawer.tsx`, `web/src/styles/tasks.css`, `web/tests/StepList.test.tsx` | 11 | steps in the drawer |
| `web/src/components/tasks/TaskMoneyPanel.tsx`, `web/src/components/board/ExpenseAddForm.tsx`, `web/src/components/tasks/TaskDrawer.tsx`, `web/src/styles/tasks.css`, `web/tests/{TaskMoneyPanel,ExpenseAddForm}.test.tsx` | 12 | money in the drawer |
| `web/src/components/tasks/{CommentThread,TaskActivity}.tsx`, `web/src/components/tasks/authors.ts`, `web/src/components/tasks/TaskDrawer.tsx`, `web/src/styles/tasks.css`, `web/tests/{CommentThread,TaskActivity}.test.tsx` | 13 | comments and activity |
| `web/src/components/tasks/{useQuickLine.ts,quickChips.ts,QuickAdd.tsx}`, `web/src/components/board/TaskAddForm.tsx` (deleted), `web/src/components/board/TasksBoard.tsx`, `web/src/styles/tasks.css`, `web/tests/{QuickAdd,quickChips}.test.ts(x)` | 14 | quick typing |
| `web/e2e/tasks.spec.ts`, `web/e2e/pickers.spec.ts`, `CLAUDE.md`, `tests/test_docs.py` | 15 | E2E, docs, the final checks |

---
### Task 1: Leftovers: a due in the calendar's first hour is a plain refusal, and no "Sept" on the Board

Two leftovers from earlier reviews, folded in first because later tasks touch the same files.
- **Year 1.** `POST /api/tasks {"due_date": "0001-01-01T00:00"}` answers 500: the default advance reminder (30 minutes before) is computed in `roost/tasks/reminders.py` line 38 as `base - timedelta(...)`, which underflows the calendar (`OverflowError`). It becomes a `ValueError` with a plain sentence, so the routes answer 422 and the tools "Refused: …".
- **"Sept".** ICU spells September "Sept" in `en-GB`. `dayLabel` (`web/src/components/board/money.ts:72`) and `dateLabel` / `momentDay` (`web/src/components/projects/projects.ts:61`, `:54`) format through `Intl`; they move onto P1's fixed month table through a new `dayText` in `web/src/ui/date/dates.ts`, which `friendlyDue` uses too.

**Files:**
- Modify: `roost/tasks/reminders.py`, `web/src/ui/date/dates.ts`, `web/src/components/board/money.ts`, `web/src/components/projects/projects.ts`
- Test: `tests/test_task_time.py`, `tests/test_tasks_api.py`, `web/tests/dates.test.ts`, `web/tests/money.test.ts`, `web/tests/projectsText.test.ts` (new)

**Interfaces:**
- Consumes: `build_schedule` (`roost/tasks/due.py`), `isIsoDay`, `todayIn`, `WEEKDAY_NAMES`, `MONTH_NAMES` (`web/src/ui/date/dates.ts`).
- Produces: `TOO_EARLY_TEXT` in `roost/tasks/reminders.py`; `dayText(day, { weekday?, year? })` and `DayTextOptions` in `web/src/ui/date/dates.ts`. Task 12 shows expense days with `dayLabel`, Task 13 shows comment and activity days with `dayText`.

- [ ] **Step 1: Path guard**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

Then confirm P2 has landed and this plan has not started:

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && test -f web/src/components/chat/RichText.tsx && grep -c "TOO_EARLY_TEXT" roost/tasks/reminders.py; grep -c "export function dayText" web/src/ui/date/dates.ts`
Expected: `0` then `0`. Otherwise stop.

- [ ] **Step 2: Write the failing tests**

Append to the end of `tests/test_task_time.py`:

```python


@pytest.mark.parametrize("due", ["0001-01-01T00:00", "0001-01-01T00:20:00+00:00"])
def test_a_due_in_the_calendars_first_hour_is_a_plain_refusal_not_an_overflow(due):
    """Redesign P3 leftover: the default advance reminder (30 minutes before) used to underflow to a 500."""
    with pytest.raises(ValueError, match="before the first day of the calendar"):
        build_schedule(due, None, None)
    assert build_schedule(due, None, []).pre_reminders == ()
```

Append to the end of `tests/test_tasks_api.py`:

```python


def test_a_due_in_year_one_is_422_with_a_plain_reason_not_a_500():
    c = _client()
    created = c.post("/api/tasks", json={"title": "x", "due_date": "0001-01-01T00:00"}, headers=O)
    assert created.status_code == 422
    assert "before the first day of the calendar" in created.json()["detail"]
    task = c.post("/api/tasks", json={"title": "x"}, headers=O).json()
    patched = c.patch(f"/api/tasks/{task['id']}", json={"due_date": "0001-01-01T00:00"}, headers=O)
    assert patched.status_code == 422 and "first day of the calendar" in patched.json()["detail"]
```

`web/tests/dates.test.ts`. Find:

```ts
  addDays, dateToDay, dayToDate, dueParts, friendlyDue, isIsoDay, joinDue, nextMonday, pickedParts, pickerText, todayIn,
} from "../src/ui/date/dates";
```

Replace with:

```ts
  addDays, dateToDay, dayText, dayToDate, dueParts, friendlyDue, isIsoDay, joinDue, nextMonday, pickedParts, pickerText,
  todayIn,
} from "../src/ui/date/dates";
```

`web/tests/dates.test.ts`. Find:

```ts
  it("the calendar's dates round-trip to the same day in any zone", () => {
```

Replace with:

```ts
  it("names a day with or without its weekday and year, September as Sep, and leaves a non-day alone", () => {
    expect(dayText("2026-09-15")).toBe("15 Sep");
    expect(dayText("2026-09-15", { weekday: true })).toBe("Tue 15 Sep");
    expect(dayText("2026-09-15", { year: true })).toBe("15 Sep 2026");
    expect(dayText("2026-09-15", { weekday: true, year: true })).toBe("Tue 15 Sep 2026");
    expect(dayText("2026-02-30")).toBe("2026-02-30");
    expect(dayText("soon")).toBe("soon");
  });

  it("the calendar's dates round-trip to the same day in any zone", () => {
```

`web/tests/money.test.ts`. Find:

```ts
    expect(dayLabel("2026-10-13")).toBe("Tue 13 Oct");
    expect(dayLabel("not a day")).toBe("not a day");
```

Replace with:

```ts
    expect(dayLabel("2026-10-13")).toBe("Tue 13 Oct");
    expect(dayLabel("2026-09-15")).toBe("Tue 15 Sep"); // ICU's en-GB says "Sept"
    expect(dayLabel("not a day")).toBe("not a day");
```

Create `web/tests/projectsText.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { dateLabel, momentDay } from "../src/components/projects/projects";

describe("project day labels (redesign P3)", () => {
  it("say September as Sep, like the pickers, and leave a non-day alone", () => {
    expect(dateLabel("2026-09-20")).toBe("20 Sep 2026");
    expect(dateLabel("2026-12-20")).toBe("20 Dec 2026");
    expect(dateLabel("someday")).toBe("someday");
  });

  it("name a moment by its Madrid day", () => {
    expect(momentDay("2026-09-30T22:30:00Z")).toBe("1 Oct 2026"); // 00:30 in Madrid
    expect(momentDay("2026-09-10T08:00:00Z")).toBe("10 Sep 2026");
    expect(momentDay("not a time")).toBe("not a time");
  });
});
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && ROOST_DATA_DIR=$(mktemp -d) ROOST_DESKS_DIR=$(mktemp -d) uv run pytest tests/test_task_time.py tests/test_tasks_api.py -q`
Expected: FAIL: the three new tests, with `OverflowError: date value out of range` (the API test sees the 500 as a raised `OverflowError` from the TestClient).

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npx vitest run tests/dates.test.ts tests/money.test.ts tests/projectsText.test.ts`
Expected: FAIL: `dayText is not a function` in `dates.test.ts`; `"Tue 15 Sept"` is not `"Tue 15 Sep"` in `money.test.ts`; `"20 Sept 2026"` in `projectsText.test.ts`.

- [ ] **Step 4: The refusal**

`roost/tasks/reminders.py`. Find:

```python
_OFFSET_RE = re.compile(
```

Replace with:

```python
TOO_EARLY_TEXT = "The advance reminder {entry} would fall before the first day of the calendar. Pick a later time."

_OFFSET_RE = re.compile(
```

`roost/tasks/reminders.py`. Find:

```python
def resolve_pre_reminders(entries: Sequence[str] | None, reminder_at: str | None) -> tuple[str, ...]:
    """UTC ISO instants for ``entries`` (offsets like -30m, or ISO times).
    ``None`` means LazyClaw's default (30 minutes before) when there is a
    reminder; ``[]`` means none."""
    if reminder_at is None:
        if entries:
            raise ValueError("Advance reminders need a reminder time.")
        return ()
    base = parse_iso_datetime(reminder_at)
    if base is None:
        raise ValueError(f"{reminder_at!r} is not a date and time.")
    wanted = DEFAULT_PRE_REMINDERS if entries is None else tuple(entries)
    instants = tuple(parse_offset_against(entry, base) or parse_iso_datetime(entry) for entry in wanted)
```

Replace with:

```python
def _instant(entry: str, base: datetime) -> datetime | None:
    """One advance reminder's instant, or ``None`` when ``entry`` is neither
    an offset nor a time. A reminder in the calendar's first hours (year 1)
    has no room before it: ``base - 30m`` overflows, which is a plain
    refusal (``ValueError``), never a crash (redesign P3)."""
    try:
        return parse_offset_against(entry, base) or parse_iso_datetime(entry)
    except OverflowError as exc:
        raise ValueError(TOO_EARLY_TEXT.format(entry=entry)) from exc


def resolve_pre_reminders(entries: Sequence[str] | None, reminder_at: str | None) -> tuple[str, ...]:
    """UTC ISO instants for ``entries`` (offsets like -30m, or ISO times).
    ``None`` means LazyClaw's default (30 minutes before) when there is a
    reminder; ``[]`` means none."""
    if reminder_at is None:
        if entries:
            raise ValueError("Advance reminders need a reminder time.")
        return ()
    base = parse_iso_datetime(reminder_at)
    if base is None:
        raise ValueError(f"{reminder_at!r} is not a date and time.")
    wanted = DEFAULT_PRE_REMINDERS if entries is None else tuple(entries)
    instants = tuple(_instant(entry, base) for entry in wanted)
```

Both routes already turn a `ValueError` from `build_schedule` into a 422 (`roost/gateway/routes/tasks.py` `_unreadable`), and the tools into "Refused: …", so nothing else changes.

- [ ] **Step 5: One way to name a day**

`web/src/ui/date/dates.ts`. Find:

```ts
/** "Fri 16 Oct 2026", or "Fri 16 Oct 2026, 09:00". */
export function friendlyDue(parts: DueParts, withTime = true): string {
  const noon = utcNoon(parts.day);
  const day = `${WEEKDAY_NAMES[noon.getUTCDay()]} ${noon.getUTCDate()} ${MONTH_NAMES[noon.getUTCMonth()]} ${noon.getUTCFullYear()}`;
  return withTime && parts.time ? `${day}, ${parts.time}` : day;
}
```

Replace with:

```ts
export interface DayTextOptions {
  weekday?: boolean; // "Tue 13 Oct"
  year?: boolean; // "13 Oct 2026"
}

/** A day with the fixed names: "13 Oct", "Tue 13 Oct", "13 Oct 2026" or "Tue 13 Oct 2026". Anything that
 * is not a day comes back as it is. Every day label on the Board goes through here (redesign P3). */
export function dayText(day: string, { weekday = false, year = false }: DayTextOptions = {}): string {
  if (!isIsoDay(day)) return day;
  const noon = utcNoon(day);
  const named = `${noon.getUTCDate()} ${MONTH_NAMES[noon.getUTCMonth()]}`;
  const dated = year ? `${named} ${noon.getUTCFullYear()}` : named;
  return weekday ? `${WEEKDAY_NAMES[noon.getUTCDay()]} ${dated}` : dated;
}

/** "Fri 16 Oct 2026", or "Fri 16 Oct 2026, 09:00". */
export function friendlyDue(parts: DueParts, withTime = true): string {
  const day = dayText(parts.day, { weekday: true, year: true });
  return withTime && parts.time ? `${day}, ${parts.time}` : day;
}
```

`web/src/components/board/money.ts`. Find:

```ts
// Roost amounts are decimal strings ("12.50") from the gateway, which sums them
// with Decimal; here they are only displayed, never added up.
```

Replace with:

```ts
// Roost amounts are decimal strings ("12.50") from the gateway, which sums them
// with Decimal; here they are only displayed, never added up.
import { dayText } from "../../ui/date/dates";
```

`web/src/components/board/money.ts`. Find:

```ts
/** A spent_at day ("2026-10-13", already a Madrid day) → "Tue 13 Oct". */
export function dayLabel(day: string): string {
  const [year, month, date] = day.split("-").map(Number);
  if (!year || !month || !date) return day;
  return new Date(Date.UTC(year, month - 1, date)).toLocaleDateString("en-GB", {
    weekday: "short", day: "numeric", month: "short", timeZone: "UTC",
  }).replace(",", "");
}
```

Replace with:

```ts
/** A spent_at day ("2026-10-13", already a Madrid day) → "Tue 13 Oct", with the fixed month names. */
export function dayLabel(day: string): string {
  return dayText(day, { weekday: true });
}
```

`web/src/components/projects/projects.ts`. Find:

```ts
import { formatMoney } from "../board/money";
```

Replace with:

```ts
import { formatMoney } from "../board/money";
import { dayText, todayIn } from "../../ui/date/dates";
```

`web/src/components/projects/projects.ts`. Find:

```ts
const CURRENCY_CODE = /^[A-Z]{3}$/;
const MADRID = "Europe/Madrid";
const MOMENT_DAY = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: MADRID });
```

Replace with:

```ts
const CURRENCY_CODE = /^[A-Z]{3}$/;
```

`web/src/components/projects/projects.ts`. Find:

```ts
/** A moment (UTC ISO) → its Madrid day, "10 Oct 2026". */
export function momentDay(iso: string): string {
  const when = new Date(iso);
  return Number.isNaN(when.getTime()) ? iso : MOMENT_DAY.format(when);
}

/** A plain day ("2026-12-20") → "20 Dec 2026". */
export function dateLabel(day: string): string {
  const [year, month, date] = day.split("-").map(Number);
  if (!year || !month || !date) return day;
  return new Date(Date.UTC(year, month - 1, date)).toLocaleDateString("en-GB", {
    day: "numeric", month: "short", year: "numeric", timeZone: "UTC",
  });
}
```

Replace with:

```ts
/** A moment (UTC ISO) → its Madrid day, "10 Oct 2026". */
export function momentDay(iso: string): string {
  const when = new Date(iso);
  return Number.isNaN(when.getTime()) ? iso : dayText(todayIn(when), { year: true });
}

/** A plain day ("2026-12-20") → "20 Dec 2026", with the fixed month names. */
export function dateLabel(day: string): string {
  return dayText(day, { year: true });
}
```

- [ ] **Step 6: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && ROOST_DATA_DIR=$(mktemp -d) ROOST_DESKS_DIR=$(mktemp -d) uv run pytest tests/test_task_time.py tests/test_tasks_api.py -q`
Expected: PASS.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npx vitest run tests/dates.test.ts tests/money.test.ts tests/projectsText.test.ts tests/ExpenseList.test.tsx tests/TopupHistory.test.tsx tests/ProjectsBoard.test.tsx tests/Project.test.tsx tests/MoneyBoard.test.tsx`
Expected: PASS (8 files).

- [ ] **Step 7: Commit**

Run:

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && \
git add roost/tasks/reminders.py tests/test_task_time.py tests/test_tasks_api.py web/src/ui/date/dates.ts \
  web/src/components/board/money.ts web/src/components/projects/projects.ts web/tests/dates.test.ts \
  web/tests/money.test.ts web/tests/projectsText.test.ts && \
git commit -m "fix: a due in the calendar's first hour is a 422, and the Board's days never say Sept"
```

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git status --short`
Expected: none of the files above is listed.

---
### Task 2: Sheets that work with menus and pickers: focus back from a menu item, overlays drawn inside

Two Sheet bugs, both found before the drawer (Task 10) puts a Sheet in daily use.
- **Focus from a menu item (P1's review).** The Sheet remembers what had focus as it opens (`onOpenAutoFocus`) so it can give focus back on close. When a menu item opens it, the menu closes in the same render, the item is removed, and focus has already fallen to the page body: on close, focus is lost. The fix is in `MenuItem`: before it acts, it focuses its menu's own button (passed down by `Menu` through a context), so the Sheet remembers the button. An item that opens nothing leaves focus on the button, as Radix did; an item that opens a dialog which focuses its own field (New room) keeps that focus, because `keepFocusAnItemMoved` still stops Radix from pulling it back.
- **A Select inside a Sheet freezes the page.** Each Radix package in `web/node_modules` carries its own copy of `@radix-ui/react-focus-scope` (1.1.16 under `react-dialog`, `react-select`, `react-popover` and `react-menu`; 1.3.1 at the top for Univer), so the Sheet's focus trap and the Select's do not know each other: opening the Select moves focus to its list on the page body, the Sheet pulls it back, the Select pulls it again, until `RangeError: Maximum call stack size exceeded`. The calendar popover has the same fight with the trap. The fix: the Sheet provides its panel through `PortalContainer` (`web/src/ui/portalContainer.ts`), and the kit's `Select`, `Popover` and `Menu` draw their portals into it, so focus never leaves the Sheet. Outside a Sheet nothing changes. No dependency changes.

**Files:**
- Create: `web/src/ui/portalContainer.ts`
- Modify: `web/src/ui/Menu.tsx`, `web/src/ui/Sheet.tsx`, `web/src/ui/Select.tsx`, `web/src/ui/Popover.tsx`
- Test: `web/tests/sheetFocus.test.tsx` (new); `web/tests/{Menu,overlays,Select,NewRoomDialog,BotMenu,Layout,DatePicker,DateTimePicker}.test.tsx` stay green unchanged

**Interfaces:**
- Consumes: the Radix `Dialog`, `Select`, `Popover` and `DropdownMenu` primitives.
- Produces: `MenuItem` focuses its menu's button before calling `onSelect` (same props); `PortalContainer` and `usePortalContainer(): HTMLElement | undefined`; `Sheet` provides its panel; `Select`, `Popover` and `Menu` portal into it. Task 10's drawer holds Selects, date pickers and a row menu opens it.

- [ ] **Step 1: Path guard**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && grep -c "TOO_EARLY_TEXT" roost/tasks/reminders.py && test ! -e web/src/ui/portalContainer.ts && grep -c "MenuButton" web/src/ui/Menu.tsx`
Expected: `2` then `0` (Task 1 landed, this task has not). Otherwise stop.

- [ ] **Step 2: Write the failing tests**

Create `web/tests/sheetFocus.test.tsx`:

```tsx
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { Menu, MenuItem } from "../src/ui/Menu";
import { Select } from "../src/ui/Select";
import { Sheet } from "../src/ui/Sheet";
import { MoreIcon } from "../src/components/icons";

afterEach(() => cleanup());

// P1 review: a Sheet opened from a menu item gave focus to the page body when it closed, because the
// item is gone by the time the Sheet remembers what opened it.
function RowWithMenu({ onOther }: { onOther: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Menu label="More for Fix the sink" trigger={<MoreIcon />}>
        <MenuItem onSelect={() => setOpen(true)}>Open details</MenuItem>
        <MenuItem onSelect={onOther}>Copy link</MenuItem>
      </Menu>
      <Sheet open={open} onOpenChange={setOpen} title="Fix the sink"><input aria-label="Title" /></Sheet>
    </>
  );
}

describe("a Sheet opened from a menu item (redesign P3)", () => {
  it("gives focus back to the menu's button when it closes", async () => {
    const user = userEvent.setup();
    render(<RowWithMenu onOther={vi.fn()} />);
    const button = screen.getByRole("button", { name: "More for Fix the sink" });
    await user.click(button);
    await user.click(await screen.findByRole("menuitem", { name: "Open details" }));
    const sheet = await screen.findByRole("dialog", { name: "Fix the sink" });
    expect(sheet).toContainElement(document.activeElement as HTMLElement);
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(button).toHaveFocus();
  });

  it("an item that opens nothing still runs and leaves focus on the menu's button", async () => {
    const onOther = vi.fn();
    const user = userEvent.setup();
    render(<RowWithMenu onOther={onOther} />);
    const button = screen.getByRole("button", { name: "More for Fix the sink" });
    await user.click(button);
    await user.click(await screen.findByRole("menuitem", { name: "Copy link" }));
    expect(onOther).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(button).toHaveFocus();
  });
});

function SheetWithPickers() {
  const [priority, setPriority] = useState("medium");
  return (
    <Sheet open onOpenChange={() => undefined} title="Fix the sink">
      <Select label="Priority" value={priority} onChange={setPriority}
        options={[{ value: "medium", label: "Medium" }, { value: "high", label: "High" }]} />
      <Menu label="More" trigger={<MoreIcon />}><MenuItem onSelect={() => undefined}>Copy link</MenuItem></Menu>
    </Sheet>
  );
}

describe("overlays inside a Sheet (redesign P3)", () => {
  it("a Select opens inside the Sheet's panel and picks, and the Sheet stays open", async () => {
    const user = userEvent.setup();
    render(<SheetWithPickers />);
    const sheet = screen.getByRole("dialog", { name: "Fix the sink" });
    const priority = within(sheet).getByRole("combobox", { name: "Priority" });
    await user.click(priority);
    expect(sheet).toContainElement(await screen.findByRole("listbox"));
    await user.click(screen.getByRole("option", { name: "High" }));
    expect(priority).toHaveTextContent("High");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "Fix the sink" })).toBeInTheDocument();
  });

  it("a Menu opens inside the Sheet's panel", async () => {
    const user = userEvent.setup();
    render(<SheetWithPickers />);
    const sheet = screen.getByRole("dialog", { name: "Fix the sink" });
    await user.click(within(sheet).getByRole("button", { name: "More" }));
    expect(sheet).toContainElement(await screen.findByRole("menu"));
  });
});
```

- [ ] **Step 3: Run them to see them fail**

The Select test does not fail cleanly before the fix: the two focus traps call each other until the stack overflows, and vitest keeps printing `RangeError`. So run the menu tests on their own first, then the Select test under a time limit:

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npx vitest run tests/sheetFocus.test.tsx -t "menu item"`
Expected: FAIL: "gives focus back to the menu's button when it closes" (focus is on `<body>`); "an item that opens nothing" passes already.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && (perl -e 'alarm 60; exec @ARGV' npx vitest run tests/sheetFocus.test.tsx -t "Select opens" 2>&1 | grep -m 3 -E "RangeError|Tests "); pkill -f "vitest run tests/sheetFocus" ; true`
Expected: `RangeError: Maximum call stack size exceeded`, raised in `handleFocusOut` of both `react-dialog/node_modules/@radix-ui/react-focus-scope` and `react-select/node_modules/@radix-ui/react-focus-scope`.

- [ ] **Step 4: The portal container**

Create `web/src/ui/portalContainer.ts`:

```ts
import { createContext, useContext } from "react";

// Where an overlay inside a Sheet draws (redesign P3): the Sheet's own panel. Each Radix package here
// carries its own copy of Radix's focus scope, so a Select or a calendar drawn on the page body would fight
// the Sheet's focus trap (each pulls focus back, without end). Drawn inside the Sheet, focus stays within
// it. Outside a Sheet there is no container, and overlays draw on the body as before.
export const PortalContainer = createContext<HTMLElement | null>(null);

export function usePortalContainer(): HTMLElement | undefined {
  return useContext(PortalContainer) ?? undefined;
}
```

- [ ] **Step 5: The Sheet provides its panel; Select, Popover and Menu draw into it; a menu item focuses its button**

Replace the whole of `web/src/ui/Sheet.tsx` with:

```tsx
import * as RadixDialog from "@radix-ui/react-dialog";
import { useRef, useState, type ReactNode } from "react";
import { CloseIcon } from "../components/icons";
import { IconButton } from "./IconButton";
import { PortalContainer } from "./portalContainer";

export interface SheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string; // a line under the title
  children: ReactNode;
  footer?: ReactNode; // actions, pinned to the bottom
}

// A drawer from the right edge (redesign P1, Radix Dialog): modal, focus kept inside, Escape and
// the scrim close it, and focus goes back to what opened it. The kit's overlays inside it (Select,
// Popover, Menu) draw inside its panel (redesign P3, ui/portalContainer.ts).
export function Sheet({ open, onOpenChange, title, description, children, footer }: SheetProps) {
  const opener = useRef<HTMLElement | null>(null);
  const [panel, setPanel] = useState<HTMLDivElement | null>(null);
  // Remembered as it opens, before focus moves in: a sheet opened from code has no Radix trigger.
  const remember = () => {
    opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  };
  const giveBack = (event: Event) => {
    event.preventDefault();
    if (opener.current?.isConnected) opener.current.focus();
  };
  return (
    <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
      <RadixDialog.Portal>
        <RadixDialog.Overlay className="ui-sheet__scrim" />
        <RadixDialog.Content ref={setPanel} className="ui-sheet" onOpenAutoFocus={remember} onCloseAutoFocus={giveBack}
          {...(description ? {} : { "aria-describedby": undefined })}>
          <PortalContainer.Provider value={panel}>
            <header className="ui-sheet__head">
              <RadixDialog.Title className="ui-sheet__title">{title}</RadixDialog.Title>
              <RadixDialog.Close asChild>
                <IconButton label="Close" icon={<CloseIcon />} tooltip={false} />
              </RadixDialog.Close>
            </header>
            {description ? <RadixDialog.Description className="ui-sheet__description">{description}</RadixDialog.Description> : null}
            <div className="ui-sheet__body">{children}</div>
            {footer ? <footer className="ui-sheet__foot">{footer}</footer> : null}
          </PortalContainer.Provider>
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}
```

Replace the whole of `web/src/ui/Select.tsx` with:

```tsx
import * as RadixSelect from "@radix-ui/react-select";
import { CheckIcon, ChevronDownIcon } from "../components/icons";
import { cx } from "./cx";
import { controlA11y, useFieldControl } from "./Field";
import { usePortalContainer } from "./portalContainer";
import type { ControlSize } from "./Button";

// An option's value is never "" (Radix keeps "" for "nothing chosen"): use a word such as "none".
export interface SelectOption<T extends string = string> {
  value: T;
  label: string;
  disabled?: boolean;
}

export interface SelectProps<T extends string = string> {
  value: T;
  onChange: (value: T) => void;
  options: ReadonlyArray<SelectOption<T>>;
  label?: string; // the accessible name when the select is not inside a Field
  id?: string;
  disabled?: boolean;
  placeholder?: string;
  size?: ControlSize;
}

// A styled list to pick one from (redesign P1, Radix Select): the keyboard, typeahead and screen
// reader behaviour of a native select, in Roost's look. It opens below its button.
export function Select<T extends string = string>({
  value, onChange, options, label, id, disabled = false, placeholder, size = "lg",
}: SelectProps<T>) {
  const a11y = controlA11y(useFieldControl(), { id });
  const container = usePortalContainer();
  return (
    <RadixSelect.Root value={value} onValueChange={(next) => onChange(next as T)} disabled={disabled}>
      <RadixSelect.Trigger {...a11y} aria-label={label} className={cx("select", `select--${size}`)}>
        <RadixSelect.Value placeholder={placeholder} />
        <RadixSelect.Icon className="select__icon"><ChevronDownIcon /></RadixSelect.Icon>
      </RadixSelect.Trigger>
      <RadixSelect.Portal container={container}>
        <RadixSelect.Content className="select__content" position="popper" sideOffset={4}>
          <RadixSelect.Viewport className="select__viewport">
            {options.map((option) => (
              <RadixSelect.Item key={option.value} value={option.value} disabled={option.disabled} className="select__item">
                <RadixSelect.ItemText>{option.label}</RadixSelect.ItemText>
                <RadixSelect.ItemIndicator className="select__check"><CheckIcon /></RadixSelect.ItemIndicator>
              </RadixSelect.Item>
            ))}
          </RadixSelect.Viewport>
        </RadixSelect.Content>
      </RadixSelect.Portal>
    </RadixSelect.Root>
  );
}
```

Replace the whole of `web/src/ui/Popover.tsx` with:

```tsx
import * as RadixPopover from "@radix-ui/react-popover";
import type { ReactElement, ReactNode } from "react";
import { usePortalContainer } from "./portalContainer";

export interface PopoverProps {
  trigger: ReactElement; // one element that opens it, such as an IconButton
  label: string; // the panel's accessible name
  children: ReactNode;
  open?: boolean; // controlled when given, with onOpenChange
  onOpenChange?: (open: boolean) => void;
  side?: "top" | "bottom";
  align?: "start" | "center" | "end";
}

// A small panel beside its button (redesign P1, Radix Popover): Escape and a click outside close it,
// and focus goes back to the button.
export function Popover({ trigger, label, children, open, onOpenChange, side = "bottom", align = "end" }: PopoverProps) {
  const container = usePortalContainer();
  return (
    <RadixPopover.Root open={open} onOpenChange={onOpenChange}>
      <RadixPopover.Trigger asChild>{trigger}</RadixPopover.Trigger>
      <RadixPopover.Portal container={container}>
        <RadixPopover.Content className="popover" aria-label={label} side={side} align={align} sideOffset={6}>
          {children}
        </RadixPopover.Content>
      </RadixPopover.Portal>
    </RadixPopover.Root>
  );
}
```

Replace the whole of `web/src/ui/Menu.tsx` with:

```tsx
import * as RadixMenu from "@radix-ui/react-dropdown-menu";
import { createContext, useContext, useRef, type ReactNode, type RefObject } from "react";
import { Link } from "react-router-dom";
import { usePortalContainer } from "./portalContainer";

export interface MenuProps {
  label: string; // names the button and the menu
  trigger: ReactNode; // what the button shows (an icon, initials)
  children: ReactNode; // MenuItem, MenuLink and MenuNote
  side?: "top" | "bottom";
  align?: "start" | "end";
}

// The menu's own button, for its items (MenuItem).
const MenuButton = createContext<RefObject<HTMLButtonElement | null> | null>(null);

// Radix gives focus back to the button when the menu closes. When the chosen item has already put
// focus somewhere (New room focuses the dialog's name field), leave it there.
function keepFocusAnItemMoved(event: Event) {
  const active = document.activeElement;
  const moved = active instanceof HTMLElement && active !== document.body && active.isConnected
    && !active.closest("[role='menu']");
  if (moved) event.preventDefault();
}

// A pop-up menu (redesign P1, Radix DropdownMenu): arrow keys, typeahead, Escape, and focus back to
// its button. Picking an item closes it. Not modal: an item may open a dialog that takes the focus.
export function Menu({ label, trigger, children, side = "bottom", align = "end" }: MenuProps) {
  const button = useRef<HTMLButtonElement>(null);
  const container = usePortalContainer();
  return (
    <div className="menu">
      <MenuButton.Provider value={button}>
        <RadixMenu.Root modal={false}>
          <RadixMenu.Trigger ref={button} className="icon-btn" aria-label={label}>{trigger}</RadixMenu.Trigger>
          <RadixMenu.Portal container={container}>
            <RadixMenu.Content className="menu__list" side={side} align={align} sideOffset={6}
              onCloseAutoFocus={keepFocusAnItemMoved}>
              {children}
            </RadixMenu.Content>
          </RadixMenu.Portal>
        </RadixMenu.Root>
      </MenuButton.Provider>
    </div>
  );
}

// Focus goes back to the menu's button before the item acts (redesign P3). The item is gone once the
// menu closes, so a Sheet it opens remembers the button as its opener and gives focus back to it; a
// dialog that focuses its own field keeps that focus (keepFocusAnItemMoved).
export function MenuItem({ onSelect, disabled = false, title, children }: {
  onSelect: () => void; disabled?: boolean; title?: string; children: ReactNode;
}) {
  const button = useContext(MenuButton);
  const select = () => {
    button?.current?.focus();
    onSelect();
  };
  return (
    <RadixMenu.Item className="menu__item" disabled={disabled} title={title} onSelect={select}>
      {children}
    </RadixMenu.Item>
  );
}

export function MenuLink({ to, children }: { to: string; children: ReactNode }) {
  return (
    <RadixMenu.Item asChild className="menu__item">
      <Link to={to}>{children}</Link>
    </RadixMenu.Item>
  );
}

export function MenuNote({ children }: { children: ReactNode }) {
  return <RadixMenu.Label className="menu__note">{children}</RadixMenu.Label>;
}
```

- [ ] **Step 6: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npx vitest run tests/sheetFocus.test.tsx tests/Menu.test.tsx tests/overlays.test.tsx tests/Select.test.tsx tests/NewRoomDialog.test.tsx tests/BotMenu.test.tsx tests/Layout.test.tsx tests/DatePicker.test.tsx tests/DateTimePicker.test.tsx`
Expected: PASS (9 files; `sheetFocus.test.tsx` 4 passed).

- [ ] **Step 7: Commit**

Run:

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && \
git add web/src/ui/portalContainer.ts web/src/ui/Sheet.tsx web/src/ui/Select.tsx web/src/ui/Popover.tsx \
  web/src/ui/Menu.tsx web/tests/sheetFocus.test.tsx && \
git commit -m "fix: a sheet gives focus back to a menu's button, and selects, popovers and menus open inside it"
```

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git status --short`
Expected: none of the files above is listed.

---
### Task 3: Schema v14 and comments on a task or a step

Design P3 "Comments", Design meets code 1, 2 and 9. A new table, `task_comments`, holds comments on a task (or on one of its steps): the body `enc:v2` under `task_comments:body`, the author ("user" or a bot's id), a taint bit, and soft deletion. `CommentStore` reads and writes them, only while their task is live and the user's (checked in the same session as the write). `CommentService` is the one door for the tools (Task 5) and the routes (Task 6): it checks the body and the step, refuses to change a bot's comment (`CommentNotYours`), and publishes `tasks_changed` with `change: "commented"` through a new shared `publish_task_change`.

The fixture `tests/fixtures/schema_v13.sql` is frozen **before** `roost/db/migrations.py` changes, as the projects hub froze v12.

**Files:**
- Create: `tests/fixtures/schema_v13.sql` (generated in Step 2), `roost/tasks/comments.py`, `roost/tasks/comment_store.py`, `roost/tasks/comment_service.py`
- Modify: `roost/db/migrations.py`, `roost/constants.py`, `roost/tasks/models.py`, `roost/tasks/service.py`
- Test: `tests/test_migrations_v13.py` (new), `tests/test_task_comments.py` (new)

**Interfaces:**
- Consumes: `encrypt_field`, `decrypt_field`, `user_aad`, `get_user_dek`, `db_session`; `TaskStore.get`; `EventHub.publish`; `test_migrations_v12._ROWS` / `_EXPECTED` and `test_migrations_v8._NOW` (tests only).
- Produces (the Shared Contract's names): schema v14; the seven constants; `STEP_NOT_FOUND_TEXT`; `TaskChange` with `"commented"` and `publish_task_change`; `TaskComment`, `COMMENT_BY_USER`, `comment_body`, `comment_out`, `EMPTY_COMMENT_TEXT`, `LONG_COMMENT_TEXT`; `CommentStore`; `CommentService`, `CommentNotYours`, `NOT_YOURS_TEXT`. Task 4 uses `CommentStore.unlink_step` and `STEP_NOT_FOUND_TEXT`, Task 5 `CommentService` and `COMMENT_TOOL_LIMIT`, Task 6 the service and `comment_out`.

No test pins schema version 13: `tests/test_migrations_v12.py` asserts `latest_version() >= 13` and the older ones compare with `latest_version()`. Step 1 checks it with a grep.

- [ ] **Step 1: Path guard**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && grep -c "MenuButton" web/src/ui/Menu.tsx && test ! -e tests/fixtures/schema_v13.sql && grep -n "Migration(1[34]," roost/db/migrations.py && grep -rn "latest_version() == 1[34]" tests/ ; echo "end"`
Expected: a count above `0`, then `    Migration(13, "projects hub", (` alone, then `end`. If `schema_v13.sql` exists, `Migration(14,` shows up, or a test pins a version, stop: this task already ran, or a test needs updating first.

- [ ] **Step 2: Freeze the current schema (v13), then write the failing tests**

**2a. Freeze schema v13.** This must run **before** `roost/db/migrations.py` changes. The script builds a throwaway database in its own `mktemp -d`, never in `~/Roost/data`:

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && ROOST_DATA_DIR=$(mktemp -d) ROOST_DESKS_DIR=$(mktemp -d) uv run python - <<'PY'
import asyncio, os, sqlite3
from pathlib import Path
import aiosqlite
from roost.db.migrations import apply_migrations, latest_version

assert latest_version() == 13, f"expected schema v13 before redesign P3, got {latest_version()}"

async def build(path: Path) -> None:
    async with aiosqlite.connect(path) as db:
        await db.executescript(Path("roost/db/schema.sql").read_text())
        await db.commit()
        await apply_migrations(db)

path = Path(os.environ["ROOST_DATA_DIR"]) / "v13.db"
asyncio.run(build(path))
con = sqlite3.connect(path)
rows = con.execute(
    "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY rowid"
).fetchall()
con.close()
header = ("-- Roost schema version 13, frozen by redesign P3 Task 3 (schema.sql + migrations 1-13).\n"
          "-- The live ~/Roost/data/roost.db runs this schema at the start of redesign P3. Never edit.\n\n")
Path("tests/fixtures/schema_v13.sql").write_text(header + ";\n\n".join(r[0] for r in rows) + ";\n")
print("tables/indexes:", len(rows))
PY
grep -c "CREATE" tests/fixtures/schema_v13.sql              # 45
grep -c "allocated_budget" tests/fixtures/schema_v13.sql    # 1
grep -c "task_comments" tests/fixtures/schema_v13.sql       # 0
diff <(sed 1,3d tests/fixtures/schema_v12.sql) <(sed 1,3d tests/fixtures/schema_v13.sql)
```

Expected:
- The script prints `tables/indexes: 45`; the three greps print `45`, `1` and `0`.
- The file starts with exactly these lines:

```sql
-- Roost schema version 13, frozen by redesign P3 Task 3 (schema.sql + migrations 1-13).
-- The live ~/Roost/data/roost.db runs this schema at the start of redesign P3. Never edit.

CREATE TABLE users (
```

- The `diff` shows only v13's additions: six `);` lines that become `, <new columns>);` (`tasks`: `project_id`, `allocated_budget`; `money_projects`: `color`, `start_date`, `due_date`, `monthly_budget`, `lead_bot_id`; `money_expenses`: `step_id`, `is_favorite`; `money_topups`: `topup_id`; `notes` and `documents`: `project_id`), and one added block at the end with `idx_tasks_user_project`, `idx_notes_user_project` and `idx_documents_user_project`. Nothing is removed. (`diff` exits 1 because the files differ; that is expected.)

**2b. The migration test from v13, with rows.**

Create `tests/test_migrations_v13.py`:

```python
"""Migrating from the schema the live gateway runs at the start of redesign P3 (version 13).

``tests/fixtures/schema_v13.sql`` was frozen by redesign P3 Task 3. Rows go in every table the
user's account uses today (the v12 test's rows, plus a task in a project with a budget slice and an
expense filed under one of its steps). v14 only adds the ``task_comments`` table and its index."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.db.migrations import latest_version
from test_migrations_v8 import _NOW
from test_migrations_v12 import _EXPECTED as _V12_EXPECTED
from test_migrations_v12 import _ROWS as _V12_ROWS

_V13_SCHEMA = Path(__file__).parent / "fixtures" / "schema_v13.sql"
_ROWS = (
    *_V12_ROWS,
    "INSERT INTO tasks (id, user_id, title, created_at, updated_at, project_id, allocated_budget) "
    f"VALUES ('task3','u1','enc:t','{_NOW}','{_NOW}','p1','enc:b')",
    "INSERT INTO money_expenses (id, user_id, project_id, task_id, step_id, amount, spent_at, created_at, updated_at) "
    f"VALUES ('e2','u1','p1','task3','s-1','enc:a','2026-10-03','{_NOW}','{_NOW}')",
)
_EXPECTED = {**_V12_EXPECTED, "tasks": 3, "money_expenses": 2}
_COMMENT_COLUMNS = {"id", "user_id", "task_id", "step_id", "author", "body", "tainted", "created_at", "edited_at",
                    "deleted_at"}
_COMMENT = ("INSERT INTO task_comments (id, user_id, task_id, step_id, author, body, created_at) "
            f"VALUES ('c1','u1','{{task}}',NULL,'user','enc:c','{_NOW}')")


def _query(db_path: Path, sql: str, params: tuple = ()) -> list[tuple]:
    con = sqlite3.connect(db_path)
    try:
        return con.execute(sql, params).fetchall()
    finally:
        con.close()


def _counts(db_path: Path) -> dict[str, int]:
    return {table: _query(db_path, f"SELECT COUNT(*) FROM {table}")[0][0] for table in _EXPECTED}


def _connect(db_path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA foreign_keys = ON")
    return con


@pytest.fixture
def seeded_v13():
    cfg = load_config()
    db_path = get_db_path(cfg)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        con.executescript(_V13_SCHEMA.read_text())
        con.execute("PRAGMA user_version = 13")
        for statement in _ROWS:
            con.execute(statement)
        con.commit()
    finally:
        con.close()
    return cfg, db_path


async def test_v13_database_migrates_to_latest_and_keeps_every_row(seeded_v13):
    cfg, db_path = seeded_v13
    await init_db(cfg)
    assert latest_version() >= 14
    assert _query(db_path, "PRAGMA user_version")[0][0] == latest_version()
    assert _counts(db_path) == _EXPECTED
    assert _query(db_path, "SELECT project_id, allocated_budget FROM tasks WHERE id = 'task3'") == [("p1", "enc:b")]
    assert _query(db_path, "SELECT task_id, step_id FROM money_expenses WHERE id = 'e2'") == [("task3", "s-1")]


async def test_v13_database_gains_the_comments_table_and_its_index(seeded_v13):
    cfg, db_path = seeded_v13
    await init_db(cfg)
    assert {row[1] for row in _query(db_path, "PRAGMA table_info(task_comments)")} == _COMMENT_COLUMNS
    indexes = {row[0] for row in _query(db_path, "SELECT name FROM sqlite_master WHERE type = 'index'")}
    assert "idx_task_comments_task" in indexes
    assert _query(db_path, "SELECT COUNT(*) FROM task_comments") == [(0,)]


async def test_a_comment_names_a_real_task_and_goes_with_its_row(seeded_v13):
    cfg, db_path = seeded_v13
    await init_db(cfg)
    con = _connect(db_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(_COMMENT.format(task="no-such-task"))
        con.execute(_COMMENT.format(task="task3"))
        assert con.execute("SELECT tainted, edited_at, deleted_at FROM task_comments").fetchall() == [(0, None, None)]
        con.execute("DELETE FROM tasks WHERE id = 'task3'")
        assert con.execute("SELECT COUNT(*) FROM task_comments").fetchone() == (0,)
    finally:
        con.close()


async def test_migrating_v13_twice_is_a_no_op_and_backs_up_once(seeded_v13):
    cfg, db_path = seeded_v13
    await init_db(cfg)
    await init_db(cfg)
    assert _counts(db_path) == _EXPECTED
    [backup] = sorted(db_path.parent.glob(f"roost.db.pre-v{latest_version()}-*.bak"))
    assert _query(backup, "PRAGMA user_version")[0][0] == 13
```

**2c. The comments.**

Create `tests/test_task_comments.py`:

```python
"""Comments on a task or one of its steps (redesign P3): encrypted on disk, scoped to their user,
only the user's own can change, and every change publishes tasks_changed."""

from __future__ import annotations

import sqlite3

import pytest

from roost.config import load_config
from roost.constants import MAX_COMMENT_LENGTH
from roost.db.connection import db_session, get_db_path, init_db
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.tasks.comment_service import NOT_YOURS_TEXT, CommentNotYours, CommentService
from roost.tasks.comment_store import CommentStore
from roost.tasks.comments import EMPTY_COMMENT_TEXT, LONG_COMMENT_TEXT
from roost.tasks.models import STEP_NOT_FOUND_TEXT, TaskDraft
from roost.tasks.store import TaskStore


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


@pytest.fixture
def service(cfg):
    return CommentService(CommentStore(cfg), TaskStore(cfg), EventHub(cfg))


async def _task(cfg, user_id: str, title: str = "Fix the sink", steps: tuple[str, ...] = ("Buy a washer",)):
    return await TaskStore(cfg).create(user_id, TaskDraft(title=title, steps=steps), created_by_bot=None, tainted=False)


def _frames(cfg) -> list[str]:
    con = sqlite3.connect(get_db_path(cfg))
    try:
        return [row[0] for row in con.execute("SELECT kind FROM events ORDER BY seq")]
    finally:
        con.close()


async def test_a_comment_is_ciphertext_on_disk_and_reads_back(cfg, user_id, service):
    task = await _task(cfg, user_id)
    comment = await service.add(user_id, task.id, "  The plumber comes at 9  ")
    assert (comment.body, comment.author, comment.step_id, comment.tainted) == ("The plumber comes at 9", "user", None, False)
    async with db_session(cfg) as db:
        [row] = await (await db.execute("SELECT body FROM task_comments")).fetchall()
    assert row[0].startswith("enc:v2:") and "plumber" not in row[0]
    assert [c.body for c in await service.list(user_id, task.id)] == ["The plumber comes at 9"]
    assert _frames(cfg)[-1] == "tasks_changed"


async def test_a_thread_is_oldest_first_and_keeps_the_newest_when_capped(cfg, user_id, service):
    task = await _task(cfg, user_id)
    for word in ("one", "two", "three"):
        await service.add(user_id, task.id, word)
    assert [c.body for c in await service.list(user_id, task.id)] == ["one", "two", "three"]
    assert [c.body for c in await service.list(user_id, task.id, limit=2)] == ["two", "three"]


async def test_a_comment_on_a_step_must_name_one_of_the_tasks_steps(cfg, user_id, service):
    task = await _task(cfg, user_id)
    on_step = await service.add(user_id, task.id, "Size 15 mm", step_id=task.steps[0].id)
    assert on_step.step_id == task.steps[0].id
    with pytest.raises(ValueError, match=STEP_NOT_FOUND_TEXT):
        await service.add(user_id, task.id, "x", step_id="s-nope")


@pytest.mark.parametrize(("body", "reason"), [("   ", EMPTY_COMMENT_TEXT), ("x" * (MAX_COMMENT_LENGTH + 1), LONG_COMMENT_TEXT)])
async def test_an_empty_or_long_comment_is_refused(cfg, user_id, service, body, reason):
    task = await _task(cfg, user_id)
    with pytest.raises(ValueError, match=reason):
        await service.add(user_id, task.id, body)
    assert await service.list(user_id, task.id) == ()


async def test_a_bot_comment_keeps_its_author_and_taint_and_the_user_cannot_change_it(cfg, user_id, service):
    task = await _task(cfg, user_id)
    bots = await service.add(user_id, task.id, "Found it on shop.example", author="bot-1", tainted=True)
    assert (bots.author, bots.tainted, bots.by_user) == ("bot-1", True, False)
    with pytest.raises(CommentNotYours, match=NOT_YOURS_TEXT):
        await service.edit(user_id, bots.id, "rewritten")
    with pytest.raises(CommentNotYours):
        await service.delete(user_id, bots.id)
    assert [c.body for c in await service.list(user_id, task.id)] == ["Found it on shop.example"]


async def test_the_user_edits_and_deletes_their_own_comment(cfg, user_id, service):
    task = await _task(cfg, user_id)
    mine = await service.add(user_id, task.id, "Call first")
    edited = await service.edit(user_id, mine.id, "Call first, then go")
    assert (edited.body, edited.edited_at is not None) == ("Call first, then go", True)
    assert await service.delete(user_id, mine.id) is True
    assert await service.list(user_id, task.id) == ()
    assert await service.delete(user_id, mine.id) is False
    assert await service.edit(user_id, mine.id, "back?") is None


async def test_another_users_task_and_comment_are_not_found(cfg, user_id, service):
    task = await _task(cfg, user_id)
    mine = await service.add(user_id, task.id, "Mine")
    other = (await register_user(cfg, "bob", "pw-123456")).id
    assert await service.list(other, task.id) is None
    assert await service.add(other, task.id, "Sneaky") is None
    assert await service.edit(other, mine.id, "Sneaky") is None
    assert await service.delete(other, mine.id) is False
    assert [c.body for c in await service.list(user_id, task.id)] == ["Mine"]


async def test_a_deleted_tasks_comments_are_gone_with_it(cfg, user_id, service):
    task = await _task(cfg, user_id)
    mine = await service.add(user_id, task.id, "Mine")
    await TaskStore(cfg).delete(user_id, task.id)
    assert await service.list(user_id, task.id) is None
    assert await service.add(user_id, task.id, "Late") is None
    assert await service.edit(user_id, mine.id, "Late") is None


async def test_unlinking_a_step_keeps_its_comments_on_the_task(cfg, user_id):
    task = await _task(cfg, user_id)
    store = CommentStore(cfg)
    await store.add(user_id, task.id, step_id=task.steps[0].id, author="user", body="On the step", tainted=False)
    assert await store.unlink_step(user_id, task.id, task.steps[0].id) == 1
    [comment] = await store.list(user_id, task.id, limit=10)
    assert (comment.body, comment.step_id) == ("On the step", None)
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && ROOST_DATA_DIR=$(mktemp -d) ROOST_DESKS_DIR=$(mktemp -d) uv run pytest tests/test_migrations_v13.py tests/test_task_comments.py -q`
Expected: FAIL: `test_task_comments.py` cannot import `roost.tasks.comment_service` (and `MAX_COMMENT_LENGTH`); in `test_migrations_v13.py`, `latest_version() >= 14` fails, there is no `task_comments` table, and the backup check finds no `pre-v14` file.

- [ ] **Step 4: The migration**

`roost/db/migrations.py`. Find:

```python
    answer_item_id TEXT,
    created_at TEXT NOT NULL,
    closed_at TEXT
)"""

MIGRATIONS: tuple[Migration, ...] = (
```

Replace with:

```python
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

MIGRATIONS: tuple[Migration, ...] = (
```

`roost/db/migrations.py`. Find:

```python
        "CREATE INDEX IF NOT EXISTS idx_documents_user_project ON documents(user_id, project_id)",
    )),
)
```

Replace with:

```python
        "CREATE INDEX IF NOT EXISTS idx_documents_user_project ON documents(user_id, project_id)",
    )),
    # Redesign P3. Live control's site_logins, planned as v14 before this, takes v15.
    Migration(14, "task comments", (
        _TASK_COMMENTS,
        "CREATE INDEX IF NOT EXISTS idx_task_comments_task ON task_comments(user_id, task_id, created_at)",
    )),
)
```

- [ ] **Step 5: The constants, the shared step sentence and the shared frame**

The constants go in the Tasks section. Task 8's two quick-line constants are added here too, so the section is written once.

`roost/constants.py`. Find:

```python
TASK_LIST_LIMIT = 50
```

Replace with:

```python
TASK_LIST_LIMIT = 50
# Redesign P3: a task's steps and comments.
MAX_STEP_TITLE_LENGTH = 200
STEP_WRITE_ATTEMPTS = 3          # compare-and-set tries for one steps change before "try again"
MAX_COMMENT_LENGTH = 4000
COMMENT_LIST_LIMIT = 200         # the newest comments a thread shows over HTTP, oldest first
COMMENT_TOOL_LIMIT = 20          # the newest comments list_comments shows a bot
QUICK_LINE_MAX_LENGTH = 300      # the quick-add line the Board reads as you type
# The money signs the quick-add line reads as a budget slice, and the currency each one means.
QUICK_LINE_CURRENCIES: tuple[tuple[str, str], ...] = (("€", "EUR"), ("$", "USD"), ("£", "GBP"))
```

`roost/tasks/models.py`. Find:

```python
@dataclass(frozen=True)
class Step:
```

Replace with:

```python
STEP_NOT_FOUND_TEXT = "That task has no such step."


@dataclass(frozen=True)
class Step:
```

`roost/tasks/service.py`. Find:

```python
TaskChange = Literal["created", "updated", "completed", "failed", "deleted"]
```

Replace with:

```python
# "commented" (redesign P3): a comment on the task was added, edited or deleted.
TaskChange = Literal["created", "updated", "completed", "failed", "deleted", "commented"]
```

`roost/tasks/service.py`. Find:

```python
    async def _changed(self, user_id: str, change: TaskChange, task_id: str) -> None:
        await self._events.publish(user_id, {"type": "tasks_changed", "change": change, "task_id": task_id})
```

Replace with:

```python
    async def _changed(self, user_id: str, change: TaskChange, task_id: str) -> None:
        await publish_task_change(self._events, user_id, change, task_id)


async def publish_task_change(events: EventHub, user_id: str, change: TaskChange, task_id: str) -> None:
    """The one ``tasks_changed`` frame (M1 D8): the task, steps and comment services all send it."""
    await events.publish(user_id, {"type": "tasks_changed", "change": change, "task_id": task_id})
```

- [ ] **Step 6: The comment, its store and its service**

Create `roost/tasks/comments.py`:

```python
"""A comment on a task or on one of its steps (redesign P3).

A comment is the user's ("user") or a bot's (its id). Its body is ``enc:v2``
under ``task_comments:body``; a bot's comment written after reading outside
content carries the taint bit, like every record (M1 D3). Only the user's
own comments can be edited or deleted, and only over HTTP."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from roost.constants import MAX_COMMENT_LENGTH

COMMENT_BY_USER = "user"
EMPTY_COMMENT_TEXT = "A comment needs some words."
LONG_COMMENT_TEXT = f"A comment holds at most {MAX_COMMENT_LENGTH} characters."


@dataclass(frozen=True)
class TaskComment:
    id: str
    user_id: str
    task_id: str
    step_id: str | None      # one of the task's steps; None: the whole task
    author: str              # "user", or the bot's id
    body: str
    tainted: bool
    created_at: str
    edited_at: str | None

    @property
    def by_user(self) -> bool:
        return self.author == COMMENT_BY_USER


def comment_body(text: str | None) -> str:
    """The trimmed body, or a ``ValueError`` with a plain sentence."""
    body = (text or "").strip()
    if not body:
        raise ValueError(EMPTY_COMMENT_TEXT)
    if len(body) > MAX_COMMENT_LENGTH:
        raise ValueError(LONG_COMMENT_TEXT)
    return body


def comment_out(comment: TaskComment) -> dict[str, Any]:
    """``CommentOut``, the web's shape."""
    return {
        "id": comment.id, "task_id": comment.task_id, "step_id": comment.step_id, "author": comment.author,
        "body": comment.body, "tainted": comment.tainted, "created_at": comment.created_at,
        "edited_at": comment.edited_at,
    }
```

Create `roost/tasks/comment_store.py`:

```python
"""``CommentStore`` — comments on the user's tasks, encrypted (redesign P3).

- The body is ``enc:v2`` under ``task_comments:body``; ids, the author, the
  step, the taint bit and the times stay plaintext.
- Every query names the user. A comment is only ever read, added or changed
  while its task is live (not deleted) and the user's, checked in the same
  session as the write.
- Deleting is soft. ``edit`` and ``delete`` only touch the user's own comments
  (``author = 'user'``): the service says why, this is the floor under it."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import aiosqlite

from roost.config import Config
from roost.crypto.encryption import decrypt_field, encrypt_field, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session
from roost.tasks.comments import COMMENT_BY_USER, TaskComment

_COLUMNS = ("id", "user_id", "task_id", "step_id", "author", "body", "tainted", "created_at", "edited_at")
_SELECT = ", ".join(f"c.{column}" for column in _COLUMNS)
_FROM_LIVE = ("FROM task_comments c JOIN tasks t ON t.id = c.task_id AND t.user_id = c.user_id "
              "WHERE c.user_id = ? AND c.deleted_at IS NULL AND t.deleted_at IS NULL")
_LIVE_TASK = "SELECT 1 FROM tasks WHERE id = ? AND user_id = ? AND deleted_at IS NULL"
_OWN = "WHERE id = ? AND user_id = ? AND author = ? AND deleted_at IS NULL"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _aad(user_id: str) -> bytes:
    return user_aad(user_id, "task_comments:body")


def _row_to_comment(row: aiosqlite.Row, dek: bytes) -> TaskComment:
    return TaskComment(
        id=row["id"], user_id=row["user_id"], task_id=row["task_id"], step_id=row["step_id"],
        author=row["author"], body=decrypt_field(row["body"], dek, _aad(row["user_id"])) or "",
        tainted=bool(row["tainted"]), created_at=row["created_at"], edited_at=row["edited_at"],
    )


class CommentStore:
    def __init__(self, config: Config) -> None:
        self._config = config

    async def add(self, user_id: str, task_id: str, *, step_id: str | None, author: str, body: str,
                  tainted: bool) -> TaskComment | None:
        """The new comment; ``None`` (nothing written) when the task isn't a live task of the user's."""
        comment = TaskComment(id=str(uuid4()), user_id=user_id, task_id=task_id, step_id=step_id, author=author,
                              body=body, tainted=tainted, created_at=_now_iso(), edited_at=None)
        dek = await get_user_dek(self._config, user_id)
        values = (comment.id, user_id, task_id, step_id, author, encrypt_field(body, dek, _aad(user_id)),
                  int(tainted), comment.created_at, None)
        async with db_session(self._config) as db:
            if await (await db.execute(_LIVE_TASK, (task_id, user_id))).fetchone() is None:
                return None
            await db.execute(f"INSERT INTO task_comments ({', '.join(_COLUMNS)}) "
                             f"VALUES ({','.join('?' * len(_COLUMNS))})", values)
            await db.commit()
        return comment

    async def list(self, user_id: str, task_id: str, *, limit: int) -> tuple[TaskComment, ...]:
        """The task's newest ``limit`` comments, oldest first."""
        newest = await self._select(user_id, f"{_FROM_LIVE} AND c.task_id = ? "
                                              "ORDER BY c.created_at DESC, c.rowid DESC LIMIT ?",
                                    (user_id, task_id, limit))
        return tuple(reversed(newest))

    async def get(self, user_id: str, comment_id: str) -> TaskComment | None:
        found = await self._select(user_id, f"{_FROM_LIVE} AND c.id = ?", (user_id, comment_id))
        return found[0] if found else None

    async def edit(self, user_id: str, comment_id: str, body: str) -> TaskComment | None:
        """The edited comment; ``None`` when it is gone, a bot's, or not the user's."""
        dek = await get_user_dek(self._config, user_id)
        async with db_session(self._config) as db:
            cursor = await db.execute(f"UPDATE task_comments SET body = ?, edited_at = ? {_OWN}",
                                      (encrypt_field(body, dek, _aad(user_id)), _now_iso(), comment_id, user_id,
                                       COMMENT_BY_USER))
            await db.commit()
        return await self.get(user_id, comment_id) if cursor.rowcount else None

    async def delete(self, user_id: str, comment_id: str) -> bool:
        async with db_session(self._config) as db:
            cursor = await db.execute(f"UPDATE task_comments SET deleted_at = ? {_OWN}",
                                      (_now_iso(), comment_id, user_id, COMMENT_BY_USER))
            await db.commit()
        return cursor.rowcount > 0

    async def unlink_step(self, user_id: str, task_id: str, step_id: str) -> int:
        """A deleted step's comments stay on its task (redesign P3). Returns how many moved."""
        async with db_session(self._config) as db:
            cursor = await db.execute(
                "UPDATE task_comments SET step_id = NULL WHERE user_id = ? AND task_id = ? AND step_id = ?",
                (user_id, task_id, step_id))
            await db.commit()
        return cursor.rowcount

    async def _select(self, user_id: str, where: str, params: tuple) -> tuple[TaskComment, ...]:
        async with db_session(self._config) as db:
            rows = await (await db.execute(f"SELECT {_SELECT} {where}", params)).fetchall()
        if not rows:
            return ()
        dek = await get_user_dek(self._config, user_id)
        return tuple(_row_to_comment(row, dek) for row in rows)
```

Create `roost/tasks/comment_service.py`:

```python
"""``CommentService`` — comments on a task or a step, plus their live frame
(redesign P3). The tools and the HTTP routes both go through it, so every
change publishes ``tasks_changed`` with ``change: "commented"``.

- A comment's step must be one of its task's steps (``ValueError``).
- Only the user's own comments can be edited or deleted: a bot's comment
  raises ``CommentNotYours``, which the routes answer 403.
- ``None`` everywhere means "no such task or comment of this user's" (a 404)."""

from __future__ import annotations

from roost.constants import COMMENT_LIST_LIMIT
from roost.events.hub import EventHub
from roost.tasks.comment_store import CommentStore
from roost.tasks.comments import COMMENT_BY_USER, TaskComment, comment_body
from roost.tasks.models import STEP_NOT_FOUND_TEXT
from roost.tasks.service import publish_task_change
from roost.tasks.store import TaskStore

NOT_YOURS_TEXT = "Only your own comments can be changed."


class CommentNotYours(PermissionError):
    """A bot's comment: the user may read it, never edit or delete it."""


class CommentService:
    def __init__(self, comments: CommentStore, tasks: TaskStore, events: EventHub) -> None:
        self._comments = comments
        self._tasks = tasks
        self._events = events

    async def list(self, user_id: str, task_id: str, *, limit: int = COMMENT_LIST_LIMIT,
                   ) -> tuple[TaskComment, ...] | None:
        if await self._tasks.get(user_id, task_id) is None:
            return None
        return await self._comments.list(user_id, task_id, limit=limit)

    async def add(self, user_id: str, task_id: str, body: str, *, step_id: str | None = None,
                  author: str = COMMENT_BY_USER, tainted: bool = False) -> TaskComment | None:
        text = comment_body(body)
        task = await self._tasks.get(user_id, task_id)
        if task is None:
            return None
        if step_id is not None and step_id not in {step.id for step in task.steps}:
            raise ValueError(STEP_NOT_FOUND_TEXT)
        comment = await self._comments.add(user_id, task_id, step_id=step_id, author=author, body=text,
                                           tainted=tainted)
        if comment is not None:
            await publish_task_change(self._events, user_id, "commented", task_id)
        return comment

    async def edit(self, user_id: str, comment_id: str, body: str) -> TaskComment | None:
        text = comment_body(body)
        current = await self._own(user_id, comment_id)
        if current is None:
            return None
        edited = await self._comments.edit(user_id, comment_id, text)
        if edited is not None:
            await publish_task_change(self._events, user_id, "commented", edited.task_id)
        return edited

    async def delete(self, user_id: str, comment_id: str) -> bool:
        current = await self._own(user_id, comment_id)
        if current is None or not await self._comments.delete(user_id, comment_id):
            return False
        await publish_task_change(self._events, user_id, "commented", current.task_id)
        return True

    async def _own(self, user_id: str, comment_id: str) -> TaskComment | None:
        current = await self._comments.get(user_id, comment_id)
        if current is not None and not current.by_user:
            raise CommentNotYours(NOT_YOURS_TEXT)
        return current
```

- [ ] **Step 7: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && ROOST_DATA_DIR=$(mktemp -d) ROOST_DESKS_DIR=$(mktemp -d) uv run pytest tests/test_migrations_v13.py tests/test_task_comments.py tests/test_migrations_v12.py tests/test_migrations.py tests/test_task_store.py tests/test_tasks_api.py -q`
Expected: PASS (`test_migrations_v13.py` 4 passed, `test_task_comments.py` 10 passed).

- [ ] **Step 8: Commit**

Run:

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && \
git add tests/fixtures/schema_v13.sql roost/db/migrations.py roost/constants.py roost/tasks/models.py \
  roost/tasks/service.py roost/tasks/comments.py roost/tasks/comment_store.py roost/tasks/comment_service.py \
  tests/test_migrations_v13.py tests/test_task_comments.py && \
git commit -m "feat: comments on a task or a step, encrypted, in schema v14"
```

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git status --short`
Expected: none of the files above is listed.

---
### Task 4: Steps, one change at a time, and a deleted step's money and comments stay on its task

Design P3 "Subtasks", Design meets code 3, 4 and 6, Review Focus 1 and 2.
- **Pure changes** (`roost/tasks/steps.py`): one function per change from the steps to the new steps. A new step gets a fresh id (`s-` and 12 hex digits); a rename, a tick or a move keeps it, so what is filed under a step stays with it. A tick is stamped now; an untick drops the stamp and the cascade mark. A move clamps a place past either end. An unknown id is `StepNotFound`; a refused title or a 51st step is a `ValueError` with a plain sentence.
- **One write per change** (`TaskStore.edit_steps`): read the task, apply the change to its current steps, write `steps` (and `tainted`, `updated_at`) only if `updated_at` is still what was read; otherwise read again and apply the change again, up to `STEP_WRITE_ATTEMPTS`, then `StepsBusy` ("Try again."). `_write` learns `guard_params` for the `?` in its guard.
- **`StepService`** (`roost/tasks/step_service.py`): add (a tainted run's step marks its task), rename, tick, move and delete, each publishing `tasks_changed`. Deleting clears `step_id` on the step's expenses (`ExpenseStore.unlink_step`, each publishing `money_changed`) and comments (`CommentStore.unlink_step`).

**Files:**
- Create: `roost/tasks/step_service.py`
- Modify: `roost/tasks/steps.py`, `roost/tasks/store.py`, `roost/money/expense_store.py`
- Test: `tests/test_task_steps.py` (new); `tests/test_task_store.py`, `tests/test_money_store.py`, `tests/test_task_steps_recurrence.py` stay green unchanged

**Interfaces:**
- Consumes: Task 3's `STEP_NOT_FOUND_TEXT`, `MAX_STEP_TITLE_LENGTH`, `STEP_WRITE_ATTEMPTS`, `CommentStore.unlink_step`, `publish_task_change`; `MAX_TASK_STEPS`; `numbers.task_money` and `ExpenseStore.for_tasks` (tests).
- Produces: `StepNotFound`, `step_title`, `with_step_added`, `with_step_renamed`, `with_step_done`, `with_step_moved`, `without_step`, `STEP_TITLE_TEXT`, `LONG_STEP_TEXT`, `TOO_MANY_STEPS_TEXT`; `TaskStore.edit_steps`, `StepsBusy`, `STEPS_BUSY_TEXT`; `ExpenseStore.unlink_step`; `StepService`, `StepRemoval`. Tasks 5 and 6 use the service; the routes answer 404 / 409 / 422 from these errors.

- [ ] **Step 1: Path guard**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && test -f roost/tasks/comment_store.py && test ! -e roost/tasks/step_service.py && grep -c "def edit_steps" roost/tasks/store.py`
Expected: `0`. Otherwise stop: Task 3 comes first, or this task already ran.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_task_steps.py`:

```python
"""A task's checklist, one change at a time (redesign P3): stable ids, compare-and-set writes, and a
deleted step's money and comments stay on its task."""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from roost.config import load_config
from roost.constants import MAX_TASK_STEPS, STEP_WRITE_ATTEMPTS
from roost.db.connection import get_db_path, init_db
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.money.expense_store import ExpenseStore
from roost.money.models import ExpenseDraft, ProjectDraft
from roost.money.months import today_madrid
from roost.money.project_store import ProjectStore
from roost.projects.numbers import task_money
from roost.tasks.comment_store import CommentStore
from roost.tasks.models import Step, TaskDraft
from roost.tasks.step_service import StepService
from roost.tasks.steps import (
    STEP_TITLE_TEXT, TOO_MANY_STEPS_TEXT, StepNotFound, with_step_added, with_step_done, with_step_moved,
    with_step_renamed, without_step,
)
from roost.tasks.store import STEPS_BUSY_TEXT, StepsBusy, TaskStore

A, B, C = (Step(id=f"s-{name}", title=name, done=False) for name in ("a", "b", "c"))


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


def _service(cfg, store: TaskStore | None = None) -> StepService:
    return StepService(store or TaskStore(cfg), ExpenseStore(cfg), CommentStore(cfg), EventHub(cfg))


async def _task(cfg, user_id: str, steps: tuple[str, ...] = ("Buy a washer", "Fit it")):
    return await TaskStore(cfg).create(user_id, TaskDraft(title="Fix the sink", steps=steps),
                                       created_by_bot=None, tainted=False)


def _frames(cfg) -> list[str]:
    con = sqlite3.connect(get_db_path(cfg))
    try:
        return [row[0] for row in con.execute("SELECT kind FROM events ORDER BY seq")]
    finally:
        con.close()


def test_adding_gives_a_fresh_id_and_keeps_the_others():
    added = with_step_added((A, B), "  Call the plumber  ")
    assert [step.title for step in added] == ["a", "b", "Call the plumber"]
    assert added[:2] == (A, B) and added[2].id not in {A.id, B.id} and added[2].done is False
    with pytest.raises(ValueError, match=STEP_TITLE_TEXT):
        with_step_added((A,), "   ")
    full = tuple(Step(id=f"s-{n}", title=str(n), done=False) for n in range(MAX_TASK_STEPS))
    with pytest.raises(ValueError, match=TOO_MANY_STEPS_TEXT):
        with_step_added(full, "one more")


def test_rename_tick_untick_keep_the_id():
    renamed = with_step_renamed((A, B), "s-b", "Fit the washer")
    assert (renamed[1].id, renamed[1].title) == ("s-b", "Fit the washer")
    ticked = with_step_done(renamed, "s-a", True)
    assert ticked[0].done is True and ticked[0].completed_at is not None
    unticked = with_step_done(ticked, "s-a", False)
    assert (unticked[0].done, unticked[0].completed_at, unticked[0].id) == (False, None, "s-a")
    assert with_step_done((A,), "s-a", False) == (A,)


@pytest.mark.parametrize(("step_id", "position", "order"), [
    ("s-c", 0, ["c", "a", "b"]),
    ("s-a", 2, ["b", "c", "a"]),
    ("s-a", 99, ["b", "c", "a"]),
    ("s-c", -5, ["c", "a", "b"]),
    ("s-b", 1, ["a", "b", "c"]),
])
def test_moving_puts_the_step_at_its_place_and_clamps_past_either_end(step_id, position, order):
    assert [step.title for step in with_step_moved((A, B, C), step_id, position)] == order


@pytest.mark.parametrize("change", [
    lambda steps: with_step_renamed(steps, "s-x", "y"), lambda steps: with_step_done(steps, "s-x", True),
    lambda steps: with_step_moved(steps, "s-x", 0), lambda steps: without_step(steps, "s-x"),
])
def test_an_unknown_step_is_not_found(change):
    with pytest.raises(StepNotFound):
        change((A, B))


async def test_each_change_is_stored_encrypted_and_published(cfg, user_id):
    task = await _task(cfg, user_id)
    service = _service(cfg)
    added = await service.add(user_id, task.id, "Test for leaks")
    new_id = added.steps[-1].id
    await service.set_done(user_id, task.id, new_id, True)
    await service.move(user_id, task.id, new_id, 0)
    await service.rename(user_id, task.id, new_id, "Test for leaks twice")
    stored = await TaskStore(cfg).get(user_id, task.id)
    assert [(step.title, step.done) for step in stored.steps] == [
        ("Test for leaks twice", True), ("Buy a washer", False), ("Fit it", False)]
    assert stored.steps[0].id == new_id
    assert _frames(cfg)[-4:] == ["tasks_changed"] * 4


async def test_two_step_changes_at_once_both_land(cfg, user_id):
    """Review Focus 1: a bot ticks one step while the user renames another; neither change is lost."""
    task = await _task(cfg, user_id)
    first, second = task.steps
    racer = _service(cfg)

    class RacingStore(TaskStore):
        raced = False

        async def get(self, user_id, task_id):
            found = await super().get(user_id, task_id)
            if not RacingStore.raced:
                RacingStore.raced = True
                await racer.set_done(user_id, task_id, second.id, True)    # lands between this read and its write
            return found

    renamed = await _service(cfg, RacingStore(cfg)).rename(user_id, task.id, first.id, "Buy two washers")
    assert [(step.title, step.done) for step in renamed.steps] == [("Buy two washers", False), ("Fit it", True)]
    stored = await TaskStore(cfg).get(user_id, task.id)
    assert stored.steps == renamed.steps


async def test_a_change_that_keeps_losing_the_race_says_try_again(cfg, user_id):
    task = await _task(cfg, user_id)
    racer = TaskStore(cfg)
    calls = []

    class AlwaysRaced(TaskStore):
        async def get(self, user_id, task_id):
            found = await super().get(user_id, task_id)
            calls.append(1)
            await racer.edit_steps(user_id, task_id, lambda steps: steps)    # bumps updated_at every time
            return found

    with pytest.raises(StepsBusy, match=STEPS_BUSY_TEXT):
        await _service(cfg, AlwaysRaced(cfg)).rename(user_id, task.id, task.steps[0].id, "x")
    assert len(calls) == STEP_WRITE_ATTEMPTS


async def test_a_step_added_by_a_tainted_run_marks_the_task(cfg, user_id):
    task = await _task(cfg, user_id)
    added = await _service(cfg).add(user_id, task.id, "Order the gadget", tainted=True)
    assert added.tainted is True
    assert (await TaskStore(cfg).get(user_id, task.id)).tainted is True


async def test_another_users_or_a_deleted_task_is_none(cfg, user_id):
    task = await _task(cfg, user_id)
    other = (await register_user(cfg, "bob", "pw-123456")).id
    service = _service(cfg)
    assert await service.add(other, task.id, "Sneaky") is None
    assert await service.delete(other, task.id, task.steps[0].id) is None
    await TaskStore(cfg).delete(user_id, task.id)
    assert await service.set_done(user_id, task.id, task.steps[0].id, True) is None


async def test_deleting_a_step_keeps_its_money_and_comments_on_the_task(cfg, user_id):
    """Review Focus 2: the expense and the comment filed under the step stay on the task, and the
    task's spent is the same before and after."""
    project = await ProjectStore(cfg).create(user_id, ProjectDraft(name="Home"), created_by_bot=None, tainted=False)
    task = await TaskStore(cfg).create(user_id, TaskDraft(title="Fix the sink", steps=("Buy a washer",),
                                                          project_id=project.id, allocated_budget=Decimal("50")),
                                       created_by_bot=None, tainted=False)
    step = task.steps[0]
    expenses = ExpenseStore(cfg)
    spent = await expenses.add(user_id, ExpenseDraft(project.id, Decimal("12.50"), spent_at=today_madrid(),
                                                     task_id=task.id, step_id=step.id),
                               created_by_bot=None, tainted=False)
    await CommentStore(cfg).add(user_id, task.id, step_id=step.id, author="user", body="15 mm", tainted=False)
    before = task_money(task, await expenses.for_tasks(user_id, [task.id]), project.currency)

    removal = await _service(cfg).delete(user_id, task.id, step.id)

    assert removal.task.steps == () and removal.moved_expenses == (spent.id,) and removal.moved_comments == 1
    [moved] = await expenses.for_tasks(user_id, [task.id])
    assert (moved.task_id, moved.step_id) == (task.id, None)
    [comment] = await CommentStore(cfg).list(user_id, task.id, limit=10)
    assert comment.step_id is None
    after = task_money(removal.task, (moved,), project.currency)
    assert after == before
    assert _frames(cfg)[-2:] == ["tasks_changed", "money_changed"]
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && ROOST_DATA_DIR=$(mktemp -d) ROOST_DESKS_DIR=$(mktemp -d) uv run pytest tests/test_task_steps.py -q`
Expected: FAIL at collection: `ImportError: cannot import name 'STEP_TITLE_TEXT' from 'roost.tasks.steps'` (and no `roost.tasks.step_service`).

- [ ] **Step 4: The pure changes**

`roost/tasks/steps.py`. Find:

```python
from datetime import datetime, timezone
from typing import Any, Sequence
```

Replace with:

```python
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Sequence
```

`roost/tasks/steps.py`. Find:

```python
from roost.tasks.models import Step
```

Replace with:

```python
from roost.constants import MAX_STEP_TITLE_LENGTH, MAX_TASK_STEPS
from roost.tasks.models import STEP_NOT_FOUND_TEXT, Step
```

Append to the end of `roost/tasks/steps.py`:

```python


# ---------------------------------------------------------------------------
# Roost (redesign P3): one change to a checklist, as a pure function from the
# steps to the new steps. Ids are stable: a new step gets a fresh one, and a
# rename, a tick or a move keeps it, so an expense or a comment filed under a
# step stays with it. Each raises ``StepNotFound`` for an id the task doesn't
# have, or ``ValueError`` with a plain sentence for a change it refuses.
# ---------------------------------------------------------------------------

STEP_TITLE_TEXT = "A step needs a title."
LONG_STEP_TEXT = f"A step's title holds at most {MAX_STEP_TITLE_LENGTH} characters."
TOO_MANY_STEPS_TEXT = f"A task holds at most {MAX_TASK_STEPS} steps."


class StepNotFound(LookupError):
    """The task has no step with that id (a 404 over HTTP)."""


def step_title(text: str | None) -> str:
    title = (text or "").strip()
    if not title:
        raise ValueError(STEP_TITLE_TEXT)
    if len(title) > MAX_STEP_TITLE_LENGTH:
        raise ValueError(LONG_STEP_TEXT)
    return title


def _index(steps: Sequence[Step], step_id: str) -> int:
    for index, step in enumerate(steps):
        if step.id == step_id:
            return index
    raise StepNotFound(STEP_NOT_FOUND_TEXT)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def with_step_added(steps: Sequence[Step], title: str) -> tuple[Step, ...]:
    """``steps`` plus a new open step at the end."""
    if len(steps) >= MAX_TASK_STEPS:
        raise ValueError(TOO_MANY_STEPS_TEXT)
    added = Step(id=f"s-{uuid4().hex[:12]}", title=step_title(title), done=False, created_at=_now_iso())
    return (*steps, added)


def with_step_renamed(steps: Sequence[Step], step_id: str, title: str) -> tuple[Step, ...]:
    index = _index(steps, step_id)
    renamed = replace(steps[index], title=step_title(title))
    return (*steps[:index], renamed, *steps[index + 1:])


def with_step_done(steps: Sequence[Step], step_id: str, done: bool) -> tuple[Step, ...]:
    """Tick or untick. A tick is stamped now; an untick drops the stamp and the cascade mark."""
    index = _index(steps, step_id)
    current = steps[index]
    if current.done == done:
        return tuple(steps)
    changed = replace(current, done=done, completed_at=_now_iso() if done else None, cascaded=False)
    return (*steps[:index], changed, *steps[index + 1:])


def with_step_moved(steps: Sequence[Step], step_id: str, position: int) -> tuple[Step, ...]:
    """The step at ``position`` (0 is first), the others in their order. A position past either
    end puts it at that end."""
    index = _index(steps, step_id)
    rest = (*steps[:index], *steps[index + 1:])
    target = min(max(position, 0), len(rest))
    return (*rest[:target], steps[index], *rest[target:])


def without_step(steps: Sequence[Step], step_id: str) -> tuple[Step, ...]:
    index = _index(steps, step_id)
    return (*steps[:index], *steps[index + 1:])
```

- [ ] **Step 5: One compare-and-set write per change**

`roost/tasks/store.py`. Find:

```python
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping
```

Replace with:

```python
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Mapping
```

`roost/tasks/store.py`. Find:

```python
from roost.config import Config
from roost.crypto.encryption
```

Replace with:

```python
from roost.config import Config
from roost.constants import STEP_WRITE_ATTEMPTS
from roost.crypto.encryption
```

`roost/tasks/store.py`. Find:

```python
from roost.tasks.models import Task, TaskDraft, TaskFilter, TaskPatch
```

Replace with:

```python
from roost.tasks.models import Step, Task, TaskDraft, TaskFilter, TaskPatch
```

`roost/tasks/store.py`. Find:

```python
SLICE_NEEDS_PROJECT = "A budget slice needs a project."
```

Replace with:

```python
SLICE_NEEDS_PROJECT = "A budget slice needs a project."
STEPS_BUSY_TEXT = "This task's steps changed while yours was being saved. Try again."
```

`roost/tasks/store.py`. Find:

```python
_CLOSED_SQL = (
```

Replace with:

```python
_SAME_VERSION_SQL = " AND updated_at = ?"
_STEP_COLUMNS = ("steps", "tainted", "updated_at")
_CLOSED_SQL = (
```

`roost/tasks/store.py`. Find:

```python
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
```

Replace with:

```python
class StepsBusy(RuntimeError):
    """A steps change lost the compare-and-set ``STEP_WRITE_ATTEMPTS`` times (a 409 over HTTP)."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
```

`roost/tasks/store.py`. Find:

```python
    async def keep(self, user_id: str, task_id: str) -> Task | None:
```

Replace with:

```python
    async def edit_steps(self, user_id: str, task_id: str, edit: Callable[[tuple[Step, ...]], tuple[Step, ...]],
                         *, taint: bool = False) -> Task | None:
        """Apply one checklist change (redesign P3) to the task's current steps and write them, a
        compare-and-set on ``updated_at``: when anything changed the task in between (a bot ticks a
        step while the user renames another), the change is applied again to the new steps, so
        neither is lost. ``taint`` marks the task "from web content" (a step a tainted run added).
        ``None``: no live task of the user's. ``edit``'s own errors propagate; ``StepsBusy`` after
        ``STEP_WRITE_ATTEMPTS`` lost races."""
        for _ in range(STEP_WRITE_ATTEMPTS):
            current = await self.get(user_id, task_id)
            if current is None:
                return None
            updated = replace(current, steps=edit(current.steps), tainted=current.tainted or taint,
                              updated_at=_now_iso())
            written = await self._write(updated, _STEP_COLUMNS, guard_sql=_SAME_VERSION_SQL,
                                        guard_params=(current.updated_at,))
            if written is not None:
                return written
        raise StepsBusy(STEPS_BUSY_TEXT)

    async def keep(self, user_id: str, task_id: str) -> Task | None:
```

`roost/tasks/store.py`. Find:

```python
    async def _write(self, task: Task, columns: tuple[str, ...], *, guard_sql: str = "") -> Task | None:
        """Update exactly ``columns``. ``guard_sql`` is a literal, caller-fixed
        SQL fragment (never built from user input) that makes the UPDATE a
        compare-and-set against the row the caller already checked, so a
        racing write that no longer matches touches nothing. A new
        ``project_id`` is checked in the same session as the UPDATE."""
```

Replace with:

```python
    async def _write(self, task: Task, columns: tuple[str, ...], *, guard_sql: str = "",
                     guard_params: tuple = ()) -> Task | None:
        """Update exactly ``columns``. ``guard_sql`` is a literal, caller-fixed
        SQL fragment (never built from user input) that makes the UPDATE a
        compare-and-set against the row the caller already checked, so a
        racing write that no longer matches touches nothing; ``guard_params``
        fill its ``?`` marks. A new ``project_id`` is checked in the same
        session as the UPDATE."""
```

`roost/tasks/store.py`. Find:

```python
                (*(_encode(task, column, dek) for column in columns), task.id, task.user_id),
```

Replace with:

```python
                (*(_encode(task, column, dek) for column in columns), task.id, task.user_id, *guard_params),
```

- [ ] **Step 6: A deleted step's expenses stay on the task**

`roost/money/expense_store.py`. Find:

```python
    async def made_by(self, user_id: str, bot_id: str, limit: int) -> tuple[Expense, ...]:
```

Replace with:

```python
    async def unlink_step(self, user_id: str, task_id: str, step_id: str) -> tuple[str, ...]:
        """A deleted step's expenses stay on its task (redesign P3, LazyClaw's rule): their
        ``step_id`` is cleared. Deleted expenses too, so none is left naming a missing step.
        Returns the ids of the expenses that moved."""
        where = "WHERE user_id = ? AND task_id = ? AND step_id = ?"
        params = (user_id, task_id, step_id)
        async with db_session(self._config) as db:
            rows = await (await db.execute(f"SELECT id FROM money_expenses {where}", params)).fetchall()
            await db.execute(f"UPDATE money_expenses SET step_id = NULL, updated_at = ? {where}", (_now_iso(), *params))
            await db.commit()
        return tuple(row[0] for row in rows)

    async def made_by(self, user_id: str, bot_id: str, limit: int) -> tuple[Expense, ...]:
```

- [ ] **Step 7: The service**

Create `roost/tasks/step_service.py`:

```python
"""``StepService`` — a task's checklist, one change at a time (redesign P3).

The tools and the HTTP routes both go through it. Every change is applied to
the task's current steps in a compare-and-set (``TaskStore.edit_steps``) and
publishes ``tasks_changed``. Deleting a step keeps what was filed under it on
the task: its expenses lose their ``step_id`` (each publishes
``money_changed``) and so do its comments.

``None`` means no live task of the user's (a 404). ``StepNotFound``: the task
has no such step (a 404). ``ValueError``: a title or a change it refuses (a
422). ``StepsBusy``: too many changes at once (a 409)."""

from __future__ import annotations

from dataclasses import dataclass

from roost.events.hub import EventHub
from roost.money.expense_store import ExpenseStore
from roost.tasks.comment_store import CommentStore
from roost.tasks.models import Task
from roost.tasks.service import publish_task_change
from roost.tasks.steps import (
    with_step_added, with_step_done, with_step_moved, with_step_renamed, without_step,
)
from roost.tasks.store import TaskStore


@dataclass(frozen=True)
class StepRemoval:
    task: Task
    moved_expenses: tuple[str, ...]   # the expenses now filed under the whole task
    moved_comments: int


class StepService:
    def __init__(self, tasks: TaskStore, expenses: ExpenseStore, comments: CommentStore, events: EventHub) -> None:
        self._tasks = tasks
        self._expenses = expenses
        self._comments = comments
        self._events = events

    async def add(self, user_id: str, task_id: str, title: str, *, tainted: bool = False) -> Task | None:
        """A new open step at the end. ``tainted``: a run that read outside content added it, so the
        task now holds web text and is marked so (a step has no taint bit of its own)."""
        task = await self._tasks.edit_steps(user_id, task_id, lambda steps: with_step_added(steps, title),
                                            taint=tainted)
        return await self._changed(user_id, task)

    async def rename(self, user_id: str, task_id: str, step_id: str, title: str) -> Task | None:
        task = await self._tasks.edit_steps(user_id, task_id, lambda steps: with_step_renamed(steps, step_id, title))
        return await self._changed(user_id, task)

    async def set_done(self, user_id: str, task_id: str, step_id: str, done: bool) -> Task | None:
        task = await self._tasks.edit_steps(user_id, task_id, lambda steps: with_step_done(steps, step_id, done))
        return await self._changed(user_id, task)

    async def move(self, user_id: str, task_id: str, step_id: str, position: int) -> Task | None:
        task = await self._tasks.edit_steps(user_id, task_id,
                                            lambda steps: with_step_moved(steps, step_id, position))
        return await self._changed(user_id, task)

    async def delete(self, user_id: str, task_id: str, step_id: str) -> StepRemoval | None:
        task = await self._tasks.edit_steps(user_id, task_id, lambda steps: without_step(steps, step_id))
        if task is None:
            return None
        moved = await self._expenses.unlink_step(user_id, task_id, step_id)
        comments = await self._comments.unlink_step(user_id, task_id, step_id)
        await self._changed(user_id, task)
        for expense_id in moved:
            await self._events.publish(user_id, {"type": "money_changed", "change": "expense_updated", "id": expense_id})
        return StepRemoval(task=task, moved_expenses=moved, moved_comments=comments)

    async def _changed(self, user_id: str, task: Task | None) -> Task | None:
        if task is not None:
            await publish_task_change(self._events, user_id, "updated", task.id)
        return task
```

- [ ] **Step 8: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && ROOST_DATA_DIR=$(mktemp -d) ROOST_DESKS_DIR=$(mktemp -d) uv run pytest tests/test_task_steps.py tests/test_task_comments.py tests/test_task_store.py tests/test_money_store.py tests/test_task_steps_recurrence.py -q`
Expected: PASS (`test_task_steps.py` 17 passed).

- [ ] **Step 9: Commit**

Run:

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && \
git add roost/tasks/steps.py roost/tasks/store.py roost/money/expense_store.py roost/tasks/step_service.py \
  tests/test_task_steps.py && \
git commit -m "feat: a task's steps change one at a time, and a deleted step's money and comments stay on the task"
```

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git status --short`
Expected: none of the files above is listed.

---
### Task 5: The bots' step and comment tools

Design P3 "Subtasks" and "Comments" (tools), Design meets code 6 and 7, Review Focus 2 and 4. Every bot gets six tools (S1: every bot gets every tool):
- `add_step` (write_create): a step at the end of a task. From a tainted run it marks the task "from web content".
- `update_step` (write_change): a new title and/or `done`; `delete_step` (write_change): the reply says how many expenses and comments stay on the task; `move_step` (write_change): `position`, 1 is first.
- `add_comment` (write_create): on the task or on one of its steps, by this bot, carrying the run's taint; `list_comments` (read): the newest `COMMENT_TOOL_LIMIT`, oldest first, each with its author ("the user", "you", or "bot <id>"), its step, and `[from web content]` on a web-made one; the result carries the taint of the task and of every comment shown.

A task is named among tasks of **every status** and a step among its task's steps, with the money tools' exact-or-ask rule (`find_task`, `find_step` in `roost/money/expense_links.py`). Each reply lists the task's steps with their ids, so the model can name them next. The new verbs need a past tense on the web ("moving" → "moved"), which `tests/test_tool_lines.py` checks.

**Files:**
- Create: `roost/tasks/step_specs.py`, `roost/tasks/step_tools.py`, `roost/tasks/comment_tools.py`
- Modify: `roost/talk/tool_catalog.py`, `roost/talk/domain_tools.py`, `web/src/lib/toolLines.ts`
- Test: `tests/test_step_comment_tools.py` (new); `tests/test_every_bot_tools.py`, `tests/test_tool_lines.py`, `tests/test_gate.py` and `tests/test_task_tools.py` stay green unchanged

**Interfaces:**
- Consumes: Task 3's `CommentService`, `TaskComment`, `COMMENT_TOOL_LIMIT`, `MAX_COMMENT_LENGTH`; Task 4's `StepService`, `StepsBusy`, `MAX_STEP_TITLE_LENGTH`; `find_task` / `find_step` (`roost/money/expense_links.py`); `ToolText`, `RecordContext`, `ToolOutcome`, `ToolDef`, `ToolSpec`; `team_helpers` (tests).
- Produces: `STEP_TOOL_DEFS`, `COMMENT_TOOL_DEFS` and the six `*_SPEC`s; `StepTools`, `steps_text`, `GONE_TEXT`, `NOTHING_TO_CHANGE_TEXT`; `CommentTools`; both handlers in `build_domain_tools` and the specs in `CATALOG`.

- [ ] **Step 1: Path guard**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && test -f roost/tasks/step_service.py && test ! -e roost/tasks/step_tools.py && grep -c "STEP_TOOL_DEFS" roost/talk/tool_catalog.py`
Expected: `0`. Otherwise stop.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_step_comment_tools.py`:

```python
"""The step and comment tools (redesign P3): every bot can work a task's checklist and comment on it;
a run that read outside content may add (and marks what it added) but never change."""

from __future__ import annotations

from decimal import Decimal

import pytest

from roost.config import load_config
from roost.db.connection import init_db
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.llm.types import ToolCallRequested, TurnDone
from roost.money.expense_store import ExpenseStore
from roost.money.models import ExpenseDraft, ProjectDraft
from roost.money.months import today_madrid
from roost.money.project_store import ProjectStore
from roost.talk.domain_tools import RecordContext
from roost.talk.gate import TAINTED_CHANGE_TEXT
from roost.tasks.comment_service import CommentService
from roost.tasks.comment_store import CommentStore
from roost.tasks.comment_tools import CommentTools
from roost.tasks.models import TaskDraft
from roost.tasks.service import TaskService
from roost.tasks.step_service import StepService
from roost.tasks.step_tools import NOTHING_TO_CHANGE_TEXT, StepTools
from roost.tasks.store import TaskStore
from team_helpers import make_bot, make_rig, say, send, team_model, wait_idle


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


def _tools(cfg) -> tuple[StepTools, CommentTools]:
    events, store, comments = EventHub(cfg), TaskStore(cfg), CommentStore(cfg)
    tasks = TaskService(store, events)
    return (StepTools(tasks, StepService(store, ExpenseStore(cfg), comments, events)),
            CommentTools(tasks, CommentService(comments, store, events)))


def _ctx(user_id: str, *, tainted: bool = False) -> RecordContext:
    return RecordContext(user_id=user_id, bot_id="bot-1", tainted=tainted)


async def _task(cfg, user_id: str, title: str = "Fix the sink", steps: tuple[str, ...] = ("Buy a washer", "Fit it"),
                **fields):
    return await TaskStore(cfg).create(user_id, TaskDraft(title=title, steps=steps, **fields),
                                       created_by_bot=None, tainted=False)


def _tool(call_id: str, name: str, **arguments):
    return [ToolCallRequested(id=call_id, name=name, arguments=arguments), TurnDone("tool_use")]


async def test_a_bot_adds_ticks_renames_moves_and_deletes_steps(cfg, user_id):
    task = await _task(cfg, user_id)
    steps, _ = _tools(cfg)
    added = await steps.run("add_step", {"task": "Fix the sink", "title": "Test for leaks"}, _ctx(user_id))
    assert added.created is True and "Added step “Test for leaks” to Fix the sink." in added.text
    assert "[ ] Test for leaks (id=s-" in added.text
    ticked = await steps.run("update_step", {"task": task.id, "step": "washer", "done": True}, _ctx(user_id))
    assert "[x] Buy a washer" in ticked.text
    await steps.run("update_step", {"task": "Fix the sink", "step": "Fit it", "title": "Fit the washer"}, _ctx(user_id))
    await steps.run("move_step", {"task": "Fix the sink", "step": "Test for leaks", "position": 1}, _ctx(user_id))
    deleted = await steps.run("delete_step", {"task": "Fix the sink", "step": "Buy a washer"}, _ctx(user_id))
    assert "Deleted step “Buy a washer” from Fix the sink." in deleted.text
    stored = await TaskStore(cfg).get(user_id, task.id)
    assert [(step.title, step.done) for step in stored.steps] == [("Test for leaks", False), ("Fit the washer", False)]


async def test_update_step_with_nothing_to_change_or_an_unknown_step_is_refused(cfg, user_id):
    await _task(cfg, user_id)
    steps, _ = _tools(cfg)
    assert (await steps.run("update_step", {"task": "Fix the sink", "step": "Fit it"}, _ctx(user_id))).text == NOTHING_TO_CHANGE_TEXT
    refused = await steps.run("delete_step", {"task": "Fix the sink", "step": "Paint"}, _ctx(user_id))
    assert refused.text.startswith("Refused: “Fix the sink” has no step “Paint”.")
    assert (await steps.run("move_step", {"task": "Fix the sink", "step": "Fit it"}, _ctx(user_id))).text == (
        "Refused: move_step needs the task, the step and its new place (1 is first).")
    assert (await steps.run("add_step", {"task": "Paint the hall", "title": "x"}, _ctx(user_id))).text == (
        "Refused: no task matches “Paint the hall”.")


async def test_deleting_a_step_says_its_money_stays_on_the_task(cfg, user_id):
    project = await ProjectStore(cfg).create(user_id, ProjectDraft(name="Home"), created_by_bot=None, tainted=False)
    task = await _task(cfg, user_id, project_id=project.id, allocated_budget=Decimal("40"))
    await ExpenseStore(cfg).add(user_id, ExpenseDraft(project.id, Decimal("9"), spent_at=today_madrid(), task_id=task.id,
                                                      step_id=task.steps[0].id), created_by_bot=None, tainted=False)
    steps, _ = _tools(cfg)
    deleted = await steps.run("delete_step", {"task": "Fix the sink", "step": "Buy a washer"}, _ctx(user_id))
    assert "1 expense(s) and 0 comment(s) filed under it stay on the task." in deleted.text


async def test_a_step_added_by_a_tainted_run_marks_the_task_and_the_result(cfg, user_id):
    task = await _task(cfg, user_id)
    steps, _ = _tools(cfg)
    added = await steps.run("add_step", {"task": "Fix the sink", "title": "Order the gadget"}, _ctx(user_id, tainted=True))
    assert added.tainted is True
    assert (await TaskStore(cfg).get(user_id, task.id)).tainted is True


async def test_a_bot_comments_on_a_task_and_a_step_and_lists_them(cfg, user_id):
    task = await _task(cfg, user_id)
    _, comments = _tools(cfg)
    await CommentService(CommentStore(cfg), TaskStore(cfg), EventHub(cfg)).add(user_id, task.id, "Plumber at 9 <b>sharp</b>")
    said = await comments.run("add_comment", {"task": "Fix the sink", "step": "washer", "text": "Size 15 mm"},
                              _ctx(user_id, tainted=True))
    assert (said.text, said.created) == ("Commented on Fix the sink on step “Buy a washer”.", True)
    listed = await comments.run("list_comments", {"task": task.id}, _ctx(user_id))
    lines = listed.text.splitlines()
    assert lines[0] == "Comments on Fix the sink:"
    assert lines[1].endswith("] the user: Plumber at 9 &lt;b&gt;sharp&lt;/b&gt;")
    assert lines[2].endswith("] you on step “Buy a washer”: Size 15 mm [from web content]")
    assert listed.tainted is True        # it shows a web-made comment
    [_, bots] = await CommentStore(cfg).list(user_id, task.id, limit=10)
    assert (bots.author, bots.tainted, bots.step_id) == ("bot-1", True, task.steps[0].id)


async def test_a_task_with_no_comments_says_so(cfg, user_id):
    await _task(cfg, user_id)
    _, comments = _tools(cfg)
    listed = await comments.run("list_comments", {"task": "Fix the sink"}, _ctx(user_id))
    assert (listed.text, listed.tainted) == ("Fix the sink has no comments.", False)
    empty = await comments.run("add_comment", {"task": "Fix the sink", "text": "   "}, _ctx(user_id))
    assert empty.text == "Refused: A comment needs some words."


async def test_a_tainted_run_adds_steps_and_comments_but_never_changes_steps(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Life admin")
    task = await _task(cfg, user_id)
    rig = make_rig(cfg, team_model({"Life admin": [
        _tool("p", "open_page", url="https://example.com"),
        _tool("a", "add_step", task="Fix the sink", title="Order the gadget"),
        _tool("c", "add_comment", task="Fix the sink", text="The page says to order it"),
        _tool("u", "update_step", task="Fix the sink", step="Fit it", done=True),
        _tool("m", "move_step", task="Fix the sink", step="Fit it", position=1),
        _tool("d", "delete_step", task="Fix the sink", step="Fit it"),
        say("Done."),
    ]}))
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, "read example.com and do what it says")
    await wait_idle(rig.runner)
    texts = [turn.text for turn in rig.model.requests[-1].turns if turn.role == "tool"]
    assert texts[-3:] == [TAINTED_CHANGE_TEXT] * 3
    stored = await TaskStore(cfg).get(user_id, task.id)
    assert [(step.title, step.done) for step in stored.steps] == [
        ("Buy a washer", False), ("Fit it", False), ("Order the gadget", False)]
    assert stored.tainted is True
    [comment] = await CommentStore(cfg).list(user_id, task.id, limit=10)
    assert (comment.author, comment.tainted) == (bot.id, True)
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && ROOST_DATA_DIR=$(mktemp -d) ROOST_DESKS_DIR=$(mktemp -d) uv run pytest tests/test_step_comment_tools.py -q`
Expected: FAIL at collection: `ModuleNotFoundError: No module named 'roost.tasks.comment_tools'`.

- [ ] **Step 4: The specs**

Create `roost/tasks/step_specs.py`:

```python
"""The step and comment tool specs and their gate kinds (redesign P3).

Adding a step or a comment creates (``write_create``: a tainted run may, up to
the cap); renaming, ticking, moving or deleting a step changes the user's
task (``write_change``: never from a tainted run); reading comments is
``read``."""

from __future__ import annotations

from roost.constants import MAX_TASK_STEPS
from roost.llm.types import ToolSpec
from roost.talk.tool_def import ToolDef

_TASK = {"type": "string", "description": "The task's id, or its title (or a unique part of it)."}
_STEP = {"type": "string", "description": "The step's id, or its title (or a unique part of it)."}

ADD_STEP_SPEC = ToolSpec(
    name="add_step",
    description="Add a step (a subtask) to the end of one of the user's tasks.",
    input_schema={"type": "object", "properties": {
        "task": _TASK, "title": {"type": "string", "description": "The step, e.g. 'Buy a washer'."},
    }, "required": ["task", "title"]},
)
UPDATE_STEP_SPEC = ToolSpec(
    name="update_step",
    description="Rename a task's step, or tick it (done true) or untick it (done false). Name the step exactly.",
    input_schema={"type": "object", "properties": {
        "task": _TASK, "step": _STEP, "title": {"type": "string", "description": "Its new title."},
        "done": {"type": "boolean"},
    }, "required": ["task", "step"]},
)
DELETE_STEP_SPEC = ToolSpec(
    name="delete_step",
    description="Delete a task's step. Money and comments filed under it stay on the task. Name the step exactly.",
    input_schema={"type": "object", "properties": {"task": _TASK, "step": _STEP}, "required": ["task", "step"]},
)
MOVE_STEP_SPEC = ToolSpec(
    name="move_step",
    description="Move a task's step to another place in its list; 1 is the first place.",
    input_schema={"type": "object", "properties": {
        "task": _TASK, "step": _STEP,
        "position": {"type": "integer", "minimum": 1, "maximum": MAX_TASK_STEPS, "description": "Its new place."},
    }, "required": ["task", "step", "position"]},
)
ADD_COMMENT_SPEC = ToolSpec(
    name="add_comment",
    description=("Add a comment to one of the user's tasks, or to one of its steps: what you did, found or need. "
                 "The user reads it in the task."),
    input_schema={"type": "object", "properties": {
        "task": _TASK, "step": {**_STEP, "description": "Optional: the step it is about."},
        "text": {"type": "string", "description": "The comment."},
    }, "required": ["task", "text"]},
)
LIST_COMMENTS_SPEC = ToolSpec(
    name="list_comments",
    description="Read a task's comments, oldest first (the newest ones when there are many).",
    input_schema={"type": "object", "properties": {"task": _TASK}, "required": ["task"]},
)

STEP_TOOL_DEFS: tuple[ToolDef, ...] = (
    ToolDef(ADD_STEP_SPEC, "write_create"),
    ToolDef(UPDATE_STEP_SPEC, "write_change"),
    ToolDef(DELETE_STEP_SPEC, "write_change"),
    ToolDef(MOVE_STEP_SPEC, "write_change"),
)
COMMENT_TOOL_DEFS: tuple[ToolDef, ...] = (
    ToolDef(ADD_COMMENT_SPEC, "write_create"),
    ToolDef(LIST_COMMENTS_SPEC, "read"),
)
```

- [ ] **Step 5: The step tools and the comment tools**

Create `roost/tasks/step_tools.py`:

```python
"""The step tools over the user's tasks (redesign P3): ``add_step``,
``update_step``, ``delete_step`` and ``move_step``.

A task is named the way the money tools name one (``roost.money.expense_links``):
its id, its exact title or a unique part of one, among tasks of every status;
a near miss or a title several tasks share is a refusal that lists them. A
step is named the same way among its task's steps. Results are escaped, and
carry the task's taint: they echo its title and its steps."""

from __future__ import annotations

import html
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationError

from roost.constants import MAX_STEP_TITLE_LENGTH, MAX_TASK_STEPS, MAX_TASK_TITLE_LENGTH
from roost.money.expense_links import find_step, find_task
from roost.records.tool_text import ToolText
from roost.talk.domain_tools import RecordContext
from roost.talk.outcome import ToolOutcome
from roost.tasks.models import Step, Task
from roost.tasks.service import TaskService
from roost.tasks.step_service import StepService
from roost.tasks.store import StepsBusy

_ACTIVITY = {
    "add_step": "adding a step", "update_step": "changing a step", "delete_step": "deleting a step",
    "move_step": "moving a step",
}
_NEEDS = {
    "add_step": "the task (its id or title) and the step's title",
    "update_step": "the task, the step, and a new title or done (true or false)",
    "delete_step": "the task and the step (each by id or title)",
    "move_step": "the task, the step and its new place (1 is first)",
}
GONE_TEXT = "Refused: that task is gone."
NOTHING_TO_CHANGE_TEXT = "Refused: update_step needs a new title or done (true or false)."


def _escape(text: str) -> str:
    return html.escape(text, quote=True)


def steps_text(task: Task) -> str:
    """The task's steps in order, with their ids, for the model to name them next."""
    if not task.steps:
        return "It has no steps."
    lines = "; ".join(f"{'[x]' if step.done else '[ ]'} {_escape(step.title)} (id={step.id})" for step in task.steps)
    return f"Its steps: {lines}."


class AddStepArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    task: ToolText = Field(min_length=1, max_length=MAX_TASK_TITLE_LENGTH)
    title: ToolText = Field(min_length=1, max_length=MAX_STEP_TITLE_LENGTH)


class StepRefArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    task: ToolText = Field(min_length=1, max_length=MAX_TASK_TITLE_LENGTH)
    step: ToolText = Field(min_length=1, max_length=MAX_STEP_TITLE_LENGTH)


class UpdateStepArgs(StepRefArgs):
    title: ToolText | None = Field(default=None, max_length=MAX_STEP_TITLE_LENGTH)
    done: StrictBool | None = None


class MoveStepArgs(StepRefArgs):
    position: int = Field(ge=1, le=MAX_TASK_STEPS)


class StepTools:
    names = frozenset(_ACTIVITY)

    def __init__(self, tasks: TaskService, steps: StepService) -> None:
        self._tasks = tasks
        self._steps = steps

    def activity(self, name: str) -> str:
        return _ACTIVITY[name]

    async def run(self, name: str, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        handlers = {"add_step": self._add, "update_step": self._update, "delete_step": self._delete,
                    "move_step": self._move}
        try:
            return await handlers[name](arguments, ctx)
        except ValidationError:
            return ToolOutcome(f"Refused: {name} needs {_NEEDS[name]}.")
        except StepsBusy as exc:
            return ToolOutcome(f"Refused: {_escape(str(exc))}")
        except (ValueError, LookupError) as exc:    # a title it refuses; a step gone since it was named
            return ToolOutcome(f"Refused: {_escape(str(exc))}")

    async def _add(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = AddStepArgs.model_validate(arguments)
        task = await find_task(self._tasks, ctx.user_id, args.task)
        if isinstance(task, ToolOutcome):
            return task
        updated = await self._steps.add(ctx.user_id, task.id, args.title, tainted=ctx.tainted)
        if updated is None:
            return ToolOutcome(GONE_TEXT, tainted=task.tainted)
        text = f"Added step “{_escape(updated.steps[-1].title)}” to {_escape(task.title)}. {steps_text(updated)}"
        return ToolOutcome(text, created=True, tainted=updated.tainted)

    async def _update(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = UpdateStepArgs.model_validate(arguments)
        if args.title is None and args.done is None:
            return ToolOutcome(NOTHING_TO_CHANGE_TEXT)
        found = await self._step_of(ctx.user_id, args)
        if isinstance(found, ToolOutcome):
            return found
        task, step = found
        updated: Task | None = task
        if args.title is not None:
            updated = await self._steps.rename(ctx.user_id, task.id, step.id, args.title)
        if updated is not None and args.done is not None:
            updated = await self._steps.set_done(ctx.user_id, task.id, step.id, args.done)
        if updated is None:
            return ToolOutcome(GONE_TEXT, tainted=task.tainted)
        return ToolOutcome(f"Updated a step of {_escape(task.title)}. {steps_text(updated)}", tainted=updated.tainted)

    async def _delete(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        found = await self._step_of(ctx.user_id, StepRefArgs.model_validate(arguments))
        if isinstance(found, ToolOutcome):
            return found
        task, step = found
        removal = await self._steps.delete(ctx.user_id, task.id, step.id)
        if removal is None:
            return ToolOutcome(GONE_TEXT, tainted=task.tainted)
        kept = (f" {len(removal.moved_expenses)} expense(s) and {removal.moved_comments} comment(s) filed under it "
                "stay on the task." if removal.moved_expenses or removal.moved_comments else "")
        text = f"Deleted step “{_escape(step.title)}” from {_escape(task.title)}.{kept} {steps_text(removal.task)}"
        return ToolOutcome(text, tainted=task.tainted)

    async def _move(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = MoveStepArgs.model_validate(arguments)
        found = await self._step_of(ctx.user_id, args)
        if isinstance(found, ToolOutcome):
            return found
        task, step = found
        updated = await self._steps.move(ctx.user_id, task.id, step.id, args.position - 1)
        if updated is None:
            return ToolOutcome(GONE_TEXT, tainted=task.tainted)
        return ToolOutcome(f"Moved step “{_escape(step.title)}”. {steps_text(updated)}", tainted=updated.tainted)

    async def _step_of(self, user_id: str, args: StepRefArgs) -> tuple[Task, Step] | ToolOutcome:
        task = await find_task(self._tasks, user_id, args.task)
        if isinstance(task, ToolOutcome):
            return task
        step = find_step(task, args.step)
        return step if isinstance(step, ToolOutcome) else (task, step)
```

Create `roost/tasks/comment_tools.py`:

```python
"""The comment tools (redesign P3): ``add_comment`` and ``list_comments``.

A bot's comment records the bot as its author and the run's taint, like every
record a bot writes (M1 D3). Listing shows each comment's author ("the user",
"you" for this bot, or another bot by id) and marks a web-made one; the
result carries the taint of the task and of every comment it shows."""

from __future__ import annotations

import html
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from roost.constants import COMMENT_TOOL_LIMIT, MAX_COMMENT_LENGTH, MAX_STEP_TITLE_LENGTH, MAX_TASK_TITLE_LENGTH
from roost.money.expense_links import find_step, find_task
from roost.records.tool_text import ToolText
from roost.talk.domain_tools import RecordContext
from roost.talk.instructions import MADRID_TZ
from roost.talk.outcome import ToolOutcome
from roost.tasks.comment_service import CommentService
from roost.tasks.comments import TaskComment
from roost.tasks.models import Task
from roost.tasks.service import TaskService

_ACTIVITY = {"add_comment": "adding a comment", "list_comments": "reading comments"}
_NEEDS = {
    "add_comment": "the task (its id or title), the text, and optionally the step",
    "list_comments": "the task (its id or title)",
}
GONE_TEXT = "Refused: that task is gone."
_WEB_MARK = " [from web content]"


def _escape(text: str) -> str:
    return html.escape(text, quote=True)


class AddCommentArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    task: ToolText = Field(min_length=1, max_length=MAX_TASK_TITLE_LENGTH)
    step: ToolText | None = Field(default=None, max_length=MAX_STEP_TITLE_LENGTH)
    text: ToolText = Field(min_length=1, max_length=MAX_COMMENT_LENGTH)


class ListCommentsArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    task: ToolText = Field(min_length=1, max_length=MAX_TASK_TITLE_LENGTH)


def _when(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).astimezone(MADRID_TZ).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return iso


def _comment_line(comment: TaskComment, task: Task, bot_id: str) -> str:
    author = "the user" if comment.by_user else "you" if comment.author == bot_id else f"bot {comment.author}"
    steps = {step.id: step.title for step in task.steps}
    about = f" on step “{_escape(steps[comment.step_id])}”" if comment.step_id in steps else ""
    mark = _WEB_MARK if comment.tainted else ""
    return f"[{_when(comment.created_at)}] {author}{about}: {_escape(comment.body)}{mark}"


class CommentTools:
    names = frozenset(_ACTIVITY)

    def __init__(self, tasks: TaskService, comments: CommentService) -> None:
        self._tasks = tasks
        self._comments = comments

    def activity(self, name: str) -> str:
        return _ACTIVITY[name]

    async def run(self, name: str, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        handlers = {"add_comment": self._add, "list_comments": self._list}
        try:
            return await handlers[name](arguments, ctx)
        except ValidationError:
            return ToolOutcome(f"Refused: {name} needs {_NEEDS[name]}.")
        except ValueError as exc:
            return ToolOutcome(f"Refused: {_escape(str(exc))}")

    async def _add(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = AddCommentArgs.model_validate(arguments)
        task = await find_task(self._tasks, ctx.user_id, args.task)
        if isinstance(task, ToolOutcome):
            return task
        step = None if args.step is None or not args.step.strip() else find_step(task, args.step)
        if isinstance(step, ToolOutcome):
            return step
        comment = await self._comments.add(ctx.user_id, task.id, args.text, step_id=None if step is None else step.id,
                                           author=ctx.bot_id, tainted=ctx.tainted)
        if comment is None:
            return ToolOutcome(GONE_TEXT, tainted=task.tainted)
        about = "" if step is None else f" on step “{_escape(step.title)}”"
        return ToolOutcome(f"Commented on {_escape(task.title)}{about}.", created=True, tainted=task.tainted)

    async def _list(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        task = await find_task(self._tasks, ctx.user_id, ListCommentsArgs.model_validate(arguments).task)
        if isinstance(task, ToolOutcome):
            return task
        shown = await self._comments.list(ctx.user_id, task.id, limit=COMMENT_TOOL_LIMIT)
        if shown is None:
            return ToolOutcome(GONE_TEXT, tainted=task.tainted)
        if not shown:
            return ToolOutcome(f"{_escape(task.title)} has no comments.", tainted=task.tainted)
        lines = "\n".join(_comment_line(comment, task, ctx.bot_id) for comment in shown)
        tainted = task.tainted or any(comment.tainted for comment in shown)
        return ToolOutcome(f"Comments on {_escape(task.title)}:\n{lines}", tainted=tainted)
```

- [ ] **Step 6: Every bot gets them**

`roost/talk/tool_catalog.py`. Find:

```python
from roost.tasks.tool_specs import TASK_TOOL_DEFS
```

Replace with:

```python
from roost.tasks.step_specs import COMMENT_TOOL_DEFS, STEP_TOOL_DEFS
from roost.tasks.tool_specs import TASK_TOOL_DEFS
```

`roost/talk/tool_catalog.py`. Find:

```python
    *TASK_TOOL_DEFS,
    *MONEY_TOOL_DEFS,
```

Replace with:

```python
    *TASK_TOOL_DEFS,
    *STEP_TOOL_DEFS,
    *COMMENT_TOOL_DEFS,
    *MONEY_TOOL_DEFS,
```

`roost/talk/domain_tools.py`. Find:

```python
def build_domain_tools(config: Config, events: EventHub) -> DomainTools:
    """Every domain's tools (tasks, money, notes, documents and projects), wired
    to the user's shared stores. The stores hold no state, so one of each serves
    every service, and one ``ProjectService`` answers every tool that names a
    project (projects hub H3)."""
```

Replace with:

```python
def build_domain_tools(config: Config, events: EventHub) -> DomainTools:
    """Every domain's tools (tasks with their steps and comments, money, notes,
    documents and projects), wired to the user's shared stores. The stores hold
    no state, so one of each serves every service, and one ``ProjectService``
    answers every tool that names a project (projects hub H3)."""
```

`roost/talk/domain_tools.py`. Find:

```python
    from roost.tasks.service import TaskService   # local: roost.tasks imports this module
    from roost.tasks.store import TaskStore
    from roost.tasks.tools import TaskTools
```

Replace with:

```python
    from roost.tasks.comment_service import CommentService
    from roost.tasks.comment_store import CommentStore
    from roost.tasks.comment_tools import CommentTools
    from roost.tasks.service import TaskService   # local: roost.tasks imports this module
    from roost.tasks.step_service import StepService
    from roost.tasks.step_tools import StepTools
    from roost.tasks.store import TaskStore
    from roost.tasks.tools import TaskTools
```

`roost/talk/domain_tools.py`. Find:

```python
    tasks = TaskService(task_store, events)
    return DomainTools((
        TaskTools(tasks, projects),
```

Replace with:

```python
    tasks = TaskService(task_store, events)
    comments = CommentStore(config)
    return DomainTools((
        TaskTools(tasks, projects),
        StepTools(tasks, StepService(task_store, expenses, comments, events)),
        CommentTools(tasks, CommentService(comments, task_store, events)),
```

The web's step lines need the new verb's past tense (`tests/test_tool_lines.py`):

`web/src/lib/toolLines.ts`. Find:

```ts
  looking: "looked", making: "made", opening: "opened",
```

Replace with:

```ts
  looking: "looked", making: "made", moving: "moved", opening: "opened",
```

- [ ] **Step 7: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && ROOST_DATA_DIR=$(mktemp -d) ROOST_DESKS_DIR=$(mktemp -d) uv run pytest tests/test_step_comment_tools.py tests/test_every_bot_tools.py tests/test_tool_lines.py tests/test_gate.py tests/test_task_tools.py -q`
Expected: PASS (`test_step_comment_tools.py` 7 passed; `test_gate.py` now checks the six new tools too).

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npx vitest run tests/toolLines.test.ts`
Expected: PASS.

- [ ] **Step 8: Commit**

Run:

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && \
git add roost/tasks/step_specs.py roost/tasks/step_tools.py roost/tasks/comment_tools.py roost/talk/tool_catalog.py \
  roost/talk/domain_tools.py web/src/lib/toolLines.ts tests/test_step_comment_tools.py && \
git commit -m "feat: every bot can add, change, move and delete a task's steps, and comment on a task"
```

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git status --short`
Expected: none of the files above is listed.

---
### Task 6: Steps and comments over HTTP

Design P3 "Comments" (routes) and the steps the drawer needs, Design meets code 9, Review Focus 5. Two routers, each over its service from `app.state`:
- `roost/gateway/routes/task_steps.py`: `POST /api/tasks/{id}/steps`, `PATCH /api/tasks/{id}/steps/{step_id}` (`title` and/or `done`, at least one), `POST …/{step_id}/move` (`position`, 0 is first) and `DELETE …/{step_id}` (with `moved_expenses` and `moved_comments`). `StepNotFound` and a missing task are 404, `StepsBusy` 409, a refused title 422.
- `roost/gateway/routes/comments.py`: `GET` / `POST /api/tasks/{id}/comments`, `PATCH` / `DELETE /api/comments/{id}`. A bot's comment is 403, a missing or another user's 404, a body or step it refuses 422.

Every mutation needs the Origin. Registration closes after the first account, so the two-user test makes Bob with `register_user` and logs him in.

**Files:**
- Create: `roost/gateway/routes/task_steps.py`, `roost/gateway/routes/comments.py`
- Modify: `roost/gateway/app.py`
- Test: `tests/test_steps_comments_api.py` (new)

**Interfaces:**
- Consumes: Task 3's `CommentService`, `CommentNotYours`, `comment_out`, `MAX_COMMENT_LENGTH`; Task 4's `StepService`, `StepRemoval`, `StepNotFound`, `StepsBusy`, `STEP_NOT_FOUND_TEXT`, `MAX_STEP_TITLE_LENGTH`; `task_out`; `CurrentUser`, `RequireOrigin`; `MAX_RECORD_ID_LENGTH`, `MAX_TASK_STEPS`.
- Produces: `app.state.steps` (`StepService`), `app.state.comments` (`CommentService`); `steps_router`, `comments_router`; the routes in the Shared Contract's HTTP table. Task 9's web API calls them.

- [ ] **Step 1: Path guard**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && test -f roost/tasks/step_tools.py && test ! -e roost/gateway/routes/task_steps.py && grep -c "app.state.steps" roost/gateway/app.py`
Expected: `0`. Otherwise stop.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_steps_comments_api.py`:

```python
"""A task's steps and comments over HTTP (redesign P3), and Review Focus 5: another user's task,
step or comment is a 404, never the object."""

from __future__ import annotations

import asyncio
import sqlite3

from fastapi.testclient import TestClient

from roost.config import load_config
from roost.db.connection import get_db_path
from roost.events.hub import EventHub
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.tasks.comment_service import CommentService
from roost.tasks.comment_store import CommentStore
from roost.tasks.store import TaskStore

O = {"Origin": "http://127.0.0.1:18800"}


def _client() -> TestClient:
    c = TestClient(create_app())
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O).status_code == 201
    return c


def _second_user() -> TestClient:
    """Bob: registration closes after the first account, so he is made directly, then logs in."""
    asyncio.run(register_user(load_config(), "bob", "pw-123456"))
    c = TestClient(create_app())
    assert c.post("/api/auth/login", json={"username": "bob", "password": "pw-123456"}, headers=O).status_code == 200
    return c


def _task(c: TestClient, title: str = "Fix the sink") -> dict:
    return c.post("/api/tasks", json={"title": title}, headers=O).json()


def _frames() -> list[str]:
    con = sqlite3.connect(get_db_path(load_config()))
    try:
        return [row[0] for row in con.execute("SELECT kind FROM events ORDER BY seq")]
    finally:
        con.close()


def test_add_rename_tick_move_and_delete_steps():
    c = _client()
    task = _task(c)
    first = c.post(f"/api/tasks/{task['id']}/steps", json={"title": "Buy a washer"}, headers=O)
    assert first.status_code == 201
    second = c.post(f"/api/tasks/{task['id']}/steps", json={"title": "Fit it"}, headers=O).json()
    washer, fit = (step["id"] for step in second["steps"])
    ticked = c.patch(f"/api/tasks/{task['id']}/steps/{washer}", json={"done": True, "title": "Buy two washers"}, headers=O)
    assert ticked.json()["steps"][0] == {"id": washer, "title": "Buy two washers", "done": True}
    moved = c.post(f"/api/tasks/{task['id']}/steps/{fit}/move", json={"position": 0}, headers=O).json()
    assert [step["id"] for step in moved["steps"]] == [fit, washer]
    deleted = c.delete(f"/api/tasks/{task['id']}/steps/{fit}", headers=O).json()
    assert ([step["id"] for step in deleted["steps"]], deleted["moved_expenses"], deleted["moved_comments"]) == ([washer], 0, 0)
    assert _frames()[-5:] == ["tasks_changed"] * 5


def test_a_step_change_it_refuses_says_why():
    c = _client()
    task = _task(c)
    assert c.post(f"/api/tasks/{task['id']}/steps", json={"title": "  "}, headers=O).json()["detail"] == "A step needs a title."
    step = c.post(f"/api/tasks/{task['id']}/steps", json={"title": "Buy a washer"}, headers=O).json()["steps"][0]
    assert c.patch(f"/api/tasks/{task['id']}/steps/{step['id']}", json={}, headers=O).status_code == 422
    assert c.post(f"/api/tasks/{task['id']}/steps/{step['id']}/move", json={"position": -1}, headers=O).status_code == 422
    unknown = c.patch(f"/api/tasks/{task['id']}/steps/s-nope", json={"done": True}, headers=O)
    assert (unknown.status_code, unknown.json()["detail"]) == (404, "That task has no such step.")
    assert c.post("/api/tasks/no-such-task/steps", json={"title": "x"}, headers=O).status_code == 404


def test_comment_thread_add_edit_delete():
    c = _client()
    task = _task(c)
    step = c.post(f"/api/tasks/{task['id']}/steps", json={"title": "Buy a washer"}, headers=O).json()["steps"][0]
    on_task = c.post(f"/api/tasks/{task['id']}/comments", json={"body": "Plumber at 9"}, headers=O)
    assert on_task.status_code == 201 and on_task.json()["author"] == "user"
    on_step = c.post(f"/api/tasks/{task['id']}/comments", json={"body": "15 mm", "step_id": step["id"]}, headers=O).json()
    assert on_step["step_id"] == step["id"]
    edited = c.patch(f"/api/comments/{on_task.json()['id']}", json={"body": "Plumber at 10"}, headers=O).json()
    assert edited["body"] == "Plumber at 10" and edited["edited_at"]
    assert c.delete(f"/api/comments/{on_step['id']}", headers=O).status_code == 204
    assert [comment["body"] for comment in c.get(f"/api/tasks/{task['id']}/comments").json()] == ["Plumber at 10"]
    refused = c.post(f"/api/tasks/{task['id']}/comments", json={"body": "x", "step_id": "s-nope"}, headers=O)
    assert (refused.status_code, refused.json()["detail"]) == (422, "That task has no such step.")
    assert c.post(f"/api/tasks/{task['id']}/comments", json={"body": "   "}, headers=O).status_code == 422


def test_a_bots_comment_is_403_to_edit_or_delete():
    c = _client()
    task = _task(c)
    user_id = c.get("/api/auth/me").json()["id"]
    cfg = load_config()
    bots = asyncio.run(CommentService(CommentStore(cfg), TaskStore(cfg), EventHub(cfg)).add(
        user_id, task["id"], "Found it on shop.example", author="bot-1", tainted=True))
    [shown] = c.get(f"/api/tasks/{task['id']}/comments").json()
    assert (shown["author"], shown["tainted"]) == ("bot-1", True)
    edit = c.patch(f"/api/comments/{bots.id}", json={"body": "mine now"}, headers=O)
    assert (edit.status_code, edit.json()["detail"]) == (403, "Only your own comments can be changed.")
    assert c.delete(f"/api/comments/{bots.id}", headers=O).status_code == 403


def test_another_users_task_steps_and_comments_are_404():
    """Review Focus 5."""
    alice = _client()
    task = _task(alice)
    step = alice.post(f"/api/tasks/{task['id']}/steps", json={"title": "Buy a washer"}, headers=O).json()["steps"][0]
    comment = alice.post(f"/api/tasks/{task['id']}/comments", json={"body": "Mine"}, headers=O).json()
    bob = _second_user()
    tid, sid = task["id"], step["id"]
    for response in (
        bob.post(f"/api/tasks/{tid}/steps", json={"title": "x"}, headers=O),
        bob.patch(f"/api/tasks/{tid}/steps/{sid}", json={"done": True}, headers=O),
        bob.post(f"/api/tasks/{tid}/steps/{sid}/move", json={"position": 0}, headers=O),
        bob.delete(f"/api/tasks/{tid}/steps/{sid}", headers=O),
        bob.get(f"/api/tasks/{tid}/comments"),
        bob.post(f"/api/tasks/{tid}/comments", json={"body": "x"}, headers=O),
        bob.patch(f"/api/comments/{comment['id']}", json={"body": "x"}, headers=O),
        bob.delete(f"/api/comments/{comment['id']}", headers=O),
    ):
        assert response.status_code == 404, response.request.url
        assert "Mine" not in response.text and "Buy a washer" not in response.text
    [kept] = alice.get(f"/api/tasks/{tid}/comments").json()
    assert kept["body"] == "Mine"


def test_step_and_comment_changes_need_the_origin_and_a_login():
    c = _client()
    task = _task(c)
    evil = {"Origin": "http://evil.example"}
    assert c.post(f"/api/tasks/{task['id']}/steps", json={"title": "x"}, headers=evil).status_code == 403
    assert c.post(f"/api/tasks/{task['id']}/comments", json={"body": "x"}, headers=evil).status_code == 403
    assert TestClient(create_app()).get(f"/api/tasks/{task['id']}/comments").status_code == 401
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && ROOST_DATA_DIR=$(mktemp -d) ROOST_DESKS_DIR=$(mktemp -d) uv run pytest tests/test_steps_comments_api.py -q`
Expected: FAIL: the routes do not exist yet, so the tests get 404 or 405 where they expect 200, 201, 204, 403 or 422.

- [ ] **Step 4: The routes**

Create `roost/gateway/routes/task_steps.py`:

```python
"""A task's steps over HTTP (redesign P3): add, rename, tick or untick, move and delete. The same
``StepService`` as the bots' step tools, so every change publishes ``tasks_changed``.

- Another user's task, a deleted task or a step the task doesn't have: 404.
- A title it refuses, or too many steps: 422 with the plain sentence.
- Too many changes at once (the compare-and-set lost every try): 409, "Try again."
- Each answer is the task (``task_out``); deleting a step also says how many of its expenses and
  comments moved to the whole task."""

from __future__ import annotations

from typing import Any, Awaitable

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from roost.constants import MAX_STEP_TITLE_LENGTH, MAX_TASK_STEPS
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.tasks.format import task_out
from roost.tasks.models import STEP_NOT_FOUND_TEXT, Task
from roost.tasks.step_service import StepRemoval, StepService
from roost.tasks.steps import StepNotFound
from roost.tasks.store import StepsBusy

steps_router = APIRouter(prefix="/api/tasks", tags=["steps"])
TASK_NOT_FOUND_TEXT = "Task not found"
NOTHING_TO_CHANGE_TEXT = "Send a new title, or done."


class StepIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=MAX_STEP_TITLE_LENGTH)


class StepPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=MAX_STEP_TITLE_LENGTH)
    done: StrictBool | None = None

    @model_validator(mode="after")
    def _something_to_change(self) -> "StepPatchIn":
        if self.title is None and self.done is None:
            raise ValueError(NOTHING_TO_CHANGE_TEXT)
        return self


class StepMoveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    position: int = Field(ge=0, le=MAX_TASK_STEPS - 1)   # 0 is first; past the end puts it last


def _service(request: Request) -> StepService:
    return request.app.state.steps


async def _settled(change: Awaitable[Task | StepRemoval | None]) -> Task | StepRemoval:
    """The change's result, or the HTTP error that says why there is none."""
    try:
        result = await change
    except StepNotFound as exc:
        raise HTTPException(status_code=404, detail=STEP_NOT_FOUND_TEXT) from exc
    except StepsBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail=TASK_NOT_FOUND_TEXT)
    return result


@steps_router.post("/{task_id}/steps", status_code=201, dependencies=[RequireOrigin])
async def add_step(task_id: str, body: StepIn, request: Request, user: CurrentUser) -> dict[str, Any]:
    return task_out(await _settled(_service(request).add(user.id, task_id, body.title)))


@steps_router.patch("/{task_id}/steps/{step_id}", dependencies=[RequireOrigin])
async def update_step(task_id: str, step_id: str, body: StepPatchIn, request: Request,
                      user: CurrentUser) -> dict[str, Any]:
    """A new title, a tick (``done: true``) or an untick, or both."""
    service = _service(request)
    task = None
    if body.title is not None:
        task = await _settled(service.rename(user.id, task_id, step_id, body.title))
    if body.done is not None:
        task = await _settled(service.set_done(user.id, task_id, step_id, body.done))
    return task_out(task)


@steps_router.post("/{task_id}/steps/{step_id}/move", dependencies=[RequireOrigin])
async def move_step(task_id: str, step_id: str, body: StepMoveIn, request: Request,
                    user: CurrentUser) -> dict[str, Any]:
    return task_out(await _settled(_service(request).move(user.id, task_id, step_id, body.position)))


@steps_router.delete("/{task_id}/steps/{step_id}", dependencies=[RequireOrigin])
async def delete_step(task_id: str, step_id: str, request: Request, user: CurrentUser) -> dict[str, Any]:
    """The task without the step. Its expenses and comments stay on the task."""
    removal = await _settled(_service(request).delete(user.id, task_id, step_id))
    return {**task_out(removal.task), "moved_expenses": len(removal.moved_expenses),
            "moved_comments": removal.moved_comments}
```

Create `roost/gateway/routes/comments.py`:

```python
"""Comments over HTTP (redesign P3): a task's thread, and the user's own comments.

- ``GET`` / ``POST /api/tasks/{id}/comments``: the thread, oldest first, and a new comment by the user
  (``step_id`` puts it on one of the task's steps).
- ``PATCH`` / ``DELETE /api/comments/{id}``: only the user's own comments; a bot's is 403.
- Another user's task or comment, or one that is gone: 404. A body or step it refuses: 422.
The same ``CommentService`` as the bots' tools, so every change publishes ``tasks_changed``."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from roost.constants import MAX_COMMENT_LENGTH, MAX_RECORD_ID_LENGTH
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.tasks.comment_service import CommentNotYours, CommentService
from roost.tasks.comments import comment_out

comments_router = APIRouter(tags=["comments"])
TASK_NOT_FOUND_TEXT = "Task not found"
COMMENT_NOT_FOUND_TEXT = "Comment not found"


class CommentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str = Field(min_length=1, max_length=MAX_COMMENT_LENGTH)
    step_id: str | None = Field(default=None, max_length=MAX_RECORD_ID_LENGTH)


class CommentPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str = Field(min_length=1, max_length=MAX_COMMENT_LENGTH)


def _service(request: Request) -> CommentService:
    return request.app.state.comments


@comments_router.get("/api/tasks/{task_id}/comments")
async def list_comments(task_id: str, request: Request, user: CurrentUser) -> list[dict[str, Any]]:
    comments = await _service(request).list(user.id, task_id)
    if comments is None:
        raise HTTPException(status_code=404, detail=TASK_NOT_FOUND_TEXT)
    return [comment_out(comment) for comment in comments]


@comments_router.post("/api/tasks/{task_id}/comments", status_code=201, dependencies=[RequireOrigin])
async def add_comment(task_id: str, body: CommentIn, request: Request, user: CurrentUser) -> dict[str, Any]:
    try:
        comment = await _service(request).add(user.id, task_id, body.body, step_id=body.step_id)
    except ValueError as exc:   # an empty body after trimming, or a step the task doesn't have
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if comment is None:
        raise HTTPException(status_code=404, detail=TASK_NOT_FOUND_TEXT)
    return comment_out(comment)


@comments_router.patch("/api/comments/{comment_id}", dependencies=[RequireOrigin])
async def edit_comment(comment_id: str, body: CommentPatchIn, request: Request, user: CurrentUser) -> dict[str, Any]:
    try:
        comment = await _service(request).edit(user.id, comment_id, body.body)
    except CommentNotYours as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if comment is None:
        raise HTTPException(status_code=404, detail=COMMENT_NOT_FOUND_TEXT)
    return comment_out(comment)


@comments_router.delete("/api/comments/{comment_id}", status_code=204, dependencies=[RequireOrigin])
async def delete_comment(comment_id: str, request: Request, user: CurrentUser) -> None:
    try:
        deleted = await _service(request).delete(user.id, comment_id)
    except CommentNotYours as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail=COMMENT_NOT_FOUND_TEXT)
```

- [ ] **Step 5: Wire them**

`roost/gateway/app.py`. Find:

```python
from roost.gateway.routes.chats import chats_router
```

Replace with:

```python
from roost.gateway.routes.chats import chats_router
from roost.gateway.routes.comments import comments_router
```

`roost/gateway/app.py`. Find:

```python
from roost.gateway.routes.stuck import stuck_router
```

Replace with:

```python
from roost.gateway.routes.stuck import stuck_router
from roost.gateway.routes.task_steps import steps_router
```

`roost/gateway/app.py`. Find:

```python
from roost.talk.store import TalkStore
from roost.tasks.service import TaskService
from roost.tasks.store import TaskStore
```

Replace with:

```python
from roost.talk.store import TalkStore
from roost.tasks.comment_service import CommentService
from roost.tasks.comment_store import CommentStore
from roost.tasks.service import TaskService
from roost.tasks.step_service import StepService
from roost.tasks.store import TaskStore
```

`roost/gateway/app.py`. Find:

```python
    app.state.tasks = TaskService(TaskStore(resolved_config), app.state.events)
```

Replace with:

```python
    app.state.tasks = TaskService(TaskStore(resolved_config), app.state.events)
    # Redesign P3: a task's steps and comments, behind the same doors as the bots' tools.
    app.state.steps = StepService(TaskStore(resolved_config), ExpenseStore(resolved_config),
                                  CommentStore(resolved_config), app.state.events)
    app.state.comments = CommentService(CommentStore(resolved_config), TaskStore(resolved_config), app.state.events)
```

`roost/gateway/app.py`. Find:

```python
    app.include_router(tasks_router)
```

Replace with:

```python
    app.include_router(tasks_router)
    app.include_router(steps_router)
    app.include_router(comments_router)
```

- [ ] **Step 6: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && ROOST_DATA_DIR=$(mktemp -d) ROOST_DESKS_DIR=$(mktemp -d) uv run pytest tests/test_steps_comments_api.py tests/test_tasks_api.py tests/test_static.py -q`
Expected: PASS (`test_steps_comments_api.py` 6 passed).

- [ ] **Step 7: Commit**

Run:

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && \
git add roost/gateway/routes/task_steps.py roost/gateway/routes/comments.py roost/gateway/app.py \
  tests/test_steps_comments_api.py && \
git commit -m "feat: a task's steps and comments over HTTP, another user's ids a 404"
```

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git status --short`
Expected: none of the files above is listed.

---
### Task 7: The drawer's data, the reminder and the repeat, and an expense for a task or a step

Design P3 "The task drawer" (its server side), H11, Design meets code 5 and 10, Review Focus 5.
- **`GET /api/tasks/{id}`** (`roost/gateway/routes/task_detail.py`): the task (any status) as `task_out`, plus `money`: its slice, spent and left (`numbers.task_money`) and what is spent on each step (new `numbers.step_spent`), in its project's currency, or `null` with no project; plus `expenses`, every expense filed under it (`MoneyService.for_task`), as the Board's rows. The web adds nothing up.
- **`PATCH /api/tasks/{id}`** learns `reminder_at` (words or ISO on Madrid time that name a time; the advance reminder goes back to 30 minutes before; `null` clears both; a `due_date` in the same patch is read first, then the reminder wins) and `recurring` (a cron, `validate_cron`; `null` stops the repeat).
- **`POST /api/money/expenses`** learns `task_id` and `step_id`: one of the user's tasks of any status, and one of its steps (a step alone is refused). With no project named, the expense goes to the task's project.

**Files:**
- Create: `roost/gateway/routes/task_detail.py`
- Modify: `roost/projects/numbers.py`, `roost/money/service.py`, `roost/tasks/due.py`, `roost/gateway/routes/tasks.py`, `roost/gateway/routes/money.py`, `roost/gateway/app.py`
- Test: `tests/test_task_detail_api.py` (new); `tests/test_tasks_api.py`, `tests/test_money_api.py`, `tests/test_project_numbers.py`, `tests/test_task_time.py` stay green unchanged

**Interfaces:**
- Consumes: `task_money`, `counted`, `total_of` (`roost/projects/numbers.py`), `task_money_out` (`roost/gateway/routes/projects.py`), `expense_row`, `ExpenseStore.for_tasks`, `validate_cron`, `resolve_pre_reminders`, `parse_due`; Task 3's `STEP_NOT_FOUND_TEXT`; `STEP_NEEDS_TASK_TEXT` (`roost/money/expense_links.py`).
- Produces: `step_spent`; `MoneyService.for_task`; `TaskPatchIn.reminder_at` / `.recurring`; `ExpenseIn.task_id` / `.step_id`, `NO_SUCH_TASK_TEXT`; `detail_router`, `get_task`, `TASK_NOT_FOUND_TEXT`. Task 8 adds `POST /parse` to `task_detail.py`; Task 9's `getTask` reads `TaskDetailOut`.

- [ ] **Step 1: Path guard**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && test -f roost/gateway/routes/task_steps.py && test ! -e roost/gateway/routes/task_detail.py && grep -c "def step_spent" roost/projects/numbers.py`
Expected: `0`. Otherwise stop.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_task_detail_api.py`:

```python
"""The task drawer's server side (redesign P3): one task with its money and expenses, the reminder
and the repeat set on their own, and an expense added for a task or one of its steps."""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from roost.config import load_config
from roost.gateway.app import create_app
from roost.gateway.auth import register_user

O = {"Origin": "http://127.0.0.1:18800"}


def _client() -> TestClient:
    c = TestClient(create_app())
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O).status_code == 201
    return c


def _project(c: TestClient, name: str = "Renovation", currency: str = "EUR") -> dict:
    return c.post("/api/projects", json={"name": name, "currency": currency}, headers=O).json()


def _expense(c: TestClient, **fields) -> dict:
    created = c.post("/api/money/expenses", json={"amount": "10", **fields}, headers=O)
    assert created.status_code == 201, created.text
    return created.json()


def test_a_task_with_its_money_per_task_and_per_step_and_its_expenses():
    c = _client()
    project = _project(c)
    task = c.post("/api/tasks", json={"title": "Fix the sink", "project_id": project["id"],
                                      "allocated_budget": "50"}, headers=O).json()
    step = c.post(f"/api/tasks/{task['id']}/steps", json={"title": "Buy a washer"}, headers=O).json()["steps"][0]
    on_step = _expense(c, amount="12,50", task_id=task["id"], step_id=step["id"], note="washers")
    on_task = _expense(c, amount="30", task_id=task["id"])
    assert (on_step["project_id"], on_step["step_id"], on_task["step_id"]) == (project["id"], step["id"], None)
    detail = c.get(f"/api/tasks/{task['id']}").json()
    assert detail["title"] == "Fix the sink"
    assert detail["money"] == {"planned": "50.00", "spent": "42.50", "left": "7.50", "currency": "EUR",
                               "steps": {step["id"]: "12.50"}}
    assert sorted(e["amount"] for e in detail["expenses"]) == ["12.50", "30.00"]


def test_a_task_with_no_project_has_no_money_block_but_lists_its_expenses():
    c = _client()
    task = c.post("/api/tasks", json={"title": "Buy stamps"}, headers=O).json()
    _expense(c, task_id=task["id"])
    detail = c.get(f"/api/tasks/{task['id']}").json()
    assert detail["money"] is None and [e["project"] for e in detail["expenses"]] == ["General"]


def test_an_expense_names_a_real_task_and_one_of_its_steps():
    c = _client()
    task = c.post("/api/tasks", json={"title": "Fix the sink"}, headers=O).json()
    for body, reason in (
        ({"task_id": "no-such-task"}, "No such task."),
        ({"task_id": task["id"], "step_id": "s-nope"}, "That task has no such step."),
        ({"step_id": "s-nope"}, "A step needs its task: name the task too."),
    ):
        refused = c.post("/api/money/expenses", json={"amount": "10", **body}, headers=O)
        assert (refused.status_code, refused.json()["detail"]) == (422, reason)


def test_the_reminder_and_the_repeat_are_set_and_cleared_on_their_own():
    c = _client()
    task = c.post("/api/tasks", json={"title": "Water the plants", "due_date": "2026-12-01"}, headers=O).json()
    reminded = c.patch(f"/api/tasks/{task['id']}", json={"reminder_at": "2026-11-30T20:00"}, headers=O).json()
    assert (reminded["due_date"], reminded["reminder_at"], reminded["pre_reminders"]) == (
        "2026-12-01", "2026-11-30T19:00:00+00:00", ["2026-11-30T18:30:00+00:00"])
    repeating = c.patch(f"/api/tasks/{task['id']}", json={"recurring": "0 9 * * 1"}, headers=O).json()
    assert repeating["recurring"] == "0 9 * * 1"
    cleared = c.patch(f"/api/tasks/{task['id']}", json={"reminder_at": None, "recurring": None}, headers=O).json()
    assert (cleared["reminder_at"], cleared["pre_reminders"], cleared["recurring"]) == (None, [], None)


def test_a_reminder_or_repeat_it_cannot_read_is_422():
    c = _client()
    task = c.post("/api/tasks", json={"title": "x"}, headers=O).json()
    no_time = c.patch(f"/api/tasks/{task['id']}", json={"reminder_at": "next monday"}, headers=O)
    assert no_time.status_code == 422 and "could not read a time" in no_time.json()["detail"]
    bad_cron = c.patch(f"/api/tasks/{task['id']}", json={"recurring": "every day"}, headers=O)
    assert bad_cron.status_code == 422 and "is not a cron expression" in bad_cron.json()["detail"]


def test_another_users_task_is_404_and_their_task_cannot_take_an_expense():
    alice = _client()
    task = alice.post("/api/tasks", json={"title": "Mine"}, headers=O).json()
    asyncio.run(register_user(load_config(), "bob", "pw-123456"))
    bob = TestClient(create_app())
    assert bob.post("/api/auth/login", json={"username": "bob", "password": "pw-123456"}, headers=O).status_code == 200
    assert bob.get(f"/api/tasks/{task['id']}").status_code == 404
    sneaky = bob.post("/api/money/expenses", json={"amount": "10", "task_id": task["id"]}, headers=O)
    assert (sneaky.status_code, sneaky.json()["detail"]) == (422, "No such task.")
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && ROOST_DATA_DIR=$(mktemp -d) ROOST_DESKS_DIR=$(mktemp -d) uv run pytest tests/test_task_detail_api.py -q`
Expected: FAIL: `ExpenseIn` refuses `task_id` (422 "Extra inputs are not permitted"), `GET /api/tasks/{id}` has no route yet (405, since only PATCH and DELETE are on that path), and `reminder_at` / `recurring` are refused as extra fields.

- [ ] **Step 4: What is spent on each step, and a task's expenses**

`roost/projects/numbers.py`. Find:

```python
def progress(tasks: Sequence[Task]) -> Progress:
```

Replace with:

```python
def step_spent(task: Task, expenses: Sequence[Expense], currency: str) -> Mapping[str, Decimal]:
    """What is spent on each of the task's steps (redesign P3), in ``currency``, by step id, in the
    steps' order: the counted expenses filed under that step. An expense whose step is gone counts
    on the task only (``task_money``), so the steps' sums may add up to less than the task's."""
    mine = tuple(e for e in expenses if e.task_id == task.id and counted(e, currency))
    return MappingProxyType({step.id: total_of(tuple(e for e in mine if e.step_id == step.id)) for step in task.steps})


def progress(tasks: Sequence[Task]) -> Progress:
```

`roost/money/service.py`. Find:

```python
    async def get_expense(self, user_id: str, expense_id: str) -> Expense | None:
```

Replace with:

```python
    async def for_task(self, user_id: str, task_id: str) -> tuple[Expense, ...]:
        """Every expense filed under the task or one of its steps (redesign P3's drawer), voids included."""
        return await self._expenses.for_tasks(user_id, (task_id,))

    async def get_expense(self, user_id: str, expense_id: str) -> Expense | None:
```

- [ ] **Step 5: The reminder and the repeat in a patch**

`roost/tasks/due.py`. Find:

```python
def build_schedule(due: str | None, reminder: str | None, pre_reminders: Sequence[str] | None) -> Schedule:
    """A timed due is also the reminder unless ``reminder`` names another time."""
    parsed = parse_due(due)
    reminder_at = parse_due(reminder).reminder_at if reminder else parsed.reminder_at
    if reminder and reminder_at is None:
        raise ValueError(f"I could not read a time in “{reminder}”. Try “tomorrow at 8:30”.")
    return Schedule(parsed.due_date, reminder_at, resolve_pre_reminders(pre_reminders, reminder_at))


def patch_from_fields(fields: Mapping[str, Any]) -> TaskPatch:
    """A ``TaskPatch`` from the fields a caller set (``None`` clears). A new
    ``due_date`` (words or ISO) also resets the reminder and its advance
    reminders to the defaults."""
    changes = {name: value for name, value in fields.items() if name != "due_date"}
```

Replace with:

```python
_UNREADABLE_TIME = "I could not read a time in “{text}”. Try “tomorrow at 8:30”."


def build_schedule(due: str | None, reminder: str | None, pre_reminders: Sequence[str] | None) -> Schedule:
    """A timed due is also the reminder unless ``reminder`` names another time."""
    parsed = parse_due(due)
    reminder_at = parse_due(reminder).reminder_at if reminder else parsed.reminder_at
    if reminder and reminder_at is None:
        raise ValueError(_UNREADABLE_TIME.format(text=reminder))
    return Schedule(parsed.due_date, reminder_at, resolve_pre_reminders(pre_reminders, reminder_at))


def _reminder_changes(text: str | None) -> dict[str, Any]:
    """A reminder set on its own (redesign P3's drawer): words or ISO on Madrid time, which must name
    a time, with the default advance reminder. Empty or ``None`` clears both."""
    if text is None or not text.strip():
        return {"reminder_at": None, "pre_reminders": ()}
    reminder_at = parse_due(text).reminder_at
    if reminder_at is None:
        raise ValueError(_UNREADABLE_TIME.format(text=text))
    return {"reminder_at": reminder_at, "pre_reminders": resolve_pre_reminders(None, reminder_at)}


def patch_from_fields(fields: Mapping[str, Any]) -> TaskPatch:
    """A ``TaskPatch`` from the fields a caller set (``None`` clears). A new
    ``due_date`` (words or ISO) also resets the reminder and its advance
    reminders to the defaults; a ``reminder_at`` set in the same patch wins."""
    changes = {name: value for name, value in fields.items() if name not in ("due_date", "reminder_at")}
```

`roost/tasks/due.py`. Find:

```python
        changes.update(due_date=schedule.due_date, reminder_at=schedule.reminder_at,
                       pre_reminders=schedule.pre_reminders)
    return TaskPatch(changes)
```

Replace with:

```python
        changes.update(due_date=schedule.due_date, reminder_at=schedule.reminder_at,
                       pre_reminders=schedule.pre_reminders)
    if "reminder_at" in fields:
        changes.update(_reminder_changes(fields["reminder_at"]))
    return TaskPatch(changes)
```

`roost/gateway/routes/tasks.py`. Find:

```python
from roost.tasks.models import Priority, Task, TaskDraft, TaskFilter
```

Replace with:

```python
from roost.tasks.models import Priority, Task, TaskDraft, TaskFilter
from roost.tasks.recurrence import validate_cron
```

`roost/gateway/routes/tasks.py`. Find:

```python
    project_id: str | None = Field(default=None, max_length=MAX_RECORD_ID_LENGTH)   # null unlinks
    allocated_budget: Amount | None = None                                           # null clears the slice
```

Replace with:

```python
    project_id: str | None = Field(default=None, max_length=MAX_RECORD_ID_LENGTH)   # null unlinks
    allocated_budget: Amount | None = None                                           # null clears the slice
    reminder_at: str | None = Field(default=None, max_length=MAX_DUE_TEXT_LENGTH)   # words or ISO; null clears
    recurring: str | None = Field(default=None, max_length=MAX_DUE_TEXT_LENGTH)     # a cron; null: no repeat
```

`roost/gateway/routes/tasks.py`. Find:

```python
def _patch_fields(body: TaskPatchIn) -> dict[str, Any]:
    fields = body.model_dump(include=body.model_fields_set)
    if "allocated_budget" in fields:
        return {**fields, "allocated_budget": _slice(fields["allocated_budget"])}
    return fields
```

Replace with:

```python
def _patch_fields(body: TaskPatchIn) -> dict[str, Any]:
    """The fields the body set, read: a slice by the amount rules, a repeat as a cron. ``ValueError``."""
    fields = body.model_dump(include=body.model_fields_set)
    sliced = {"allocated_budget": _slice(fields["allocated_budget"])} if "allocated_budget" in fields else {}
    repeat = {"recurring": validate_cron(fields["recurring"])} if "recurring" in fields else {}
    return {**fields, **sliced, **repeat}
```

`update_task` already calls `patch_from_fields(_patch_fields(body))` inside the `try` that answers a `ValueError` with 422, so a reminder without a time and a cron it can't read are 422s.

- [ ] **Step 6: An expense for a task or one of its steps**

`roost/gateway/routes/money.py`. Find:

```python
from roost.money.amounts import JsonAmount, parse_amount
```

Replace with:

```python
from roost.money.amounts import JsonAmount, parse_amount
from roost.money.expense_links import STEP_NEEDS_TASK_TEXT
```

`roost/gateway/routes/money.py`. Find:

```python
from roost.records.project_link import NO_SUCH_PROJECT_TEXT
```

Replace with:

```python
from roost.records.project_link import NO_SUCH_PROJECT_TEXT
from roost.tasks.models import STEP_NOT_FOUND_TEXT, Task
```

`roost/gateway/routes/money.py`. Find:

```python
ONE_PROJECT_TEXT = "Name the project or send its id, not both."
```

Replace with:

```python
ONE_PROJECT_TEXT = "Name the project or send its id, not both."
NO_SUCH_TASK_TEXT = "No such task."
```

`roost/gateway/routes/money.py`. Find:

```python
    currency: OptionalCurrencyCode = None
    spent_at: str | None = Field(default=None, max_length=MAX_DUE_TEXT_LENGTH)

    @model_validator(mode="after")
```

Replace with:

```python
    currency: OptionalCurrencyCode = None
    spent_at: str | None = Field(default=None, max_length=MAX_DUE_TEXT_LENGTH)
    # Redesign P3: an expense added from a task's drawer is filed under the task, or one of its steps.
    task_id: str | None = Field(default=None, max_length=MAX_RECORD_ID_LENGTH)
    step_id: str | None = Field(default=None, max_length=MAX_RECORD_ID_LENGTH)

    @model_validator(mode="after")
```

`roost/gateway/routes/money.py`. Find:

```python
@money_router.post("/expenses", status_code=201, dependencies=[RequireOrigin])
async def add_expense(body: ExpenseIn, request: Request, user: CurrentUser):
    """A project named by id gets exactly that project (Task 7's ``project=``);
    one named by name is found or made, as before. An archived project
    refuses (H3, ``ARCHIVED_TEXT``), so ``log_expense`` runs inside the ``try``."""
    service = _service(request)
    try:
        entry = ExpenseEntry(amount=parse_amount(body.amount), spent_at=parse_spent_at(body.spent_at),
                             project=body.project, note=body.note, currency=body.currency)
        project = None if body.project_id is None else await _project_by_id(service, user.id, body.project_id)
        expense, target = await service.log_expense(user.id, entry, project=project)
```

Replace with:

```python
async def _linked_task(request: Request, user_id: str, body: ExpenseIn) -> Task | None:
    """The task (and step) the expense is for: one of the user's tasks of any status, and one of
    its steps. ``ValueError`` (a 422, nothing written) for an unknown task or step, or a step alone."""
    if body.task_id is None:
        if body.step_id is not None:
            raise ValueError(STEP_NEEDS_TASK_TEXT)
        return None
    task = await request.app.state.tasks.get(user_id, body.task_id)
    if task is None:
        raise ValueError(NO_SUCH_TASK_TEXT)
    if body.step_id is not None and body.step_id not in {step.id for step in task.steps}:
        raise ValueError(STEP_NOT_FOUND_TEXT)
    return task


@money_router.post("/expenses", status_code=201, dependencies=[RequireOrigin])
async def add_expense(body: ExpenseIn, request: Request, user: CurrentUser):
    """A project named by id gets exactly that project (Task 7's ``project=``);
    one named by name is found or made, as before. An archived project
    refuses (H3, ``ARCHIVED_TEXT``), so ``log_expense`` runs inside the ``try``.
    An expense for a task with no project named goes to the task's project."""
    service = _service(request)
    try:
        task = await _linked_task(request, user.id, body)
        entry = ExpenseEntry(amount=parse_amount(body.amount), spent_at=parse_spent_at(body.spent_at),
                             project=body.project, note=body.note, currency=body.currency,
                             task_id=body.task_id, step_id=body.step_id)
        project_id = body.project_id
        if project_id is None and body.project is None and task is not None:
            project_id = task.project_id
        project = None if project_id is None else await _project_by_id(service, user.id, project_id)
        expense, target = await service.log_expense(user.id, entry, project=project)
```

- [ ] **Step 7: The drawer's task**

Create `roost/gateway/routes/task_detail.py`:

```python
"""The task drawer's data over HTTP (redesign P3).

- ``GET /api/tasks/{id}``: one task (any status) with its money: the slice, what is spent and what is
  left, in its project's currency, and what is spent on each step (``roost.projects.numbers``; the web
  adds nothing up), plus every expense filed under it. ``money`` is ``null`` for a task with no project.
Another user's task is a 404."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from roost.gateway.deps import CurrentUser
from roost.gateway.routes.projects import task_money_out
from roost.money.amounts import amount_text
from roost.money.models import Expense, Project
from roost.money.summary import expense_row
from roost.projects.numbers import step_spent, task_money
from roost.tasks.format import task_out
from roost.tasks.models import Task

detail_router = APIRouter(prefix="/api/tasks", tags=["tasks"])
TASK_NOT_FOUND_TEXT = "Task not found"


def _money_out(task: Task, project: Project | None, expenses: tuple[Expense, ...]) -> dict[str, Any] | None:
    """``TaskDetailMoneyOut``, in the task's project's currency; ``None`` with no project."""
    if project is None:
        return None
    spent_by_step = step_spent(task, expenses, project.currency)
    return {**task_money_out(task_money(task, expenses, project.currency)), "currency": project.currency,
            "steps": {step_id: amount_text(amount) for step_id, amount in spent_by_step.items()}}


@detail_router.get("/{task_id}")
async def get_task(task_id: str, request: Request, user: CurrentUser) -> dict[str, Any]:
    task = await request.app.state.tasks.get(user.id, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=TASK_NOT_FOUND_TEXT)
    money = request.app.state.money
    projects = {project.id: project for project in await money.projects(user.id)}
    expenses = await money.for_task(user.id, task.id)
    return {**task_out(task), "money": _money_out(task, projects.get(task.project_id or ""), expenses),
            "expenses": [expense_row(expense, projects.get(expense.project_id)) for expense in expenses]}
```

`roost/gateway/app.py`. Find:

```python
from roost.gateway.routes.task_steps import steps_router
```

Replace with:

```python
from roost.gateway.routes.task_detail import detail_router
from roost.gateway.routes.task_steps import steps_router
```

`roost/gateway/app.py`. Find:

```python
    app.include_router(steps_router)
```

Replace with:

```python
    app.include_router(steps_router)
    app.include_router(detail_router)
```

- [ ] **Step 8: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && ROOST_DATA_DIR=$(mktemp -d) ROOST_DESKS_DIR=$(mktemp -d) uv run pytest tests/test_task_detail_api.py tests/test_tasks_api.py tests/test_money_api.py tests/test_money_routes_tools_polish.py tests/test_project_numbers.py tests/test_task_time.py tests/test_task_tools.py -q`
Expected: PASS (`test_task_detail_api.py` 6 passed).

- [ ] **Step 9: Commit**

Run:

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && \
git add roost/projects/numbers.py roost/money/service.py roost/tasks/due.py roost/gateway/routes/tasks.py \
  roost/gateway/routes/money.py roost/gateway/routes/task_detail.py roost/gateway/app.py tests/test_task_detail_api.py && \
git commit -m "feat: a task's drawer data with its money per step, reminder and repeat edits, expenses for a task or step"
```

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git status --short`
Expected: none of the files above is listed.

---
### Task 8: The quick-add line, read by the server

Design P3 "Quick typing", Design meets code 11 and 12, Review Focus 3. `roost/tasks/quick_line.py` reads a whole line in four passes, each taking the first match of its kind out of the line: the priority (`!urgent`, `!high`, `!medium`, `!low`, standing alone), the amount (`€200`, `200€`, `$12.50`, `£12,50`), the project (`#Renovation`) and, on what is left, the date by the `nl_time` rules a typed due follows (`due_from_parsed`, pulled out of `_read_due` so both read a due the same way). What remains is the title.
- **The project** is exact or ask (`ProjectService.resolve(change=True)`): a unique part of a name is fine; a near miss, several matches, a name no project has, General, or a project page's own project that is gone are each a `project_question`, never a guess.
- **The slice** needs a project and is in its currency (H11): no project, a money sign in another currency, or an amount outside the amount rules is a `budget_problem`.
- **`skip`** names the chips the user removed: those kinds are not read, and their words stay in the title.
- A day past the calendar's ends reads as no date, never an error.

`POST /api/tasks/parse` answers `QuickLineOut`, changes nothing, and needs the Origin like every POST. `ready` is true when there is a title and no question or problem.

**Files:**
- Create: `roost/tasks/quick_line.py`
- Modify: `roost/tasks/due.py`, `roost/gateway/routes/task_detail.py`
- Test: `tests/test_quick_line.py` (new); `tests/test_task_time.py`, `tests/test_dates_api.py` stay green unchanged

**Interfaces:**
- Consumes: `nl_time.parse`, `nl_time.ParsedTime`, `Due`, `_moment`; `ProjectService.resolve`, `ProjectRefusal`, `GENERAL_FIXED_TEXT`, `NO_PROJECT_TEXT`, `is_general`; `parse_amount`, `amount_text`; `SLICE_NEEDS_PROJECT`; Task 3's `QUICK_LINE_MAX_LENGTH` and `QUICK_LINE_CURRENCIES`.
- Produces: `due_from_parsed`; `QuickKind`, `LineWords`, `QuickLine` (`.ready`), `read_words`, `read_date`, `read_quick_line`, `quick_line_out`, `SLICE_CURRENCY_TEXT`, `NO_PROJECT_HERE_TEXT`, `PROJECT_GONE_TEXT`; `QuickLineIn`, `QUICK_KINDS`, `POST /api/tasks/parse`. Task 14's quick add draws its chips from `QuickLineOut`.

- [ ] **Step 1: Path guard**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && test -f roost/gateway/routes/task_detail.py && test ! -e roost/tasks/quick_line.py && grep -c "def due_from_parsed" roost/tasks/due.py`
Expected: `0`. Otherwise stop.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_quick_line.py`:

```python
"""The quick-add line (redesign P3): the server reads `Call plumber tomorrow 9am #Renovation €200 !high`,
and the web draws its chips from that reading."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, time, timedelta

import pytest
from fastapi.testclient import TestClient

from roost.config import load_config
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.talk.instructions import MADRID_TZ
from roost.tasks.quick_line import read_date, read_words

O = {"Origin": "http://127.0.0.1:18800"}


def _tomorrow() -> date:
    return datetime.now(MADRID_TZ).date() + timedelta(days=1)


def _client() -> TestClient:
    c = TestClient(create_app())
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O).status_code == 201
    return c


def _parse(c: TestClient, text: str, **fields) -> dict:
    read = c.post("/api/tasks/parse", json={"text": text, **fields}, headers=O)
    assert read.status_code == 200, read.text
    return read.json()


@pytest.mark.parametrize(("text", "priority", "amount", "currency", "project", "rest"), [
    ("Call plumber #Renovation €200 !high", "high", "200", "EUR", "Renovation", "Call plumber"),
    ("Pay 12,50$ !LOW", "low", "12,50", "USD", None, "Pay"),
    ("Buy stamps £3", None, "3", "GBP", None, "Buy stamps"),
    ("wow!high stays, so does €", None, None, None, None, "wow!high stays, so does €"),
])
def test_the_words_each_kind_reads(text, priority, amount, currency, project, rest):
    words = read_words(text)
    assert (words.priority, words.amount, words.currency, words.project_ref) == (priority, amount, currency, project)
    assert " ".join(words.rest.split()) == rest


def test_a_skipped_kind_keeps_its_words():
    words = read_words("Book 2 tickets #Trip €20 !high", frozenset({"project", "budget", "priority"}))
    assert (words.priority, words.amount, words.project_ref) == (None, None, None)
    assert read_date("Book 2 tickets", frozenset({"date"})) == (read_date("", frozenset())[0], "Book 2 tickets")


def test_the_whole_line_becomes_chips():
    c = _client()
    project = c.post("/api/projects", json={"name": "Renovation"}, headers=O).json()
    read = _parse(c, "Call plumber tomorrow 9am #Renovation €200 !high")
    nine = datetime.combine(_tomorrow(), time(9, 0), tzinfo=MADRID_TZ).isoformat()
    assert read == {
        "title": "Call plumber", "due_date": nine, "priority": "high",
        "project": {"id": project["id"], "name": "Renovation", "currency": "EUR", "color": project["color"]},
        "project_words": "#Renovation", "project_question": None, "budget": "200.00", "budget_words": "€200",
        "budget_problem": None, "ready": True,
    }


def test_a_near_project_name_asks_and_a_foreign_sign_or_no_project_explains():
    """Review Focus 3: never a silent wrong project, never a slice in the wrong currency."""
    c = _client()
    c.post("/api/projects", json={"name": "Renovation"}, headers=O)
    near = _parse(c, "Paint #Renovaton €20")
    assert (near["project"], near["ready"], near["budget"]) == (None, False, None)
    assert "Renovaton" in near["project_question"] and near["budget_words"] == "€20"
    foreign = _parse(c, "Paint #Renovation $20")
    assert foreign["budget_problem"] == "“Renovation” keeps its money in EUR: write the budget in EUR."
    loose = _parse(c, "Paint €20")
    assert (loose["budget_problem"], loose["ready"]) == ("A budget slice needs a project.", False)
    unknown = _parse(c, "Paint #Garage")
    assert unknown["project_question"] == "No project is called “Garage”. Make it on the Projects tab first."
    c.post("/api/money/expenses", json={"amount": "5"}, headers=O)          # a loose expense makes General
    general = _parse(c, "Paint #General")
    assert general["project_question"].startswith("General is where expenses with no project go")


def test_a_project_page_passes_its_project_and_a_dismissed_date_stays_in_the_title():
    c = _client()
    garden = c.post("/api/projects", json={"name": "Garden", "currency": "GBP"}, headers=O).json()
    read = _parse(c, "Book 2 tickets £30", project_id=garden["id"], skip=["date"])
    assert (read["title"], read["due_date"], read["project"]["id"], read["budget"]) == ("Book 2 tickets", None, garden["id"], "30.00")


def test_an_empty_line_or_another_users_project_is_not_ready():
    c = _client()
    assert _parse(c, "   !high")["ready"] is False
    asyncio.run(register_user(load_config(), "bob", "pw-123456"))
    bob = TestClient(create_app())
    assert bob.post("/api/auth/login", json={"username": "bob", "password": "pw-123456"}, headers=O).status_code == 200
    house = c.post("/api/projects", json={"name": "House"}, headers=O).json()
    sneaky = _parse(bob, "Paint", project_id=house["id"])
    assert (sneaky["project"], sneaky["project_question"]) == (None, "This project is gone.")


def test_parse_needs_the_origin_and_refuses_an_unknown_kind_or_a_long_line():
    c = _client()
    assert c.post("/api/tasks/parse", json={"text": "x"}, headers={"Origin": "http://evil.example"}).status_code == 403
    assert c.post("/api/tasks/parse", json={"text": "x", "skip": ["colour"]}, headers=O).status_code == 422
    assert c.post("/api/tasks/parse", json={"text": "x" * 301}, headers=O).status_code == 422
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && ROOST_DATA_DIR=$(mktemp -d) ROOST_DESKS_DIR=$(mktemp -d) uv run pytest tests/test_quick_line.py -q`
Expected: FAIL at collection: `ModuleNotFoundError: No module named 'roost.tasks.quick_line'`.

- [ ] **Step 4: One rule for a typed due**

`roost/tasks/due.py`. Find:

```python
def _read_due(value: str, tz: ZoneInfo) -> Due:
    iso = _from_iso(value, tz)
    if iso is not None:
        return iso
    parsed = nl_time.parse(value, tz=tz)
    if parsed.due_date is None:
        raise ValueError(_UNREADABLE_DUE.format(text=value))
    if parsed.reminder_at is None or not nl_time.has_clock_time(value):
        return Due(parsed.due_date, None)
    return _moment(datetime.fromisoformat(parsed.reminder_at), tz)
```

Replace with:

```python
def due_from_parsed(parsed: nl_time.ParsedTime, text: str, tz: ZoneInfo = MADRID_TZ) -> Due:
    """The due ``nl_time`` read in ``text`` (``parsed.due_date`` set): a day, or a Madrid moment when
    the words name a time of day. The one rule for a typed due and the quick-add line (redesign P3)."""
    if parsed.reminder_at is None or not nl_time.has_clock_time(text):
        return Due(parsed.due_date, None)
    return _moment(datetime.fromisoformat(parsed.reminder_at), tz)


def _read_due(value: str, tz: ZoneInfo) -> Due:
    iso = _from_iso(value, tz)
    if iso is not None:
        return iso
    parsed = nl_time.parse(value, tz=tz)
    if parsed.due_date is None:
        raise ValueError(_UNREADABLE_DUE.format(text=value))
    return due_from_parsed(parsed, value, tz)
```

- [ ] **Step 5: The reader**

Create `roost/tasks/quick_line.py`:

```python
"""The quick-add line (redesign P3): ``Call plumber tomorrow 9am #Renovation €200 !high``.

The server reads the whole line, and the web draws its chips from this reading, so what is added is
exactly what was shown. In order:

- ``!urgent`` / ``!high`` / ``!medium`` / ``!low``: the priority (the first one; the word must stand
  alone, so "wow!high" stays in the title);
- ``€200``, ``200€``, ``$12.50``, ``£12,50``: the budget slice, in the money sign's currency, which must
  be the project's (H11: a slice needs a project and is in its currency);
- ``#Renovation``: the project, exact or ask (``ProjectService.resolve`` with ``change=True``: its id,
  its exact name or a unique part of one; a near miss is a question, never a guess, never a new project,
  never General). A project page passes its project as the default;
- the date, by the ``nl_time`` rules a typed due follows (``due_from_parsed``);
- what is left is the title.

``skip`` names the kinds the user dismissed from the chips: their words stay in the title."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any, Literal

from roost.constants import QUICK_LINE_CURRENCIES
from roost.money.amounts import amount_text, parse_amount
from roost.money.models import Project
from roost.money.project_store import is_general
from roost.projects.service import GENERAL_FIXED_TEXT, NO_PROJECT_TEXT, ProjectRefusal, ProjectService
from roost.talk.instructions import MADRID_TZ
from roost.tasks import nl_time
from roost.tasks.due import Due, due_from_parsed
from roost.tasks.models import Priority
from roost.tasks.store import SLICE_NEEDS_PROJECT

QuickKind = Literal["date", "project", "budget", "priority"]
SLICE_CURRENCY_TEXT = "“{name}” keeps its money in {currency}: write the budget in {currency}."
NO_PROJECT_HERE_TEXT = "No project is called “{name}”. Make it on the Projects tab first."
PROJECT_GONE_TEXT = "This project is gone."

_SIGNS = "".join(sign for sign, _ in QUICK_LINE_CURRENCIES)
_CURRENCY_OF = dict(QUICK_LINE_CURRENCIES)
_NUMBER = r"\d+(?:[.,]\d{1,2})?"
_PRIORITY = re.compile(r"(?<!\S)!(urgent|high|medium|low)(?!\S)", re.IGNORECASE)
_AMOUNT = re.compile(rf"(?<!\S)(?:([{_SIGNS}])\s?({_NUMBER})|({_NUMBER})\s?([{_SIGNS}]))(?!\S)")
_PROJECT = re.compile(r"(?<!\S)#([^\s#]+)")
_NO_DUE = Due(None, None)


@dataclass(frozen=True)
class LineWords:
    """The line with the priority, amount and project words taken out, and what they said."""

    rest: str
    priority: Priority | None = None
    amount: str | None = None           # "200", "12,50"
    currency: str | None = None         # the money sign's currency
    budget_words: str | None = None     # "€200", as typed
    project_ref: str | None = None      # "Renovation"
    project_words: str | None = None    # "#Renovation", as typed


@dataclass(frozen=True)
class QuickLine:
    title: str
    due: Due
    priority: Priority | None
    project: Project | None
    project_words: str | None
    project_question: str | None        # why the #project can't be used as typed
    budget: Decimal | None
    budget_words: str | None
    budget_problem: str | None          # why the amount can't be the slice

    @property
    def ready(self) -> bool:
        return bool(self.title) and self.project_question is None and self.budget_problem is None


def _cut(text: str, match: re.Match[str]) -> str:
    return f"{text[:match.start()]} {text[match.end():]}"


def read_words(text: str, skip: frozenset[str] = frozenset()) -> LineWords:
    """The pure part: priority, amount and project words, each the first of its kind."""
    words = LineWords(rest=text)
    found = None if "priority" in skip else _PRIORITY.search(words.rest)
    if found:
        words = replace(words, rest=_cut(words.rest, found), priority=found.group(1).lower())
    found = None if "budget" in skip else _AMOUNT.search(words.rest)
    if found:
        words = replace(words, rest=_cut(words.rest, found), amount=found.group(2) or found.group(3),
                        currency=_CURRENCY_OF[found.group(1) or found.group(4)], budget_words=found.group(0))
    found = None if "project" in skip else _PROJECT.search(words.rest)
    if found:
        words = replace(words, rest=_cut(words.rest, found), project_ref=found.group(1), project_words=found.group(0))
    return words


def read_date(text: str, skip: frozenset[str] = frozenset()) -> tuple[Due, str]:
    """The due the words name and the words left; a day past the calendar's ends reads as none."""
    if "date" in skip:
        return _NO_DUE, text
    try:
        parsed = nl_time.parse(text, tz=MADRID_TZ)
        if parsed.due_date is None:
            return _NO_DUE, text
        return due_from_parsed(parsed, text, MADRID_TZ), parsed.remaining
    except (OverflowError, ValueError):
        return _NO_DUE, text


async def _project(projects: ProjectService, user_id: str, ref: str | None,
                   default_id: str | None) -> tuple[Project | None, str | None]:
    wanted = ref if ref is not None else default_id
    if wanted is None:
        return None, None
    found = await projects.resolve(user_id, wanted, change=True)
    if isinstance(found, ProjectRefusal):
        if ref is None:
            return None, PROJECT_GONE_TEXT       # the page's own project, deleted meanwhile (or not the user's)
        unknown = str(found) == NO_PROJECT_TEXT.format(name=ref.strip())
        return None, NO_PROJECT_HERE_TEXT.format(name=ref.strip()) if unknown else str(found)
    if is_general(found):
        return None, GENERAL_FIXED_TEXT
    return found, None


def _budget(words: LineWords, project: Project | None) -> tuple[Decimal | None, str | None]:
    if words.amount is None:
        return None, None
    if project is None:
        return None, SLICE_NEEDS_PROJECT
    if words.currency != project.currency:
        return None, SLICE_CURRENCY_TEXT.format(name=project.name, currency=project.currency)
    try:
        return parse_amount(words.amount), None
    except ValueError as exc:
        return None, str(exc)


async def read_quick_line(projects: ProjectService, user_id: str, text: str, *, project_id: str | None = None,
                          skip: frozenset[str] = frozenset()) -> QuickLine:
    words = read_words(text, skip)
    due, rest = read_date(words.rest, skip)
    project, question = await _project(projects, user_id, words.project_ref, project_id)
    budget, problem = (None, None) if question is not None else _budget(words, project)
    return QuickLine(title=" ".join(rest.split()), due=due, priority=words.priority, project=project,
                     project_words=words.project_words, project_question=question, budget=budget,
                     budget_words=words.budget_words, budget_problem=problem)


def quick_line_out(line: QuickLine) -> dict[str, Any]:
    """``QuickLineOut``: what the web shows as chips, and what it sends to add the task."""
    project = None if line.project is None else {
        "id": line.project.id, "name": line.project.name, "currency": line.project.currency,
        "color": line.project.color,
    }
    return {
        "title": line.title, "due_date": line.due.due_date, "priority": line.priority, "project": project,
        "project_words": line.project_words, "project_question": line.project_question,
        "budget": None if line.budget is None else amount_text(line.budget), "budget_words": line.budget_words,
        "budget_problem": line.budget_problem, "ready": line.ready,
    }
```

- [ ] **Step 6: The route**

`roost/gateway/routes/task_detail.py`. Find:

```python
"""The task drawer's data over HTTP (redesign P3).

- ``GET /api/tasks/{id}``: one task (any status) with its money: the slice, what is spent and what is
  left, in its project's currency, and what is spent on each step (``roost.projects.numbers``; the web
  adds nothing up), plus every expense filed under it. ``money`` is ``null`` for a task with no project.
Another user's task is a 404."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from roost.gateway.deps import CurrentUser
from roost.gateway.routes.projects import task_money_out
```

Replace with:

```python
"""The task drawer's data and the quick-add line over HTTP (redesign P3).

- ``GET /api/tasks/{id}``: one task (any status) with its money: the slice, what is spent and what is
  left, in its project's currency, and what is spent on each step (``roost.projects.numbers``; the web
  adds nothing up), plus every expense filed under it. ``money`` is ``null`` for a task with no project.
- ``POST /api/tasks/parse``: how the server reads a quick-add line (``roost.tasks.quick_line``). It
  changes nothing; the web adds the task from this reading. A project page passes ``project_id``.
Another user's task is a 404; another user's project reads as no such project."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from roost.constants import MAX_RECORD_ID_LENGTH, QUICK_LINE_MAX_LENGTH
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.gateway.routes.projects import task_money_out
```

`roost/gateway/routes/task_detail.py`. Find:

```python
from roost.tasks.models import Task

detail_router = APIRouter(prefix="/api/tasks", tags=["tasks"])
TASK_NOT_FOUND_TEXT = "Task not found"
```

Replace with:

```python
from roost.tasks.models import Task
from roost.tasks.quick_line import quick_line_out, read_quick_line

detail_router = APIRouter(prefix="/api/tasks", tags=["tasks"])
TASK_NOT_FOUND_TEXT = "Task not found"
QUICK_KINDS = ("date", "project", "budget", "priority")


class QuickLineIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(max_length=QUICK_LINE_MAX_LENGTH)
    project_id: str | None = Field(default=None, max_length=MAX_RECORD_ID_LENGTH)    # a project page's own
    skip: list[Literal["date", "project", "budget", "priority"]] = Field(default_factory=list,
                                                                         max_length=len(QUICK_KINDS))
```

Append to the end of `roost/gateway/routes/task_detail.py`:

```python


@detail_router.post("/parse", dependencies=[RequireOrigin])
async def parse_quick_line(body: QuickLineIn, request: Request, user: CurrentUser) -> dict[str, Any]:
    line = await read_quick_line(request.app.state.projects, user.id, body.text, project_id=body.project_id,
                                 skip=frozenset(body.skip))
    return quick_line_out(line)
```

`POST /api/tasks/parse` cannot clash with a task's own routes: every POST on a task has a second segment after its id (`/complete`, `/fail`, `/keep`, `/steps`, `/comments`).

- [ ] **Step 7: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && ROOST_DATA_DIR=$(mktemp -d) ROOST_DESKS_DIR=$(mktemp -d) uv run pytest tests/test_quick_line.py tests/test_task_detail_api.py tests/test_task_time.py tests/test_dates_api.py tests/test_tasks_api.py -q`
Expected: PASS (`test_quick_line.py` 10 passed).

Then the whole suite with coverage, since Tasks 3 to 8 changed the server:

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && ROOST_DATA_DIR=$(mktemp -d) ROOST_DESKS_DIR=$(mktemp -d) uv run pytest --cov=roost --cov-fail-under=80 -q`
Expected: PASS, coverage above 80%.

- [ ] **Step 8: Commit**

Run:

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && \
git add roost/tasks/due.py roost/tasks/quick_line.py roost/gateway/routes/task_detail.py tests/test_quick_line.py && \
git commit -m "feat: the server reads a quick-add line into a date, a project, a budget slice and a priority"
```

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git status --short`
Expected: none of the files above is listed.

---
### Task 9: The web's data layer for steps, comments, the drawer and the quick add

The wire shapes and requests every later web task uses, with no screen yet: the drawer's task (`TaskDetailOut`: `task_out` plus `money` and `expenses`), a step removal's counts, a comment, the quick line's reading; `getTask`, the four step requests, `parseQuickLine`, the four comment requests; `ExpenseIn` learns `task_id` / `step_id`; `TaskPatchIn` learns `project_id`, `reminder_at` and `recurring`; `TasksChangedFrame` learns `"commented"`. The task components' numbers go in their own `constants.ts`, and a shared fixture file serves the task tests.

**Files:**
- Create: `web/src/api/comments.ts`, `web/src/components/tasks/constants.ts`, `web/tests/taskFixtures.ts`, `web/tests/tasksApi.test.ts`
- Modify: `web/src/api/types.ts`, `web/src/api/tasks.ts`, `web/src/api/money.ts`
- Test: `web/tests/tasksApi.test.ts`

**Interfaces:**
- Consumes: `apiRequest` (`web/src/api/client.ts`); the routes of Tasks 6, 7 and 8.
- Produces: `TaskDetailMoneyOut`, `TaskDetailOut`, `StepRemovalOut`, `CommentOut`, `QuickKind`, `QuickLineProjectOut`, `QuickLineOut`; `getTask`, `addStep`, `updateStep`, `moveStep`, `deleteStep`, `parseQuickLine`, `StepPatchIn`, `QuickLineIn`; `listComments`, `addComment`, `editComment`, `deleteComment`, `CommentIn`; the constants; `makeTask`, `makeTaskDetail`, `makeComment`, `makeQuickLine` (tests).

- [ ] **Step 1: Path guard**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && test -f roost/tasks/quick_line.py && test ! -e web/src/api/comments.ts && grep -c "parseQuickLine" web/src/api/tasks.ts`
Expected: `0`. Otherwise stop.

- [ ] **Step 2: Write the failing tests**

Create `web/tests/taskFixtures.ts`:

```ts
import type { CommentOut, QuickLineOut, TaskDetailOut, TaskOut } from "../src/api/types";

// Redesign P3's wire shapes for the task tests: a task, its drawer's detail, a comment, a quick line.

export function makeTask(overrides: Partial<TaskOut> = {}): TaskOut {
  return {
    id: "t1", title: "Fix the sink", description: null, category: null, priority: "medium", status: "todo",
    owner: "user", due_date: "2026-10-16T09:00:00+02:00", reminder_at: "2026-10-16T07:00:00+00:00",
    pre_reminders: ["2026-10-16T06:30:00+00:00"], recurring: null, recur_until: null, tags: [],
    steps: [{ id: "s-1", title: "Buy a washer", done: true }, { id: "s-2", title: "Fit it", done: false }],
    created_at: "2026-10-14T08:00:00+00:00", updated_at: "2026-10-14T08:00:00+00:00", completed_at: null,
    created_by_bot: null, tainted: false, project_id: null, allocated_budget: null, ...overrides,
  };
}

export function makeTaskDetail(overrides: Partial<TaskDetailOut> = {}): TaskDetailOut {
  return { ...makeTask(), money: null, expenses: [], ...overrides };
}

export function makeComment(overrides: Partial<CommentOut> = {}): CommentOut {
  return {
    id: "c1", task_id: "t1", step_id: null, author: "user", body: "The plumber comes at 9", tainted: false,
    created_at: "2026-10-15T08:00:00+00:00", edited_at: null, ...overrides,
  };
}

export function makeQuickLine(overrides: Partial<QuickLineOut> = {}): QuickLineOut {
  return {
    title: "", due_date: null, priority: null, project: null, project_words: null, project_question: null,
    budget: null, budget_words: null, budget_problem: null, ready: false, ...overrides,
  };
}
```

Create `web/tests/tasksApi.test.ts`:

```ts
import { beforeEach, describe, expect, it, vi } from "vitest";

const apiRequestMock = vi.fn();
vi.mock("../src/api/client", () => ({ apiRequest: (...args: unknown[]) => apiRequestMock(...args) }));
import { addStep, deleteStep, getTask, moveStep, parseQuickLine, updateStep } from "../src/api/tasks";
import { addComment, deleteComment, editComment, listComments } from "../src/api/comments";

beforeEach(() => apiRequestMock.mockReset().mockResolvedValue({}));

describe("the task drawer's requests (redesign P3)", () => {
  it("reads one task, and changes its steps by id, ids escaped", async () => {
    await getTask("t 1");
    expect(apiRequestMock).toHaveBeenLastCalledWith("GET", "/api/tasks/t%201");
    await addStep("t1", "Buy a washer");
    expect(apiRequestMock).toHaveBeenLastCalledWith("POST", "/api/tasks/t1/steps", { title: "Buy a washer" });
    await updateStep("t1", "s/1", { done: true });
    expect(apiRequestMock).toHaveBeenLastCalledWith("PATCH", "/api/tasks/t1/steps/s%2F1", { done: true });
    await moveStep("t1", "s-1", 0);
    expect(apiRequestMock).toHaveBeenLastCalledWith("POST", "/api/tasks/t1/steps/s-1/move", { position: 0 });
    await deleteStep("t1", "s-1");
    expect(apiRequestMock).toHaveBeenLastCalledWith("DELETE", "/api/tasks/t1/steps/s-1");
  });

  it("reads a quick-add line, with a project page's project and the removed chips", async () => {
    await parseQuickLine({ text: "Call plumber #Home", project_id: "p1", skip: ["date"] });
    expect(apiRequestMock).toHaveBeenLastCalledWith("POST", "/api/tasks/parse",
      { text: "Call plumber #Home", project_id: "p1", skip: ["date"] });
  });

  it("reads and writes a task's comments", async () => {
    await listComments("t1");
    expect(apiRequestMock).toHaveBeenLastCalledWith("GET", "/api/tasks/t1/comments");
    await addComment("t1", { body: "15 mm", step_id: "s-1" });
    expect(apiRequestMock).toHaveBeenLastCalledWith("POST", "/api/tasks/t1/comments", { body: "15 mm", step_id: "s-1" });
    await editComment("c1", "16 mm");
    expect(apiRequestMock).toHaveBeenLastCalledWith("PATCH", "/api/comments/c1", { body: "16 mm" });
    await deleteComment("c1");
    expect(apiRequestMock).toHaveBeenLastCalledWith("DELETE", "/api/comments/c1");
  });
});
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npx vitest run tests/tasksApi.test.ts`
Expected: FAIL: `Failed to resolve import "../src/api/comments"`.

- [ ] **Step 4: The shapes**

`web/src/api/types.ts`. Find:

```ts
// A project's page (GET /api/projects/{id}).
export interface ProjectDetailOut extends ProjectOut {
```

Replace with:

```ts
// A task's money in its drawer (redesign P3, GET /api/tasks/{id}): the TaskMoneyOut numbers in its
// project's currency, and what is spent on each step, by step id. The server reckons every number.
export interface TaskDetailMoneyOut extends TaskMoneyOut {
  currency: string;
  steps: Record<string, string>;
}

// One task as its drawer shows it: money is null for a task with no project; expenses are every
// expense filed under the task or one of its steps, void ones included.
export interface TaskDetailOut extends TaskOut {
  money: TaskDetailMoneyOut | null;
  expenses: ExpenseOut[];
}

// The task after a step was deleted: its expenses and comments moved to the whole task.
export interface StepRemovalOut extends TaskOut {
  moved_expenses: number;
  moved_comments: number;
}

// A comment on a task or one of its steps (redesign P3). `author` is "user" or a bot's id.
export interface CommentOut {
  id: string;
  task_id: string;
  step_id: string | null;
  author: string;
  body: string;
  tainted: boolean; // a bot wrote it after reading web content
  created_at: string;
  edited_at: string | null;
}

// The kinds of words the quick-add line reads; a removed chip's kind is skipped.
export type QuickKind = "date" | "project" | "budget" | "priority";

export interface QuickLineProjectOut {
  id: string;
  name: string;
  currency: string;
  color: string;
}

// How the server reads a quick-add line (POST /api/tasks/parse): what the chips show, and what is added.
export interface QuickLineOut {
  title: string;
  due_date: string | null;
  priority: TaskOut["priority"] | null;
  project: QuickLineProjectOut | null;
  project_words: string | null; // "#Renovation", as typed
  project_question: string | null; // why that project can't be used as typed
  budget: string | null; // the slice, "200.00", in the project's currency
  budget_words: string | null; // "€200", as typed
  budget_problem: string | null; // why that amount can't be the slice
  ready: boolean;
}

// A project's page (GET /api/projects/{id}).
export interface ProjectDetailOut extends ProjectOut {
```

`web/src/api/types.ts`. Find:

```ts
  change: "created" | "updated" | "completed" | "deleted" | "failed";
  task_id: string;
```

Replace with:

```ts
  change: "created" | "updated" | "completed" | "deleted" | "failed" | "commented";
  task_id: string;
```

- [ ] **Step 5: The requests**

`web/src/api/tasks.ts`. Find:

```ts
import { apiRequest } from "./client";
import type { TaskOut } from "./types";
```

Replace with:

```ts
import { apiRequest } from "./client";
import type { QuickKind, QuickLineOut, StepRemovalOut, TaskDetailOut, TaskOut } from "./types";
```

`web/src/api/tasks.ts`. Find:

```ts
  priority?: TaskOut["priority"];
  project_id?: string; // the project it belongs to (a project page's Tasks tab)
}

// allocated_budget is the task's budget slice ("250.00", or null to clear it); it needs a project (H11).
export type TaskPatchIn = Partial<
  Pick<TaskOut, "title" | "description" | "category" | "priority" | "due_date" | "allocated_budget">
>;
```

Replace with:

```ts
  priority?: TaskOut["priority"];
  project_id?: string; // the project it belongs to (a project page's Tasks tab)
  allocated_budget?: string; // its budget slice ("200.00"), in that project's currency (H11)
}

// allocated_budget is the task's budget slice ("250.00", or null to clear it); it needs a project (H11).
// reminder_at takes words or ISO on Madrid time (null clears it); recurring is a cron (null: no repeat).
export type TaskPatchIn = Partial<
  Pick<TaskOut, "title" | "description" | "category" | "priority" | "due_date" | "allocated_budget"
    | "project_id" | "reminder_at" | "recurring">
>;

// A step change (redesign P3): a new title, a tick or an untick.
export interface StepPatchIn {
  title?: string;
  done?: boolean;
}

// A quick-add line to read (redesign P3). A project page sends its project; `skip` holds removed chips.
export interface QuickLineIn {
  text: string;
  project_id?: string;
  skip?: QuickKind[];
}

const taskPath = (taskId: string) => `/api/tasks/${encodeURIComponent(taskId)}`;
const stepPath = (taskId: string, stepId: string) => `${taskPath(taskId)}/steps/${encodeURIComponent(stepId)}`;
```

Append to the end of `web/src/api/tasks.ts`:

```ts

// The drawer's task: its money (per task and per step) and its expenses (redesign P3).
export function getTask(taskId: string): Promise<TaskDetailOut> {
  return apiRequest<TaskDetailOut>("GET", taskPath(taskId));
}

export function addStep(taskId: string, title: string): Promise<TaskOut> {
  return apiRequest<TaskOut>("POST", `${taskPath(taskId)}/steps`, { title });
}

export function updateStep(taskId: string, stepId: string, patch: StepPatchIn): Promise<TaskOut> {
  return apiRequest<TaskOut>("PATCH", stepPath(taskId, stepId), patch);
}

// position 0 is first; past the end puts it last.
export function moveStep(taskId: string, stepId: string, position: number): Promise<TaskOut> {
  return apiRequest<TaskOut>("POST", `${stepPath(taskId, stepId)}/move`, { position });
}

export function deleteStep(taskId: string, stepId: string): Promise<StepRemovalOut> {
  return apiRequest<StepRemovalOut>("DELETE", stepPath(taskId, stepId));
}

// How the server reads a quick-add line; it changes nothing.
export function parseQuickLine(input: QuickLineIn): Promise<QuickLineOut> {
  return apiRequest<QuickLineOut>("POST", "/api/tasks/parse", input);
}
```

`web/src/api/money.ts`. Find:

```ts
  spent_at?: string; // "YYYY-MM-DD", a Madrid day; none is today (the gateway refuses a future day)
}
```

Replace with:

```ts
  spent_at?: string; // "YYYY-MM-DD", a Madrid day; none is today (the gateway refuses a future day)
  task_id?: string; // a task's drawer (redesign P3): filed under the task; no project named → the task's
  step_id?: string; // …or under one of its steps
}
```

Create `web/src/api/comments.ts`:

```ts
import { apiRequest } from "./client";
import type { CommentOut } from "./types";

// Comments on the user's tasks (redesign P3). Bots comment through their tools; here the user reads
// the thread and writes, edits or deletes their own (the gateway refuses a bot's comment with 403).

export interface CommentIn {
  body: string;
  step_id?: string; // one of the task's steps; none is the whole task
}

const threadPath = (taskId: string) => `/api/tasks/${encodeURIComponent(taskId)}/comments`;
const commentPath = (commentId: string) => `/api/comments/${encodeURIComponent(commentId)}`;

export function listComments(taskId: string): Promise<CommentOut[]> {
  return apiRequest<CommentOut[]>("GET", threadPath(taskId));
}

export function addComment(taskId: string, input: CommentIn): Promise<CommentOut> {
  return apiRequest<CommentOut>("POST", threadPath(taskId), input);
}

export function editComment(commentId: string, body: string): Promise<CommentOut> {
  return apiRequest<CommentOut>("PATCH", commentPath(commentId), { body });
}

export function deleteComment(commentId: string): Promise<void> {
  return apiRequest<void>("DELETE", commentPath(commentId));
}
```

Create `web/src/components/tasks/constants.ts`:

```ts
// The task drawer's and the quick add's numbers (redesign P3). The limits are the gateway's
// (roost/constants.py MAX_STEP_TITLE_LENGTH, MAX_COMMENT_LENGTH, QUICK_LINE_MAX_LENGTH): the inputs stop
// there, and the gateway checks again.
export const MAX_STEP_TITLE = 200;
export const MAX_COMMENT = 4000;
export const MAX_QUICK_LINE = 300;
export const QUICK_PARSE_DELAY_MS = 250; // the quick add asks the server this long after the last key
export const REPEAT_DEFAULT_TIME = "09:00"; // a repeat for a task due on a day with no time
export const TASK_PARAM = "task"; // the open drawer's task id in the address (?task=…)
export const COMMENT_ROWS = 6; // the comment box grows to this many lines, then scrolls
```

- [ ] **Step 6: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npx vitest run tests/tasksApi.test.ts tests/datesApi.test.ts && npx tsc --noEmit -p tsconfig.app.json`
Expected: PASS (`tasksApi.test.ts` 3 passed), and no type error.

- [ ] **Step 7: Commit**

Run:

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && \
git add web/src/api/types.ts web/src/api/tasks.ts web/src/api/money.ts web/src/api/comments.ts \
  web/src/components/tasks/constants.ts web/tests/taskFixtures.ts web/tests/tasksApi.test.ts && \
git commit -m "feat: the web's requests for a task's drawer, steps, comments and the quick-add line"
```

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git status --short`
Expected: none of the files above is listed.

---
### Task 10: Structured task rows, and the task drawer with its details

Design P3 "Task rows are structured" and "The task drawer" (its first part), Design meets code 10 and 13.
- **Rows** (`TaskRow`, rewritten): the checkbox; the title as a button whose `::after` covers the row, so a click anywhere opens the drawer; chips for the due, the **project** (the Board names it; a project's page does not), the **steps done** ("1/2 steps"), priority, list, repeat, slice and spending, maker and web mark; and a menu ("More for <title>": Open, Mark failed) that shows on hover or keyboard focus. Reminder chips move into the drawer.
- **The drawer** (`web/src/components/tasks/TaskDrawer.tsx`, default export, reached only through `React.lazy` from `TasksBoard`): a P1 `Sheet` titled with the task, opened at `?task=<id>` (`useOpenTask`), reloading on `tasks_changed` and `money_changed`. A task deleted meanwhile shows "This task is gone…" instead of an error. Its foot has Mark failed and a two-step Delete. Tasks 11–13 add Steps, Money, Comments and Activity under the details.
- **Details** (`TaskDetailsForm`, replacing P1's inline `TaskEditForm`): Title, List, Priority, Due, Reminder (shown on Madrid's clock, `wallText`), Repeat (`repeat.ts`: Never, Every day, Every weekday, Every week, Every month, and Custom for a cron a bot set), Project (live projects but General; an archived one only if it is the task's own) and Budget slice. Save sends only what changed, and is off until something did; when the task changes elsewhere and nothing was touched, the fields follow it, and once the user types they keep what was typed.

**Files:**
- Create: `web/src/components/tasks/{progress,repeat,useOpenTask,useProjects}.ts`, `web/src/components/tasks/{TaskDrawer,TaskDetailsForm}.tsx`, `web/src/styles/tasks.css`, `web/tests/{TaskDrawer.test.tsx,repeat.test.ts}`
- Modify: `web/src/components/board/TaskRow.tsx` (rewritten), `web/src/components/board/TasksBoard.tsx` (rewritten), `web/src/components/board/taskLimits.ts`, `web/src/ui/date/dates.ts`, `web/src/styles/board.css`, `web/src/styles/projects.css`, `web/src/styles.css`
- Delete: `web/src/components/board/TaskEditForm.tsx`
- Test: `web/tests/TasksBoard.test.tsx` (rewritten), `web/tests/TaskDrawer.test.tsx`, `web/tests/repeat.test.ts`, `web/tests/dates.test.ts`, `web/tests/bundleGuard.test.ts`; `web/tests/{Board,Project,tokens}.test.ts(x)` stay green unchanged

**Interfaces:**
- Consumes: Task 2's `Sheet` and `Menu`; Task 9's `getTask`, `TaskDetailOut`, `TaskPatchIn`, `TASK_PARAM`, `REPEAT_DEFAULT_TIME`, `makeTask` / `makeTaskDetail`; `listProjects`, `isGeneral`; `Field`, `Input`, `Select`, `Button`, `DateTimePicker`, `pickerText`, `dueParts`, `todayIn`; `readAmount`, `AMOUNT_HELP`, `formatDueChip`, `MadeByChip`, `WebContentChip`.
- Produces: `wallText`; `MAX_LIST`; `StepProgress`, `stepProgress`, `stepsText`; `RepeatKind`, `REPEAT_OPTIONS`, `CUSTOM_OPTION`, `repeatOf`, `cronFor`; `useOpenTask`; `useProjects`; `TaskRow` with `projectName`, `onOpen`, `onFail`; `TaskDrawer` (default) and `TaskDrawerProps`; `TaskDetailsForm`, `changesOf`; the `tasks.css` classes `task-row__open`, `task-row__actions`, `board-chip--project`, `board-chip--steps`, `task-drawer`, `task-drawer__section`, `task-drawer__heading`, `task-details`. Tasks 11–13 add sections to the drawer's body; Task 14 replaces `TaskAddForm`.

- [ ] **Step 1: Path guard**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && test -f web/src/api/comments.ts && test ! -e web/src/components/tasks/TaskDrawer.tsx && test -f web/src/components/board/TaskEditForm.tsx && echo ready`
Expected: `ready`. Otherwise stop.

- [ ] **Step 2: Write the failing tests**

Replace the whole of `web/tests/TasksBoard.test.tsx` with:

```tsx
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { TasksBoard, type TasksBoardProps } from "../src/components/board/TasksBoard";
import type { BotOut } from "../src/api/types";
import { makeBot } from "./fixtures";
import { makeProject } from "./projectFixtures";
import { makeTask as task, makeTaskDetail } from "./taskFixtures";

const listTasksMock = vi.fn();
const createTaskMock = vi.fn();
const completeTaskMock = vi.fn();
const keepTaskMock = vi.fn();
const failTaskMock = vi.fn();
const getTaskMock = vi.fn();
vi.mock("../src/api/tasks", () => ({
  failTask: (...a: unknown[]) => failTaskMock(...a),
  keepTask: (...a: unknown[]) => keepTaskMock(...a),
  listTasks: (...a: unknown[]) => listTasksMock(...a),
  createTask: (...a: unknown[]) => createTaskMock(...a),
  completeTask: (...a: unknown[]) => completeTaskMock(...a),
  getTask: (...a: unknown[]) => getTaskMock(...a),
  updateTask: vi.fn(),
  deleteTask: vi.fn(),
}));
const listProjectsMock = vi.fn();
vi.mock("../src/api/projects", () => ({ listProjects: (...a: unknown[]) => listProjectsMock(...a) }));
const BOTS: Record<string, BotOut> = { "bot-1": makeBot({ id: "bot-1", name: "Helper" }) };
let live = { bots: BOTS, boardVersion: { tasks: 0, money: 0 } };
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => live }));
const parseDateMock = vi.fn().mockResolvedValue({ due_date: null });
vi.mock("../src/api/dates", () => ({ parseDate: (text: string) => parseDateMock(text) }));

function Where() {
  const location = useLocation();
  return <output aria-label="Address">{location.search}</output>;
}

function board(props: TasksBoardProps = {}) {
  const tree = () => (
    <MemoryRouter initialEntries={["/board?tab=tasks"]}>
      <TasksBoard {...props} />
      <Where />
    </MemoryRouter>
  );
  const view = render(tree());
  return { ...view, again: () => view.rerender(tree()) };
}

beforeEach(() => {
  live = { bots: BOTS, boardVersion: { tasks: 0, money: 0 } };
  for (const mock of [listTasksMock, createTaskMock, completeTaskMock, keepTaskMock, failTaskMock, getTaskMock]) {
    mock.mockReset();
  }
  listProjectsMock.mockReset().mockResolvedValue([makeProject({ id: "p1", name: "Renovation" })]);
  listTasksMock.mockResolvedValue([
    task({ project_id: "p1", created_by_bot: "bot-1" }),
    task({ id: "t2", title: "Buy the gadget", due_date: null, reminder_at: null, steps: [], tainted: true }),
  ]);
  getTaskMock.mockResolvedValue(makeTaskDetail());
});
afterEach(() => { cleanup(); vi.useRealTimers(); });

const rowOf = async (title: string) => (await screen.findByText(title)).closest("li") as HTMLElement;

describe("TasksBoard rows (redesign P3)", () => {
  it("shows each task's due, project, steps done and maker as chips, and marks web content", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-10-15T10:00:00Z"));
    board();
    const sink = await rowOf("Fix the sink");
    expect(within(sink).getByText("in 21h")).toHaveClass("board-chip--soon");
    expect(await within(sink).findByText("Renovation")).toHaveClass("board-chip--project");
    expect(within(sink).getByText("1/2 steps")).toBeInTheDocument();
    expect(within(sink).getByText("by Helper")).toBeInTheDocument();
    expect(within(sink).queryByText(/^Reminder /)).not.toBeInTheDocument();
    expect(within(await rowOf("Buy the gadget")).getByText("from web content")).toBeInTheDocument();
    expect(listTasksMock).toHaveBeenCalledWith("open");
    expect(listProjectsMock).toHaveBeenCalledWith(true);
  });

  it("a click on the title opens the task's drawer at ?task=, and Close puts the address back", async () => {
    const user = userEvent.setup();
    board();
    await user.click(await screen.findByRole("button", { name: "Fix the sink" }));
    expect(screen.getByRole("status", { name: "Address" })).toHaveTextContent("?tab=tasks&task=t1");
    expect(await screen.findByRole("dialog", { name: "Fix the sink" })).toBeInTheDocument();
    expect(getTaskMock).toHaveBeenCalledWith("t1");
    await user.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("status", { name: "Address" })).toHaveTextContent(/^\?tab=tasks$/);
  });

  it("the row's menu opens the drawer or marks the task failed", async () => {
    failTaskMock.mockResolvedValue(task({ status: "failed" }));
    const user = userEvent.setup();
    board();
    await user.click(await screen.findByRole("button", { name: "More for Fix the sink" }));
    await user.click(await screen.findByRole("menuitem", { name: "Mark failed" }));
    expect(failTaskMock).toHaveBeenCalledWith("t1");
    await waitFor(() => expect(listTasksMock).toHaveBeenCalledTimes(2));
    await user.click(screen.getByRole("button", { name: "More for Fix the sink" }));
    await user.click(await screen.findByRole("menuitem", { name: "Open" }));
    expect(await screen.findByRole("dialog", { name: "Fix the sink" })).toBeInTheDocument();
  });

  it("completes a task, and offers Keep only on a web-made one", async () => {
    completeTaskMock.mockResolvedValue(task({ status: "done" }));
    keepTaskMock.mockResolvedValue(task({ id: "t2", tainted: false }));
    const user = userEvent.setup();
    board();
    expect(within(await rowOf("Fix the sink")).queryByRole("button", { name: /^Keep/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: "Complete Fix the sink" }));
    expect(completeTaskMock).toHaveBeenCalledWith("t1");
    await user.click(within(await rowOf("Buy the gadget")).getByRole("button", { name: "Keep Buy the gadget as yours" }));
    expect(keepTaskMock).toHaveBeenCalledWith("t2");
  });

  it("reloads when a tasks_changed frame arrives", async () => {
    const view = board();
    await screen.findByText("Fix the sink");
    live = { bots: BOTS, boardVersion: { tasks: 1, money: 0 } };
    view.again();
    await waitFor(() => expect(listTasksMock).toHaveBeenCalledTimes(2));
  });

  it("says nothing is open in the shared words", async () => {
    listTasksMock.mockResolvedValue([]);
    board();
    expect(await screen.findByText("Nothing open. Add a task, or ask any bot.")).toBeInTheDocument();
  });

  it("adds a task from words and reloads", async () => {
    createTaskMock.mockResolvedValue(task({ id: "t3", title: "Buy milk" }));
    const user = userEvent.setup();
    board();
    await user.type(await screen.findByLabelText("New task"), "Buy milk");
    await user.type(screen.getByLabelText("When"), "tomorrow at 9");
    await user.click(screen.getByRole("button", { name: "Add" }));
    expect(createTaskMock).toHaveBeenCalledWith({ title: "Buy milk", due_date: "tomorrow at 9" });
    await waitFor(() => expect(listTasksMock).toHaveBeenCalledTimes(2));
  });
});

describe("TasksBoard on a project's page", () => {
  it("lists every task of the project, open first, with no project chip and a red chip on a failed one", async () => {
    listTasksMock.mockResolvedValue([
      task({ id: "t3", title: "Fix the fence", status: "failed", project_id: "p1", completed_at: "2026-10-14T18:00:00+00:00" }),
      task({ project_id: "p1" }),
    ]);
    board({ projectId: "p1", currency: "EUR" });
    const fence = await rowOf("Fix the fence");
    expect(within(fence).getByText("failed")).toHaveClass("board-chip--failed");
    expect(within(fence).getByRole("checkbox", { name: "Complete Fix the fence" })).toBeDisabled();
    const titles = screen.getAllByRole("listitem").map((item) => item.querySelector(".task-row__title")?.textContent);
    expect(titles).toEqual(["Fix the sink", "Fix the fence"]);
    expect(within(await rowOf("Fix the sink")).queryByText("Renovation")).not.toBeInTheDocument();
    expect(listTasksMock).toHaveBeenCalledWith("all", { projectId: "p1" });
    expect(listProjectsMock).not.toHaveBeenCalled();
  });

  it("adds a task into the project", async () => {
    createTaskMock.mockResolvedValue(task({ id: "t4", title: "Buy seeds", project_id: "p1" }));
    const user = userEvent.setup();
    board({ projectId: "p1", currency: "EUR" });
    await user.type(await screen.findByLabelText("New task"), "Buy seeds");
    await user.click(screen.getByRole("button", { name: "Add" }));
    expect(createTaskMock).toHaveBeenCalledWith({ title: "Buy seeds", due_date: null, project_id: "p1" });
  });

  it("shows a task's slice, what is spent and what is left, as the server reckons them", async () => {
    listTasksMock.mockResolvedValue([
      task({ project_id: "p1", allocated_budget: "100.00" }),
      task({ id: "t2", title: "Fix the fence", project_id: "p1", allocated_budget: "100.00" }),
      task({ id: "t3", title: "Buy seeds", project_id: "p1" }),
    ]);
    const money = {
      t1: { planned: "100.00", spent: "80.00", left: "20.00" },
      t2: { planned: "100.00", spent: "130.00", left: "-30.00" },
      t3: { planned: null, spent: "0.00", left: null },
    };
    board({ projectId: "p1", currency: "EUR", money });
    expect(within(await rowOf("Fix the sink")).getByText("budget €100.00")).toBeInTheDocument();
    expect(within(await rowOf("Fix the sink")).getByText("€80.00 spent, €20.00 left")).toBeInTheDocument();
    expect(within(await rowOf("Fix the fence")).getByText("€130.00 spent, over by €30.00")).toBeInTheDocument();
    expect(within(await rowOf("Buy seeds")).queryByText(/spent/)).toBeNull();
  });
});
```

Create `web/tests/TaskDrawer.test.tsx`:

```tsx
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import TaskDrawer from "../src/components/tasks/TaskDrawer";
import { ApiError } from "../src/api/client";
import { makeProject } from "./projectFixtures";
import { makeTask, makeTaskDetail } from "./taskFixtures";

const getTaskMock = vi.fn();
const updateTaskMock = vi.fn();
const failTaskMock = vi.fn();
const deleteTaskMock = vi.fn();
vi.mock("../src/api/tasks", () => ({
  getTask: (...a: unknown[]) => getTaskMock(...a),
  updateTask: (...a: unknown[]) => updateTaskMock(...a),
  failTask: (...a: unknown[]) => failTaskMock(...a),
  deleteTask: (...a: unknown[]) => deleteTaskMock(...a),
}));
const listProjectsMock = vi.fn();
vi.mock("../src/api/projects", () => ({ listProjects: (...a: unknown[]) => listProjectsMock(...a) }));
let live = { bots: {}, boardVersion: { tasks: 0, money: 0 } };
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => live }));
vi.mock("../src/api/dates", () => ({ parseDate: vi.fn().mockResolvedValue({ due_date: null }) }));

const onClose = vi.fn();
const drawer = () => <TaskDrawer taskId="t1" onClose={onClose} />;
const details = () => screen.getByRole("form", { name: "Details" });

beforeEach(() => {
  live = { bots: {}, boardVersion: { tasks: 0, money: 0 } };
  for (const mock of [getTaskMock, updateTaskMock, failTaskMock, deleteTaskMock, onClose]) mock.mockReset();
  getTaskMock.mockResolvedValue(makeTaskDetail());
  updateTaskMock.mockImplementation(async (_id: string, patch: object) => makeTask({ ...patch, updated_at: "later" }));
  listProjectsMock.mockReset().mockResolvedValue([
    makeProject({ id: "p1", name: "Renovation" }), makeProject({ id: "p2", name: "Old shed", status: "archived" }),
  ]);
});
afterEach(() => cleanup());

describe("the task drawer's details (redesign P3)", () => {
  it("opens on the task, and saves only what changed", async () => {
    const user = userEvent.setup();
    render(drawer());
    expect(await screen.findByRole("dialog", { name: "Fix the sink" })).toBeInTheDocument();
    const save = within(details()).getByRole("button", { name: "Save changes" });
    expect(save).toBeDisabled();
    const title = within(details()).getByLabelText("Title");
    await user.clear(title);
    await user.type(title, "Fix the kitchen sink");
    await user.click(within(details()).getByRole("combobox", { name: "Priority" }));
    await user.click(await screen.findByRole("option", { name: "High" }));
    await user.click(save);
    expect(updateTaskMock).toHaveBeenCalledWith("t1", { title: "Fix the kitchen sink", priority: "high" });
    await waitFor(() => expect(getTaskMock).toHaveBeenCalledTimes(2));
    expect(within(details()).getByRole("button", { name: "Save changes" })).toBeDisabled();
  });

  it("shows the reminder on Madrid's clock and sets a weekly repeat on the due's weekday", async () => {
    const user = userEvent.setup();
    render(drawer());
    await screen.findByRole("dialog", { name: "Fix the sink" });
    expect(within(details()).getByLabelText("Due")).toHaveValue("2026-10-16 09:00");
    const reminder = within(details()).getByLabelText("Reminder");
    expect(reminder).toHaveValue("2026-10-16 09:00");
    await user.clear(reminder);
    await user.type(reminder, "2026-10-15 20:00");
    await user.click(within(details()).getByRole("combobox", { name: "Repeat" }));
    await user.click(await screen.findByRole("option", { name: "Every week" }));
    await user.click(within(details()).getByRole("button", { name: "Save changes" }));
    expect(updateTaskMock).toHaveBeenCalledWith("t1", { reminder_at: "2026-10-15 20:00", recurring: "0 9 * * 5" });
  });

  it("keeps a bot's custom repeat, and clears a repeat with Never", async () => {
    getTaskMock.mockResolvedValue(makeTaskDetail({ recurring: "0 9 * * 1,3" }));
    const user = userEvent.setup();
    render(drawer());
    await screen.findByRole("dialog", { name: "Fix the sink" });
    const repeat = within(details()).getByRole("combobox", { name: "Repeat" });
    expect(repeat).toHaveTextContent("Custom");
    await user.click(repeat);
    await user.click(await screen.findByRole("option", { name: "Never" }));
    await user.click(within(details()).getByRole("button", { name: "Save changes" }));
    expect(updateTaskMock).toHaveBeenCalledWith("t1", { recurring: null });
  });

  it("moves the task into an active project with a slice, and refuses a slice it can't read", async () => {
    const user = userEvent.setup();
    render(drawer());
    await screen.findByRole("dialog", { name: "Fix the sink" });
    await user.click(within(details()).getByRole("combobox", { name: "Project" }));
    expect(screen.queryByRole("option", { name: "Old shed" })).not.toBeInTheDocument();
    await user.click(await screen.findByRole("option", { name: "Renovation" }));
    const slice = within(details()).getByLabelText("Budget slice");
    await user.type(slice, "lots");
    await user.click(within(details()).getByRole("button", { name: "Save changes" }));
    expect(await within(details()).findByRole("alert")).toHaveTextContent("Enter an amount like 12,50.");
    expect(updateTaskMock).not.toHaveBeenCalled();
    await user.clear(slice);
    await user.type(slice, "200");
    await user.click(within(details()).getByRole("button", { name: "Save changes" }));
    expect(updateTaskMock).toHaveBeenCalledWith("t1", { project_id: "p1", allocated_budget: "200.00" });
  });

  it("follows a change made elsewhere until the user types, then keeps what they typed", async () => {
    const user = userEvent.setup();
    const view = render(drawer());
    await screen.findByRole("dialog", { name: "Fix the sink" });
    getTaskMock.mockResolvedValue(makeTaskDetail({ title: "Fix the sink today", updated_at: "v2" }));
    live = { bots: {}, boardVersion: { tasks: 1, money: 0 } };
    view.rerender(drawer());
    await waitFor(() => expect(within(details()).getByLabelText("Title")).toHaveValue("Fix the sink today"));
    await user.type(within(details()).getByLabelText("List"), "Home");
    getTaskMock.mockResolvedValue(makeTaskDetail({ title: "Fix it", updated_at: "v3" }));
    live = { bots: {}, boardVersion: { tasks: 2, money: 0 } };
    view.rerender(drawer());
    await screen.findByRole("dialog", { name: "Fix it" });
    expect(within(details()).getByLabelText("List")).toHaveValue("Home");
    expect(within(details()).getByLabelText("Title")).toHaveValue("Fix the sink today");
  });
});

describe("the task drawer's actions", () => {
  it("marks an open task failed", async () => {
    failTaskMock.mockResolvedValue(makeTask({ status: "failed" }));
    const user = userEvent.setup();
    render(drawer());
    await user.click(await screen.findByRole("button", { name: "Mark failed" }));
    expect(failTaskMock).toHaveBeenCalledWith("t1");
  });

  it("deletes in two steps, then closes", async () => {
    deleteTaskMock.mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(drawer());
    await user.click(await screen.findByRole("button", { name: "Delete task" }));
    expect(deleteTaskMock).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Delete Fix the sink for good" }));
    expect(deleteTaskMock).toHaveBeenCalledWith("t1");
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  it("says a task deleted elsewhere is gone, and shows the server's reason for any other failure", async () => {
    getTaskMock.mockRejectedValue(new ApiError(404, "Task not found"));
    const first = render(drawer());
    expect(await screen.findByText("This task is gone. It may have been deleted somewhere else.")).toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "Task not found" })).toBeInTheDocument();
    first.unmount();
    getTaskMock.mockRejectedValue(new ApiError(500, "The database is busy."));
    render(drawer());
    expect(await screen.findByRole("alert")).toHaveTextContent("The database is busy.");
  });
});
```

Create `web/tests/repeat.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { cronFor, repeatOf } from "../src/components/tasks/repeat";

describe("a task's repeat (redesign P3)", () => {
  it("names the crons the drawer builds, and anything else Custom", () => {
    expect(repeatOf(null)).toBe("never");
    expect(repeatOf("0 9 * * *")).toBe("daily");
    expect(repeatOf("30 18 * * 1-5")).toBe("weekdays");
    expect(repeatOf("0 9 * * 5")).toBe("weekly");
    expect(repeatOf("0 9 16 * *")).toBe("monthly");
    expect(repeatOf("0 9 * * 1,3")).toBe("custom");
    expect(repeatOf("*/15 * * * *")).toBe("custom");
  });

  it("builds each repeat at the due's wall time, on its weekday or day of the month", () => {
    const due = "2026-10-16T18:30:00+02:00"; // a Friday, 18:30 in Madrid
    expect(cronFor("daily", due)).toBe("30 18 * * *");
    expect(cronFor("weekdays", due)).toBe("30 18 * * 1-5");
    expect(cronFor("weekly", due)).toBe("30 18 * * 5");
    expect(cronFor("monthly", due)).toBe("30 18 16 * *");
    expect(cronFor("never", due)).toBeNull();
    expect(cronFor("custom", due)).toBeNull();
  });

  it("uses 09:00 for a due with no time, and round-trips through repeatOf", () => {
    expect(cronFor("weekly", "2026-10-19")).toBe("0 9 * * 1");
    for (const kind of ["daily", "weekdays", "weekly", "monthly"] as const) {
      expect(repeatOf(cronFor(kind, "2026-10-19 07:05"))).toBe(kind);
    }
  });
});
```

`web/tests/dates.test.ts`. Find:

```ts
  addDays, dateToDay, dayText, dayToDate, dueParts, friendlyDue, isIsoDay, joinDue, nextMonday, pickedParts, pickerText,
  todayIn,
} from "../src/ui/date/dates";
```

Replace with:

```ts
  addDays, dateToDay, dayText, dayToDate, dueParts, friendlyDue, isIsoDay, joinDue, nextMonday, pickedParts, pickerText,
  todayIn, wallText,
} from "../src/ui/date/dates";
```

`web/tests/dates.test.ts`. Find:

```ts
  it("the calendar's dates round-trip to the same day in any zone", () => {
```

Replace with:

```ts
  it("shows an instant as Madrid's day and wall time, in winter and summer", () => {
    expect(wallText("2026-11-30T19:00:00+00:00")).toBe("2026-11-30 20:00");
    expect(wallText("2026-07-01T07:00:00Z")).toBe("2026-07-01 09:00");
    expect(wallText("2026-10-24T23:30:00Z")).toBe("2026-10-25 01:30");
    expect(wallText(null)).toBe("");
    expect(wallText("not a time")).toBe("");
  });

  it("the calendar's dates round-trip to the same day in any zone", () => {
```

`web/tests/bundleGuard.test.ts`. Find:

```ts
// Final-review fix: the chat preloads the chunk when it opens;
```

Replace with:

```ts
// Redesign P3: the task drawer, and everything only it uses, is its own chunk.
  it("nothing imports the task drawer statically: the tasks board reaches it through React.lazy only", () => {
    const importers = sources(SRC)
      .filter((path) => staticImports(path).some((spec) => /(^|\/)TaskDrawer$/.test(spec)))
      .map((path) => relative(SRC, path));
    expect(importers).toEqual([]);
    const board = readFileSync(join(SRC, "components/board/TasksBoard.tsx"), "utf8");
    expect(board).toContain('lazy(() => import("../tasks/TaskDrawer"))');
  });

  // Final-review fix: the chat preloads the chunk when it opens;
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npx vitest run tests/TasksBoard.test.tsx tests/TaskDrawer.test.tsx tests/repeat.test.ts tests/dates.test.ts tests/bundleGuard.test.ts`
Expected: FAIL: `TaskDrawer.test.tsx` and `repeat.test.ts` cannot resolve `../src/components/tasks/…`; `TasksBoard.test.tsx` fails on the project and steps chips, the title button, the menu and the address (`useLocation` sees no `?task=`); `dates.test.ts` on `wallText is not a function`; the bundle guard finds no `lazy(() => import("../tasks/TaskDrawer"))`.

- [ ] **Step 4: Small helpers: Madrid wall time, a list's limit, progress, repeats, the open task, the projects**

`web/src/ui/date/dates.ts`. Find:

```ts
/** A stored due (TaskOut.due_date) as the picker's text: its Madrid day and wall time as written. */
```

Replace with:

```ts
const WALL_FORMAT = new Intl.DateTimeFormat("en-CA", {
  timeZone: APP_TIME_ZONE, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
  hourCycle: "h23",
});

/** An instant (a UTC ISO time such as TaskOut.reminder_at) as the picker's text: Madrid's day and wall
 * time, "2026-11-30 20:00". "" for no instant or one that is not a time. */
export function wallText(iso: string | null): string {
  if (!iso) return "";
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return "";
  const parts = WALL_FORMAT.formatToParts(when);
  const part = (type: Intl.DateTimeFormatPartTypes) => parts.find((p) => p.type === type)?.value ?? "";
  return `${part("year")}-${part("month")}-${part("day")} ${part("hour")}:${part("minute")}`;
}

/** A stored due (TaskOut.due_date) as the picker's text: its Madrid day and wall time as written. */
```

`web/src/components/board/taskLimits.ts`. Find:

```ts
export const MAX_TITLE = 200;
```

Replace with:

```ts
export const MAX_TITLE = 200;
export const MAX_LIST = 60; // a task's list (roost/constants.py MAX_TASK_CATEGORY_LENGTH)
```

Create `web/src/components/tasks/progress.ts`:

```ts
import type { TaskStepOut } from "../../api/types";

// A task's steps done out of all of them (redesign P3): the row's chip and the drawer's bar.
export interface StepProgress {
  done: number;
  total: number;
}

export function stepProgress(steps: readonly TaskStepOut[]): StepProgress {
  return { done: steps.filter((step) => step.done).length, total: steps.length };
}

/** "2/5 steps", or null for a task with no steps. */
export function stepsText(steps: readonly TaskStepOut[]): string | null {
  const { done, total } = stepProgress(steps);
  return total === 0 ? null : `${done}/${total} steps`;
}
```

Create `web/src/components/tasks/repeat.ts`:

```ts
import type { SelectOption } from "../../ui/Select";
import { dueParts, pickerText, todayIn } from "../../ui/date/dates";
import { REPEAT_DEFAULT_TIME } from "./constants";

// A task's repeat as the drawer offers it (redesign P3). The gateway stores a cron on Madrid time
// (roost/tasks/recurrence.py); the drawer builds one from the due's day and time, and names the crons it
// built. A cron a bot set that matches none of them is "Custom" and is kept as it is.
export type RepeatKind = "never" | "daily" | "weekdays" | "weekly" | "monthly" | "custom";

export const REPEAT_OPTIONS: ReadonlyArray<SelectOption<RepeatKind>> = [
  { value: "never", label: "Never" },
  { value: "daily", label: "Every day" },
  { value: "weekdays", label: "Every weekday" },
  { value: "weekly", label: "Every week" },
  { value: "monthly", label: "Every month" },
];
export const CUSTOM_OPTION: SelectOption<RepeatKind> = { value: "custom", label: "Custom" };

const CLOCK = String.raw`(\d{1,2}) (\d{1,2})`;
const PATTERNS: ReadonlyArray<readonly [RepeatKind, RegExp]> = [
  ["daily", new RegExp(`^${CLOCK} \\* \\* \\*$`)],
  ["weekdays", new RegExp(`^${CLOCK} \\* \\* 1-5$`)],
  ["weekly", new RegExp(`^${CLOCK} \\* \\* [0-6]$`)],
  ["monthly", new RegExp(`^${CLOCK} (\\d{1,2}) \\* \\*$`)],
];

/** Which of the drawer's repeats a stored cron is. */
export function repeatOf(cron: string | null): RepeatKind {
  if (!cron || !cron.trim()) return "never";
  const found = PATTERNS.find(([, pattern]) => pattern.test(cron.trim()));
  return found ? found[0] : "custom";
}

/** The cron for a repeat, at the due's wall time (09:00 without one), on the due's weekday or day of the
 * month (today's without a due). null for Never; "custom" is never built here. */
export function cronFor(kind: RepeatKind, due: string | null): string | null {
  if (kind === "never" || kind === "custom") return null;
  const parts = dueParts(pickerText(due)) ?? { day: todayIn(), time: null };
  const [hour, minute] = (parts.time ?? REPEAT_DEFAULT_TIME).split(":").map(Number);
  const [year, month, date] = parts.day.split("-").map(Number);
  const clock = `${minute} ${hour}`;
  if (kind === "daily") return `${clock} * * *`;
  if (kind === "weekdays") return `${clock} * * 1-5`;
  if (kind === "weekly") return `${clock} * * ${new Date(Date.UTC(year, month - 1, date)).getUTCDay()}`;
  return `${clock} ${date} * *`;
}
```

Create `web/src/components/tasks/useOpenTask.ts`:

```ts
import { useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import { TASK_PARAM } from "./constants";

// The task whose drawer is open, kept in the address (?task=<id>, redesign P3) beside the Board's own
// ?tab=, so a reload or a link opens the same drawer. Closing removes it without a history entry.
export function useOpenTask(): { openId: string | null; open: (taskId: string) => void; close: () => void } {
  const [params, setParams] = useSearchParams();
  const open = useCallback((taskId: string) => {
    setParams((current) => {
      const next = new URLSearchParams(current);
      next.set(TASK_PARAM, taskId);
      return next;
    });
  }, [setParams]);
  const close = useCallback(() => {
    setParams((current) => {
      const next = new URLSearchParams(current);
      next.delete(TASK_PARAM);
      return next;
    }, { replace: true });
  }, [setParams]);
  return { openId: params.get(TASK_PARAM), open, close };
}
```

Create `web/src/components/tasks/useProjects.ts`:

```ts
import { useEffect, useState } from "react";
import * as projectsApi from "../../api/projects";
import { describeError } from "../../api/client";
import { useLiveState } from "../../hooks/useLiveStore";
import { isGeneral } from "../projects/projects";
import type { ProjectOut } from "../../api/types";

// The user's projects a task may belong to (redesign P3): every live one but General, archived ones
// included (a task may already be in one). Reloads on money_changed, which carries project changes (H10).
// `enabled` false (a project's own page) asks for nothing. A failed load leaves the list empty, and says
// why in the console: the rows lose their project chip, nothing else breaks.
export function useProjects(enabled = true): readonly ProjectOut[] {
  const version = useLiveState().boardVersion.money;
  const [projects, setProjects] = useState<readonly ProjectOut[]>([]);
  useEffect(() => {
    if (!enabled) return undefined;
    let current = true;
    projectsApi.listProjects(true)
      .then((found) => { if (current) setProjects(found.filter((project) => !isGeneral(project))); })
      .catch((err: unknown) => console.warn("Could not load the projects:", describeError(err)));
    return () => { current = false; };
  }, [enabled, version]);
  return projects;
}
```

- [ ] **Step 5: The rows and the board**

Replace the whole of `web/src/components/board/TaskRow.tsx` with:

```tsx
import { MadeByChip } from "./MadeByChip";
import { formatMoney } from "./money";
import { formatDueChip } from "./taskChips";
import { WebContentChip } from "./WebContentChip";
import { MoreIcon } from "../icons";
import { stepsText } from "../tasks/progress";
import { Menu, MenuItem } from "../../ui/Menu";
import type { TaskMoneyOut, TaskOut } from "../../api/types";

export interface TaskRowProps {
  task: TaskOut;
  currency?: string; // its project's currency (a project page), to show its budget slice
  money?: TaskMoneyOut; // what is spent on it and what is left (a project page)
  projectName?: string; // the Board names each task's project; a project's own page does not
  completing: boolean;
  onComplete: (taskId: string) => void;
  onOpen: (taskId: string) => void; // opens its drawer
  onFail: (taskId: string) => void;
  onKeep: (taskId: string) => void;
}

const FLAGGED: ReadonlySet<TaskOut["priority"]> = new Set(["high", "urgent"]);
const OPEN: ReadonlySet<TaskOut["status"]> = new Set(["todo", "in_progress"]);
// How a finished task ended; failed is red (design §2: it counts as finished but is shown red).
const ENDED: Partial<Record<TaskOut["status"], string>> = { done: "done", failed: "failed", cancelled: "cancelled" };
const NOTHING_SPENT = "0.00";

type ChipsProps = Pick<TaskRowProps, "task" | "currency" | "money" | "projectName" | "onKeep">;

// "€80.00 spent, €40.00 left" or "€130.00 spent, over by €30.00" (design §2). The server
// reckons every number; this only formats them.
function spentText(money: TaskMoneyOut, currency: string): string {
  const spent = `${formatMoney(money.spent, currency)} spent`;
  if (money.left === null) return spent;
  return money.left.startsWith("-")
    ? `${spent}, over by ${formatMoney(money.left.slice(1), currency)}`
    : `${spent}, ${formatMoney(money.left, currency)} left`;
}

// The chips under a task's title (redesign P3): how it ended, its priority, when it is due, its project,
// its steps done, its list, its repeat, its budget slice and where it came from. Reminders live in the drawer.
function TaskChips({ task, currency, money, projectName, onKeep }: ChipsProps) {
  const open = OPEN.has(task.status);
  const ended = ENDED[task.status];
  const due = formatDueChip(task.due_date, task.reminder_at);
  const steps = stepsText(task.steps);
  return (
    <div className="task-row__chips">
      {ended ? <span className={`board-chip board-chip--${task.status}`}>{ended}</span> : null}
      {FLAGGED.has(task.priority) ? (
        <span className={`board-chip board-chip--${task.priority}`}>{task.priority}</span>
      ) : null}
      {open && due.label ? <span className={`board-chip board-chip--${due.tone}`}>{due.label}</span> : null}
      {projectName ? <span className="board-chip board-chip--project">{projectName}</span> : null}
      {steps ? <span className="board-chip board-chip--steps">{steps}</span> : null}
      {task.category ? <span className="board-chip">{task.category}</span> : null}
      {task.recurring ? <span className="board-chip">repeats</span> : null}
      {task.allocated_budget && currency ? (
        <span className="board-chip">budget {formatMoney(task.allocated_budget, currency)}</span>
      ) : null}
      {money && currency && (money.planned !== null || money.spent !== NOTHING_SPENT) ? (
        <span className="board-chip">{spentText(money, currency)}</span>
      ) : null}
      <MadeByChip botId={task.created_by_bot} />
      {task.tainted ? <WebContentChip what={task.title} onKeep={() => onKeep(task.id)} /> : null}
    </div>
  );
}

// One task (redesign P3): the checkbox, the title (a click anywhere on the row opens the drawer), the
// chips, and its actions, shown on hover or keyboard focus.
export function TaskRow({
  task, currency, money, projectName, completing, onComplete, onOpen, onFail, onKeep,
}: TaskRowProps) {
  const open = OPEN.has(task.status);
  return (
    <li className={`task-row task-row--${task.priority}${open ? "" : " task-row--closed"}`}>
      <input type="checkbox" className="task-row__check" aria-label={`Complete ${task.title}`}
        checked={completing || task.status === "done"} disabled={completing || !open}
        onChange={() => onComplete(task.id)} />
      <div className="task-row__main">
        <button type="button" className="task-row__open" onClick={() => onOpen(task.id)}>
          <span className="task-row__title">{task.title}</span>
        </button>
        <TaskChips task={task} currency={currency} money={money} projectName={projectName} onKeep={onKeep} />
      </div>
      <div className="task-row__actions">
        <Menu label={`More for ${task.title}`} trigger={<MoreIcon />}>
          <MenuItem onSelect={() => onOpen(task.id)}>Open</MenuItem>
          {open ? <MenuItem onSelect={() => onFail(task.id)}>Mark failed</MenuItem> : null}
        </Menu>
      </div>
    </li>
  );
}
```

Replace the whole of `web/src/components/board/TasksBoard.tsx` with:

```tsx
import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { TaskAddForm } from "./TaskAddForm";
import { TaskRow } from "./TaskRow";
import { useOpenTask } from "../tasks/useOpenTask";
import { useProjects } from "../tasks/useProjects";
import { useLiveState } from "../../hooks/useLiveStore";
import * as tasksApi from "../../api/tasks";
import { describeError } from "../../api/client";
import type { TaskMoneyOut, TaskOut } from "../../api/types";

// The drawer and everything only it uses are their own chunk (redesign P3): the Board's entry stays small.
const TaskDrawer = lazy(() => import("../tasks/TaskDrawer"));

const NONE: ReadonlySet<string> = new Set();
const OPEN: ReadonlySet<TaskOut["status"]> = new Set(["todo", "in_progress"]);

export interface TasksBoardProps {
  projectId?: string; // one project's tasks of every status (its page); a new task joins it
  currency?: string; // that project's currency, for the budget slices
  money?: Readonly<Record<string, TaskMoneyOut>>; // each task's planned / spent / left, from the project's page
}

// Open tasks first; a project's page lists its finished ones under them.
function openFirst(tasks: readonly TaskOut[]): TaskOut[] {
  return [...tasks.filter((task) => OPEN.has(task.status)), ...tasks.filter((task) => !OPEN.has(task.status))];
}

// The project is asked for only when there is one, so the Board's own call stays listTasks("open").
function useTaskList(projectId: string | undefined) {
  const live = useLiveState();
  const [tasks, setTasks] = useState<TaskOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => {
    const request = projectId ? tasksApi.listTasks("all", { projectId }) : tasksApi.listTasks("open");
    request.then((loaded) => { setTasks(openFirst(loaded)); setError(null); })
      .catch((err: unknown) => setError(describeError(err)));
  }, [projectId]);
  useEffect(() => load(), [load, live.boardVersion.tasks]);
  return { tasks, setTasks, error, setError, load };
}

// The Board names each task's project on its row; a project's page does not need to.
function useProjectNames(projectId: string | undefined): Readonly<Record<string, string>> {
  const projects = useProjects(projectId === undefined);
  return useMemo(() => Object.fromEntries(projects.map((project) => [project.id, project.name])), [projects]);
}

// The user's open tasks, shared by every bot (D1), or one project's tasks. Reloads whenever a
// tasks_changed frame arrives (a bot or another tab changed one). A row opens the task's drawer.
export function TasksBoard({ projectId, currency, money }: TasksBoardProps) {
  const { tasks, setTasks, error, setError, load } = useTaskList(projectId);
  const names = useProjectNames(projectId);
  const { openId, open, close } = useOpenTask();
  const [completing, setCompleting] = useState<ReadonlySet<string>>(NONE);
  const fail = (err: unknown) => setError(describeError(err));

  const complete = (taskId: string) => {
    setCompleting((ids) => new Set([...ids, taskId]));
    tasksApi.completeTask(taskId)
      .then(() => { setTasks((shown) => shown && shown.filter((task) => task.id !== taskId)); load(); })
      .catch(fail)
      .finally(() => setCompleting((ids) => new Set([...ids].filter((id) => id !== taskId))));
  };
  const markFailed = (taskId: string) => { tasksApi.failTask(taskId).then(load).catch(fail); };
  const keep = (taskId: string) => { tasksApi.keepTask(taskId).then(load).catch(fail); };
  const empty = projectId ? "No tasks in this project yet. Add one, or ask any bot." : "Nothing open. Add a task, or ask any bot.";

  return (
    <section className="tasks-board" aria-label="Tasks">
      <TaskAddForm projectId={projectId} onAdded={load} />
      {error ? <ErrorNotice message={error} onRetry={load} /> : null}
      {tasks === null && !error ? <p className="board-loading">Loading&hellip;</p> : null}
      {tasks !== null && tasks.length === 0 ? <p className="board-empty">{empty}</p> : null}
      {tasks && tasks.length > 0 ? (
        <ul className="task-list">
          {tasks.map((task) => (
            <TaskRow key={task.id} task={task} currency={currency} money={money?.[task.id]}
              projectName={task.project_id ? names[task.project_id] : undefined}
              completing={completing.has(task.id)} onComplete={complete} onOpen={open} onFail={markFailed}
              onKeep={keep} />
          ))}
        </ul>
      ) : null}
      {openId ? (
        <Suspense fallback={null}>
          <TaskDrawer taskId={openId} onClose={close} />
        </Suspense>
      ) : null}
    </section>
  );
}
```

- [ ] **Step 6: The drawer and its details**

Create `web/src/components/tasks/TaskDetailsForm.tsx`:

```tsx
import { useEffect, useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { AMOUNT_HELP, MAX_AMOUNT_TEXT, readAmount } from "../board/money";
import { MAX_LIST, MAX_TITLE } from "../board/taskLimits";
import { CUSTOM_OPTION, REPEAT_OPTIONS, cronFor, repeatOf, type RepeatKind } from "./repeat";
import { useProjects } from "./useProjects";
import * as tasksApi from "../../api/tasks";
import { describeError } from "../../api/client";
import type { ProjectOut, TaskOut } from "../../api/types";
import { Button } from "../../ui/Button";
import { Field } from "../../ui/Field";
import { Input } from "../../ui/Input";
import { Select, type SelectOption } from "../../ui/Select";
import { DateTimePicker } from "../../ui/date/DateTimePicker";
import { pickerText, wallText } from "../../ui/date/dates";

const PRIORITIES: ReadonlyArray<SelectOption<TaskOut["priority"]>> = [
  { value: "low", label: "Low" }, { value: "medium", label: "Medium" }, { value: "high", label: "High" },
  { value: "urgent", label: "Urgent" },
];
const NO_PROJECT = "none"; // a Select option is never "" (ui/Select.tsx)

interface Fields {
  title: string;
  list: string;
  priority: TaskOut["priority"];
  when: string;
  reminder: string;
  repeat: RepeatKind;
  project: string;
  slice: string;
}

function fieldsOf(task: TaskOut): Fields {
  return {
    title: task.title, list: task.category ?? "", priority: task.priority, when: pickerText(task.due_date),
    reminder: wallText(task.reminder_at), repeat: repeatOf(task.recurring), project: task.project_id ?? NO_PROJECT,
    slice: task.allocated_budget ?? "",
  };
}

// Only what changed goes out; an emptied field clears it. A new due also moves a weekly or monthly
// repeat to the new day. undefined: a budget slice it can't read (the form says so instead of sending).
export function changesOf(before: Fields, after: Fields): tasksApi.TaskPatchIn | undefined {
  const changed = (key: keyof Fields) => before[key] !== after[key];
  const projectId = after.project === NO_PROJECT ? null : after.project;
  const slice = readAmount(after.slice);
  if (projectId !== null && changed("slice") && slice === undefined) return undefined;
  const repeatMoves = changed("repeat") || (changed("when") && after.repeat !== "never" && after.repeat !== "custom");
  return {
    ...(changed("title") ? { title: after.title.trim() } : {}),
    ...(changed("list") ? { category: after.list.trim() || null } : {}),
    ...(changed("priority") ? { priority: after.priority } : {}),
    ...(changed("when") ? { due_date: after.when.trim() || null } : {}),
    ...(changed("reminder") ? { reminder_at: after.reminder.trim() || null } : {}),
    ...(repeatMoves ? { recurring: cronFor(after.repeat, after.when.trim() || null) } : {}),
    ...(changed("project") ? { project_id: projectId } : {}),
    ...(projectId !== null && changed("slice") ? { allocated_budget: slice ?? null } : {}),
  };
}

function projectOptions(projects: readonly ProjectOut[], current: string): ReadonlyArray<SelectOption> {
  const shown = projects.filter((project) => project.status === "active" || project.id === current);
  return [{ value: NO_PROJECT, label: "No project" }, ...shown.map((project) => ({ value: project.id, label: project.name }))];
}

// The fields keep what the user typed; when the task changes elsewhere (a bot, another tab) and nothing
// here was touched, they follow it.
function useFields(task: TaskOut) {
  const [base, setBase] = useState<Fields>(() => fieldsOf(task));
  const [fields, setFields] = useState<Fields>(base);
  const touched = JSON.stringify(base) !== JSON.stringify(fields);
  useEffect(() => {
    if (touched) return;
    setBase(fieldsOf(task));
    setFields(fieldsOf(task));
    // Only a new version of the task resets the fields; typing never does.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [task.updated_at]);
  const set = <K extends keyof Fields>(key: K, value: Fields[K]) => setFields((current) => ({ ...current, [key]: value }));
  return { base, fields, set, touched, settle: (next: TaskOut) => { setBase(fieldsOf(next)); setFields(fieldsOf(next)); } };
}

// The drawer's Details (redesign P3): title, list, project, priority, due, reminder, repeat and the
// budget slice, saved together. Save is on only when something changed.
export function TaskDetailsForm({ task, onSaved }: { task: TaskOut; onSaved: () => void }) {
  const { base, fields, set, touched, settle } = useFields(task);
  const projects = useProjects();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const save = async () => {
    const patch = changesOf(base, fields);
    if (patch === undefined) { setError(AMOUNT_HELP); return; }
    setBusy(true);
    setError(null);
    try {
      settle(await tasksApi.updateTask(task.id, patch));
      onSaved();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  };
  const repeats = fields.repeat === "custom" ? [...REPEAT_OPTIONS, CUSTOM_OPTION] : REPEAT_OPTIONS;
  return (
    <form className="task-details" aria-label="Details" onSubmit={(e) => { e.preventDefault(); void save(); }}>
      <Field label="Title" className="task-details__wide">
        <Input value={fields.title} maxLength={MAX_TITLE} onChange={(e) => set("title", e.target.value)} />
      </Field>
      <Field label="List" optional>
        <Input value={fields.list} maxLength={MAX_LIST} placeholder="Home, Work…" onChange={(e) => set("list", e.target.value)} />
      </Field>
      <Field label="Priority">
        <Select value={fields.priority} options={PRIORITIES} onChange={(priority) => set("priority", priority)} />
      </Field>
      <Field label="Due" className="task-details__wide">
        <DateTimePicker value={fields.when} placeholder="tomorrow at 9, 2026-10-20, or empty" onChange={(text) => set("when", text)} />
      </Field>
      <Field label="Reminder" hint="A timed due reminds you at its time.">
        <DateTimePicker value={fields.reminder} placeholder="At the due time" onChange={(text) => set("reminder", text)} />
      </Field>
      <Field label="Repeat">
        <Select value={fields.repeat} options={repeats} onChange={(repeat) => set("repeat", repeat)} />
      </Field>
      <Field label="Project">
        <Select value={fields.project} options={projectOptions(projects, base.project)} onChange={(id) => set("project", id)} />
      </Field>
      {fields.project !== NO_PROJECT ? (
        <Field label="Budget slice" hint="Part of the project's budget, in its currency.">
          <Input inputMode="decimal" value={fields.slice} maxLength={MAX_AMOUNT_TEXT} placeholder="empty: none"
            onChange={(e) => set("slice", e.target.value)} />
        </Field>
      ) : null}
      {error ? <ErrorNotice message={error} /> : null}
      <div className="task-details__actions">
        <Button type="submit" variant="primary" size="sm" loading={busy} disabled={!touched || !fields.title.trim()}>
          Save changes
        </Button>
      </div>
    </form>
  );
}
```

Create `web/src/components/tasks/TaskDrawer.tsx`:

```tsx
import { useCallback, useEffect, useRef, useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { TaskDetailsForm } from "./TaskDetailsForm";
import { useLiveState } from "../../hooks/useLiveStore";
import * as tasksApi from "../../api/tasks";
import { ApiError, describeError } from "../../api/client";
import type { TaskDetailOut } from "../../api/types";
import { Button } from "../../ui/Button";
import { Sheet } from "../../ui/Sheet";

export interface TaskDrawerProps {
  taskId: string;
  onClose: () => void;
}

const OPEN: ReadonlySet<TaskDetailOut["status"]> = new Set(["todo", "in_progress"]);
const GONE_TEXT = "This task is gone. It may have been deleted somewhere else.";

// The task, reloaded whenever a task or money frame arrives (a bot ticked a step, an expense was filed).
// A 404 means it was deleted (or never was the user's): the drawer says so instead of an error.
function useTaskDetail(taskId: string) {
  const { tasks, money } = useLiveState().boardVersion;
  const [task, setTask] = useState<TaskDetailOut | null>(null);
  const [gone, setGone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef(0);
  const reload = useCallback(() => {
    const ticket = ++latest.current;
    tasksApi.getTask(taskId)
      .then((found) => { if (ticket === latest.current) { setTask(found); setGone(false); setError(null); } })
      .catch((err: unknown) => {
        if (ticket !== latest.current) return;
        if (err instanceof ApiError && err.status === 404) { setTask(null); setGone(true); return; }
        setError(describeError(err));
      });
  }, [taskId]);
  useEffect(() => reload(), [reload, tasks, money]);
  return { task, gone, error, reload };
}

// Mark failed and Delete (with a second step), pinned to the drawer's foot.
function DrawerActions({ task, onChanged, onDeleted }: { task: TaskDetailOut; onChanged: () => void; onDeleted: () => void }) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const act = (request: () => Promise<unknown>, then: () => void) => {
    setBusy(true);
    setError(null);
    request().then(then).catch((err: unknown) => setError(describeError(err))).finally(() => setBusy(false));
  };
  return (
    <div className="task-drawer__actions">
      {OPEN.has(task.status) ? (
        <Button variant="ghost" size="sm" disabled={busy} onClick={() => act(() => tasksApi.failTask(task.id), onChanged)}>
          Mark failed
        </Button>
      ) : null}
      {confirming ? (
        <div className="task-drawer__confirm" role="group" aria-label={`Delete ${task.title}?`}>
          <p>Its steps and comments go with it.</p>
          <Button variant="danger" size="sm" aria-label={`Delete ${task.title} for good`} disabled={busy}
            onClick={() => act(() => tasksApi.deleteTask(task.id), onDeleted)}>Delete</Button>
          <Button variant="ghost" size="sm" onClick={() => setConfirming(false)}>Cancel</Button>
        </div>
      ) : (
        <Button variant="ghost" size="sm" onClick={() => setConfirming(true)}>Delete task</Button>
      )}
      {error ? <ErrorNotice message={error} /> : null}
    </div>
  );
}

// One task, everything about it (redesign P3), in a Sheet from the right: its details, then what later
// sections add. Its own lazy chunk (TasksBoard imports it through React.lazy only).
export default function TaskDrawer({ taskId, onClose }: TaskDrawerProps) {
  const { task, gone, error, reload } = useTaskDetail(taskId);
  const title = task?.title ?? (gone ? "Task not found" : "Loading…");
  return (
    <Sheet open title={title} onOpenChange={(open) => { if (!open) onClose(); }}
      footer={task ? <DrawerActions task={task} onChanged={reload} onDeleted={onClose} /> : undefined}>
      {error ? <ErrorNotice message={error} onRetry={reload} /> : null}
      {gone ? <p className="task-drawer__gone">{GONE_TEXT}</p> : null}
      {task ? (
        <div className="task-drawer">
          <TaskDetailsForm task={task} onSaved={reload} />
        </div>
      ) : null}
    </Sheet>
  );
}
```

Delete `web/src/components/board/TaskEditForm.tsx` (`git rm web/src/components/board/TaskEditForm.tsx`).

- [ ] **Step 7: The styles**

The edit form's rules go with it:

`web/src/styles/board.css`. Find:

```css
.task-row--editing {
  display: block;
  padding: 16px;
  border-color: var(--color-border-strong);
}
```

Replace with:

```css

```

`web/src/styles/board.css`. Find:

```css
/* ---- Edit form -------------------------------------------------------- */

.task-edit {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr);
  gap: 12px;
}

.task-edit__title,
.task-edit .error-notice,
.task-edit__actions {
  grid-column: 1 / -1;
}

.task-edit__actions {
  display: flex;
  gap: 8px;
}
```

Replace with:

```css

```

`web/src/styles/board.css`. Find:

```css
  .task-edit {
    grid-template-columns: minmax(0, 1fr);
  }
```

Replace with:

```css

```

`web/src/styles/projects.css`. Find:

```css
.task-edit__fail {
  margin-left: auto;
}
```

Replace with:

```css

```

`web/src/styles.css`. Find:

```css
@import "./styles/board.css";
```

Replace with:

```css
@import "./styles/board.css";
@import "./styles/tasks.css";
```

Create `web/src/styles/tasks.css`: Tasks 11 to 14 add their sections at its end:

```css
/* Tasks done properly (redesign P3): structured rows, the task drawer, its steps, money and comments,
   and the quick add. Every value is a token (tokens.css). */

/* ---- Rows ----------------------------------------------------------------- */

.task-row {
  position: relative;
  transition: border-color var(--duration-fast) var(--ease-standard);
}

.task-row:hover {
  border-color: var(--color-border-strong);
}

/* The title is the row's button: its ::after covers the row, so a click anywhere opens the drawer. */
.task-row__open {
  padding: 0;
  border: 0;
  background: none;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.task-row__open::after {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
}

.task-row__open:focus-visible {
  outline: none;
}

.task-row__open:focus-visible::after {
  box-shadow: var(--focus-ring);
}

/* What acts on its own sits above the row's button. */
.task-row__check,
.task-row__actions,
.task-row__chips .board-keep {
  position: relative;
  z-index: 1;
}

.task-row__actions {
  opacity: 0;
  transition: opacity var(--duration-fast) var(--ease-standard);
}

.task-row:hover .task-row__actions,
.task-row:focus-within .task-row__actions {
  opacity: 1;
}

@media (hover: none) {
  .task-row__actions {
    opacity: 1;
  }
}

.board-chip--project {
  color: var(--color-text);
}

.board-chip--steps {
  border-color: var(--color-accent-edge);
  color: var(--color-accent-soft);
}

/* ---- The drawer ----------------------------------------------------------- */

.task-drawer {
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
}

.task-drawer__section {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.task-drawer__heading {
  margin: 0;
  color: var(--color-text-secondary);
  font-size: var(--fs-label);
  font-weight: 600;
}

.task-drawer__gone {
  margin: 0;
  color: var(--color-text-secondary);
}

.task-drawer__actions,
.task-drawer__confirm {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
}

.task-drawer__confirm p {
  margin: 0;
  color: var(--color-text-secondary);
  font-size: var(--fs-label);
}

.task-details {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-3);
}

.task-details__wide,
.task-details .error-notice,
.task-details__actions {
  grid-column: 1 / -1;
}

.task-details__actions {
  display: flex;
  justify-content: flex-end;
}

@media (max-width: 768px) {
  .task-details {
    grid-template-columns: minmax(0, 1fr);
  }
}
```

- [ ] **Step 8: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npx vitest run tests/TasksBoard.test.tsx tests/TaskDrawer.test.tsx tests/repeat.test.ts tests/dates.test.ts tests/bundleGuard.test.ts tests/Board.test.tsx tests/Project.test.tsx tests/tokens.test.ts tests/sheetFocus.test.tsx`
Expected: PASS (`TasksBoard.test.tsx` 10, `TaskDrawer.test.tsx` 8, `repeat.test.ts` 3).

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npm test && npm run build && npm run size`
Expected: every file passes; the build succeeds; the entry stays within budget, and `dist/assets/` holds a `TaskDrawer-*.js` chunk.

- [ ] **Step 9: Commit**

Run:

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && \
git add web/src/components/tasks/progress.ts web/src/components/tasks/repeat.ts web/src/components/tasks/useOpenTask.ts \
  web/src/components/tasks/useProjects.ts web/src/components/tasks/TaskDrawer.tsx \
  web/src/components/tasks/TaskDetailsForm.tsx web/src/components/board/TaskRow.tsx \
  web/src/components/board/TasksBoard.tsx web/src/components/board/taskLimits.ts web/src/ui/date/dates.ts \
  web/src/styles/tasks.css web/src/styles/board.css web/src/styles/projects.css web/src/styles.css \
  web/tests/TasksBoard.test.tsx web/tests/TaskDrawer.test.tsx web/tests/repeat.test.ts web/tests/dates.test.ts \
  web/tests/bundleGuard.test.ts && \
git commit -m "feat: structured task rows open a lazy task drawer with the task's details, reminder and repeat"
```

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git status --short`
Expected: none of the files above is listed, and `TaskEditForm.tsx` is gone (its `git rm` in Step 6 staged the deletion).

---
### Task 11: Steps in the drawer

Design P3 "Subtasks with progress" on the web, Review Focus 2. `StepList` shows the progress (a `Meter`, "1 of 3 done"), then each step: its tick, its title with Rename (an inline box with Save and Cancel), what is spent on it (the server's `money.steps`, shown when more than nothing), Move up and Move down (off at either end), and Delete, which says when the step's expenses and comments moved to the whole task. "Add a step…" adds at the end. Every change is one request, then the drawer reloads; a refusal (a 409 "Try again." included) shows the server's sentence and keeps what was typed. The step actions show on hover or keyboard focus.

**Files:**
- Create: `web/src/components/tasks/StepList.tsx`, `web/tests/StepList.test.tsx`
- Modify: `web/src/components/tasks/TaskDrawer.tsx`, `web/src/components/icons.tsx`, `web/src/styles/tasks.css`
- Test: `web/tests/StepList.test.tsx`; `web/tests/TaskDrawer.test.tsx` stays green unchanged

**Interfaces:**
- Consumes: Task 9's `addStep`, `updateStep`, `moveStep`, `deleteStep`, `StepRemovalOut`, `MAX_STEP_TITLE`; Task 10's `stepProgress` and the drawer; `Meter`, `IconButton`, `Input`, `Button`, `formatMoney`.
- Produces: `StepList` and `StepListProps`; `ChevronUpIcon`; the classes `step`, `step__check`, `step__title`, `step__action`, `step-list`, `step-add`, `step-progress`.

- [ ] **Step 1: Path guard**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && test -f web/src/components/tasks/TaskDrawer.tsx && test ! -e web/src/components/tasks/StepList.tsx && echo ready`
Expected: `ready`. Otherwise stop.

- [ ] **Step 2: Write the failing test**

Create `web/tests/StepList.test.tsx`:

```tsx
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StepList } from "../src/components/tasks/StepList";
import { ApiError } from "../src/api/client";
import { makeTask } from "./taskFixtures";

const addStepMock = vi.fn();
const updateStepMock = vi.fn();
const moveStepMock = vi.fn();
const deleteStepMock = vi.fn();
vi.mock("../src/api/tasks", () => ({
  addStep: (...a: unknown[]) => addStepMock(...a),
  updateStep: (...a: unknown[]) => updateStepMock(...a),
  moveStep: (...a: unknown[]) => moveStepMock(...a),
  deleteStep: (...a: unknown[]) => deleteStepMock(...a),
}));

const onChanged = vi.fn();
const task = makeTask({
  steps: [
    { id: "s-1", title: "Buy a washer", done: true }, { id: "s-2", title: "Fit it", done: false },
    { id: "s-3", title: "Test for leaks", done: false },
  ],
});
const stepRow = (title: string) => screen.getByText(title).closest("li") as HTMLElement;

beforeEach(() => {
  for (const mock of [addStepMock, updateStepMock, moveStepMock, deleteStepMock, onChanged]) mock.mockReset();
  for (const mock of [addStepMock, updateStepMock, moveStepMock]) mock.mockResolvedValue(task);
  deleteStepMock.mockResolvedValue({ ...task, moved_expenses: 0, moved_comments: 0 });
});
afterEach(() => cleanup());

describe("the drawer's steps (redesign P3)", () => {
  it("shows the progress, each step and what is spent on it", () => {
    render(<StepList task={task} spent={{ "s-1": "12.50", "s-2": "0.00" }} currency="EUR" onChanged={onChanged} />);
    expect(screen.getByRole("meter", { name: "Steps done" })).toHaveAttribute("aria-valuetext", "1 of 3 steps done");
    expect(screen.getByRole("checkbox", { name: "Done: Buy a washer" })).toBeChecked();
    expect(within(stepRow("Buy a washer")).getByText("€12.50 spent")).toBeInTheDocument();
    expect(within(stepRow("Fit it")).queryByText(/spent/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Move Buy a washer up" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Move Test for leaks down" })).toBeDisabled();
  });

  it("ticks and unticks a step, and the drawer reloads", async () => {
    const user = userEvent.setup();
    render(<StepList task={task} onChanged={onChanged} />);
    await user.click(screen.getByRole("checkbox", { name: "Done: Fit it" }));
    expect(updateStepMock).toHaveBeenCalledWith("t1", "s-2", { done: true });
    await user.click(screen.getByRole("checkbox", { name: "Done: Buy a washer" }));
    expect(updateStepMock).toHaveBeenLastCalledWith("t1", "s-1", { done: false });
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(2));
  });

  it("adds a step at the end, and renames one with Enter or keeps it with Cancel", async () => {
    const user = userEvent.setup();
    render(<StepList task={task} onChanged={onChanged} />);
    await user.type(screen.getByLabelText("New step"), "Call the plumber{Enter}");
    expect(addStepMock).toHaveBeenCalledWith("t1", "Call the plumber");
    await waitFor(() => expect(screen.getByLabelText("New step")).toHaveValue(""));
    await user.click(screen.getByRole("button", { name: "Rename Fit it" }));
    const box = screen.getByLabelText("New title for Fit it");
    await user.clear(box);
    await user.type(box, "Fit the washer{Enter}");
    expect(updateStepMock).toHaveBeenCalledWith("t1", "s-2", { title: "Fit the washer" });
    await user.click(screen.getByRole("button", { name: "Rename Test for leaks" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByLabelText("New title for Test for leaks")).not.toBeInTheDocument();
    expect(updateStepMock).toHaveBeenCalledTimes(1);
  });

  it("moves a step up or down by one place", async () => {
    const user = userEvent.setup();
    render(<StepList task={task} onChanged={onChanged} />);
    await user.click(screen.getByRole("button", { name: "Move Test for leaks up" }));
    expect(moveStepMock).toHaveBeenCalledWith("t1", "s-3", 1);
    await user.click(screen.getByRole("button", { name: "Move Buy a washer down" }));
    expect(moveStepMock).toHaveBeenLastCalledWith("t1", "s-1", 1);
  });

  it("deletes a step and says its money and comments stay on the task", async () => {
    deleteStepMock.mockResolvedValue({ ...task, moved_expenses: 1, moved_comments: 2 });
    const user = userEvent.setup();
    render(<StepList task={task} onChanged={onChanged} />);
    await user.click(screen.getByRole("button", { name: "Delete Buy a washer" }));
    expect(deleteStepMock).toHaveBeenCalledWith("t1", "s-1");
    expect(await screen.findByRole("status")).toHaveTextContent("Its 1 expense and 2 comments stay on the task.");
  });

  it("shows the server's reason when a change is refused, and keeps the text typed", async () => {
    addStepMock.mockRejectedValue(new ApiError(409, "This task's steps changed while yours was being saved. Try again."));
    const user = userEvent.setup();
    render(<StepList task={makeTask({ steps: [] })} onChanged={onChanged} />);
    expect(screen.queryByRole("meter")).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("New step"), "Buy a washer");
    await user.click(screen.getByRole("button", { name: "Add step" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Try again.");
    expect(screen.getByLabelText("New step")).toHaveValue("Buy a washer");
    expect(onChanged).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 3: Run it to see it fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npx vitest run tests/StepList.test.tsx`
Expected: FAIL: `Failed to resolve import "../src/components/tasks/StepList"`.

- [ ] **Step 4: The list**

`web/src/components/icons.tsx`. Find:

```tsx
export function ChevronDownIcon() {
  return <Icon><path d="M5 8l5 5 5-5" /></Icon>;
}
```

Replace with:

```tsx
export function ChevronDownIcon() {
  return <Icon><path d="M5 8l5 5 5-5" /></Icon>;
}

export function ChevronUpIcon() {
  return <Icon><path d="M5 12l5-5 5 5" /></Icon>;
}
```

Create `web/src/components/tasks/StepList.tsx`:

```tsx
import { useState, type FormEvent } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { ChevronDownIcon, ChevronUpIcon, CloseIcon, PencilIcon } from "../icons";
import { formatMoney } from "../board/money";
import { MAX_STEP_TITLE } from "./constants";
import { stepProgress } from "./progress";
import * as tasksApi from "../../api/tasks";
import { describeError } from "../../api/client";
import type { StepRemovalOut, TaskOut, TaskStepOut } from "../../api/types";
import { Button } from "../../ui/Button";
import { IconButton } from "../../ui/IconButton";
import { Input } from "../../ui/Input";
import { Meter } from "../../ui/Meter";

export interface StepListProps {
  task: TaskOut;
  spent?: Readonly<Record<string, string>>; // what is spent on each step, by id (the server's numbers)
  currency?: string; // the task's project's currency
  onChanged: () => void; // the drawer reloads the task
}

const NOTHING_SPENT = "0.00";

// One request at a time; the drawer reloads after each, and the server's sentence shows on a refusal.
function useStepAction(onChanged: () => void) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const run = async (request: () => Promise<unknown>, said: (result: unknown) => string | null = () => null) => {
    setBusy(true);
    setError(null);
    try {
      setNote(said(await request()));
      onChanged();
      return true;
    } catch (err) {
      setError(describeError(err));
      return false;
    } finally {
      setBusy(false);
    }
  };
  return { busy, error, note, run };
}

// "Its 1 expense and 2 comments stay on the task." after a delete that moved something, else null.
function movedText(result: unknown): string | null {
  const { moved_expenses: expenses = 0, moved_comments: comments = 0 } = result as Partial<StepRemovalOut>;
  if (!expenses && !comments) return null;
  return `Its ${expenses} expense${expenses === 1 ? "" : "s"} and ${comments} comment${comments === 1 ? "" : "s"} stay on the task.`;
}

interface StepItemProps {
  step: TaskStepOut;
  index: number;
  count: number;
  spent: string | null;
  busy: boolean;
  act: (request: () => Promise<unknown>, said?: (result: unknown) => string | null) => Promise<boolean>;
  taskId: string;
}

function StepTitle({ step, taskId, busy, act }: Pick<StepItemProps, "step" | "taskId" | "busy" | "act">) {
  const [editing, setEditing] = useState<string | null>(null);
  if (editing === null) {
    return (
      <>
        <span className="step__title">{step.title}</span>
        <IconButton label={`Rename ${step.title}`} icon={<PencilIcon />} size="sm" className="step__action"
          disabled={busy} onClick={() => setEditing(step.title)} />
      </>
    );
  }
  const save = async (event: FormEvent) => {
    event.preventDefault();
    const title = editing.trim();
    if (title && title !== step.title && !(await act(() => tasksApi.updateStep(taskId, step.id, { title })))) return;
    setEditing(null);
  };
  return (
    <form className="step__rename" onSubmit={(event) => void save(event)}>
      <Input aria-label={`New title for ${step.title}`} controlSize="sm" value={editing} maxLength={MAX_STEP_TITLE}
        autoFocus onChange={(e) => setEditing(e.target.value)} />
      <Button type="submit" size="sm" variant="secondary" disabled={busy}>Save</Button>
      <Button size="sm" variant="ghost" onClick={() => setEditing(null)}>Cancel</Button>
    </form>
  );
}

function StepItem({ step, index, count, spent, busy, act, taskId }: StepItemProps) {
  const move = (position: number) => act(() => tasksApi.moveStep(taskId, step.id, position));
  return (
    <li className={`step${step.done ? " step--done" : ""}`}>
      <input type="checkbox" className="step__check" aria-label={`Done: ${step.title}`} checked={step.done}
        disabled={busy} onChange={() => void act(() => tasksApi.updateStep(taskId, step.id, { done: !step.done }))} />
      <StepTitle step={step} taskId={taskId} busy={busy} act={act} />
      {spent ? <span className="board-chip">{spent} spent</span> : null}
      <IconButton label={`Move ${step.title} up`} icon={<ChevronUpIcon />} size="sm" className="step__action"
        disabled={busy || index === 0} onClick={() => void move(index - 1)} />
      <IconButton label={`Move ${step.title} down`} icon={<ChevronDownIcon />} size="sm" className="step__action"
        disabled={busy || index === count - 1} onClick={() => void move(index + 1)} />
      <IconButton label={`Delete ${step.title}`} icon={<CloseIcon />} size="sm" className="step__action"
        disabled={busy} onClick={() => void act(() => tasksApi.deleteStep(taskId, step.id), movedText)} />
    </li>
  );
}

function AddStep({ taskId, busy, act }: Pick<StepItemProps, "taskId" | "busy" | "act">) {
  const [title, setTitle] = useState("");
  const add = async (event: FormEvent) => {
    event.preventDefault();
    if (title.trim() && (await act(() => tasksApi.addStep(taskId, title.trim())))) setTitle("");
  };
  return (
    <form className="step-add" onSubmit={(event) => void add(event)}>
      <Input aria-label="New step" controlSize="md" placeholder="Add a step…" value={title} maxLength={MAX_STEP_TITLE}
        onChange={(e) => setTitle(e.target.value)} />
      <Button type="submit" size="md" variant="secondary" disabled={busy || !title.trim()}>Add step</Button>
    </form>
  );
}

// The drawer's Steps (redesign P3): progress, then each step with its tick, rename, move up and down,
// delete and what is spent on it; a new step goes at the end.
export function StepList({ task, spent = {}, currency, onChanged }: StepListProps) {
  const { busy, error, note, run } = useStepAction(onChanged);
  const { done, total } = stepProgress(task.steps);
  const spentOn = (step: TaskStepOut) => {
    const amount = spent[step.id];
    return amount && amount !== NOTHING_SPENT && currency ? formatMoney(amount, currency) : null;
  };
  return (
    <section className="task-drawer__section" aria-label="Steps">
      <h3 className="task-drawer__heading">Steps</h3>
      {total > 0 ? (
        <div className="step-progress">
          <Meter label="Steps done" value={done} max={total} valueText={`${done} of ${total} steps done`} />
          <span className="step-progress__text">{done} of {total} done</span>
        </div>
      ) : null}
      {total > 0 ? (
        <ul className="step-list">
          {task.steps.map((step, index) => (
            <StepItem key={step.id} step={step} index={index} count={total} spent={spentOn(step)} busy={busy} act={run}
              taskId={task.id} />
          ))}
        </ul>
      ) : null}
      <AddStep taskId={task.id} busy={busy} act={run} />
      {note ? <p className="step-list__note" role="status">{note}</p> : null}
      {error ? <ErrorNotice message={error} /> : null}
    </section>
  );
}
```

- [ ] **Step 5: In the drawer, under the details**

`web/src/components/tasks/TaskDrawer.tsx`. Find:

```tsx
import { TaskDetailsForm } from "./TaskDetailsForm";
```

Replace with:

```tsx
import { StepList } from "./StepList";
import { TaskDetailsForm } from "./TaskDetailsForm";
```

`web/src/components/tasks/TaskDrawer.tsx`. Find:

```tsx
          <TaskDetailsForm task={task} onSaved={reload} />
```

Replace with:

```tsx
          <TaskDetailsForm task={task} onSaved={reload} />
          <StepList task={task} spent={task.money?.steps} currency={task.money?.currency} onChanged={reload} />
```

Append to the end of `web/src/styles/tasks.css`:

```css

/* ---- Steps ---------------------------------------------------------------- */

.step-progress {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.step-progress .meter {
  flex: 1;
}

.step-progress__text,
.step-list__note {
  margin: 0;
  color: var(--color-text-secondary);
  font-size: var(--fs-label);
  white-space: nowrap;
}

.step-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  margin: 0;
  padding: 0;
  list-style: none;
}

.step {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-height: var(--control-md);
  padding: 0 var(--space-2);
  border-radius: var(--radius-sm);
}

.step:hover,
.step:focus-within {
  background: var(--color-raised);
}

.step__check {
  width: 16px;
  height: 16px;
  margin: 0;
  accent-color: var(--color-accent);
  cursor: pointer;
}

.step__title {
  flex: 1;
  min-width: 0;
  color: var(--color-text);
  font-size: var(--fs-body);
  overflow-wrap: anywhere;
}

.step--done .step__title {
  color: var(--color-text-secondary);
  text-decoration: line-through;
}

.step__action {
  opacity: 0;
}

.step:hover .step__action,
.step:focus-within .step__action {
  opacity: 1;
}

@media (hover: none) {
  .step__action {
    opacity: 1;
  }
}

.step__rename,
.step-add {
  display: flex;
  flex: 1;
  gap: var(--space-2);
}

.step__rename .input,
.step-add .input {
  flex: 1;
  min-width: 0;
}
```

- [ ] **Step 6: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npx vitest run tests/StepList.test.tsx tests/TaskDrawer.test.tsx tests/tokens.test.ts`
Expected: PASS (`StepList.test.tsx` 6 passed).

- [ ] **Step 7: Commit**

Run:

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && \
git add web/src/components/tasks/StepList.tsx web/src/components/tasks/TaskDrawer.tsx web/src/components/icons.tsx \
  web/src/styles/tasks.css web/tests/StepList.test.tsx && \
git commit -m "feat: a task's steps in its drawer: tick, rename, move, delete and add, with progress and spending"
```

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git status --short`
Expected: none of the files above is listed.

---
### Task 12: Money in the drawer

Design P3 "Budget slice, spent and left, per task and per step" and "the linked expenses (add an expense for this task or step right there)", Design meets code 5. `TaskMoneyPanel` shows the slice's bar (red once over) and one line of the server's numbers ("Budget €50.00 · €62.50 spent · over by €12.50"; "No budget slice · …"; or, for a task in no project, why there is no budget), the expenses filed under the task with Keep, star and void as on the Board, and **Add an expense**: P1's `ExpenseAddForm`, which learns a `task` prop and a **For** select (The whole task, or one of its steps). The expense goes to the task's project; with no project the form keeps its Project box. The per-step spending shows on each step (Task 11).

The bar's width is the only arithmetic on the web, and it is drawing, not money: every figure shown is the server's string.

**Files:**
- Create: `web/src/components/tasks/TaskMoneyPanel.tsx`, `web/tests/TaskMoneyPanel.test.tsx`
- Modify: `web/src/components/board/ExpenseAddForm.tsx`, `web/src/components/tasks/TaskDrawer.tsx`, `web/src/styles/tasks.css`
- Test: `web/tests/TaskMoneyPanel.test.tsx`, `web/tests/ExpenseAddForm.test.tsx`; `web/tests/MoneyBoard.test.tsx` stays green unchanged

**Interfaces:**
- Consumes: Task 9's `TaskDetailOut`, `TaskDetailMoneyOut`, `ExpenseIn.task_id` / `.step_id`; Task 7's routes; `ExpenseList`, `formatMoney`, `keepExpense`, `starExpense`, `voidExpense`, `Meter`, `Select`.
- Produces: `TaskMoneyPanel`; `ExpenseAddFormProps.task`; the classes `task-money__line`, `task-money__add`.

- [ ] **Step 1: Path guard**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && test -f web/src/components/tasks/StepList.tsx && test ! -e web/src/components/tasks/TaskMoneyPanel.tsx && echo ready`
Expected: `ready`. Otherwise stop.

- [ ] **Step 2: Write the failing tests**

Create `web/tests/TaskMoneyPanel.test.tsx`:

```tsx
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TaskMoneyPanel } from "../src/components/tasks/TaskMoneyPanel";
import { makeExpense } from "./projectFixtures";
import { makeTaskDetail } from "./taskFixtures";

const createExpenseMock = vi.fn();
const voidExpenseMock = vi.fn();
vi.mock("../src/api/money", () => ({
  createExpense: (...a: unknown[]) => createExpenseMock(...a),
  voidExpense: (...a: unknown[]) => voidExpenseMock(...a),
  starExpense: vi.fn(),
  keepExpense: vi.fn(),
}));
vi.mock("../src/api/dates", () => ({ parseDate: vi.fn() }));
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => ({ bots: {} }) }));

const onChanged = vi.fn();
const inProject = makeTaskDetail({
  project_id: "p1", allocated_budget: "50.00",
  money: { planned: "50.00", spent: "62.50", left: "-12.50", currency: "EUR", steps: { "s-1": "12.50", "s-2": "0.00" } },
  expenses: [makeExpense({ id: "e1", task_id: "t1", step_id: "s-1", amount: "12.50", description: "washers" })],
});

beforeEach(() => {
  for (const mock of [createExpenseMock, voidExpenseMock, onChanged]) mock.mockReset();
  createExpenseMock.mockResolvedValue({});
  voidExpenseMock.mockResolvedValue({});
});
afterEach(() => cleanup());

describe("the drawer's money (redesign P3)", () => {
  it("shows the slice, what is spent and how far over, as the server reckons them, and the expenses", () => {
    render(<TaskMoneyPanel task={inProject} onChanged={onChanged} />);
    expect(screen.getByText("Budget €50.00 · €62.50 spent · over by €12.50")).toBeInTheDocument();
    expect(screen.getByRole("meter", { name: "Budget slice used" })).toHaveAttribute("aria-valuenow", "100");
    expect(screen.getByText("washers")).toBeInTheDocument();
  });

  it("adds an expense for one of the task's steps, in the task's project", async () => {
    const user = userEvent.setup();
    render(<TaskMoneyPanel task={inProject} onChanged={onChanged} />);
    await user.click(screen.getByRole("button", { name: "Add an expense" }));
    await user.type(screen.getByLabelText("Amount"), "8,40");
    await user.click(screen.getByRole("combobox", { name: "For" }));
    await user.click(await screen.findByRole("option", { name: "Fit it" }));
    await user.click(screen.getByRole("button", { name: "Add expense" }));
    expect(createExpenseMock).toHaveBeenCalledWith({
      amount: "8.40", project_id: "p1", note: undefined, task_id: "t1", step_id: "s-2",
    });
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(screen.getByRole("button", { name: "Add an expense" })).toBeInTheDocument();
  });

  it("voids an expense and the drawer reloads", async () => {
    const user = userEvent.setup();
    render(<TaskMoneyPanel task={inProject} onChanged={onChanged} />);
    await user.click(screen.getByRole("button", { name: /^Void the / }));
    expect(voidExpenseMock).toHaveBeenCalledWith("e1", true);
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it("a task in no project says it has no budget, and its expense goes to the whole task", async () => {
    const user = userEvent.setup();
    render(<TaskMoneyPanel task={makeTaskDetail({ steps: [] })} onChanged={onChanged} />);
    expect(screen.getByText(/is in no project, so it has no budget/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Add an expense" }));
    expect(screen.queryByRole("combobox", { name: "For" })).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("Amount"), "3");
    await user.click(screen.getByRole("button", { name: "Add expense" }));
    expect(createExpenseMock).toHaveBeenCalledWith({ amount: "3.00", project: undefined, note: undefined, task_id: "t1" });
  });
});
```

Append to the end of `web/tests/ExpenseAddForm.test.tsx`:

```tsx

describe("ExpenseAddForm in a task's drawer (redesign P3)", () => {
  it("files the expense under the whole task by default, or under the step picked", async () => {
    vi.useRealTimers();
    const user = userEvent.setup();
    const task = { id: "t1", steps: [{ id: "s-1", title: "Buy a washer", done: false }] };
    render(<ExpenseAddForm projects={[]} fixedProjectId="p1" task={task} onAdded={vi.fn()} />);
    await user.type(screen.getByLabelText("Amount"), "5");
    await user.click(screen.getByRole("button", { name: "Add expense" }));
    expect(createExpenseMock).toHaveBeenLastCalledWith({ amount: "5.00", project_id: "p1", note: undefined, task_id: "t1" });
    await user.type(screen.getByLabelText("Amount"), "6");
    await user.click(screen.getByRole("combobox", { name: "For" }));
    await user.click(await screen.findByRole("option", { name: "Buy a washer" }));
    await user.click(screen.getByRole("button", { name: "Add expense" }));
    expect(createExpenseMock).toHaveBeenLastCalledWith(
      { amount: "6.00", project_id: "p1", note: undefined, task_id: "t1", step_id: "s-1" });
  });
});
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npx vitest run tests/TaskMoneyPanel.test.tsx tests/ExpenseAddForm.test.tsx`
Expected: FAIL: `TaskMoneyPanel` cannot be resolved; in `ExpenseAddForm.test.tsx` the new test finds no `For` select and the expense carries no `task_id`.

- [ ] **Step 4: The expense form files under a task or a step**

`web/src/components/board/ExpenseAddForm.tsx`. Find:

```tsx
import { useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
```

Replace with:

```tsx
import { useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
import type { TaskStepOut } from "../../api/types";
import { Select, type SelectOption } from "../../ui/Select";
```

`web/src/components/board/ExpenseAddForm.tsx`. Find:

```tsx
  fixedProjectId?: string;
  onAdded: () => void;
}
```

Replace with:

```tsx
  fixedProjectId?: string;
  // A task's drawer (redesign P3): the expense is filed under the task, or one of its steps (For).
  task?: { id: string; steps: readonly TaskStepOut[] };
  onAdded: () => void;
}

const WHOLE_TASK = "task"; // a Select option is never "" (ui/Select.tsx)

// "The whole task" and each step: where in the task the money went.
function forOptions(steps: readonly TaskStepOut[]): ReadonlyArray<SelectOption> {
  return [{ value: WHOLE_TASK, label: "The whole task" }, ...steps.map((step) => ({ value: step.id, label: step.title }))];
}

// The task and step fields for the gateway; none outside a task's drawer.
function taskLink(task: ExpenseAddFormProps["task"], target: string): { task_id?: string; step_id?: string } {
  if (!task) return {};
  return target === WHOLE_TASK ? { task_id: task.id } : { task_id: task.id, step_id: target };
}
```

`web/src/components/board/ExpenseAddForm.tsx`. Find:

```tsx
export function ExpenseAddForm({ projects, fixedProjectId, onAdded }: ExpenseAddFormProps) {
  const [amount, setAmount] = useState("");
```

Replace with:

```tsx
export function ExpenseAddForm({ projects, fixedProjectId, task, onAdded }: ExpenseAddFormProps) {
  const [amount, setAmount] = useState("");
  const [target, setTarget] = useState(WHOLE_TASK);
```

`web/src/components/board/ExpenseAddForm.tsx`. Find:

```tsx
      const target = fixedProjectId === undefined
        ? { project: project.trim() || undefined }
        : { project_id: fixedProjectId };
      const when = spentAt ? { spent_at: spentAt } : {};
      await moneyApi.createExpense({ amount: parsed, ...target, note: note.trim() || undefined, ...when });
```

Replace with:

```tsx
      const when = spentAt ? { spent_at: spentAt } : {};
      const into = fixedProjectId === undefined
        ? { project: project.trim() || undefined }
        : { project_id: fixedProjectId };
      const link = taskLink(task, target);
      await moneyApi.createExpense({ amount: parsed, ...into, note: note.trim() || undefined, ...when, ...link });
```

`web/src/components/board/ExpenseAddForm.tsx`. Find:

```tsx
      <input className="input" aria-label="Note" placeholder="What was it?" value={note}
        maxLength={MAX_NOTE} onChange={(e) => setNote(e.target.value)} />
```

Replace with:

```tsx
      <input className="input" aria-label="Note" placeholder="What was it?" value={note}
        maxLength={MAX_NOTE} onChange={(e) => setNote(e.target.value)} />
      {task && task.steps.length > 0 ? (
        <Select label="For" value={target} options={forOptions(task.steps)} onChange={setTarget} size="md" />
      ) : null}
```

- [ ] **Step 5: The panel, in the drawer under the steps**

Create `web/src/components/tasks/TaskMoneyPanel.tsx`:

```tsx
import { useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { ExpenseAddForm } from "../board/ExpenseAddForm";
import { ExpenseList } from "../board/ExpenseList";
import { formatMoney } from "../board/money";
import * as moneyApi from "../../api/money";
import { describeError } from "../../api/client";
import type { TaskDetailMoneyOut, TaskDetailOut } from "../../api/types";
import { Button } from "../../ui/Button";
import { Meter } from "../../ui/Meter";

const FULL = 100;
const NO_PROJECT_TEXT = "This task is in no project, so it has no budget. Its expenses still show here.";

// "Budget €50.00 · €42.50 spent · €7.50 left", or "… over by €3.00". The server reckons every number.
function moneyLine(money: TaskDetailMoneyOut): string {
  const spent = `${formatMoney(money.spent, money.currency)} spent`;
  if (money.planned === null || money.left === null) return `No budget slice · ${spent}`;
  const left = money.left.startsWith("-")
    ? `over by ${formatMoney(money.left.slice(1), money.currency)}`
    : `${formatMoney(money.left, money.currency)} left`;
  return `Budget ${formatMoney(money.planned, money.currency)} · ${spent} · ${left}`;
}

// The slice's bar: how much of it is spent, red once over. Shown only with a slice.
function SliceBar({ money }: { money: TaskDetailMoneyOut }) {
  if (money.planned === null || money.left === null) return null;
  const planned = Number(money.planned);
  const used = planned > 0 ? Math.round((Number(money.spent) / planned) * FULL) : FULL;
  const over = money.left.startsWith("-");
  return <Meter label="Budget slice used" value={used} tone={over ? "over" : "accent"} valueText={moneyLine(money)} />;
}

// The drawer's Money (redesign P3): the task's slice, spent and left, its expenses, and a form to add
// one for the task or one of its steps. Keep, star and void act on an expense as on the Board.
export function TaskMoneyPanel({ task, onChanged }: { task: TaskDetailOut; onChanged: () => void }) {
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const act = (request: Promise<unknown>) => {
    setError(null);
    request.then(onChanged).catch((err: unknown) => setError(describeError(err)));
  };
  const { money } = task;
  return (
    <section className="task-drawer__section" aria-label="Money">
      <h3 className="task-drawer__heading">Money</h3>
      {money ? <SliceBar money={money} /> : null}
      <p className="task-money__line">{money ? moneyLine(money) : NO_PROJECT_TEXT}</p>
      {task.expenses.length > 0 ? (
        <ExpenseList expenses={task.expenses} currency={money?.currency ?? task.expenses[0].currency}
          showProject={!task.project_id} onKeep={(id) => act(moneyApi.keepExpense(id))}
          onStar={(id, starred) => act(moneyApi.starExpense(id, starred))}
          onVoid={(id, isVoid) => act(moneyApi.voidExpense(id, isVoid))} />
      ) : null}
      {adding ? (
        <ExpenseAddForm projects={[]} fixedProjectId={task.project_id ?? undefined}
          task={{ id: task.id, steps: task.steps }} onAdded={() => { setAdding(false); onChanged(); }} />
      ) : (
        <Button size="sm" variant="secondary" className="task-money__add" onClick={() => setAdding(true)}>
          Add an expense
        </Button>
      )}
      {error ? <ErrorNotice message={error} /> : null}
    </section>
  );
}
```

`web/src/components/tasks/TaskDrawer.tsx`. Find:

```tsx
import { TaskDetailsForm } from "./TaskDetailsForm";
```

Replace with:

```tsx
import { TaskDetailsForm } from "./TaskDetailsForm";
import { TaskMoneyPanel } from "./TaskMoneyPanel";
```

`web/src/components/tasks/TaskDrawer.tsx`. Find:

```tsx
          <StepList task={task} spent={task.money?.steps} currency={task.money?.currency} onChanged={reload} />
```

Replace with:

```tsx
          <StepList task={task} spent={task.money?.steps} currency={task.money?.currency} onChanged={reload} />
          <TaskMoneyPanel task={task} onChanged={reload} />
```

Append to the end of `web/src/styles/tasks.css`:

```css

/* ---- Money ---------------------------------------------------------------- */

.task-money__line {
  margin: 0;
  color: var(--color-text-secondary);
  font-size: var(--fs-label);
}

.task-money__add {
  align-self: flex-start;
}

.task-drawer .expense-add {
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
}

.task-drawer .expense-add > .input:nth-of-type(n + 2),
.task-drawer .expense-add .select,
.task-drawer .expense-add .btn,
.task-drawer .expense-add .error-notice {
  grid-column: 1 / -1;
}
```

- [ ] **Step 6: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npx vitest run tests/TaskMoneyPanel.test.tsx tests/ExpenseAddForm.test.tsx tests/TaskDrawer.test.tsx tests/MoneyBoard.test.tsx tests/Project.test.tsx tests/tokens.test.ts`
Expected: PASS (`TaskMoneyPanel.test.tsx` 4 passed, `ExpenseAddForm.test.tsx` one more than before).

- [ ] **Step 7: Commit**

Run:

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && \
git add web/src/components/tasks/TaskMoneyPanel.tsx web/src/components/board/ExpenseAddForm.tsx \
  web/src/components/tasks/TaskDrawer.tsx web/src/styles/tasks.css web/tests/TaskMoneyPanel.test.tsx \
  web/tests/ExpenseAddForm.test.tsx && \
git commit -m "feat: a task's money in its drawer: slice, spent and left, its expenses, and an expense for a step"
```

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git status --short`
Expected: none of the files above is listed.

---
### Task 13: Comments and activity in the drawer

Design P3 "the comments thread" and "the activity: made by a bot, from web content", Design meets code 9 and 14, Review Focus 4.
- **Comments** (`CommentThread`): the thread, oldest first, reloaded on `tasks_changed`; each comment with its author ("You", the bot's name, or "A retired bot"), the step it is about, its time on Madrid's clock, "edited", and "from web content" on a bot's web-made one. A body is plain text (React escapes it; `white-space: pre-wrap` keeps its lines; a long word wraps). Edit and Delete only on the user's own. The composer has an **About** select (the whole task, or a step) and sends on Comment or Cmd/Ctrl+Enter.
- **Activity** (`TaskActivity`): who made the task (a bot by name; "you, or a bot since retired" for no maker, since the store cannot tell those apart), when it was made, last changed and finished, and the "from web content" mark with Keep.
- `authors.ts` holds the names and `momentText`, on P1's fixed month names.

**Files:**
- Create: `web/src/components/tasks/{authors.ts,CommentThread.tsx,TaskActivity.tsx}`, `web/tests/{CommentThread,TaskActivity}.test.tsx`
- Modify: `web/src/components/tasks/TaskDrawer.tsx`, `web/src/styles/tasks.css`
- Test: `web/tests/CommentThread.test.tsx`, `web/tests/TaskActivity.test.tsx`; `web/tests/TaskDrawer.test.tsx` stays green unchanged

**Interfaces:**
- Consumes: Task 9's comment requests, `CommentOut`, `MAX_COMMENT`, `COMMENT_ROWS`, `keepTask`; Task 1's `dayText`; `formatClock` (`web/src/lib/chatTime.ts`); `todayIn`; `useLiveState().bots`; `Badge`, `Button`, `Select`, `Textarea`, `WebContentChip`.
- Produces: `USER_AUTHOR`, `RETIRED_BOT`, `authorName`, `momentText`; `CommentThread`; `TaskActivity`; the classes `comment*`, `comment-composer*`, `task-activity*`.

- [ ] **Step 1: Path guard**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && test -f web/src/components/tasks/TaskMoneyPanel.tsx && test ! -e web/src/components/tasks/CommentThread.tsx && echo ready`
Expected: `ready`. Otherwise stop.

- [ ] **Step 2: Write the failing tests**

Create `web/tests/CommentThread.test.tsx`:

```tsx
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CommentThread } from "../src/components/tasks/CommentThread";
import { ApiError } from "../src/api/client";
import { makeBot } from "./fixtures";
import { makeComment, makeTask } from "./taskFixtures";

const listCommentsMock = vi.fn();
const addCommentMock = vi.fn();
const editCommentMock = vi.fn();
const deleteCommentMock = vi.fn();
vi.mock("../src/api/comments", () => ({
  listComments: (...a: unknown[]) => listCommentsMock(...a),
  addComment: (...a: unknown[]) => addCommentMock(...a),
  editComment: (...a: unknown[]) => editCommentMock(...a),
  deleteComment: (...a: unknown[]) => deleteCommentMock(...a),
}));
let live = { bots: { "bot-1": makeBot({ id: "bot-1", name: "Helper" }) }, boardVersion: { tasks: 0, money: 0 } };
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => live }));

const task = makeTask();
const HOSTILE = '<img src=x onerror="alert(1)"><script>steal()</script> Buy it at shop.example';
const itemOf = (found: string | HTMLElement) =>
  (typeof found === "string" ? screen.getByText(found) : found).closest("li") as HTMLElement;

beforeEach(() => {
  live = { bots: { "bot-1": makeBot({ id: "bot-1", name: "Helper" }) }, boardVersion: { tasks: 0, money: 0 } };
  for (const mock of [listCommentsMock, addCommentMock, editCommentMock, deleteCommentMock]) mock.mockReset();
  listCommentsMock.mockResolvedValue([
    makeComment(),
    makeComment({ id: "c2", author: "bot-1", step_id: "s-1", body: "Size 15 mm", created_at: "2026-10-15T09:30:00+00:00" }),
    makeComment({ id: "c3", author: "bot-gone", body: "Old note", edited_at: "2026-10-15T10:00:00+00:00" }),
  ]);
  for (const mock of [addCommentMock, editCommentMock, deleteCommentMock]) mock.mockResolvedValue(makeComment());
});
afterEach(() => cleanup());

describe("the drawer's comments (redesign P3)", () => {
  it("lists the thread with each author, step and time, and Edit and Delete only on the user's own", async () => {
    render(<CommentThread task={task} />);
    const mine = itemOf(await screen.findByText("The plumber comes at 9"));
    expect(within(mine).getByText("You")).toBeInTheDocument();
    expect(within(mine).getByText("Thu 15 Oct, 10:00")).toBeInTheDocument();
    expect(within(mine).getByRole("button", { name: "Edit" })).toBeInTheDocument();
    const bots = itemOf("Size 15 mm");
    expect(within(bots).getByText("Helper")).toBeInTheDocument();
    expect(within(bots).getByText("on “Buy a washer”")).toBeInTheDocument();
    expect(within(bots).queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
    const old = itemOf("Old note");
    expect(within(old).getByText("A retired bot")).toBeInTheDocument();
    expect(within(old).getByText("edited")).toBeInTheDocument();
    expect(listCommentsMock).toHaveBeenCalledWith("t1");
  });

  it("shows a bot's web-made comment as plain text with its mark, and no Edit or Delete", async () => {
    listCommentsMock.mockResolvedValue([makeComment({ id: "c9", author: "bot-1", body: HOSTILE, tainted: true })]);
    const { container } = render(<CommentThread task={task} />);
    const item = itemOf(await screen.findByText(HOSTILE));
    expect(within(item).getByText("from web content")).toBeInTheDocument();
    expect(container.querySelector("img, script")).toBeNull();
    expect(within(item).queryByRole("button")).not.toBeInTheDocument();
  });

  it("comments on the whole task or on a step, with the button or Cmd+Enter", async () => {
    const user = userEvent.setup();
    render(<CommentThread task={task} />);
    await screen.findByText("The plumber comes at 9");
    await user.type(screen.getByLabelText("New comment"), "Called him");
    await user.click(screen.getByRole("button", { name: "Comment" }));
    expect(addCommentMock).toHaveBeenCalledWith("t1", { body: "Called him" });
    await waitFor(() => expect(screen.getByLabelText("New comment")).toHaveValue(""));
    await user.click(screen.getByRole("combobox", { name: "About" }));
    await user.click(await screen.findByRole("option", { name: "Fit it" }));
    await user.type(screen.getByLabelText("New comment"), "Needs a 15 mm key{Meta>}{Enter}{/Meta}");
    expect(addCommentMock).toHaveBeenLastCalledWith("t1", { body: "Needs a 15 mm key", step_id: "s-2" });
  });

  it("edits and deletes the user's own comment, and reloads", async () => {
    const user = userEvent.setup();
    render(<CommentThread task={task} />);
    const mine = itemOf(await screen.findByText("The plumber comes at 9"));
    await user.click(within(mine).getByRole("button", { name: "Edit" }));
    const box = screen.getByLabelText("Edit your comment");
    await user.clear(box);
    await user.type(box, "The plumber comes at 10");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(editCommentMock).toHaveBeenCalledWith("c1", "The plumber comes at 10");
    await user.click(within(itemOf("The plumber comes at 9")).getByRole("button", { name: "Delete" }));
    expect(deleteCommentMock).toHaveBeenCalledWith("c1");
    await waitFor(() => expect(listCommentsMock).toHaveBeenCalledTimes(3));
  });

  it("says when there are none, and shows the server's reason when a comment is refused", async () => {
    listCommentsMock.mockResolvedValue([]);
    addCommentMock.mockRejectedValue(new ApiError(422, "A comment needs some words."));
    const user = userEvent.setup();
    render(<CommentThread task={makeTask({ steps: [] })} />);
    expect(await screen.findByText("No comments yet.")).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "About" })).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("New comment"), "x");
    await user.click(screen.getByRole("button", { name: "Comment" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("A comment needs some words.");
  });
});
```

Create `web/tests/TaskActivity.test.tsx`:

```tsx
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TaskActivity } from "../src/components/tasks/TaskActivity";
import { makeBot } from "./fixtures";
import { makeTask } from "./taskFixtures";

const keepTaskMock = vi.fn();
vi.mock("../src/api/tasks", () => ({ keepTask: (...a: unknown[]) => keepTaskMock(...a) }));
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => ({ bots: { "bot-1": makeBot({ id: "bot-1", name: "Helper" }) } }) }));

const onChanged = vi.fn();
beforeEach(() => { keepTaskMock.mockReset().mockResolvedValue(makeTask()); onChanged.mockReset(); });
afterEach(() => cleanup());

describe("the drawer's activity (redesign P3)", () => {
  it("says which bot made it and when, when it changed, and when it ended", () => {
    render(<TaskActivity task={makeTask({ created_by_bot: "bot-1", status: "done", completed_at: "2026-10-15T16:05:00+00:00",
      updated_at: "2026-10-15T16:05:00+00:00" })} onChanged={onChanged} />);
    expect(screen.getByText("Made by Helper, Wed 14 Oct, 10:00")).toBeInTheDocument();
    expect(screen.getByText("Last changed Thu 15 Oct, 18:05")).toBeInTheDocument();
    expect(screen.getByText("Done Thu 15 Oct, 18:05")).toBeInTheDocument();
  });

  it("names no maker it cannot know, and a retired bot as such", () => {
    const { rerender } = render(<TaskActivity task={makeTask()} onChanged={onChanged} />);
    expect(screen.getByText(/^Made by you, or by a bot since retired, /)).toBeInTheDocument();
    rerender(<TaskActivity task={makeTask({ created_by_bot: "bot-gone" })} onChanged={onChanged} />);
    expect(screen.getByText(/^Made by a retired bot, /)).toBeInTheDocument();
  });

  it("marks a web-made task, and Keep vouches for it", async () => {
    const user = userEvent.setup();
    render(<TaskActivity task={makeTask({ tainted: true })} onChanged={onChanged} />);
    expect(screen.getByText("from web content")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Keep Fix the sink as yours" }));
    expect(keepTaskMock).toHaveBeenCalledWith("t1");
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });
});
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npx vitest run tests/CommentThread.test.tsx tests/TaskActivity.test.tsx`
Expected: FAIL: `Failed to resolve import "../src/components/tasks/CommentThread"` (and `TaskActivity`).

- [ ] **Step 4: Names and times, the thread, the activity**

Create `web/src/components/tasks/authors.ts`:

```ts
import type { BotOut } from "../../api/types";
import { formatClock } from "../../lib/chatTime";
import { dayText, todayIn } from "../../ui/date/dates";

// Who wrote a comment or made a task, and when, in the drawer's words (redesign P3).
export const USER_AUTHOR = "user";
export const RETIRED_BOT = "A retired bot";

/** "You", the bot's name, or "A retired bot" for a bot id the user no longer has. */
export function authorName(author: string, bots: Readonly<Record<string, BotOut>>): string {
  if (author === USER_AUTHOR) return "You";
  return bots[author]?.name ?? RETIRED_BOT;
}

/** A moment on Madrid's calendar and clock: "Thu 15 Oct, 10:00". "" for one that is not a time. */
export function momentText(iso: string | null): string {
  if (!iso) return "";
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return "";
  return `${dayText(todayIn(when), { weekday: true })}, ${formatClock(iso)}`;
}
```

Create `web/src/components/tasks/CommentThread.tsx`:

```tsx
import { useCallback, useEffect, useState, type KeyboardEvent } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { COMMENT_ROWS, MAX_COMMENT } from "./constants";
import { authorName, momentText } from "./authors";
import { useLiveState } from "../../hooks/useLiveStore";
import * as commentsApi from "../../api/comments";
import { describeError } from "../../api/client";
import type { CommentOut, TaskOut } from "../../api/types";
import { Badge } from "../../ui/Badge";
import { Button } from "../../ui/Button";
import { Select, type SelectOption } from "../../ui/Select";
import { Textarea } from "../../ui/Textarea";

const WHOLE_TASK = "task"; // a Select option is never "" (ui/Select.tsx)

// The thread, oldest first; it reloads on tasks_changed, which a comment from anywhere publishes.
function useThread(taskId: string) {
  const version = useLiveState().boardVersion.tasks;
  const [comments, setComments] = useState<readonly CommentOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => {
    commentsApi.listComments(taskId)
      .then((found) => { setComments(found); setError(null); })
      .catch((err: unknown) => setError(describeError(err)));
  }, [taskId]);
  useEffect(() => load(), [load, version]);
  return { comments, error, setError, load };
}

// Cmd/Ctrl+Enter sends; Enter alone is a new line.
const sendKey = (event: KeyboardEvent) => event.key === "Enter" && (event.metaKey || event.ctrlKey);

interface CommentItemProps {
  comment: CommentOut;
  task: TaskOut;
  onChanged: () => void;
  onError: (message: string) => void;
}

function CommentItem({ comment, task, onChanged, onError }: CommentItemProps) {
  const { bots } = useLiveState();
  const [editing, setEditing] = useState<string | null>(null);
  const step = task.steps.find((s) => s.id === comment.step_id);
  const act = (request: Promise<unknown>) => {
    request.then(() => { setEditing(null); onChanged(); }).catch((err: unknown) => onError(describeError(err)));
  };
  const author = authorName(comment.author, bots);
  return (
    <li className="comment">
      <div className="comment__head">
        <span className="comment__author">{author}</span>
        {step ? <span className="comment__step">on “{step.title}”</span> : null}
        <time className="comment__time" dateTime={comment.created_at}>{momentText(comment.created_at)}</time>
        {comment.edited_at ? <span className="comment__edited">edited</span> : null}
        {comment.tainted ? <Badge tone="danger">from web content</Badge> : null}
      </div>
      {editing === null ? <p className="comment__body">{comment.body}</p> : (
        <div className="comment__edit">
          <Textarea aria-label="Edit your comment" value={editing} maxLength={MAX_COMMENT} maxRows={COMMENT_ROWS}
            onChange={(e) => setEditing(e.target.value)} />
          <Button size="sm" variant="primary" disabled={!editing.trim()}
            onClick={() => act(commentsApi.editComment(comment.id, editing))}>Save</Button>
          <Button size="sm" variant="ghost" onClick={() => setEditing(null)}>Cancel</Button>
        </div>
      )}
      {comment.author === "user" && editing === null ? (
        <div className="comment__actions">
          <Button size="sm" variant="ghost" onClick={() => setEditing(comment.body)}>Edit</Button>
          <Button size="sm" variant="ghost" onClick={() => act(commentsApi.deleteComment(comment.id))}>Delete</Button>
        </div>
      ) : null}
    </li>
  );
}

function Composer({ task, onSent }: { task: TaskOut; onSent: () => void }) {
  const [body, setBody] = useState("");
  const [about, setAbout] = useState(WHOLE_TASK);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const options: ReadonlyArray<SelectOption> = [
    { value: WHOLE_TASK, label: "The whole task" }, ...task.steps.map((step) => ({ value: step.id, label: step.title })),
  ];
  const send = async () => {
    if (!body.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      await commentsApi.addComment(task.id, about === WHOLE_TASK ? { body } : { body, step_id: about });
      setBody("");
      onSent();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <form className="comment-composer" onSubmit={(e) => { e.preventDefault(); void send(); }}>
      <Textarea aria-label="New comment" placeholder="Write a comment…" value={body} maxLength={MAX_COMMENT}
        maxRows={COMMENT_ROWS} onChange={(e) => setBody(e.target.value)}
        onKeyDown={(e) => { if (sendKey(e)) { e.preventDefault(); void send(); } }} />
      <div className="comment-composer__row">
        {task.steps.length > 0 ? <Select label="About" value={about} options={options} onChange={setAbout} size="md" /> : null}
        <Button type="submit" size="md" variant="primary" disabled={busy || !body.trim()}>Comment</Button>
      </div>
      {error ? <ErrorNotice message={error} /> : null}
    </form>
  );
}

// The drawer's Comments (redesign P3): the user's and the bots' comments on the task or a step, plain
// text only, a web-made one marked; the user edits or deletes only their own.
export function CommentThread({ task }: { task: TaskOut }) {
  const { comments, error, setError, load } = useThread(task.id);
  return (
    <section className="task-drawer__section" aria-label="Comments">
      <h3 className="task-drawer__heading">Comments</h3>
      {error ? <ErrorNotice message={error} onRetry={load} /> : null}
      {comments !== null && comments.length === 0 ? <p className="comment-empty">No comments yet.</p> : null}
      {comments && comments.length > 0 ? (
        <ul className="comment-list">
          {comments.map((comment) => (
            <CommentItem key={comment.id} comment={comment} task={task} onChanged={load} onError={setError} />
          ))}
        </ul>
      ) : null}
      <Composer task={task} onSent={load} />
    </section>
  );
}
```

Create `web/src/components/tasks/TaskActivity.tsx`:

```tsx
import { useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { WebContentChip } from "../board/WebContentChip";
import { RETIRED_BOT, momentText } from "./authors";
import { useLiveState } from "../../hooks/useLiveStore";
import * as tasksApi from "../../api/tasks";
import { describeError } from "../../api/client";
import type { TaskOut } from "../../api/types";

const ENDED: Partial<Record<TaskOut["status"], string>> = { done: "Done", failed: "Failed", cancelled: "Cancelled" };

// Who made it. A task with no maker was made by the user, or by a bot since retired (the store
// cannot tell them apart), so the drawer says both.
function makerText(botId: string | null, names: Readonly<Record<string, { name: string }>>): string {
  if (!botId) return "Made by you, or by a bot since retired";
  return `Made by ${names[botId]?.name ?? RETIRED_BOT.toLowerCase()}`;
}

// The drawer's Activity (redesign P3): who made the task, when it was made, last changed and finished,
// and the "from web content" mark with Keep. Roost keeps no history of changes beyond these.
export function TaskActivity({ task, onChanged }: { task: TaskOut; onChanged: () => void }) {
  const { bots } = useLiveState();
  const [error, setError] = useState<string | null>(null);
  const ended = ENDED[task.status];
  const keep = () => {
    setError(null);
    tasksApi.keepTask(task.id).then(onChanged).catch((err: unknown) => setError(describeError(err)));
  };
  return (
    <section className="task-drawer__section" aria-label="Activity">
      <h3 className="task-drawer__heading">Activity</h3>
      <ul className="task-activity">
        <li>{makerText(task.created_by_bot, bots)}, {momentText(task.created_at)}</li>
        <li>Last changed {momentText(task.updated_at)}</li>
        {ended && task.completed_at ? <li>{ended} {momentText(task.completed_at)}</li> : null}
      </ul>
      {task.tainted ? (
        <div className="task-activity__web">
          <WebContentChip what={task.title} onKeep={keep} />
        </div>
      ) : null}
      {error ? <ErrorNotice message={error} /> : null}
    </section>
  );
}
```

- [ ] **Step 5: In the drawer, after the money**

`web/src/components/tasks/TaskDrawer.tsx`. Find:

```tsx
import { StepList } from "./StepList";
import { TaskDetailsForm } from "./TaskDetailsForm";
```

Replace with:

```tsx
import { CommentThread } from "./CommentThread";
import { StepList } from "./StepList";
import { TaskActivity } from "./TaskActivity";
import { TaskDetailsForm } from "./TaskDetailsForm";
```

`web/src/components/tasks/TaskDrawer.tsx`. Find:

```tsx
          <TaskMoneyPanel task={task} onChanged={reload} />
```

Replace with:

```tsx
          <TaskMoneyPanel task={task} onChanged={reload} />
          <CommentThread task={task} />
          <TaskActivity task={task} onChanged={reload} />
```

Append to the end of `web/src/styles/tasks.css`:

```css

/* ---- Comments and activity -------------------------------------------------- */

.comment-list,
.task-activity {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  margin: 0;
  padding: 0;
  list-style: none;
}

.comment {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.comment__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--fs-label);
}

.comment__author {
  color: var(--color-text);
  font-weight: 600;
}

.comment__step,
.comment__time,
.comment__edited,
.comment-empty,
.task-activity {
  color: var(--color-text-secondary);
  font-size: var(--fs-label);
}

.comment-empty {
  margin: 0;
}

/* A comment is plain text: its own line breaks show, and a long word wraps instead of widening the drawer. */
.comment__body {
  margin: 0;
  color: var(--color-text);
  font-size: var(--fs-body);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.comment__actions,
.comment__edit,
.comment-composer__row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
}

.comment__edit .input {
  flex: 1 1 100%;
}

.comment-composer {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.comment-composer__row {
  justify-content: flex-end;
}

.task-activity__web {
  display: flex;
  gap: var(--space-2);
}
```

- [ ] **Step 6: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npx vitest run tests/CommentThread.test.tsx tests/TaskActivity.test.tsx tests/TaskDrawer.test.tsx tests/tokens.test.ts`
Expected: PASS (`CommentThread.test.tsx` 5, `TaskActivity.test.tsx` 3).

- [ ] **Step 7: Commit**

Run:

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && \
git add web/src/components/tasks/authors.ts web/src/components/tasks/CommentThread.tsx \
  web/src/components/tasks/TaskActivity.tsx web/src/components/tasks/TaskDrawer.tsx web/src/styles/tasks.css \
  web/tests/CommentThread.test.tsx web/tests/TaskActivity.test.tsx && \
git commit -m "feat: comments and activity in a task's drawer, a bot's web-made comment marked and plain text"
```

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git status --short`
Expected: none of the files above is listed.

---
### Task 14: Quick typing with chips, read by the server

Design P3 "Quick typing", Design meets code 11 and 12, Review Focus 3. `QuickAdd` replaces P1's two-box `TaskAddForm` on the Board and on a project's page (which passes its project).
- As you type, `useQuickLine` asks `POST /api/tasks/parse` 250 ms after the last key; only the newest answer is drawn, so a slow reply never draws chips for old text.
- `chipsOf` draws the reading as chips: the date (P1's friendly words), `#project`, the slice in the project's currency, `!priority`. Words the server could not use as typed (a project to ask about, a refused budget) show as dashed chips, with the server's sentence under the line; the title it will add shows beside them when it differs from the text.
- Each chip has a × (`Remove <chip>`): its kind goes into `skip`, the line is read again, and its words go back into the title ("Book 2 tickets" stays itself).
- Enter (or Add) reads the line once more and adds exactly that reading (`taskInputOf`), or says what to fix (`blockerOf`) and adds nothing.

**Files:**
- Create: `web/src/components/tasks/{useQuickLine.ts,quickChips.ts,QuickAdd.tsx}`, `web/tests/{QuickAdd.test.tsx,quickChips.test.ts}`
- Modify: `web/src/components/board/TasksBoard.tsx`, `web/src/styles/board.css`, `web/src/styles/tasks.css`
- Delete: `web/src/components/board/TaskAddForm.tsx`
- Test: `web/tests/QuickAdd.test.tsx`, `web/tests/quickChips.test.ts`, `web/tests/TasksBoard.test.tsx`

**Interfaces:**
- Consumes: Task 9's `parseQuickLine`, `QuickLineIn`, `QuickLineOut`, `QuickKind`, `TaskIn`, `QUICK_PARSE_DELAY_MS`, `MAX_QUICK_LINE`, `makeQuickLine`; Task 8's route; `dueParts`, `pickerText`, `friendlyDue`, `formatMoney`.
- Produces: `useQuickLine`, `QuickLineReading`; `QuickChip`, `chipsOf`, `taskInputOf`, `blockerOf`; `QuickAdd`, `QuickAddProps`; the classes `quick-add*`, `quick-chip*`.

- [ ] **Step 1: Path guard**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && test -f web/src/components/tasks/CommentThread.tsx && test -f web/src/components/board/TaskAddForm.tsx && test ! -e web/src/components/tasks/QuickAdd.tsx && echo ready`
Expected: `ready`. Otherwise stop.

- [ ] **Step 2: Write the failing tests**

Create `web/tests/quickChips.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { blockerOf, chipsOf, taskInputOf } from "../src/components/tasks/quickChips";
import { makeQuickLine } from "./taskFixtures";

const RENOVATION = { id: "p1", name: "Renovation", currency: "EUR", color: "#3b82f6" };

describe("the quick add's chips (redesign P3)", () => {
  it("draws the date, project, budget and priority the server read", () => {
    const line = makeQuickLine({
      title: "Call plumber", due_date: "2026-10-21T09:00:00+02:00", priority: "high", project: RENOVATION,
      project_words: "#Renovation", budget: "200.00", budget_words: "€200", ready: true,
    });
    expect(chipsOf(line)).toEqual([
      { kind: "date", label: "Wed 21 Oct 2026, 09:00", tone: "read" },
      { kind: "project", label: "#Renovation", tone: "read" },
      { kind: "budget", label: "€200.00", tone: "read" },
      { kind: "priority", label: "!high", tone: "read" },
    ]);
    expect(taskInputOf(line)).toEqual({
      title: "Call plumber", due_date: "2026-10-21T09:00:00+02:00", priority: "high", project_id: "p1",
      allocated_budget: "200.00",
    });
    expect(blockerOf(line)).toBeNull();
  });

  it("shows words it could not use as typed, to fix, with the server's reason", () => {
    const line = makeQuickLine({
      title: "Paint", project_words: "#Renovaton", budget_words: "€20",
      project_question: "No project is called “Renovaton”. Did you mean “Renovation”? Say it exactly.",
    });
    expect(chipsOf(line)).toEqual([
      { kind: "project", label: "#Renovaton", tone: "ask" }, { kind: "budget", label: "€20", tone: "ask" },
    ]);
    expect(blockerOf(line)).toContain("Did you mean “Renovation”?");
    expect(blockerOf(makeQuickLine({ title: "", ready: false }))).toBe("Give the task a title.");
    expect(taskInputOf(makeQuickLine({ title: "Buy milk", ready: true }))).toEqual({ title: "Buy milk" });
  });
});
```

Create `web/tests/QuickAdd.test.tsx`:

```tsx
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QuickAdd } from "../src/components/tasks/QuickAdd";
import type { QuickLineOut } from "../src/api/types";
import { makeQuickLine, makeTask } from "./taskFixtures";

const parseQuickLineMock = vi.fn();
const createTaskMock = vi.fn();
vi.mock("../src/api/tasks", () => ({
  parseQuickLine: (...a: unknown[]) => parseQuickLineMock(...a),
  createTask: (...a: unknown[]) => createTaskMock(...a),
}));

const RENOVATION = { id: "p1", name: "Renovation", currency: "EUR", color: "#3b82f6" };
const LINE = "Call plumber tomorrow 9am #Renovation €200 !high";
const READ: QuickLineOut = makeQuickLine({
  title: "Call plumber", due_date: "2026-10-21T09:00:00+02:00", priority: "high", project: RENOVATION,
  project_words: "#Renovation", budget: "200.00", budget_words: "€200", ready: true,
});
const onAdded = vi.fn();

// The server, as far as these tests need it: the full line reads as READ; "Book 2 tickets" reads the 2 as a
// date unless the date is skipped.
function server({ text, skip = [] }: { text: string; skip?: string[] }): Promise<QuickLineOut> {
  if (text === LINE) return Promise.resolve(READ);
  if (text === "Book 2 tickets") {
    return Promise.resolve(skip.includes("date")
      ? makeQuickLine({ title: "Book 2 tickets", ready: true })
      : makeQuickLine({ title: "Book tickets", due_date: "2026-11-02", ready: true }));
  }
  return Promise.resolve(makeQuickLine({ title: text.trim(), ready: Boolean(text.trim()) }));
}

beforeEach(() => {
  parseQuickLineMock.mockReset().mockImplementation(server);
  createTaskMock.mockReset().mockResolvedValue(makeTask());
  onAdded.mockReset();
});
afterEach(() => cleanup());

describe("the quick add (redesign P3)", () => {
  it("turns the line into chips as you type, then adds exactly what the server read", async () => {
    const user = userEvent.setup();
    render(<QuickAdd onAdded={onAdded} />);
    await user.type(screen.getByLabelText("New task"), LINE);
    expect(await screen.findByText("Wed 21 Oct 2026, 09:00")).toHaveClass("quick-chip--read");
    for (const chip of ["#Renovation", "€200.00", "!high"]) expect(screen.getByText(chip)).toBeInTheDocument();
    expect(screen.getByText("Call plumber")).toHaveClass("quick-add__title");
    await user.keyboard("{Enter}");
    expect(createTaskMock).toHaveBeenCalledWith({
      title: "Call plumber", due_date: "2026-10-21T09:00:00+02:00", priority: "high", project_id: "p1",
      allocated_budget: "200.00",
    });
    await waitFor(() => expect(onAdded).toHaveBeenCalled());
    expect(screen.getByLabelText("New task")).toHaveValue("");
    expect(parseQuickLineMock).toHaveBeenLastCalledWith({ text: LINE });
  });

  it("draws only the newest reading, even when an older answer arrives last", async () => {
    let releaseOld: (line: QuickLineOut) => void = () => undefined;
    parseQuickLineMock.mockImplementation((input: { text: string }) => (input.text === "Book 2"
      ? new Promise<QuickLineOut>((resolve) => { releaseOld = resolve; })
      : server(input)));
    const user = userEvent.setup();
    render(<QuickAdd onAdded={onAdded} />);
    const box = screen.getByLabelText("New task");
    await user.type(box, "Book 2");
    await waitFor(() => expect(parseQuickLineMock).toHaveBeenCalledWith({ text: "Book 2" }));
    await user.type(box, " tickets");
    expect(await screen.findByText("Book tickets")).toBeInTheDocument();
    await act(async () => releaseOld(makeQuickLine({ title: "Stale", ready: true })));
    expect(screen.queryByText("Stale")).not.toBeInTheDocument();
    expect(screen.getByText("Book tickets")).toBeInTheDocument();
  });

  it("a removed chip's words go back into the title, and the line is read again without it", async () => {
    const user = userEvent.setup();
    render(<QuickAdd onAdded={onAdded} />);
    await user.type(screen.getByLabelText("New task"), "Book 2 tickets");
    expect(await screen.findByText("Book tickets")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Remove Mon 2 Nov 2026" }));
    await waitFor(() => expect(parseQuickLineMock).toHaveBeenLastCalledWith({ text: "Book 2 tickets", skip: ["date"] }));
    await waitFor(() => expect(screen.queryByText("Mon 2 Nov 2026")).not.toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Add" }));
    expect(createTaskMock).toHaveBeenCalledWith({ title: "Book 2 tickets" });
  });

  it("adds nothing while the server has a question, and says it", async () => {
    parseQuickLineMock.mockResolvedValue(makeQuickLine({
      title: "Paint", project_words: "#Renovaton",
      project_question: "No project is called “Renovaton”. Did you mean “Renovation”? Say it exactly.",
    }));
    const user = userEvent.setup();
    render(<QuickAdd onAdded={onAdded} />);
    await user.type(screen.getByLabelText("New task"), "Paint #Renovaton{Enter}");
    expect(await screen.findByText(/Did you mean “Renovation”\?/)).toBeInTheDocument();
    expect(await screen.findByText("#Renovaton")).toHaveClass("quick-chip--ask");
    expect(createTaskMock).not.toHaveBeenCalled();
  });

  it("on a project's page, reads the line with the page's project", async () => {
    const user = userEvent.setup();
    render(<QuickAdd projectId="p1" onAdded={onAdded} />);
    await user.type(screen.getByLabelText("New task"), "Buy seeds{Enter}");
    await waitFor(() => expect(createTaskMock).toHaveBeenCalled());
    expect(parseQuickLineMock).toHaveBeenLastCalledWith({ text: "Buy seeds", project_id: "p1" });
  });
});
```

`web/tests/TasksBoard.test.tsx`: the board adds through the quick add now.

`web/tests/TasksBoard.test.tsx`. Find:

```tsx
const getTaskMock = vi.fn();
vi.mock("../src/api/tasks", () => ({
```

Replace with:

```tsx
const getTaskMock = vi.fn();
const parseQuickLineMock = vi.fn();
vi.mock("../src/api/tasks", () => ({
  parseQuickLine: (...a: unknown[]) => parseQuickLineMock(...a),
```

`web/tests/TasksBoard.test.tsx`. Find:

```tsx
import { makeTask as task, makeTaskDetail } from "./taskFixtures";
```

Replace with:

```tsx
import { makeQuickLine, makeTask as task, makeTaskDetail } from "./taskFixtures";
```

`web/tests/TasksBoard.test.tsx`. Find:

```tsx
  getTaskMock.mockResolvedValue(makeTaskDetail());
});
```

Replace with:

```tsx
  getTaskMock.mockResolvedValue(makeTaskDetail());
  parseQuickLineMock.mockReset().mockImplementation(async ({ text, project_id: projectId }: { text: string; project_id?: string }) =>
    makeQuickLine({ title: text, ready: true, project: projectId ? { id: projectId, name: "Garden", currency: "EUR", color: "#22c55e" } : null }));
});
```

`web/tests/TasksBoard.test.tsx`. Find:

```tsx
  it("adds a task from words and reloads", async () => {
    createTaskMock.mockResolvedValue(task({ id: "t3", title: "Buy milk" }));
    const user = userEvent.setup();
    board();
    await user.type(await screen.findByLabelText("New task"), "Buy milk");
    await user.type(screen.getByLabelText("When"), "tomorrow at 9");
    await user.click(screen.getByRole("button", { name: "Add" }));
    expect(createTaskMock).toHaveBeenCalledWith({ title: "Buy milk", due_date: "tomorrow at 9" });
    await waitFor(() => expect(listTasksMock).toHaveBeenCalledTimes(2));
  });
```

Replace with:

```tsx
  it("adds a task from the quick add and reloads", async () => {
    createTaskMock.mockResolvedValue(task({ id: "t3", title: "Buy milk" }));
    const user = userEvent.setup();
    board();
    await user.type(await screen.findByLabelText("New task"), "Buy milk{Enter}");
    expect(createTaskMock).toHaveBeenCalledWith({ title: "Buy milk" });
    await waitFor(() => expect(listTasksMock).toHaveBeenCalledTimes(2));
  });
```

`web/tests/TasksBoard.test.tsx`. Find:

```tsx
    await user.click(screen.getByRole("button", { name: "Add" }));
    expect(createTaskMock).toHaveBeenCalledWith({ title: "Buy seeds", due_date: null, project_id: "p1" });
```

Replace with:

```tsx
    await user.click(screen.getByRole("button", { name: "Add" }));
    expect(parseQuickLineMock).toHaveBeenLastCalledWith({ text: "Buy seeds", project_id: "p1" });
    expect(createTaskMock).toHaveBeenCalledWith({ title: "Buy seeds", project_id: "p1" });
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npx vitest run tests/quickChips.test.ts tests/QuickAdd.test.tsx tests/TasksBoard.test.tsx`
Expected: FAIL: `quickChips` and `QuickAdd` cannot be resolved; the two adding tests in `TasksBoard.test.tsx` fail (the old form never calls `parseQuickLine`, and sends `due_date`).

- [ ] **Step 4: The reading, the chips, the line**

Create `web/src/components/tasks/useQuickLine.ts`:

```ts
import { useEffect, useRef, useState } from "react";
import { QUICK_PARSE_DELAY_MS } from "./constants";
import * as tasksApi from "../../api/tasks";
import { describeError } from "../../api/client";
import type { QuickKind, QuickLineOut } from "../../api/types";

export interface QuickLineReading {
  line: QuickLineOut | null; // the server's reading of the latest text, null for none (or no text)
  error: string | null;
}

/** What the server would add for this line (redesign P3): asked QUICK_PARSE_DELAY_MS after the last key,
 * and only the newest answer counts, so a slow reply never draws chips for text that has changed. */
export function useQuickLine(text: string, projectId: string | undefined, skip: readonly QuickKind[]): QuickLineReading {
  const [reading, setReading] = useState<QuickLineReading>({ line: null, error: null });
  const latest = useRef(0);
  const skipKey = skip.join(",");
  useEffect(() => {
    const ticket = ++latest.current;
    if (!text.trim()) {
      setReading({ line: null, error: null });
      return undefined;
    }
    const timer = window.setTimeout(() => {
      const input = { text, ...(projectId ? { project_id: projectId } : {}), ...(skip.length ? { skip: [...skip] } : {}) };
      tasksApi.parseQuickLine(input)
        .then((line) => { if (ticket === latest.current) setReading({ line, error: null }); })
        .catch((err: unknown) => { if (ticket === latest.current) setReading({ line: null, error: describeError(err) }); });
    }, QUICK_PARSE_DELAY_MS);
    return () => window.clearTimeout(timer);
    // skipKey stands for skip: a new array with the same kinds asks nothing new.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, projectId, skipKey]);
  return reading;
}
```

Create `web/src/components/tasks/quickChips.ts`:

```ts
import { formatMoney } from "../board/money";
import type { QuickKind, QuickLineOut, TaskOut } from "../../api/types";
import { dueParts, friendlyDue, pickerText } from "../../ui/date/dates";
import type { TaskIn } from "../../api/tasks";

// The quick add's chips (redesign P3), drawn from the server's reading of the line. A chip the server
// could not use as typed (a project to ask about, a budget it refused) is shown as typed, to fix.
export interface QuickChip {
  kind: QuickKind;
  label: string;
  tone: "read" | "ask";
}

function dateChip(due: string | null): QuickChip[] {
  if (!due) return [];
  const parts = dueParts(pickerText(due));
  return [{ kind: "date", label: parts ? friendlyDue(parts) : due, tone: "read" }];
}

function projectChip(line: QuickLineOut): QuickChip[] {
  if (line.project) return [{ kind: "project", label: `#${line.project.name}`, tone: "read" }];
  return line.project_words ? [{ kind: "project", label: line.project_words, tone: "ask" }] : [];
}

function budgetChip(line: QuickLineOut): QuickChip[] {
  if (line.budget && line.project) return [{ kind: "budget", label: formatMoney(line.budget, line.project.currency), tone: "read" }];
  return line.budget_words ? [{ kind: "budget", label: line.budget_words, tone: "ask" }] : [];
}

function priorityChip(priority: TaskOut["priority"] | null): QuickChip[] {
  return priority ? [{ kind: "priority", label: `!${priority}`, tone: "read" }] : [];
}

export function chipsOf(line: QuickLineOut): QuickChip[] {
  return [...dateChip(line.due_date), ...projectChip(line), ...budgetChip(line), ...priorityChip(line.priority)];
}

/** What a ready reading adds: exactly what the server read. */
export function taskInputOf(line: QuickLineOut): TaskIn {
  return {
    title: line.title,
    ...(line.due_date ? { due_date: line.due_date } : {}),
    ...(line.priority ? { priority: line.priority } : {}),
    ...(line.project ? { project_id: line.project.id } : {}),
    ...(line.budget && line.project ? { allocated_budget: line.budget } : {}),
  };
}

/** Why a reading can't be added yet, in the server's words. */
export function blockerOf(line: QuickLineOut): string | null {
  if (line.ready) return null;
  return line.project_question ?? line.budget_problem ?? "Give the task a title.";
}
```

Create `web/src/components/tasks/QuickAdd.tsx`:

```tsx
import { useId, useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { CloseIcon } from "../icons";
import { MAX_QUICK_LINE } from "./constants";
import { blockerOf, chipsOf, taskInputOf } from "./quickChips";
import { useQuickLine } from "./useQuickLine";
import * as tasksApi from "../../api/tasks";
import { describeError } from "../../api/client";
import type { QuickKind } from "../../api/types";
import { Button } from "../../ui/Button";
import { Input } from "../../ui/Input";

export interface QuickAddProps {
  projectId?: string; // a project's page: a new task joins it unless the line names another
  onAdded: () => void;
}

const HINT = "Add a task… e.g. Call plumber tomorrow 9am #Renovation €200 !high";

// The quick-add line (redesign P3): as you type, the server's reading shows as chips (date, project,
// budget, priority) and the title it will add. Enter reads the line once more and adds exactly that
// reading, or says what to fix. A chip's × keeps its words in the title instead.
export function QuickAdd({ projectId, onAdded }: QuickAddProps) {
  const [text, setText] = useState("");
  const [skip, setSkip] = useState<readonly QuickKind[]>([]);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const { line, error } = useQuickLine(text, projectId, skip);
  const chipsId = useId();
  const change = (next: string) => {
    setText(next);
    setProblem(null);
    if (!next.trim()) setSkip([]);
  };
  const add = async () => {
    if (!text.trim() || busy) return;
    setBusy(true);
    setProblem(null);
    try {
      const read = await tasksApi.parseQuickLine({
        text, ...(projectId ? { project_id: projectId } : {}), ...(skip.length ? { skip: [...skip] } : {}),
      });
      const blocker = blockerOf(read);
      if (blocker) { setProblem(blocker); return; }
      await tasksApi.createTask(taskInputOf(read));
      change("");
      onAdded();
    } catch (err) {
      setProblem(describeError(err));
    } finally {
      setBusy(false);
    }
  };
  const said = problem ?? (line ? blockerOf(line) : null);
  return (
    <form className="quick-add" onSubmit={(event) => { event.preventDefault(); void add(); }}>
      <div className="quick-add__row">
        <Input aria-label="New task" aria-describedby={chipsId} placeholder={HINT} value={text} maxLength={MAX_QUICK_LINE}
          autoComplete="off" onChange={(event) => change(event.target.value)} />
        <Button type="submit" variant="primary" disabled={busy || !text.trim()}>Add</Button>
      </div>
      <div id={chipsId} className="quick-add__reading" aria-live="polite">
        {line && line.title && line.title !== text.trim() ? <span className="quick-add__title">{line.title}</span> : null}
        {line ? chipsOf(line).map((chip) => (
          <span key={chip.kind} className={`quick-chip quick-chip--${chip.tone}`}>
            {chip.label}
            <button type="button" className="quick-chip__remove" aria-label={`Remove ${chip.label}`}
              onClick={() => setSkip((kinds) => [...kinds, chip.kind])}><CloseIcon /></button>
          </span>
        )) : null}
      </div>
      {said ? <p className="quick-add__ask">{said}</p> : null}
      {error ? <ErrorNotice message={error} /> : null}
    </form>
  );
}
```

- [ ] **Step 5: The board uses it; the old form and its styles go**

`web/src/components/board/TasksBoard.tsx`. Find:

```tsx
import { TaskAddForm } from "./TaskAddForm";
import { TaskRow } from "./TaskRow";
```

Replace with:

```tsx
import { TaskRow } from "./TaskRow";
import { QuickAdd } from "../tasks/QuickAdd";
```

`web/src/components/board/TasksBoard.tsx`. Find:

```tsx
      <TaskAddForm projectId={projectId} onAdded={load} />
```

Replace with:

```tsx
      <QuickAdd projectId={projectId} onAdded={load} />
```

Delete `web/src/components/board/TaskAddForm.tsx` (`git rm web/src/components/board/TaskAddForm.tsx`).

`web/src/styles/board.css`. Find:

```css
.task-add {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
}

.task-add .btn {
  height: 44px;
}

.task-add .error-notice {
  grid-column: 1 / -1;
}
```

Replace with:

```css

```

`web/src/styles/board.css`. Find:

```css
  /* The title gets its own row; When and Add share the next. */
  .task-add {
    grid-template-columns: minmax(0, 1fr) auto;
  }

  .task-add > .input:first-child {
    grid-column: 1 / -1;
  }
```

Replace with:

```css

```

Append to the end of `web/src/styles/tasks.css`:

```css

/* ---- Quick add -------------------------------------------------------------- */

.quick-add {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.quick-add__row {
  display: flex;
  gap: var(--space-2);
}

.quick-add__row .input {
  flex: 1;
  min-width: 0;
}

.quick-add__reading {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
}

.quick-add__reading:empty {
  display: none;
}

.quick-add__title {
  color: var(--color-text-secondary);
  font-size: var(--fs-label);
}

.quick-chip {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-1) var(--space-1) var(--space-1) var(--space-2);
  border: 1px solid var(--color-accent-edge);
  border-radius: var(--radius-pill);
  background: var(--color-accent-tint);
  color: var(--color-accent-soft);
  font-size: var(--fs-caption);
  font-weight: 500;
}

.quick-chip--ask {
  border-style: dashed;
  border-color: var(--color-warn);
  background: transparent;
  color: var(--color-warn);
}

.quick-chip__remove {
  display: inline-flex;
  width: 16px;
  height: 16px;
  padding: 0;
  border: 0;
  border-radius: var(--radius-pill);
  background: transparent;
  color: inherit;
  cursor: pointer;
}

.quick-chip__remove svg {
  width: 12px;
  height: 12px;
  margin: auto;
}

.quick-chip__remove:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}

.quick-add__ask {
  margin: 0;
  color: var(--color-warn);
  font-size: var(--fs-label);
}
```

- [ ] **Step 6: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npx vitest run tests/quickChips.test.ts tests/QuickAdd.test.tsx tests/TasksBoard.test.tsx tests/Board.test.tsx tests/Project.test.tsx tests/tokens.test.ts`
Expected: PASS (`QuickAdd.test.tsx` 5, `quickChips.test.ts` 2, `TasksBoard.test.tsx` 10).

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npm test && npm run build && npm run size`
Expected: every file passes (98 files at the time of writing); the entry stays within budget (about 204 KB of 257 KB gzip when this plan was checked).

- [ ] **Step 7: Commit**

Run:

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && \
git add web/src/components/tasks/useQuickLine.ts web/src/components/tasks/quickChips.ts \
  web/src/components/tasks/QuickAdd.tsx web/src/components/board/TasksBoard.tsx web/src/styles/board.css \
  web/src/styles/tasks.css web/tests/quickChips.test.ts web/tests/QuickAdd.test.tsx web/tests/TasksBoard.test.tsx && \
git commit -m "feat: quick add reads a line into chips on the server, and adds exactly what it read"
```

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git status --short`
Expected: none of the files above is listed, and `TaskAddForm.tsx` is gone (its `git rm` staged the deletion).

---
### Task 15: E2E for tasks, the docs, and the final checks

Design "Testing" (Playwright: quick-add a task with chips, open the drawer, add a step and a comment). One new spec drives the whole P3 flow in a real browser against the scripted gateway; `pickers.spec.ts` picks a task's due in the drawer now that the quick add has no date box; CLAUDE.md's map and Architecture name P3, and `tests/test_docs.py` keeps them honest.

**Files:**
- Create: `web/e2e/tasks.spec.ts`
- Modify: `web/e2e/pickers.spec.ts`, `CLAUDE.md`, `tests/test_docs.py`
- Test: `web/e2e/tasks.spec.ts`, `web/e2e/pickers.spec.ts`, `tests/test_docs.py`

**Interfaces:**
- Consumes: everything above; `signIn`, `openBoard`, `detailPane` (`web/e2e/helpers.ts`); `addDays`, `todayIn`, `friendlyDue`.
- Produces: nothing new in code.

The spec talks to the gateway the way the page does. `page.request` shares the page's cookies but sends no `Origin`, so the one setup call (a project) passes the page's own origin. The drawer is a Sheet drawn outside `main`, so it is found as `page.getByRole("dialog", { name })`, not inside `detailPane`.

- [ ] **Step 1: Path guard**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && test -f web/src/components/tasks/QuickAdd.tsx && test ! -e web/e2e/tasks.spec.ts && echo ready`
Expected: `ready`. Otherwise stop.

- [ ] **Step 2: Write the spec, the pickers change and the docs test**

Create `web/e2e/tasks.spec.ts`:

```ts
import { expect, test } from "@playwright/test";
import { addDays, friendlyDue, todayIn } from "../src/ui/date/dates";
import { detailPane, openBoard, signIn } from "./helpers";

// Redesign P3: quick-add a task with chips, open its drawer, add a step, a comment and an expense for the
// step, and close it with focus back on the row.
const PROJECT = "Plumbing";
const LINE = `Fix the leak tomorrow 9am #${PROJECT} €200 !high`;
const TASK = "Fix the leak";

test("quick add with chips, then the drawer: a step, a comment, an expense for the step", async ({ page }) => {
  test.setTimeout(60_000);
  const tomorrow = addDays(todayIn(), 1);
  await signIn(page);
  const origin = new URL(page.url()).origin;
  const created = await page.request.post("/api/projects", { data: { name: PROJECT }, headers: { Origin: origin } });
  expect(created.status()).toBe(201);
  const project = (await created.json()) as { id: string };

  await openBoard(page);
  const detail = detailPane(page);
  await detail.getByRole("tab", { name: "Tasks" }).click();
  await detail.getByLabel("New task").fill(LINE);
  for (const chip of [friendlyDue({ day: tomorrow, time: "09:00" }), `#${PROJECT}`, "€200.00", "!high"]) {
    await expect(detail.locator(".quick-chip--read", { hasText: chip })).toBeVisible();
  }
  const added = page.waitForRequest((r) => r.url().endsWith("/api/tasks") && r.method() === "POST");
  await detail.getByLabel("New task").press("Enter");
  expect((await added).postDataJSON()).toMatchObject({
    title: TASK, priority: "high", project_id: project.id, allocated_budget: "200.00",
  });
  const row = detail.getByRole("listitem").filter({ hasText: TASK });
  await expect(row.locator(".board-chip--project", { hasText: PROJECT })).toBeVisible();

  const title = row.getByRole("button", { name: TASK, exact: true });
  await title.click();
  await expect(page).toHaveURL(/[?&]task=/);
  const drawer = page.getByRole("dialog", { name: TASK });
  await expect(drawer.getByLabel("Due")).toHaveValue(`${tomorrow} 09:00`);

  await drawer.getByLabel("New step").fill("Buy a washer");
  await drawer.getByRole("button", { name: "Add step" }).click();
  await drawer.getByRole("checkbox", { name: "Done: Buy a washer" }).check();
  await expect(drawer.getByText("1 of 1 done")).toBeVisible();

  await drawer.getByLabel("New comment").fill("The plumber comes at 9");
  await drawer.getByRole("button", { name: "Comment", exact: true }).click();
  await expect(drawer.locator(".comment", { hasText: "The plumber comes at 9" }).getByText("You")).toBeVisible();

  await drawer.getByRole("button", { name: "Add an expense" }).click();
  await drawer.getByRole("textbox", { name: "Amount", exact: true }).fill("12,50");
  await drawer.getByRole("combobox", { name: "For" }).click();
  await page.getByRole("option", { name: "Buy a washer" }).click();
  await drawer.getByRole("button", { name: "Add expense", exact: true }).click();
  await expect(drawer.getByText("Budget €200.00 · €12.50 spent · €187.50 left")).toBeVisible();
  await expect(drawer.locator(".step", { hasText: "Buy a washer" }).getByText("€12.50 spent")).toBeVisible();

  await page.keyboard.press("Escape");
  await expect(drawer).toHaveCount(0);
  await expect(page).not.toHaveURL(/[?&]task=/);
  await expect(row.getByText("1/1 steps")).toBeVisible();
});
```

`web/e2e/pickers.spec.ts`. Find:

```ts
  // A task: Tomorrow and 09:00 go out as Madrid's day and wall time, and come back the same.
  await detail.getByRole("tab", { name: "Tasks" }).click();
  await detail.getByLabel("New task").fill(TASK);
  await detail.getByRole("button", { name: "Open calendar" }).click();
  await page.getByRole("button", { name: "Tomorrow", exact: true }).click();
  await page.getByRole("button", { name: "09:00", exact: true }).click();
  await expect(detail.getByLabel("When")).toHaveValue(`${tomorrow} 09:00`);
  const added = page.waitForRequest((r) => r.url().endsWith("/api/tasks") && r.method() === "POST");
  await detail.getByRole("button", { name: "Add", exact: true }).click();
  expect((await added).postDataJSON()).toMatchObject({ title: TASK, due_date: `${tomorrow} 09:00` });
  const row = detail.getByRole("listitem").filter({ hasText: TASK });
  await row.getByRole("button", { name: "Edit" }).click();
  await expect(detail.getByRole("form", { name: `Edit ${TASK}` }).getByLabel("Due")).toHaveValue(`${tomorrow} 09:00`);
  await detail.getByRole("button", { name: "Cancel" }).click();
```

Replace with:

```ts
  // A task (redesign P3: its due is picked in the drawer): Tomorrow and 09:00 go out as Madrid's day and
  // wall time, and come back the same.
  await detail.getByRole("tab", { name: "Tasks" }).click();
  await detail.getByLabel("New task").fill(TASK);
  await detail.getByLabel("New task").press("Enter");
  await detail.getByRole("listitem").filter({ hasText: TASK }).getByRole("button", { name: TASK, exact: true }).click();
  const drawer = page.getByRole("dialog", { name: TASK });
  await drawer.getByRole("button", { name: "Open calendar" }).first().click();
  await page.getByRole("button", { name: "Tomorrow", exact: true }).click();
  await page.getByRole("button", { name: "09:00", exact: true }).click();
  await expect(drawer.getByLabel("Due")).toHaveValue(`${tomorrow} 09:00`);
  const saved = page.waitForRequest((r) => /\/api\/tasks\/[^/]+$/.test(r.url()) && r.method() === "PATCH");
  await drawer.getByRole("button", { name: "Save changes" }).click();
  expect((await saved).postDataJSON()).toMatchObject({ due_date: `${tomorrow} 09:00` });
  await expect(drawer.getByLabel("Due")).toHaveValue(`${tomorrow} 09:00`);
  await page.keyboard.press("Escape");
  await expect(drawer).toHaveCount(0);
```

`tests/test_docs.py`. Find:

```python
    "docs/plans/2026-10-15-roost-redesign-p2-chat.md",
)
```

Replace with:

```python
    "docs/plans/2026-10-15-roost-redesign-p2-chat.md",
    "docs/plans/2026-10-16-roost-redesign-p3-tasks.md",
)
```

`tests/test_docs.py`. Find:

```python
    "web/src/components/markdown/", "web/src/components/chat/", "web/src/lib/unread.ts",
)
```

Replace with:

```python
    "web/src/components/markdown/", "web/src/components/chat/", "web/src/lib/unread.ts",
    "web/src/components/tasks/", "roost/tasks/step_service.py", "task_comments", "POST /api/tasks/parse",
)
```

- [ ] **Step 3: Run them to see the docs test fail and the specs pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && ROOST_DATA_DIR=$(mktemp -d) ROOST_DESKS_DIR=$(mktemp -d) uv run pytest tests/test_docs.py -q`
Expected: FAIL: the map lacks the P3 plan, and the Architecture section lacks the four P3 places.

Run the disk guard first: `df -g /System/Volumes/Data | awk 'NR==2{print $4}'`. If it shows fewer than 8, stop and report.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && ROOST_DESKS_DIR=$(mktemp -d) make e2e`
Expected: every spec passes, `tasks.spec.ts` and the changed `pickers.spec.ts` included. (`make e2e` picks port 5173 while the live gateway holds 18800, and starts a throwaway scripted gateway with its own `mktemp -d` data.)

- [ ] **Step 4: The docs**

`CLAUDE.md`. Find:

```markdown
- `docs/plans/2026-10-15-roost-redesign-p2-chat.md` — the redesign's P2 plan: bot replies as markdown (one lazy chunk shared with the notes preview), messages without borders, copy and time on hover, typing dots and a caret, a bot's steps as compact lines, the growing composer, and Home's main bot first, unread dots and plain previews.
```

Replace with:

```markdown
- `docs/plans/2026-10-15-roost-redesign-p2-chat.md` — the redesign's P2 plan: bot replies as markdown (one lazy chunk shared with the notes preview), messages without borders, copy and time on hover, typing dots and a caret, a bot's steps as compact lines, the growing composer, and Home's main bot first, unread dots and plain previews.
- `docs/plans/2026-10-16-roost-redesign-p3-tasks.md` — the redesign's P3 plan: a task's steps for the user and every bot, comments on a task or a step (schema v14 `task_comments`), the task drawer (details, steps, money per task and step, comments, activity), the server-read quick-add line with chips, structured task rows, and Sheets that hold menus and pickers.
```

`CLAUDE.md`. Find:

```markdown
Home lists the main bot first, wearing its star, with unread dots this browser remembers (`web/src/lib/unread.ts`).
```

Replace with:

```markdown
Home lists the main bot first, wearing its star, with unread dots this browser remembers (`web/src/lib/unread.ts`).

Tasks (redesign P3): a task's steps are its encrypted `steps` JSON with stable ids; every change goes through `StepService` (`roost/tasks/step_service.py`), one compare-and-set write per change, and a deleted step's expenses and comments stay on the task. Comments on a task or a step live in `task_comments` (schema v14, body `enc:v2`, a taint bit for a bot's), behind `CommentService`; the user edits or deletes only their own. Every bot has `add_step`, `update_step`, `delete_step`, `move_step`, `add_comment` and `list_comments`. A row on the Board opens the task drawer (`web/src/components/tasks/TaskDrawer.tsx`, a lazy chunk, `?task=<id>`): details, steps, money per task and step from `GET /api/tasks/{id}`, comments and activity. The quick add sends the line to `POST /api/tasks/parse` (`roost/tasks/quick_line.py`: the date, `#project` exact or ask, `€/$/£` slice, `!high`) and adds exactly what the server read. Overlays inside a Sheet draw in its panel (`web/src/ui/portalContainer.ts`).
```

- [ ] **Step 5: Full verification**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && ROOST_DATA_DIR=$(mktemp -d) ROOST_DESKS_DIR=$(mktemp -d) uv run pytest --cov=roost --cov-fail-under=80 -q`
Expected: PASS, coverage above 80%.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npm test && npm run build && npm run size`
Expected: every vitest file passes; the build succeeds; the entry stays within `bundle-budget.json`; `dist/assets/` holds a `TaskDrawer-*.js` chunk.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git grep -n "TaskEditForm\|TaskAddForm" -- web/src web/tests web/e2e ; echo "end"`
Expected: `end` alone: nothing names the old forms.

- [ ] **Step 6: Commit**

Run:

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && \
git add web/e2e/tasks.spec.ts web/e2e/pickers.spec.ts CLAUDE.md tests/test_docs.py && \
git commit -m "test: E2E for quick add and the task drawer; docs: the redesign's P3 in CLAUDE.md"
```

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git status --short`
Expected: none of the files above is listed.
