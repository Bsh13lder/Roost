# Roost Tasks & Money polish — implementation plan

> **For agentic workers:** execute task by task with superpowers:subagent-driven-development (briefs in
> `.superpowers/sdd/2026-10-20-roost-tasks-money/`). Each task is red → green → commit.

**Goal:** a safe date parser; rich task and expense quick lines (EN + ES) with autocomplete, chips and a
help popover; task views, search, sort and quick reschedule; edit/delete expenses with Undo; repeating
expenses with Upcoming charges; money reports, CSV and the General inbox.

**Design:** `docs/plans/2026-10-20-roost-tasks-money-polish-design.md` (decisions P1–P12, grammar §2–§4,
lazy repeats §5, schema §6, hand-off to Routines §9). **Audit:** `.superpowers/sdd/2026-10-20-tasks-money-audit.md`.

> **Status (2026-10-21): built.** Written against `night-1` at `f2ef80e` (latest migration v16).
> Polish R1 is built in parallel (`docs/plans/2026-10-20-roost-polish-r1.md`); see "Files R1 owns".

---

## Global Constraints

- **Path guard, first in every task:** `git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel`
  prints `/Users/blckit/Desktop/Code_Projects/roost` and `git … branch --show-current` prints `night-1`; else stop.
- **Where you may edit:** only under the repo, never `roost-ui/` or `spikes/`. Never open `~/Roost/data`,
  the lazyclaw repo, `~/.claude/projects/**` or the open-dot repos. No browser MCP tools.
- **The live Roost is never touched** (ports 18800/18801, `~/Roost/data`). Anything importing `roost`
  runs with `ROOST_DATA_DIR=$(mktemp -d) ROOST_DESKS_DIR=$(mktemp -d)`. E2E: `ROOST_DESKS_DIR=$(mktemp -d) make e2e`.
- **Files R1 owns — never edit:** `web/src/components/{Layout,ChatList,Composer,MessageList,MessageRow,StuckCard}.tsx`,
  `web/src/pages/{Home,Chat,Profile,Instructions}.tsx`, `web/src/components/{panel,sidebar,profile}/**`,
  `web/src/App.tsx`, `web/src/api/types.ts`, `web/src/api/bots.ts`, `web/src/styles.css`,
  `web/src/styles/{tokens,chat*,profile,layout,home,sidebar,panel}.css`, `web/src/ui/Sheet.tsx`,
  `web/tests/fixtures.ts`, `roost/bots/**`, `roost/gateway/routes/bots.py`.
  New wire types go in `web/src/api/tasks.ts` / `web/src/api/money.ts` (extend with `&` where an
  existing type in `types.ts` grows). New CSS is appended to `board.css`, `tasks.css` or `projects.css`
  (each ≤ 800 lines), never a new file (a new file needs a `styles.css` import). Web test data goes in
  `web/tests/moneyFixtures.ts` (new) or the existing `projectFixtures.ts`.
- **Data rules (CLAUDE.md):** money is `Decimal`, sent as strings, never added across currencies;
  every user-content column `enc:v2` with `user_aad(user_id, "<table>:<column>")`; every query names
  `user_id` in its `WHERE`; another user's id is 404; a project is matched exactly or asked, never made
  (web); General can't be a task's project.
- **Schema number:** the plan writes **v18**. v16 is R1, v17 is shared by computers-2 (`site_logins`)
  and Routines. At build time take the next free number after `latest_version()`; freeze the previous
  version as `tests/fixtures/schema_v{N-1}.sql` first; rename the test file and comments to match.
- **No LLM in tests;** tests first (red, then green); ≥80% line coverage on new code
  (`uv run pytest --cov=roost --cov-fail-under=80`); files ≤ 800 lines, functions < 50 lines;
  frozen dataclasses; pydantic at every boundary (`extra="forbid"`); plain-sentence 422s; numbers in
  `roost/constants.py` / `web/src/components/tasks/constants.ts` / `web/src/components/board/constants.ts` (new).
- **Web:** colours and font sizes only from `tokens.css` (`web/tests/tokens.test.ts`); controls from
  `web/src/ui/`; no new dependency (`web/tests/licenseGate.test.ts`); charts are plain SVG in a lazy chunk;
  the entry stays within `web/bundle-budget.json` (`npm run size`). Dark only. Vocabulary per CLAUDE.md.
- **Disk guard** before `make e2e` or `npm install`: `df -g /System/Volumes/Data | awk 'NR==2{print $4}'` ≥ 8.
- **Git:** other agents commit too. Stage by name only, never `-A`/`-a`/`.`; never amend, rebase or reset;
  conventional messages with **no AI attribution line**.
- **Commands:** `cd /Users/blckit/Desktop/Code_Projects/roost && ROOST_DATA_DIR=$(mktemp -d) ROOST_DESKS_DIR=$(mktemp -d) uv run pytest tests/<file>.py -q`;
  web `cd web && npx vitest run tests/<file>`, `npm test`, `npm run build && npm run size`.

## Shared Contract (exact names)

**Constants (`roost/constants.py`):** `TASK_ESTIMATE_MAX_MINUTES = 6000`, `PM_GUESS_HOURS = range(1, 8)`,
`RECURRING_CATCH_UP_MAX = 24`, `UPCOMING_CHARGES_DAYS = 31`, `MONEY_TREND_MONTHS = 6`,
`MONEY_TREND_MONTHS_MAX = 24`, `BULK_MOVE_MAX = 100`, `MOVE_OVERDUE_MAX = 200`, `TASK_DONE_VIEW_LIMIT = 100`,
`TASK_SEARCH_MAX_LENGTH = 100`, `CSV_EXPORT_MAX_ROWS = 10000`, `MAX_EXPENSE_VENDOR_LENGTH = 80`,
`GENERAL_INBOX_PAGE = 100`, `RECURRING_CADENCES = ("weekly", "monthly", "yearly")`.

**Pure modules:**
- `roost/tasks/day_words.py`: `@dataclass(frozen=True) DayReading(day: date, time: time | None, start: int, end: int, words: str)`;
  `find_day(text, *, now: datetime, direction: Literal["forward","past"]) -> DayReading | None`;
  `guess_hour(hour: int, suffix: str | None) -> int`.
- `roost/tasks/line_tokens.py`: `Tokens(rest, priority, priority_words, star, estimate_minutes, reminder_words, amount, currency, amount_words, vendor, warnings: tuple[str, ...])`;
  `read_tokens(text, skip: frozenset[str]) -> Tokens`; `read_amount_words(text) -> tuple[Decimal, str, str] | None`;
  `reminder_from(words, due: Due, *, now) -> str | None` (UTC ISO; `ValueError` plain sentence).
- `roost/tasks/repeat_words.py`: `RepeatReading(cron: str | None, words: str, problem: str | None, start, end)`;
  `find_repeat(text, *, due_hint: Due | None) -> RepeatReading | None`; `readable(cron: str) -> str` ("every Monday 09:00", "cada…" never: the UI is English).
- `roost/tasks/views.py`: `TaskView = Literal["today","upcoming","overdue","someday","done"]`;
  `in_view(task, view, today: date) -> bool`; `pick(tasks, view, *, today, query, sort) -> tuple[Task, ...]`.
- `roost/money/expense_line.py`: `ExpenseLine` (frozen) + `read_expense_line(projects, user_id, text, *, project_id, skip, now) -> ExpenseLine`; `expense_line_out(line) -> dict`.
- `roost/money/recurring.py`: `next_occurrence(cadence, anchor_day: date, after: date) -> date`; `occurrences(rule, through: date, limit) -> tuple[date, ...]`.

**Quick-line wire (`POST /api/tasks/parse` → `QuickLineOut`, additive):** the existing keys plus
`starred: bool`, `estimate_minutes: int | null`, `reminder_at: str | null`, `reminder_words: str | null`,
`recurring: str | null`, `repeat_text: str | null`, `repeat_words: str | null`, `repeat_problem: str | null`,
`assignee: {"id","name"} | null`, `assignee_words: str | null`, `assignee_question: str | null`,
`warnings: list[str]`. `QuickKind` / `skip` adds `"star" | "estimate" | "reminder" | "repeat" | "assignee"`.
`ready` is false while `project_question`, `budget_problem`, `repeat_problem` or `assignee_question` is set.

**`TaskIn` adds:** `reminder_at: str | None` (words or ISO), `recurring: str | None` (cron, `validate_cron`),
`starred: StrictBool = False`, `estimate_minutes: int | None` (1..max), `assign_bot_id: str | None`,
`assign_confirmed: StrictBool = False`. `TaskPatchIn` adds `starred`, `estimate_minutes`.
`task_out` adds `starred`, `estimate_minutes`, `repeat_text`. `POST /{id}/complete` adds `next_id`.

**Texts:** `ASSIGN_CONFIRM_TEXT = "Confirm handing this to {name} first."`,
`NO_BOT_HERE_TEXT = "No bot is called “{name}”."`, `TWO_KINDS_TEXT = "Two {kind}: kept {kept}."`,
`REPEAT_PROBLEM_TEXT = "Repeats can be daily, weekdays, weekly, monthly or yearly."`,
`REMINDER_NEEDS_DUE_TEXT = "“{words}” needs a due date."`, `EXPENSE_GONE_PROJECT_TEXT = "Its project is gone; restore it into another project."`,
`NO_PROJECT_HERE_TEXT` (reused from `roost/tasks/quick_line.py`).

**Routes:**
| Route | Body / query | Answer |
|---|---|---|
| `GET /api/tasks?view=&q=&sort=` | view ∈ TaskView, q ≤ 100, sort ∈ `due · priority · created` | `TaskOut[]` (no `view`: today's behaviour) |
| `POST /api/tasks/{id}/reopen` | — | `TaskOut` (404 not the user's or not closed) |
| `POST /api/tasks/move-overdue` | `{to: str}` (words, default "today") | `{moved: [{id, due_date, reminder_at, pre_reminders}]}` (the values before) |
| `POST /api/tasks/restore-dues` | `{items: [{id, due_date, reminder_at, pre_reminders}]}` ≤ 200 | `{restored: int}`; all-or-nothing |
| `POST /api/money/parse` | `{text, project_id?, skip[]}` | `ExpenseLineOut` |
| `PATCH /api/money/expenses/{id}` | `{amount?, note?, vendor?, spent_at?, project_id?}` | row |
| `DELETE /api/money/expenses/{id}` | — | 204 |
| `POST /api/money/expenses/{id}/restore` | — | row (422 `EXPENSE_GONE_PROJECT_TEXT`) |
| `POST /api/money/expenses/move` | `{expense_ids: [1..100 unique], project_id}` | `{moved: [{id, from_project_id}]}`; all-or-nothing |
| `GET/POST /api/money/recurring`, `PATCH/DELETE /api/money/recurring/{id}` | `RecurringIn {amount, project_id, cadence, anchor_day?, note?, vendor?, currency?, ends_on?}` | `RecurringOut` |
| `GET /api/money/upcoming?project_id=` | — | `[{recurring_id, project_id, day, amount, currency, note}]` |
| `GET /api/money/trend?months=&project_id=` | 1..24 | `{months: [{month, totals: {EUR: "12.00", …}}]}` |
| `GET /api/money/export.csv?from=&to=&project_id=` | months `YYYY-MM` | `text/csv` attachment |
| `GET /api/money/general?before=` | ISO day cursor | `{expenses: row[], next: str | null}` |

**Events:** every write publishes the existing `money_changed` / `tasks_changed` frames
(`expense_updated`, `expense_deleted`, `expense_created`; new `MoneyChange` value `"recurring_changed"`).

## Review Focus

1. **Ownership on every new write route** (Tasks 8, 10, 12): another user's id → 404, nothing written;
   in a batch, one foreign id refuses the whole batch (`test_a_foreign_id_refuses_the_whole_move`).
2. **Money integrity:** no float, no cross-currency sum (trend and CSV per currency), a voided or deleted
   repeating charge is never re-made, catch-up is idempotent under two concurrent reads.
3. **Assign stays inside the gate:** no tool or run is started without `assign_confirmed`; the queued
   item is a plain `message` with `ORIGIN_YOU` (Task 4, `test_assign_needs_confirmation`).
4. **Security review:** one, after Batch B, over `roost/gateway/routes/money_edit.py`,
   `roost/money/expense_store.py` (restore, move_many), the tasks' `move-overdue` / `restore-dues`
   (Task 10, reviewed with Batch C) and the CSV export's formula guard (Task 14).

## Batches

- **A — the rich lines (ship first):** 1 → 2 → 3 → 4 → 5.
- **B — expense line and editing:** 6 → 7, 8 → 9. **Security review after 8.**
- **C — task views:** 10 → 11 (10 joins the security review's second pass).
- **D — repeating expenses:** 12 → 13.
- **E — reports and the General inbox:** 14 → 15.
- **F — finish:** 16 (E2E), 17 (docs, full checks).

---

### Task 1: The safe date grammar (`day_words.py`) replaces dateutil's fuzzy read

Design §2, P2. Pure, EN + ES, both directions.

**Files:**
- Create: `roost/tasks/day_words.py`, `tests/test_day_words.py`
- Modify: `roost/tasks/nl_time.py` (drop `_rule_absolute_date` and the `dateutil` import; add `_rule_day_words`
  calling `find_day(direction="forward")`; `_extract_time` uses `guess_hour`; `pasado mañana` before `mañana`),
  `roost/money/months.py` (`_nl_time_date` → `find_day(direction="past")`, whole phrase only), `roost/constants.py`
  (`PM_GUESS_HOURS`), `tests/test_task_time.py` (only tests that asserted dateutil's lone-number reading).

**Tests (`tests/test_day_words.py`, a fixed `now = 2026-10-20 14:00 Madrid`):**
- `test_lone_numbers_are_never_dates` (parametrised over "Buy 3 apples", "iPhone 15 case", "Room 101",
  "Groceries 45 eur", "Pay 1.200€ rent": `read_date` gives no due and the title keeps every word).
- `test_day_and_month_names_en_and_es` ("15 march" → 2027-03-15, "3 de noviembre" → 2026-11-03, "Nov 3 at 9:30").
- `test_numeric_dates_are_day_first` ("3/11", "11/3", "31/02" not a date, "2026-11-03").
- `test_named_days_and_pasado_manana` (no "pasado" left in the title).
- `test_bare_weekdays_and_anchored_ones` ("Friday", "viernes", "Tuesday" → +7, "sun cream" stays a title).
- `test_week_and_month_phrases` (next week, la semana que viene, end of month, fin de mes, next month, este finde, the 15th, el día 15).
- `test_am_pm_guess` ("at 5" → 17:00 today, "at 9" → tomorrow 09:00, "a las 9 de la noche" → 21:00, "a las 15").
- `test_past_direction_for_expense_days` (ayer, anteayer, hace 3 días, el viernes pasado → 2026-10-16, "15 march" → 2026-03-15, "tomorrow" refused by `parse_spent_at`).
- `test_every_design_table_row` (the §2 example table, row by row).

- [ ] Step 1: Path guard. Step 2: write the tests; run, see them fail (`ModuleNotFoundError` / wrong dates).
- [ ] Step 3: implement `find_day` as ordered regex rules returning spans (no dateutil); wire `nl_time` and `months`.
- [ ] Step 4: `uv run pytest tests/test_day_words.py tests/test_task_time.py tests/test_quick_line.py tests/test_dates_api.py tests/test_money_values.py -q` green; then the whole suite.
- [ ] Step 5: Commit: `git add roost/tasks/day_words.py roost/tasks/nl_time.py roost/money/months.py roost/constants.py tests/test_day_words.py tests/test_task_time.py && git commit -m "feat: a safe EN/ES date grammar; a lone number is never a date"`

### Task 2: Schema v18 (starred, estimate, repeating expenses), and the task fields end to end

Design §6, P4. One migration; only the task fields are wired here (repeating expenses: Task 12).

**Files:**
- Create: `tests/fixtures/schema_v17.sql` (**first**, frozen from the current latest), `tests/test_migrations_v17.py`
  (named after the frozen version; v17 → v18 upgrade), `tests/test_task_fields_polish.py`
- Modify: `roost/db/migrations.py` (`Migration(18, "tasks and money polish", …)` with design §6 exactly; comment
  "v16 R1, v17 site_logins/routines; renumber at build time"), `roost/tasks/models.py` (`Task.starred: bool = False`,
  `Task.estimate_minutes: int | None = None`, same on `TaskDraft`; `PATCHABLE_FIELDS` adds both),
  `roost/tasks/store.py` (estimate sealed `tasks:estimate`), `roost/tasks/format.py` (`starred`, `estimate_minutes`,
  `repeat_text` = `None` until Task 3 fills it), `roost/gateway/routes/tasks.py` (`TaskIn` / `TaskPatchIn` per contract;
  `_draft` passes `reminder_at` through `build_schedule(due, reminder, pre)` and `recurring` through `validate_cron`),
  `roost/constants.py` (`TASK_ESTIMATE_MAX_MINUTES`), the `latest_version()` assertion in `tests/test_migrations.py`.

**Tests:**
- `test_v17_upgrades_to_v18_additively` (fixture DB → columns, table, unique index exist; old rows intact).
- `test_estimate_is_stored_sealed` (raw column starts `enc:v2`).
- `test_task_in_takes_recurring_reminder_star_estimate` (POST with all four → `TaskOut` echoes them; reminder words read on Madrid).
- `test_bad_cron_or_estimate_is_a_422` (plain sentence, nothing written).
- `test_patch_sets_and_clears_star_and_estimate`.

- [ ] Steps: path guard → freeze fixture → red → migration + fields → green (`tests/test_migrations*.py tests/test_tasks_api.py tests/test_task_store.py tests/test_task_fields_polish.py`) → suite.
- [ ] Commit: `git add tests/fixtures/schema_v17.sql tests/test_migrations_v17.py tests/test_task_fields_polish.py tests/test_migrations.py roost/db/migrations.py roost/tasks/models.py roost/tasks/store.py roost/tasks/format.py roost/gateway/routes/tasks.py roost/constants.py && git commit -m "feat: schema v18 adds task star and sealed estimate, repeating expenses; TaskIn takes repeat and reminder"`

### Task 3: Line tokens and repeat words (pure)

Design §3 tables. No I/O.

**Files:**
- Create: `roost/tasks/line_tokens.py`, `roost/tasks/repeat_words.py`, `tests/test_line_tokens.py`, `tests/test_repeat_words.py`
- Modify: `roost/tasks/format.py` (`repeat_text = readable(task.recurring)` when set), `roost/constants.py` (texts if not in modules).

**Tests (`test_line_tokens.py`):** `test_priority_shorthand` (`!!!`, `!!`, `!`, `!-`, `!alta`, `!baja`),
`test_priority_words_only_at_the_edges` ("Pagar luz urgente" → urgent; "dar de baja el seguro" unchanged; "urgent care appointment" → urgent only because first word — documented, asserted),
`test_two_priorities_last_wins_with_a_warning` ("Dinner 30€ !high !low" → low, title "Dinner", warning "Two priorities: kept !low"),
`test_star_tokens`, `test_estimates` (~30m, ~2h, ~1h30, ~90min, ~1,5h; ~0m and over max are warnings, words stay),
`test_reminders` (^9am, ^17:30, ^1h before with a timed due, ^1h with a day-only due uses 09:00, "remind me at 9", "avísame 1h antes"; no due → `REMINDER_NEEDS_DUE_TEXT`),
`test_amounts_with_thousands` (1.200€ → 1200.00, €1,200.50, 1.200,50€, £12,50, $12.5; "1,2345€" refused).
**Tests (`test_repeat_words.py`):** `test_daily_weekdays_weekly_monthly_yearly_en_es`, `test_every_monday_and_thursday` (`0 9 * * 1,4`),
`test_monthly_on_the_1st` (`0 9 1 * *`), `test_repeat_at_a_time` ("every day at 7" → `0 19 * * *` by the PM guess; "every day at 7am" → `0 7 * * *`),
`test_unsayable_repeats_are_a_problem` ("every 2 weeks"), `test_readable` (round-trips each cron the line or the drawer makes).

- [ ] Steps: guard → red → implement → green (`tests/test_line_tokens.py tests/test_repeat_words.py tests/test_tasks_api.py`).
- [ ] Commit: `git add roost/tasks/line_tokens.py roost/tasks/repeat_words.py roost/tasks/format.py roost/constants.py tests/test_line_tokens.py tests/test_repeat_words.py && git commit -m "feat: quick-line tokens (priority shorthand, star, estimate, reminder, amounts) and repeat words, EN and ES"`

### Task 4: The quick line reads everything; `@bot` assignment with confirmation

Design §3, P3, P5.

**Files:**
- Create: `roost/tasks/assign.py` (`assign_task(app_state, user_id, task, bot) -> None`: posts your message in the bot's main
  chat via `talk.ensure_main_thread` + `talk.add_message(role="user")` and `turns.submit(WorkDraft(kind=MESSAGE, origin=ORIGIN_YOU, …))`),
  `tests/test_quick_line_rich.py`, `tests/test_task_assign.py`
- Modify: `roost/tasks/quick_line.py` (`read_quick_line` uses `read_tokens`, `find_repeat`, `find_day`; resolves `@name` over
  `bots.list(user_id)` by exact casefold name, then a unique prefix, longest multi-word run first; unknown → `NO_BOT_HERE_TEXT`;
  `quick_line_out` per contract), `roost/gateway/routes/task_detail.py` (`QuickLineIn.skip` adds the new kinds),
  `roost/gateway/routes/tasks.py` (`create_task`: `assign_bot_id` without `assign_confirmed` → 422 `ASSIGN_CONFIRM_TEXT`;
  a foreign bot → 422 "No such bot."; the task's `owner` = bot id; then `assign_task`), `roost/tasks/store.py` (`owner` on draft).

**Tests:** `test_the_whole_rich_line` ("Call plumber tomorrow at 9 #Renovation €200 !! * ~1h ^30m before every Monday @Scout" → every field, title "Call plumber"),
`test_spanish_rich_line`, `test_skip_puts_each_kind_back`, `test_unknown_bot_is_a_question`, `test_two_projects_last_wins_with_a_warning`,
`test_repeat_with_no_date_starts_on_the_first_occurrence`;
`test_task_assign.py`: `test_assign_needs_confirmation` (422, no task, no work item), `test_confirmed_assign_queues_your_message`
(one `message` item, origin `ORIGIN_YOU`, untainted, the user message in the bot's main chat), `test_another_users_bot_cannot_be_assigned`.

- [ ] Steps: guard → red → implement → green (`tests/test_quick_line.py tests/test_quick_line_rich.py tests/test_task_assign.py tests/test_task_detail_api.py`) → suite.
- [ ] Commit: `git add roost/tasks/assign.py roost/tasks/quick_line.py roost/tasks/store.py roost/gateway/routes/task_detail.py roost/gateway/routes/tasks.py tests/test_quick_line_rich.py tests/test_task_assign.py && git commit -m "feat: the quick line reads star, estimate, reminder, repeat and @bot; a confirmed @bot gets your message"`

### Task 5: The web's rich quick line: chips, autocomplete, the "?" help

Design §7 (Quick lines), P1.

**Files:**
- Create: `web/src/components/tasks/QuickSuggest.tsx` (a listbox under the input; `aria-activedescendant`),
  `web/src/components/tasks/quickSuggest.ts` (pure: the token being typed at the caret, `#`/`@`/`!` → options; accept → new text + caret),
  `web/src/components/tasks/QuickHelp.tsx` (a `ui/Popover` from a "?" `IconButton`), `web/src/components/tasks/quickHelp.ts`
  (the token table, shared with the expense line: `TASK_TOKENS`, `EXPENSE_TOKENS`, each `{token, en, es, means}`),
  `web/tests/quickSuggest.test.ts`, `web/tests/QuickHelp.test.tsx`
- Modify: `web/src/components/tasks/QuickAdd.tsx`, `quickChips.ts` (chips for star, estimate, reminder, repeat, assignee;
  warnings as `tone: "warn"`; the assignee chip has "Assign to {name}" which sets `assign_confirmed`), `useQuickLine.ts`,
  `web/src/api/tasks.ts` (`QuickLineRichOut = QuickLineOut & {…}`, `TaskIn` fields), `web/src/components/tasks/constants.ts`,
  `web/src/styles/tasks.css` (append), `web/tests/QuickAdd.test.tsx`, `web/tests/quickChips.test.ts`.

**Tests:** `quickSuggest.test.ts`: `it("offers projects after #, bots after @, levels and star after !")`,
`it("accepting replaces only the token at the caret")`, `it("multi-word names are inserted whole")`;
`QuickAdd.test.tsx`: `it("Tab and Enter accept a suggestion, Esc closes it")`, `it("Enter is blocked until the bot chip is confirmed")`,
`it("shows a warning chip and never blocks on it")`, `it("× on a chip sends that kind in skip")`;
`QuickHelp.test.tsx`: `it("lists every token with an English and a Spanish example")`, `it("is one column at phone width")` (class check).

- [ ] Steps: guard → red → implement → green (`npx vitest run tests/quickSuggest.test.ts tests/QuickAdd.test.tsx tests/quickChips.test.ts tests/QuickHelp.test.tsx tests/tokens.test.ts`) → `npm test && npm run build && npm run size`.
- [ ] Commit: `git add web/src/components/tasks/QuickSuggest.tsx web/src/components/tasks/quickSuggest.ts web/src/components/tasks/QuickHelp.tsx web/src/components/tasks/quickHelp.ts web/src/components/tasks/QuickAdd.tsx web/src/components/tasks/quickChips.ts web/src/components/tasks/useQuickLine.ts web/src/components/tasks/constants.ts web/src/api/tasks.ts web/src/styles/tasks.css web/tests/quickSuggest.test.ts web/tests/QuickHelp.test.tsx web/tests/QuickAdd.test.tsx web/tests/quickChips.test.ts && git commit -m "feat: the quick line suggests #projects, @bots and !levels, shows every chip, and has a token help"`

### Task 6: The expense line on the server; exact-or-ask names; vendor and star on `ExpenseIn`

Design §4, P6, P7.

**Files:**
- Create: `roost/money/expense_line.py`, `roost/gateway/routes/money_line.py` (`POST /api/money/parse`), `tests/test_expense_line.py`
- Modify: `roost/gateway/routes/money.py` (`ExpenseIn.vendor` ≤ `MAX_EXPENSE_VENDOR_LENGTH`, `ExpenseIn.starred: StrictBool = False`;
  a `project` name goes through `ProjectService.resolve(change=True)`: refusal → 422 `NO_PROJECT_HERE_TEXT`/its question, never made),
  `roost/gateway/app.py` (include `money_line_router`), `roost/constants.py`, `tests/test_money_api.py` (the test that made a project from a typed name now expects 422).

**Tests:** `test_expense_line_en` ("€12 lunch #Trip yesterday vendor:Mercadona *"), `test_expense_line_es`
("12,50€ comida #Viaje ayer tienda:\"El Corte Inglés\""), `test_a_future_day_is_a_problem`, `test_unknown_project_is_a_question_never_made`,
`test_project_page_default_and_currency_from_project`, `test_a_repeat_word_reads_as_a_cadence` ("€9,99 Netflix #Casa monthly"),
`test_typed_project_name_never_creates_a_project_on_the_web`, `test_vendor_and_star_are_saved`.

- [ ] Steps: guard → red → implement → green (`tests/test_expense_line.py tests/test_money_api.py tests/test_money_routes_tools_polish.py`) → suite.
- [ ] Commit: `git add roost/money/expense_line.py roost/gateway/routes/money_line.py roost/gateway/routes/money.py roost/gateway/app.py roost/constants.py tests/test_expense_line.py tests/test_money_api.py && git commit -m "feat: the expense line (amount, #project, past day, vendor, star, repeat); web names are exact or ask"`

### Task 7: The web's expense line, and the money form's quality fixes

Design §7 (Money tab), audit quality rows.

**Files:**
- Create: `web/src/components/board/ExpenseLine.tsx`, `web/src/components/board/useExpenseLine.ts`, `web/src/components/board/constants.ts`,
  `web/tests/ExpenseLine.test.tsx`, `web/tests/moneyFixtures.ts`
- Modify: `web/src/components/board/MoneyBoard.tsx` (the line on top; the `ExpenseAddForm` is no longer on the Money tab; `PastMonth` copy:
  "Type a day in the line, like ‘yesterday’ or ‘3/10’"; the line shows on past months too), `ExpenseAddForm.tsx` (`Button` kit,
  placeholder from the project's currency, keeps the task drawer's use), `money.ts` (`parseAmountInput` strips € $ £),
  `ExpenseList.tsx` (shows the vendor), `web/src/api/money.ts` (`ExpenseLineOut`, `parseExpenseLine`, `ExpenseIn.vendor/starred`),
  `web/src/components/tasks/quickHelp.ts` (already has `EXPENSE_TOKENS`), `web/src/styles/board.css` (append),
  `web/tests/money.test.ts`, `web/tests/ExpenseAddForm.test.tsx`, `web/tests/MoneyBoard.test.tsx`, `web/tests/ExpenseList.test.tsx`.

**Tests:** `ExpenseLine.test.tsx`: `it("shows amount, project, day, vendor and star chips from the server")`, `it("adds exactly the reading")`,
`it("# suggests every project, not only this month's")`, `it("a project question blocks Enter")`, `it("has the ? help with the expense tokens")`;
`money.test.ts`: `it("reads $12 and £5")`; `ExpenseAddForm.test.tsx`: `it("uses the project's currency in the placeholder")`;
`ExpenseList.test.tsx`: `it("shows the vendor")`.

- [ ] Steps: guard → red → implement → green (vitest on those files + `tokens.test.ts`) → `npm test && npm run build && npm run size`.
- [ ] Commit: `git add web/src/components/board/ExpenseLine.tsx web/src/components/board/useExpenseLine.ts web/src/components/board/constants.ts web/src/components/board/MoneyBoard.tsx web/src/components/board/ExpenseAddForm.tsx web/src/components/board/money.ts web/src/components/board/ExpenseList.tsx web/src/api/money.ts web/src/styles/board.css web/tests/ExpenseLine.test.tsx web/tests/moneyFixtures.ts web/tests/money.test.ts web/tests/ExpenseAddForm.test.tsx web/tests/MoneyBoard.test.tsx web/tests/ExpenseList.test.tsx && git commit -m "feat: the expense line on the Money tab; amounts in any sign, vendors shown, the form uses the kit"`

### Task 8: Edit, delete, restore and bulk-move expenses (routes) — security review after

Design §8, P9. **Review focus 1 and 2.**

**Files:**
- Create: `roost/gateway/routes/money_edit.py`, `tests/test_money_edit_api.py`
- Modify: `roost/money/expense_store.py` (`restore(user_id, id)`: clears `deleted_at` only `WHERE id = ? AND user_id = ? AND deleted_at IS NOT NULL`,
  `require_project` in the same session; `move_many(user_id, ids, project_id)`: one transaction, `require_project`, `UPDATE … WHERE user_id = ? AND id IN (…) AND deleted_at IS NULL`,
  rowcount must equal `len(ids)` else rollback and `None`), `roost/money/service.py` (`restore_expense`, `move_expenses`: open project only;
  each linked expense checked with `project_conflict` against its task; events), `roost/gateway/app.py`.

**Tests:** `test_patch_changes_amount_note_vendor_day_project`, `test_patch_reads_day_words_and_refuses_a_future_day`,
`test_patch_into_an_archived_or_foreign_project_is_refused`, `test_patch_cannot_move_a_task_expense_out_of_its_project`,
`test_another_users_expense_is_404_for_patch_delete_restore`, `test_delete_then_restore`, `test_restore_into_a_deleted_project_is_refused`,
`test_bulk_move_moves_all_and_reports_where_from`, `test_a_foreign_id_refuses_the_whole_move`, `test_bulk_move_limits_and_duplicates_are_422`,
`test_every_write_needs_the_origin_header`, `test_amount_stays_decimal_and_sealed`.

- [ ] Steps: guard → red → implement → green (`tests/test_money_edit_api.py tests/test_money_store.py tests/test_money_api.py`) → suite.
- [ ] Commit: `git add roost/gateway/routes/money_edit.py roost/money/expense_store.py roost/money/service.py roost/gateway/app.py tests/test_money_edit_api.py && git commit -m "feat: edit, delete, restore and bulk-move expenses over HTTP, all-or-nothing and per user"`
- [ ] **Then the security review** (Batch B gate): auth, ownership, money integrity over the files above.

### Task 9: Edit and delete expenses in the web, with Undo toasts

Design §7, P9.

**Files:**
- Create: `web/src/components/board/ExpenseEditRow.tsx`, `web/tests/ExpenseEditRow.test.tsx`
- Modify: `web/src/ui/Toast.tsx` (`ToastOptions.action?: {label: string; run: () => void}`; the action is a kit `Button`; it dismisses on run),
  `web/src/components/board/ExpenseList.tsx` (row menu: Edit, Delete; Void/Restore), `MoneyBoard.tsx` (`expenseActions` gains edit,
  delete → toast "Expense deleted" + Undo → restore; void → toast + Undo), `web/src/api/money.ts` (`updateExpense`, `deleteExpense`, `restoreExpense`, `moveExpenses`),
  `web/src/styles/board.css` (append), `web/tests/Toast.test.tsx`.

**Tests:** `it("edits amount, note, day, project and vendor in place")`, `it("Esc cancels an edit")`, `it("delete shows Undo, which restores")`,
`it("void shows Undo")`, `Toast.test.tsx`: `it("runs the action once and closes")`.

- [ ] Steps as Task 7. Commit: `git add web/src/components/board/ExpenseEditRow.tsx web/src/ui/Toast.tsx web/src/components/board/ExpenseList.tsx web/src/components/board/MoneyBoard.tsx web/src/api/money.ts web/src/styles/board.css web/tests/ExpenseEditRow.test.tsx web/tests/Toast.test.tsx && git commit -m "feat: edit and delete expenses in place, with Undo for delete and void"`

### Task 10: Task views, search, sort, reopen, move-overdue and restore-dues (server)

Design P11, §7 (Tasks tab). **Review focus 1.**

**Files:**
- Create: `roost/tasks/views.py`, `roost/gateway/routes/task_views.py`, `tests/test_task_views.py`, `tests/test_task_views_api.py`
- Modify: `roost/gateway/routes/tasks.py` (`list_tasks` takes `view`, `q`, `sort`; `complete_task` answers `next_id`),
  `roost/tasks/service.py` (`reopen`, `move_dues(user_id, items)` in one transaction), `roost/tasks/store.py` (`reopen`, `set_dues`), `roost/gateway/app.py`.

**Tests (`test_task_views.py`, today fixed):** `test_today_has_due_today_and_timed_today`, `test_overdue_is_before_today_and_open`,
`test_upcoming_is_after_today`, `test_someday_has_no_due`, `test_done_is_newest_first_and_capped`, `test_search_is_case_and_accent_insensitive_over_title_and_description`,
`test_sort_by_due_then_priority`; (`test_task_views_api.py`) `test_view_query_and_sort_on_the_route`, `test_reopen_and_undo_a_recurring_complete`
(complete → `next_id`; reopen + delete next), `test_move_overdue_to_words_answers_the_old_values`, `test_restore_dues_puts_them_back`,
`test_another_users_task_in_restore_dues_refuses_all`, `test_restore_dues_validates_iso`.

- [ ] Steps: guard → red → implement → green (`tests/test_task_views*.py tests/test_tasks_api.py tests/test_task_store.py`) → suite.
- [ ] Commit: `git add roost/tasks/views.py roost/gateway/routes/task_views.py roost/gateway/routes/tasks.py roost/tasks/service.py roost/tasks/store.py roost/gateway/app.py tests/test_task_views.py tests/test_task_views_api.py && git commit -m "feat: task views, search and sort on the server; reopen, move overdue and restore dues"`

### Task 11: The Tasks tab: views, search, sort, quick reschedule, Move all overdue, Undo

Design §7 (Tasks tab); audit 4 and 9; chip quality rows.

**Files:**
- Create: `web/src/components/board/TaskViews.tsx` (Tabs + search `Input` + sort `Select`), `web/src/components/board/RescheduleMenu.tsx`
  (menu items + a `Popover` with a typed phrase previewed by `/api/dates/parse`), `web/tests/TaskViews.test.tsx`, `web/tests/RescheduleMenu.test.tsx`
- Modify: `web/src/components/board/TasksBoard.tsx` (view state in `?view=`, default Today; a project page keeps its list), `TaskRow.tsx`
  (Reschedule in the menu; chips: repeat text, star, estimate, tags; the comment matches `taskChips.ts`), `taskChips.ts` (comment fixed),
  `web/src/api/tasks.ts` (`listTasks` view/q/sort, `reopenTask`, `moveOverdue`, `restoreDues`), `web/src/styles/tasks.css` (append),
  `web/tests/TasksBoard.test.tsx`, `web/tests/taskFixtures.ts`.

**Tests:** `it("switches views and keeps the view in the URL")`, `it("searches as you type, debounced")`, `it("sorts by priority")`,
`it("reschedules to tomorrow from the row menu")`, `it("a typed phrase is previewed then applied")`, `it("Move all overdue shows Undo, which restores")`,
`it("completing shows Undo, which reopens and removes the next repeat")`, `it("the repeat chip says how often")`.

- [ ] Steps as Task 7. Commit: `git add web/src/components/board/TaskViews.tsx web/src/components/board/RescheduleMenu.tsx web/src/components/board/TasksBoard.tsx web/src/components/board/TaskRow.tsx web/src/components/board/taskChips.ts web/src/api/tasks.ts web/src/styles/tasks.css web/tests/TaskViews.test.tsx web/tests/RescheduleMenu.test.tsx web/tests/TasksBoard.test.tsx web/tests/taskFixtures.ts && git commit -m "feat: Today, Upcoming, Overdue, Someday and Done, with search, sort, quick reschedule and Undo"`

### Task 12: Repeating expenses (server): rules, lazy catch-up, Upcoming charges

Design §5. **Review focus 2.**

**Files:**
- Create: `roost/money/recurring.py`, `roost/money/recurring_store.py`, `roost/money/recurring_service.py`, `roost/gateway/routes/money_recurring.py`,
  `tests/test_money_recurring.py`, `tests/test_money_recurring_api.py`
- Modify: `roost/money/service.py` (reads call `catch_up` first: `summary`, `list_expenses`, `for_task`), `roost/projects/service.py`
  (`detail` catches up and adds `upcoming`; `delete` deletes the project's rules), `roost/gateway/routes/projects.py` (`upcoming_charges` in the detail),
  `roost/money/expense_line.py` + `roost/gateway/routes/money.py` (an expense line with a cadence also creates the rule: the first charge is the typed day),
  `roost/gateway/app.py`, `roost/constants.py`.

**Tests:** `test_monthly_on_the_31st_lands_on_the_last_day`, `test_weekly_and_yearly_next_occurrence`,
`test_catch_up_makes_each_missed_charge_once` (3 months → 3 expenses, `spent_at` = each occurrence),
`test_catch_up_is_idempotent_under_two_reads` (`asyncio.gather` two reads → no duplicates), `test_catch_up_is_capped`,
`test_a_voided_or_deleted_charge_is_not_remade`, `test_archived_project_pauses_its_rule`, `test_rule_amount_and_note_are_sealed`,
`test_upcoming_charges_lists_the_next_31_days`, `test_recurring_routes_are_per_user` (404), `test_ends_on_stops_the_rule`.

- [ ] Steps: guard → red → implement → green (`tests/test_money_recurring*.py tests/test_money_*.py tests/test_projects*.py`) → suite.
- [ ] Commit: `git add roost/money/recurring.py roost/money/recurring_store.py roost/money/recurring_service.py roost/gateway/routes/money_recurring.py roost/money/service.py roost/projects/service.py roost/gateway/routes/projects.py roost/money/expense_line.py roost/gateway/routes/money.py roost/gateway/app.py roost/constants.py tests/test_money_recurring.py tests/test_money_recurring_api.py && git commit -m "feat: repeating expenses made lazily and idempotently when money is read, with upcoming charges"`

### Task 13: Repeating expenses and Upcoming charges on project pages

**Files:**
- Create: `web/src/components/projects/UpcomingCharges.tsx`, `web/src/components/projects/RepeatingExpenses.tsx`, `web/tests/UpcomingCharges.test.tsx`
- Modify: `web/src/components/projects/ProjectMoney.tsx` (the expense line fixed to the project; the two sections), `web/src/api/money.ts`
  (`listRecurring`, `updateRecurring`, `stopRecurring`, `listUpcoming`), `web/src/api/projects.ts` (`ProjectDetailOut & {upcoming_charges}`),
  `web/src/styles/projects.css` (append), `web/tests/Project.test.tsx`.

**Tests:** `it("lists upcoming charges with day and amount in the project's currency")`, `it("Stop asks once and ends the rule")`,
`it("the expense line with 'monthly' shows a repeat chip")`.

- [ ] Steps as Task 7. Commit: `git add web/src/components/projects/UpcomingCharges.tsx web/src/components/projects/RepeatingExpenses.tsx web/src/components/projects/ProjectMoney.tsx web/src/api/money.ts web/src/api/projects.ts web/src/styles/projects.css web/tests/UpcomingCharges.test.tsx web/tests/Project.test.tsx && git commit -m "feat: a project's repeating expenses and upcoming charges"`

### Task 14: Money reports (server): trend, CSV, General inbox

**Files:**
- Create: `roost/money/reports.py` (pure: `trend(expenses, months) -> tuple[MonthTotals, ...]` per currency, voids out; `csv_rows(...)` with the
  formula guard), `roost/gateway/routes/money_reports.py`, `tests/test_money_reports.py`
- Modify: `roost/money/expense_store.py` (`list_range(user_id, first, following, project_id=None)`, `list_general(user_id, before, limit)`),
  `roost/money/service.py`, `roost/gateway/app.py`.

**Tests:** `test_trend_is_per_currency_and_never_mixed`, `test_trend_months_bounds_are_422`, `test_csv_has_headers_and_decimal_strings`,
`test_csv_guards_formula_cells` (`=1+1` → `'=1+1`), `test_csv_is_per_user_and_capped`, `test_general_inbox_pages_newest_first`,
`test_reports_catch_up_repeating_charges_first`.

- [ ] Steps: guard → red → implement → green → suite.
- [ ] Commit: `git add roost/money/reports.py roost/gateway/routes/money_reports.py roost/money/expense_store.py roost/money/service.py roost/gateway/app.py tests/test_money_reports.py && git commit -m "feat: money trend per currency, CSV export and the General inbox over HTTP"`

### Task 15: Reports on the Money tab (plain SVG, lazy) and the General inbox with bulk move

Design P10.

**Files:**
- Create: `web/src/components/board/reports/MoneyReports.tsx` (default export, lazy), `TrendChart.tsx` (SVG bars per month, one series per
  currency, `<title>` and a visually-hidden table for screen readers), `ProjectBars.tsx` (the month's `by_project`, grouped by currency),
  `GeneralInbox.tsx` (checkboxes, "Move to…" `Select`, Undo → `moveExpenses` back per `from_project_id`), `web/tests/MoneyReports.test.tsx`, `web/tests/GeneralInbox.test.tsx`
- Modify: `MoneyBoard.tsx` (a "Reports" disclosure that `lazy()`-loads `MoneyReports`; "Export CSV" link), `web/src/api/money.ts`, `web/src/styles/board.css` (append; colours from tokens, project colours from data).

**Tests:** `it("draws one bar group per month and one series per currency")`, `it("has an accessible table of the same numbers")`,
`it("never sums two currencies")`, `it("selects rows and moves them, with Undo")`, `it("reports load as their own chunk")` (dynamic import mocked).

- [ ] Steps as Task 7; `npm run size` must stay within budget (reports are not in the entry).
- [ ] Commit: `git add web/src/components/board/reports/MoneyReports.tsx web/src/components/board/reports/TrendChart.tsx web/src/components/board/reports/ProjectBars.tsx web/src/components/board/reports/GeneralInbox.tsx web/src/components/board/MoneyBoard.tsx web/src/api/money.ts web/src/styles/board.css web/tests/MoneyReports.test.tsx web/tests/GeneralInbox.test.tsx && git commit -m "feat: money reports in plain SVG, CSV export and the General inbox with bulk move"`

### Task 16: E2E — the rich lines, views, editing, repeats, reports

**Files:** Create `web/e2e/tasks-money.spec.ts`; Modify `web/e2e/tasks.spec.ts`, `web/e2e/records.spec.ts` only where a selector moved (the expense form).
**Specs:** `test("the rich task line adds a starred, repeating, reminded task")`, `test("@bot needs a confirm and lands in its chat")`,
`test("autocomplete with the keyboard")`, `test("the expense line adds with vendor and star; edit and Undo delete")`,
`test("views, search and Move all overdue with Undo")`, `test("a monthly expense shows in Upcoming charges")`,
`test("reports and General inbox bulk move")`, `test("the ? help fits a phone")` (viewport 375×740).

- [ ] Disk guard, then `ROOST_DESKS_DIR=$(mktemp -d) make e2e`.
- [ ] Commit: `git add web/e2e/tasks-money.spec.ts web/e2e/tasks.spec.ts web/e2e/records.spec.ts && git commit -m "test: E2E for the rich lines, task views, expense editing, repeats and reports"`

### Task 17: Docs and the full checks

**Files:** Modify `CLAUDE.md` (Documentation Map: both new docs; Architecture: one paragraph on the safe grammar, the rich lines,
`@bot` as your message, views on the server, lazy repeating expenses, reports), `tests/test_docs.py` (both docs listed),
this plan's status line.
- [ ] `uv run pytest --cov=roost --cov-fail-under=80`, `cd web && npm test && npm run build && npm run size`, `make e2e` (disk guard).
- [ ] Commit: `git add CLAUDE.md tests/test_docs.py docs/plans/2026-10-20-roost-tasks-money-polish.md && git commit -m "docs: tasks and money polish in CLAUDE.md"`
