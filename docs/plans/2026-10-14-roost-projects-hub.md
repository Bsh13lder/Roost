# Roost Projects Hub (Migration Part 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One project holds its tasks, money (a total budget and/or a monthly limit, expenses and top-ups), notes and documents. The LazyClaw features Roost lost come back, every bot can work with projects, and the Board gets a Projects tab with a page per project.

**Architecture:**
- **One project table.** Today's `money_projects` table becomes the project table (schema v13, additive only). Tasks, notes and documents get an optional `project_id`.
- **One place for the sums.** `roost/projects/numbers.py` holds the pure calculations: total and monthly budgets, other currencies, bar tones, task planned/spent/left and progress.
- **`ProjectService`** (`roost/projects/`) owns create, update, archive, delete, top-ups and the project page's detail. The money, task, note and document services learn the `project` link.
- **Bots get project tools**, and the existing record tools take a `project` argument.
- **The web Board** gets a first tab, Projects, a page per project with Tasks · Money · Notes · Docs, budget bars, top-up history, and starred and void expenses.

**Tech Stack:** The S1 stack, with no new dependency:
- Python 3.12 (uv), FastAPI, aiosqlite, pydantic 2, `cryptography` (`enc:v2` + AAD), `Decimal` amounts.
- Vite, React 19 and TypeScript, tested with vitest + Testing Library and Playwright.

**Spec:** `docs/plans/2026-10-14-roost-projects-hub-design.md`, **including §5 "Refinements after reading the code" (H1–H16), which overrides the earlier sections where they differ**. This plan runs **after** the stuck-flow plan (`docs/plans/2026-10-14-roost-stuck-flow.md`) is complete. Schema v12 is the stuck cards, so this plan's schema is v13.

> **Status (2026-10-15): ready to execute.** Drafted, checked per task and across tasks, re-anchored to the finished stuck flow.

## Global Constraints

- **Path guard, first in every task:**
  - `git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel` must print `/Users/blckit/Desktop/Code_Projects/roost`.
  - `git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current` must print `night-1`.
  - If either check fails, stop.
- **Where you may edit:**
  - Edit only under `/Users/blckit/Desktop/Code_Projects/roost`.
  - `/Users/blckit/Desktop/Code_Projects/lazyclaw` is never touched. That includes `lazyclaw/data`, its containers and its `make` targets.
- **Clean room (spec §10.3):**
  - Never open, fetch or search for the open-dot repos, `~/Roost-review/` or `~/.claude/projects/**`.
  - Do not use browser MCP tools.
  - Only MIT, Apache-2.0, BSD, ISC or MPL-2.0 dependencies. This plan adds none.
  - Code ported from LazyClaw keeps an SPDX header and a `THIRD_PARTY_NOTICES.md` entry, like `web/src/components/board/money.ts:1-2`.
- **Ports:** every listener binds `127.0.0.1` only. Never use port 9222.
- **Tests:**
  - Tests first: red, then green.
  - At least 80% line coverage on new code (`uv run pytest --cov=roost --cov-fail-under=80`).
  - Tests never call a real LLM and never launch a real browser (`tests/conftest.py` forces scripted and fake).
- **Code rules:**
  - Files at most 800 lines (typically 200–400); functions under 50 lines.
  - Frozen dataclasses; no mutation of shared state (reassign tuples and dicts instead).
  - Pydantic validation at every boundary.
  - Explicit error handling with user-friendly messages.
  - No magic values: they go in `roost/constants.py`, in the **Finance / Tasks / Notes / Documents sections**. Never at the end of the file, where the stuck-flow section lives.
- **Encryption:** every user-content column is `enc:v2` with AAD `user_aad(user_id, "<table>:<column>")`. New encrypted columns are `money_projects:monthly_budget` and `tasks:allocated_budget`. Ids, dates, status, colour and flags are plaintext.
- **Queries:**
  - Every query on user data has `user_id` in its `WHERE`. Another user's id gives **404**, never the object.
  - A `project_id` the user doesn't own is refused with 422 / "Refused: No such project.".
- **Amounts** are `Decimal`, parsed with `roost/money/amounts.py` `parse_amount` (positive, at most 2 decimals, at most `MAX_EXPENSE_AMOUNT`). The web never adds amounts: the server sends every number as a string.
- **Vocabulary (§7.4):** Board, Projects, bot, "from web content". The word "category" no longer appears in UI copy. `tasks.category` is shown as the task's **list**. Never "Take the wheel", ">Desk<" or " in Talk" (`tests/test_vocabulary.py`).
- **Git:**
  - Commit after each task's green tests. Stage files **by name**, never `git add -A`, `-a` or `.`.
  - Messages are conventional, with **no Co-Authored-By or any AI attribution line**.
- **Disk guard:** before `npm install` or `make e2e`, run `df -g /System/Volumes/Data | awk 'NR==2{print $4}'`. If it shows fewer than 8 GB free, stop and report.
- **Commands:**
  - Prefix every command with `cd /Users/blckit/Desktop/Code_Projects/roost &&`.
  - `uv run pytest tests/<file>.py -q` runs one file; `uv run pytest -q` runs the suite.
  - `cd web && npx vitest run tests/<file>` runs one web test; `npm test` runs them all; `npm run build && npm run size` checks the build and bundle size.

## Review Focus

These are the input classes the spec implies but no task's main tests exercise. The test for each one is added to the task named.

1. **A bot names a project that almost matches**, for example "Renovaton".
   - Expected: a change tool refuses with "Did you mean …?", a read tool may answer, and nothing is created except through `log_expense`.
   - Test: Task 7, `test_a_near_miss_project_name_never_changes_anything`.
2. **Undoing a top-up after it was edited.**
   - Expected: the credit and all of its edits leave the total together, and `budget == Σ live rows` still holds.
   - Test: Task 2, `test_undoing_an_edited_top_up_removes_it_and_its_edits`.
3. **An expense right at a month boundary.** Madrid runs ahead of UTC, so one entered just after midnight on the 1st in Madrid, while UTC still shows the previous month, belongs to the new Madrid month. One on the 31st at 23:30 Madrid belongs to the old one.
   - Expected: each counts in its Madrid month.
   - Test: Task 3, `test_an_expense_on_the_last_madrid_evening_counts_in_that_month`.
4. **Deleting a project whose tasks, notes and documents are open in other tabs.**
   - Expected: the items survive, unlinked; the expenses appear under General; the other tabs refresh (`money_changed project_deleted` bumps tasks, notes and documents).
   - Tests: Task 6, `test_deleting_a_project_keeps_its_items_and_moves_its_money_to_general`. Task 9, `it("refreshes tasks, notes and documents when a project is deleted")`.
5. **A tainted run (one that read a web page) tries `add_topup`, `undo_topup`, `update_project` or `set_document_project`.**
   - Expected: each is refused with the tainted-change text.
   - Test: Task 7, `test_a_tainted_run_cannot_change_projects_or_their_money`.

---

## Shared Contract (every task uses these exact names)

### Schema v13 "projects hub" (`roost/db/migrations.py`, appended after v12)

```python
Migration(13, "projects hub", (
    AddColumn("money_projects", "color", "TEXT"),
    AddColumn("money_projects", "start_date", "TEXT"),
    AddColumn("money_projects", "due_date", "TEXT"),
    AddColumn("money_projects", "monthly_budget", "TEXT"),          # enc:v2 decimal string
    AddColumn("money_projects", "lead_bot_id", "TEXT REFERENCES bots(id) ON DELETE SET NULL"),
    AddColumn("money_expenses", "step_id", "TEXT"),
    AddColumn("money_expenses", "is_favorite", "INTEGER NOT NULL DEFAULT 0"),
    AddColumn("money_topups", "topup_id", "TEXT"),
    AddColumn("tasks", "project_id", "TEXT REFERENCES money_projects(id) ON DELETE SET NULL"),
    AddColumn("tasks", "allocated_budget", "TEXT"),                   # enc:v2 decimal string
    AddColumn("notes", "project_id", "TEXT REFERENCES money_projects(id) ON DELETE SET NULL"),
    AddColumn("documents", "project_id", "TEXT REFERENCES money_projects(id) ON DELETE SET NULL"),
    "CREATE INDEX IF NOT EXISTS idx_tasks_user_project ON tasks(user_id, project_id)",
    "CREATE INDEX IF NOT EXISTS idx_notes_user_project ON notes(user_id, project_id)",
    "CREATE INDEX IF NOT EXISTS idx_documents_user_project ON documents(user_id, project_id)",
)),
```

Some statuses are plaintext values on columns that have no CHECK, so they need no rebuild:
- `money_projects.status`: `active` | `archived`
- `money_expenses.status`: `posted` | `void`
- `tasks.status` gains `failed`

Task 2 freezes `tests/fixtures/schema_v12.sql` and adds `tests/test_migrations_v12.py`.

### Constants (`roost/constants.py`)

Add these to the **Finance** section, after the existing finance constants:

```python
PROJECT_STATUSES = ("active", "archived")
PROJECT_COLORS = ("#64748b", "#ef4444", "#f97316", "#eab308", "#22c55e", "#14b8a6", "#3b82f6", "#8b5cf6", "#ec4899")
DEFAULT_PROJECT_COLOR = PROJECT_COLORS[0]
BUDGET_WARN_PERCENT = 80          # bar turns amber
BUDGET_OVER_PERCENT = 100         # bar turns red
PROJECT_LIST_LIMIT = 100
PROJECT_PAGE_ITEMS = 20           # latest expenses / notes / documents on a project page
TOPUP_SOURCE_MAX_CHARS = 120
```

`GENERAL_CATEGORY_NAME` is renamed to `GENERAL_PROJECT_NAME` in Task 1; its value is still `"General"`.

### Python names

**Task 1 (rename, no behaviour change):**
- `roost/money/category_store.py` becomes `roost/money/project_store.py`, and `CategoryStore` becomes `ProjectStore`.
- In `roost/money/models.py`, `Category` becomes `Project`, `CategoryTotal` becomes `ProjectTotal`, and `Expense.category_id` becomes `Expense.project_id`.
- `ExpenseDraft.category_id` becomes `ExpenseDraft.project_id`.
- `MoneySummary.by_category` becomes `MoneySummary.by_project`.
- In `MoneyService`, `category_for` becomes `project_for` and `categories` becomes `projects`. `ExpenseEntry.category` becomes `ExpenseEntry.project`.
- The money tool args are named `project`, with `Field(validation_alias=AliasChoices("project", "category"))`.
- Wire: an expense row has `project` (name) and `project_id`; the summary has `by_project: ProjectTotalOut[]`.

**Task 2 (store):** `Project` gains these fields:

```python
color: str
start_date: str | None
due_date: str | None
monthly_budget: Decimal | None
lead_bot_id: str | None
status: str                       # "active" | "archived"
```

**`ProjectStore`** (`roost/money/project_store.py`) gains:

```python
async def find(self, user_id: str, name: str) -> Project | None: ...                  # by name_key, never creates
async def list(self, user_id: str, *, include_archived: bool = True) -> tuple[Project, ...]: ...
async def create(self, user_id: str, draft: ProjectDraft, *, created_by_bot: str | None, tainted: bool) -> Project: ...
async def update(self, user_id: str, project_id: str, patch: ProjectPatch) -> Project | None: ...   # rename recomputes name_key; clash → ValueError("A project with that name exists.")
async def set_budget(self, user_id: str, project_id: str, amount: Decimal | None, *, created_by_bot, tainted) -> Project | None: ...  # None clears (edit row of −budget)
async def add_topup(self, user_id: str, project_id: str, amount: Decimal, source: str | None, *, created_by_bot, tainted) -> TopUp: ...
async def edit_topup(self, user_id: str, topup_id: str, amount: Decimal) -> TopUp | None: ...
async def undo_topup(self, user_id: str, topup_id: str) -> TopUp | None: ...
async def topups(self, user_id: str, project_id: str) -> tuple[TopUp, ...]: ...      # history, newest first, undone ones included with undone=True
async def delete(self, user_id: str, project_id: str) -> bool: ...                   # H9, one transaction; General refused
async def has_money(self, user_id: str, project_id: str) -> bool: ...                # any expense or top-up (currency change rule)
def is_general(self, project: Project, dek: bytes) -> bool: ...                      # or a module function, see Task 2
```

The supporting models:

```python
@dataclass(frozen=True)
class ProjectDraft:
    name: str
    currency: str = DEFAULT_CURRENCY
    budget: Decimal | None = None
    monthly_budget: Decimal | None = None
    color: str = DEFAULT_PROJECT_COLOR
    start_date: str | None = None
    due_date: str | None = None
    lead_bot_id: str | None = None

PROJECT_PATCHABLE = frozenset({"name", "color", "start_date", "due_date", "monthly_budget", "lead_bot_id", "status", "currency"})
@dataclass(frozen=True)
class ProjectPatch:
    changes: Mapping[str, object]     # keys ⊆ PROJECT_PATCHABLE; ValueError otherwise

@dataclass(frozen=True)
class TopUp:
    id: str; project_id: str; amount: Decimal; currency: str; source: str | None
    kind: str                         # "credit" | "edit"
    topup_id: str | None; undone: bool; created_at: str; created_by_bot: str | None; tainted: bool
```

**Task 3 (expenses + numbers):**
- `Expense` gains `task_id: str | None`, `step_id: str | None`, `is_favorite: bool`, and a `status` of `"posted" | "void"`.
- `EXPENSE_PATCHABLE` gains `task_id`, `step_id`, `is_favorite` and `status`.
- `ExpenseStore.list_project(user_id, project_id) -> tuple[Expense, ...]` returns every visible expense, voids included.
- Reads show void rows. `get`, `update` and `keep` use `deleted_at IS NULL`.
- `roost/projects/numbers.py`:

```python
Tone = Literal["ok", "warn", "over"]
@dataclass(frozen=True)
class BudgetLine:
    budget: Decimal | None; spent: Decimal; remaining: Decimal | None
    used_percent: int | None; tone: Tone | None          # None when no budget
@dataclass(frozen=True)
class ProjectNumbers:
    currency: str
    total: BudgetLine
    month: BudgetLine
    other_currencies: Mapping[str, Decimal]
    starred_total: Decimal
@dataclass(frozen=True)
class TaskMoney:
    planned: Decimal | None; spent: Decimal; left: Decimal | None
@dataclass(frozen=True)
class Progress:
    done: int; failed: int; total: int                   # total excludes cancelled

def counted(expense: Expense, currency: str) -> bool: ...       # posted and in that currency
def budget_line(budget: Decimal | None, spent: Decimal) -> BudgetLine: ...
def project_numbers(project: Project, expenses: Sequence[Expense], month: str) -> ProjectNumbers: ...
def task_money(task: Task, expenses: Sequence[Expense], currency: str) -> TaskMoney: ...
def progress(tasks: Sequence[Task]) -> Progress: ...
```

- `summarize(month, projects, expenses)` gives each `ProjectTotal` its own `currency`, `other_currencies`, and the `month` `BudgetLine` against `monthly_budget`.

**Task 4 (tasks):**
- `TaskStatus` gains `"failed"`, and `TaskFilter` gains `"failed"`.
- `Task` and `TaskDraft` gain `project_id: str | None = None` and `allocated_budget: Decimal | None = None`. **Task 3 adds these model fields**, because `numbers.py` needs them. Task 4 adds the storage, encryption and `PATCHABLE_FIELDS`.
- `TaskStore` gains `fail(user_id, task_id) -> Task | None` and `list(..., project_id: str | None = None)`. Its `closed_between(user_id, start_utc, end_utc) -> tuple[Task, ...]` covers done and failed tasks. `unlink_project(user_id, project_id) -> int` exists for Task 2's delete, which may run its SQL directly in one transaction instead.
- `TaskService.fail(user_id, task_id)` publishes `tasks_changed` with `"failed"` and respawns a recurring task.
- `roost/tasks/day_summary.py`:

```python
@dataclass(frozen=True)
class DaySummary:
    day: str; done: tuple[Task, ...]; failed: tuple[Task, ...]; overdue: tuple[Task, ...]
    spent: Mapping[str, Decimal]                        # counted expenses that day, per currency
def madrid_day_bounds_utc(day: str) -> tuple[str, str]: ...
async def build_day_summary(user_id: str, day: str, *, tasks: TaskStore, expenses: ExpenseStore, now: datetime | None = None) -> DaySummary: ...
def day_summary_text(summary: DaySummary) -> str: ...
```

**Task 5 (notes and documents):**
- `Note`, `NoteDraft`, `DocumentMeta` and `DocumentDraft` gain a trailing `project_id: str | None = None`.
- `NoteStore` and `DocumentStore` get `set_project(user_id, id, project_id) -> Note | DocumentMeta | None`, which does not bump the revision and refuses a project that isn't the user's.
- `list(..., project_id=None)` filters by project.
- `NoteService` and `DocumentService` get `set_project`, which publishes `*_changed "updated"`, and `for_project(user_id, project_id, limit)`.

**Task 6 (`roost/projects/service.py`):**

```python
@dataclass(frozen=True)
class ProjectDetail:
    project: Project; numbers: ProjectNumbers; progress: Progress
    tasks: tuple[Task, ...]; expenses: tuple[Expense, ...]; notes: tuple[Note, ...]; documents: tuple[DocumentMeta, ...]
    topups: tuple[TopUp, ...]; lead_bot_name: str | None; tainted: bool
    task_money: Mapping[str, TaskMoney]      # task id → planned / spent / left, over every expense of the project

class ProjectService:
    def __init__(self, projects: ProjectStore, expenses: ExpenseStore, tasks: TaskStore, notes: NoteStore,
                 documents: DocumentStore, bots: BotStore, events: EventHub) -> None: ...
    async def list(self, user_id: str, *, include_archived: bool = False) -> tuple[tuple[Project, ProjectNumbers, Progress], ...]: ...   # General hidden
    async def detail(self, user_id: str, project_id: str) -> ProjectDetail | None: ...
    async def create(self, user_id: str, draft: ProjectDraft, *, created_by_bot=None, tainted=False) -> Project: ...
    async def update(self, user_id: str, project_id: str, changes: Mapping[str, object]) -> Project | None: ...  # General refused; lead bot must be the user's; currency only if not has_money
    async def delete(self, user_id: str, project_id: str) -> bool: ...
    async def set_budget(self, user_id: str, project_id: str, amount: Decimal | None) -> Project | None: ...  # None clears (H5); money_changed "budget_set"
    async def add_topup(...) / edit_topup(...) / undo_topup(...) / topups(...)
    async def resolve(self, user_id: str, name: str, *, change: bool) -> Project | str: ...   # exact-or-ask (H3): Project, or a refusal text
```

Events go on `money_changed` with the new `change` values from H10. The id is `project_id` or `topup_id`.

**Task 7 (tools):**

`roost/projects/tool_specs.py` defines `PROJECT_TOOL_DEFS`:

| Tool | Kind |
|---|---|
| `list_projects` | read |
| `get_project` | read |
| `create_project` | write_create |
| `update_project` | write_change |
| `add_topup` | write_change |
| `edit_topup` | write_change |
| `undo_topup` | write_change |

- `roost/projects/tools.py` defines `ProjectTools`, wired into `build_domain_tools`.
- Money tools: `log_expense` and `update_expense` gain `project`, `task`, `step` and `starred`; `update_expense` also gains `void`.
- Task tools: `add_task` gets `project` and `budget`; `update_task` gets `project`, `budget` and the status `failed`; `list_tasks` gets `project` and the status `failed`.
- Note and document tools get `project` as listed in H12, plus the new `set_document_project` (write_change) in `DOCUMENT_TOOL_DEFS`.
- `instructions.py` `_RECORDS_TEXT` names projects. It never uses the word "role".

**Task 8 (HTTP):** see the route table below. The routes are `roost/gateway/routes/projects.py` (`projects_router`) plus additions to the money, tasks, notes and documents routers. `app.state.projects` holds the `ProjectService`.

### HTTP routes (every route has `CurrentUser`; every mutating route has `RequireOrigin`)

| Route | Task | Result |
|---|---|---|
| `GET /api/projects?include_archived=` | 8 | `ProjectOut[]` (with numbers and progress; General hidden) |
| `POST /api/projects` | 8 | 201 `ProjectOut` · 422 |
| `GET /api/projects/{id}` | 8 | `ProjectDetailOut` · 404 `"Project not found"` |
| `PATCH /api/projects/{id}` | 8 | `ProjectOut` · 404 · 409 `"A project with that name exists."` · 422 |
| `DELETE /api/projects/{id}` | 8 | 204 · 404 · 422 (General) |
| `PUT /api/projects/{id}/budget` body `{amount: str \| null}` | 8 | `ProjectOut` (null clears the total) · 404 · 422 |
| `GET /api/projects/{id}/topups` | 8 | `TopupOut[]` |
| `POST /api/projects/{id}/topups` | 8 | 201 `TopupOut` |
| `PATCH /api/topups/{id}` · `POST /api/topups/{id}/undo` | 8 | `TopupOut` · 404 · 409 when already undone |
| `PUT /api/money/expenses/{id}/star` body `{starred: bool}` · `PUT /api/money/expenses/{id}/void` body `{void: bool}` | 8 | `ExpenseOut` · 404 |
| `POST /api/tasks/{id}/fail` | 8 | `TaskOut` · 404 |
| `GET /api/tasks?status=&project_id=` | 8 | filter |
| `PUT /api/notes/{id}/project` · `PUT /api/documents/{id}/project` body `{project_id: str | null}` | 8 | updated item · 404 · 422 |
| `GET /api/notes?project_id=` · `GET /api/documents?project_id=` | 8 | filter |

### Web names (Task 9)

- **`api/types.ts`:**
  - `BoardTab` gains `"projects"` (first).
  - New `BudgetLineOut { budget: string | null; spent: string; remaining: string | null; used_percent: number | null; tone: "ok" | "warn" | "over" | null }`.
  - New `ProjectOut { id; name; color; currency; status; start_date; due_date; lead_bot_id; total: BudgetLineOut; month: BudgetLineOut; other_currencies: Record<string,string>; starred_total: string; progress: { done; failed; total }; tainted }`.
  - New `ProjectDetailOut extends ProjectOut { tasks: TaskOut[]; expenses: ExpenseOut[]; notes: NoteSummaryOut[]; documents: DocumentOut[]; topups: TopupOut[]; lead_bot_name: string | null; task_money: Record<string, TaskMoneyOut> }`.
  - New `TaskMoneyOut { planned: string | null; spent: string; left: string | null }`. The project page shows it on each task as "€80.00 spent, €20.00 left".
  - New `TopupOut { id; amount; currency; source; kind: "credit" | "edit"; topup_id; undone; created_at }`.
  - `ExpenseOut` gains `project`, `project_id`, `task_id`, `step_id`, `is_favorite` and `status`.
  - `TaskOut` gains `project_id` and `allocated_budget`, and its status union gains `"failed"`.
  - `NoteSummaryOut` and `DocumentOut` gain `project_id`.
  - `MoneyChangedFrame.change` gains the H10 values.
- **`api/projects.ts`:** `listProjects`, `getProject`, `createProject`, `updateProject`, `setProjectBudget`, `deleteProject`, `listTopups`, `addTopup`, `editTopup` and `undoTopup`.
- **`api/money.ts`** gains `starExpense` and `voidExpense`; **`api/tasks.ts`** gains `failTask`.
- **`components/projects/`:** `ProjectsBoard` (eager named export, the default tab), `ProjectRow`, `BudgetBar` (`role="meter"`), `ProjectEditForm`, `TopupForm` and `TopupHistory`.
- **`components/board/ExpenseList.tsx`** is extracted, with optional `onStar` and `onVoid`.
- **`pages/Project.tsx`** is the route `/board/projects/:projectId`, with sub-tabs Tasks · Money · Notes · Docs on `?tab=`. `/board/projects` redirects to `/board?tab=projects`.
- **`store/live.ts`:** `money_changed` with `project_deleted` also bumps `boardVersion.tasks`, `.notes` and `.documents`.
- **Styles** go in `styles/projects.css`.

### File structure

| File | Task | Responsibility |
|---|---|---|
| `roost/money/project_store.py` (renamed), `roost/money/*`, `roost/gateway/routes/money.py`, money tests, `web/src/components/board/{MoneyBoard,ExpenseAddForm}.tsx`, `web/src/api/{types,money}.ts`, web money tests | 1 | Category → Project rename |
| `roost/db/migrations.py`, `tests/fixtures/schema_v12.sql`, `tests/test_migrations_v12.py`, `roost/money/{models,project_store}.py`, `roost/money/topup_store.py` (new, if needed for size), `roost/constants.py` | 2 | v13, the project fields, top-ups, delete |
| `roost/money/{models,expense_store,summary,format}.py`, `roost/projects/{__init__,numbers}.py` (new), `roost/tasks/models.py` (the `Task` fields `numbers.py` needs: `project_id`, `allocated_budget`) | 3 | expenses (void, star, task, step) and the calculations |
| `roost/tasks/{store,service,format}.py`, `roost/tasks/day_summary.py` (new), `roost/records/project_link.py` (new: `require_project`, `NO_SUCH_PROJECT_TEXT`) | 4 | the task project link, budget slice, failed status, day summary |
| `roost/notes/*`, `roost/documents/*` (models, stores, services) | 5 | the project link |
| `roost/projects/service.py` (new) | 6 | `ProjectService` |
| `roost/projects/{tool_specs,tools,format}.py` (new) and Task 7's other new helper modules (named in the task), `roost/money/{tool_specs,tools,amounts}.py`, `roost/tasks/{tool_specs,tools}.py`, `roost/notes/tools.py`, `roost/documents/{tool_args,tools}.py`, `roost/talk/{tool_catalog,domain_tools,instructions}.py` | 7 | bot tools |
| `roost/gateway/routes/projects.py` (new), `roost/gateway/routes/{money,tasks,notes,documents}.py`, `roost/notes/format.py`, `roost/documents/format.py`, `roost/gateway/app.py` | 8 | HTTP |
| `web/src/...` | 9 | the Projects tab, the project page, bars, top-ups, star / void / failed |
| `web/e2e/projects.spec.ts` (new), `web/e2e/records.spec.ts`, `web/e2e/every-bot.spec.ts`, `tests/test_docs.py`, `CLAUDE.md`, `README.md` | 10 | E2E and docs |

---

### Task 1: Category becomes Project (a rename, no behaviour change)

Design H1 (and P8: today's `money_projects` table **is** the project, so the code says so). This is one mechanical rename, done before any new feature, so that every later task speaks of projects only. Nothing a user or a bot can do changes:
- **Code:** `category_store.py` becomes `project_store.py` (`git mv`), `CategoryStore` becomes `ProjectStore`, `Category` becomes `Project`, `CategoryTotal` becomes `ProjectTotal`, `Expense.category_id` / `ExpenseDraft.category_id` become `project_id`, `MoneySummary.by_category` becomes `by_project`, `MoneyService.category_for` / `categories` become `project_for` / `projects`, `ExpenseEntry.category` becomes `project`, and `GENERAL_CATEGORY_NAME` becomes `GENERAL_PROJECT_NAME` (still `"General"`).
- **Tools:** the money tools' argument is `project`. Because the args models use `extra="ignore"`, a model that still sends `category` would otherwise land in General silently; so every money args model reads `Field(validation_alias=AliasChoices("project", "category"))`, and `project` wins when both are sent. The tool names (`log_expense`, `set_budget`, …), their replies and their gate kinds are unchanged. The tool-spec descriptions say "project".
- **Wire:** an expense row carries `project` (the name) and `project_id`; the month summary carries `by_project` rows `{project, spent, budget, remaining}`. `POST /api/money/expenses` takes `project`.
- **Web:** `ProjectTotalOut`, `by_project`, `ExpenseOut.project` / `.project_id`; the Money tab's table is "By project" with a "Project" column; the add form's field is "Project" (datalist `expense-projects`) and sends `{project}`; the expense row's class is `expense-row__project`.
- **Stays:** `tasks.category` is the task's **list** (H1). Only its tool-spec wording changes, from "list or project" to "list", so it no longer competes with `project`. The length limits `MAX_CATEGORY_NAME_LENGTH` (Python) and `MAX_CATEGORY` (web) keep their names: the contract does not rename them and later tasks reuse them.

**Files:**
- Create: none (`roost/money/project_store.py` is `roost/money/category_store.py` moved with `git mv`).
- Modify:
  - `roost/constants.py` (`GENERAL_CATEGORY_NAME` → `GENERAL_PROJECT_NAME`, Finance section)
  - `roost/money/models.py` (`Project`, `ProjectTotal`, `project_id`, `by_project`)
  - `roost/money/project_store.py` (moved; `ProjectStore`, `project_id` parameters)
  - `roost/money/expense_store.py` (`project_id` field; the `project_id` column needs no special case any more)
  - `roost/money/service.py` (`ExpenseEntry.project`, `project_for`, `projects`)
  - `roost/money/summary.py` (`summarize(month, projects, expenses)`, `by_project`, `project` + `project_id` on the row)
  - `roost/money/format.py` (`expense_line(expense, project)`, `by_project`)
  - `roost/money/tools.py` (`project` arguments with the `category` alias)
  - `roost/money/tool_specs.py` (`project` properties and wording)
  - `roost/tasks/tool_specs.py` (a task's `category` is "list", not "list or project")
  - `roost/gateway/routes/money.py` (`ExpenseIn.project`, `projects`)
  - `roost/gateway/app.py` (builds `ProjectStore`)
  - `roost/talk/domain_tools.py` (builds `ProjectStore`)
  - `web/src/api/types.ts` (`ExpenseOut.project` / `.project_id`, `ProjectTotalOut`, `by_project`)
  - `web/src/api/money.ts` (`ExpenseIn.project`)
  - `web/src/components/board/MoneyBoard.tsx` (`ProjectTable`, "By project", "Project")
  - `web/src/components/board/ExpenseAddForm.tsx` (`projects` prop, "Project" field, `expense-projects`)
  - `web/src/components/profile/DocumentsTab.tsx` (`e.project`)
  - `web/src/styles/board.css` (`.expense-row__project`, the comment)
  - `web/e2e/records.spec.ts` (the "By project" comment)
  - `tests/live_shape.py`, `tests/test_profile_api.py`, `tests/test_tool_text.py`, `tests/test_document_tools.py`, `tests/test_every_bot_tools.py` (the renamed names)
- Test:
  - `tests/test_money_store.py`, `tests/test_money_tools.py`, `tests/test_money_api.py` (renamed and updated, plus new tests)
  - `tests/test_vocabulary.py` (one new test)
  - `web/tests/MoneyBoard.test.tsx`, `web/tests/DocumentsTab.test.tsx`

**Interfaces:**
- Consumes:
  - Nothing from earlier hub tasks (this is the first).
  - The finished stuck-flow plan (schema v12, `roost/gateway/app.py` with `StuckStore` / `StuckService`, `roost/constants.py` with the stuck section at the end). None of the lines this task edits are stuck-flow lines.
  - Existing: `CategoryStore`, `Category`, `CategoryTotal`, `MoneyService`, `ExpenseEntry`, `summarize`, `summary_out`, `expense_row`, `expense_out`, `expense_line`, `summary_text`, `MoneyTools`, `MONEY_TOOL_DEFS`, `GENERAL_CATEGORY_NAME`, `MAX_CATEGORY_NAME_LENGTH`, `resolve` / `NamedRef` (`roost/records/resolver.py`).
- Produces (later tasks use these exact names):
  - `roost/money/project_store.py`: `ProjectStore(config)` with `list(user_id)`, `get(user_id, project_id)`, `find_or_create(user_id, name, *, created_by_bot, tainted)`, `keep(user_id, project_id)`, `set_budget(user_id, project_id, amount, *, created_by_bot, tainted)`, `add_topup(user_id, project_id, amount, source, *, created_by_bot, tainted)`; private `_name_key(dek, name)`, `_row_to_project(row, dek)`, `_aad(user_id, column)`, `_COLUMNS`.
  - `roost/money/models.py`: `Project(id, user_id, name, budget, currency, created_at, updated_at, created_by_bot, tainted)`; `Expense.project_id`; `ExpenseDraft(project_id, amount, currency=DEFAULT_CURRENCY, description=None, vendor=None, spent_at="")`; `EXPENSE_PATCHABLE` holds `"project_id"`; `ProjectTotal(project: str, spent, budget)` with `.remaining`; `MoneySummary.by_project`.
  - `roost/money/service.py`: `ExpenseEntry(amount, spent_at, project=None, note=None, vendor=None, currency=DEFAULT_CURRENCY)`; `MoneyService(projects, expenses, events)` with `project_for(user_id, name, *, created_by_bot, tainted) -> Project`, `projects(user_id)`, `log_expense(...) -> tuple[Expense, Project]`, `made_by(...) -> tuple[tuple[Expense, Project | None], ...]`, `keep_expense(...) -> tuple[Expense, Project | None] | None`, `set_budget(...) -> Project`.
  - `roost/money/summary.py`: `summarize(month, projects, expenses)`, `summary_out(summary)` (key `by_project`, rows `{project, spent, budget, remaining}`), `expense_row(expense, project)`, `expense_out(expense, project, *, project_tainted=False)` (keys `project`, `project_id`).
  - `roost/money/format.py`: `expense_line(expense, project)`.
  - `roost/money/tools.py`: `_PROJECT_ARG = AliasChoices("project", "category")`; `LogExpenseArgs.project`, `MonthArgs.project`, `ListExpensesArgs.project`, `UpdateExpenseArgs.project`, `SetBudgetArgs.project`; `_project_name`, `_project_tainted`.
  - `roost/money/tool_specs.py`: `_PROJECT`.
  - `roost/constants.py`: `GENERAL_PROJECT_NAME = "General"`.
  - HTTP: `ExpenseIn.project`; expense rows `project` + `project_id`; summary `by_project`.
  - Web: `ProjectTotalOut { project; spent; budget; remaining }`, `MoneySummaryOut.by_project`, `ExpenseOut.project`, `ExpenseOut.project_id`, `api/money.ts` `ExpenseIn.project`, `ExpenseAddForm({ projects, onAdded })`, datalist id `expense-projects`, CSS class `expense-row__project`.

- [ ] **Step 1: Path guard**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

Then confirm the stuck-flow plan has landed and this task has not:

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && test -f roost/gateway/routes/stuck.py && test -f web/e2e/stuck.spec.ts && test -f roost/money/category_store.py && test ! -e roost/money/project_store.py && grep "^GENERAL_CATEGORY_NAME" roost/constants.py`
Expected: one line, `GENERAL_CATEGORY_NAME = "General"`. If a test fails or the grep prints nothing, stop: the stuck flow comes first, or this task already ran.

- [ ] **Step 2: Write the failing tests**

**2a.** Replace the whole of `tests/test_money_store.py` with:

```python
"""The user's money stores (M1 D2, D7): encrypted, per user, with provenance."""

from __future__ import annotations

from decimal import Decimal

import pytest

from roost.bots.store import BotStore
from roost.config import load_config
from roost.db.connection import db_session, init_db
from roost.gateway.auth import register_user
from roost.money.expense_store import ExpenseStore
from roost.money.models import ExpenseDraft, ExpensePatch
from roost.money.project_store import ProjectStore
from team_helpers import make_bot


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


async def _food(cfg, user_id, **kw):
    return await ProjectStore(cfg).find_or_create(user_id, "Food", created_by_bot=None, tainted=False, **kw)


async def test_amounts_names_and_notes_are_ciphertext_on_disk(cfg, user_id):
    food = await _food(cfg, user_id)
    expense = await ExpenseStore(cfg).add(user_id, ExpenseDraft(food.id, Decimal("12.50"), spent_at="2026-10-13",
                                                                description="lunch"), created_by_bot=None, tainted=False)
    async with db_session(cfg) as db:
        project = await (await db.execute("SELECT name, name_key FROM money_projects WHERE id = ?", (food.id,))).fetchone()
        row = await (await db.execute("SELECT amount, description FROM money_expenses WHERE id = ?", (expense.id,))).fetchone()
    assert project["name"].startswith("enc:v2:") and "Food" not in project["name_key"]
    assert row["amount"].startswith("enc:v2:") and row["description"].startswith("enc:v2:")
    assert (await ExpenseStore(cfg).get(user_id, expense.id)).amount == Decimal("12.50")


async def test_a_project_is_found_again_whatever_its_case_and_spacing(cfg, user_id):
    store = ProjectStore(cfg)
    first = await store.find_or_create(user_id, "Food", created_by_bot=None, tainted=False)
    again = await store.find_or_create(user_id, "  food ", created_by_bot=None, tainted=True)
    assert again.id == first.id and again.tainted is False
    assert [p.name for p in await store.list(user_id)] == ["Food"]


async def test_set_budget_and_top_ups_keep_a_ledger(cfg, user_id):
    store = ProjectStore(cfg)
    food = await _food(cfg, user_id)
    assert (await store.set_budget(user_id, food.id, Decimal("300"), created_by_bot=None, tainted=False)).budget == Decimal("300.00")
    assert (await store.set_budget(user_id, food.id, Decimal("250"), created_by_bot=None, tainted=False)).budget == Decimal("250.00")
    assert (await store.add_topup(user_id, food.id, Decimal("20"), "birthday", created_by_bot=None, tainted=False)).budget == Decimal("270.00")
    async with db_session(cfg) as db:
        rows = await (await db.execute("SELECT kind FROM money_topups WHERE project_id = ? ORDER BY created_at", (food.id,))).fetchall()
    assert [r["kind"] for r in rows] == ["edit", "edit", "credit"]


async def test_an_expense_keeps_its_project_and_a_patch_moves_it(cfg, user_id):
    """H1: ``Expense.project_id`` is the ``money_projects`` row; it is stored,
    read back and patched under that one name."""
    food = await _food(cfg, user_id)
    travel = await ProjectStore(cfg).find_or_create(user_id, "Travel", created_by_bot=None, tainted=False)
    store = ExpenseStore(cfg)
    expense = await store.add(user_id, ExpenseDraft(project_id=food.id, amount=Decimal("4"), spent_at="2026-10-13"),
                              created_by_bot=None, tainted=False)
    assert expense.project_id == food.id and (await store.get(user_id, expense.id)).project_id == food.id
    moved = await store.update(user_id, expense.id, ExpensePatch({"project_id": travel.id}))
    assert moved.project_id == travel.id
    assert (await store.get(user_id, expense.id)).project_id == travel.id
    async with db_session(cfg) as db:
        row = await (await db.execute("SELECT project_id FROM money_expenses WHERE id = ?", (expense.id,))).fetchone()
    assert row["project_id"] == travel.id


async def test_another_user_sees_no_money(cfg, user_id):
    food = await _food(cfg, user_id)
    expense = await ExpenseStore(cfg).add(user_id, ExpenseDraft(food.id, Decimal("5"), spent_at="2026-10-13"),
                                          created_by_bot=None, tainted=False)
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    assert await ExpenseStore(cfg).get(bob, expense.id) is None
    assert await ExpenseStore(cfg).list_month(bob, "2026-10") == ()
    assert await ProjectStore(cfg).list(bob) == ()
    assert await ExpenseStore(cfg).update(bob, expense.id, ExpensePatch({"amount": Decimal("1")})) is None
    assert await ExpenseStore(cfg).delete(bob, expense.id) is False


async def test_list_month_is_newest_first_and_skips_deleted_and_other_months(cfg, user_id):
    food = await _food(cfg, user_id)
    store = ExpenseStore(cfg)
    for day in ("2026-10-01", "2026-10-20", "2026-11-01"):
        await store.add(user_id, ExpenseDraft(food.id, Decimal("1"), spent_at=day), created_by_bot=None, tainted=False)
    gone = await store.add(user_id, ExpenseDraft(food.id, Decimal("9"), spent_at="2026-10-05"), created_by_bot=None, tainted=False)
    await store.delete(user_id, gone.id)
    assert [e.spent_at for e in await store.list_month(user_id, "2026-10")] == ["2026-10-20", "2026-10-01"]


async def test_retiring_the_bot_keeps_the_users_expenses(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Life admin")
    food = await ProjectStore(cfg).find_or_create(user_id, "Food", created_by_bot=bot.id, tainted=False)
    expense = await ExpenseStore(cfg).add(user_id, ExpenseDraft(food.id, Decimal("3"), spent_at="2026-10-13"),
                                          created_by_bot=bot.id, tainted=False)
    await BotStore(cfg).delete(user_id, bot.id)
    assert (await ExpenseStore(cfg).get(user_id, expense.id)).created_by_bot is None
```

**2b.** Replace the whole of `tests/test_money_tools.py` with (the existing tests now say `project=`; three tests are new: `test_log_expense_still_accepts_the_old_category_argument`, `test_every_money_tool_takes_project_and_still_category`, `test_money_tools_say_project_and_a_tasks_category_is_its_list`):

```python
"""The finance role end to end (M1 D2, D3, D7)."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.auth import register_user
from roost.llm.types import ToolCallRequested, TurnDone
from roost.money.expense_store import ExpenseStore
from roost.money.models import ExpenseDraft
from roost.money.months import current_month, today_madrid
from roost.money.project_store import ProjectStore
from roost.money.tool_specs import LOG_EXPENSE_SPEC, MONEY_TOOL_DEFS, SET_BUDGET_SPEC
from roost.money.tools import ListExpensesArgs, LogExpenseArgs, SetBudgetArgs, UpdateExpenseArgs
from roost.talk.gate import TAINTED_CHANGE_TEXT
from roost.tasks.tool_specs import ADD_TASK_SPEC, LIST_TASKS_SPEC
from team_helpers import make_bot, make_rig, say, send, team_model, wait_idle


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


def _tool(call_id: str, name: str, **arguments):
    return [ToolCallRequested(id=call_id, name=name, arguments=arguments), TurnDone("tool_use")]


async def _talk(cfg, user_id, bot, script: dict, text: str):
    rig = make_rig(cfg, team_model(script))
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, text)
    await wait_idle(rig.runner)
    return rig


def _tool_texts(request) -> list[str]:
    return [turn.text for turn in request.turns if turn.role == "tool"]


async def test_spent_12_50_on_lunch_food_logs_it_and_the_summary_shows_it(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Life admin")
    rig = await _talk(cfg, user_id, bot, {"Life admin": [
        _tool("e", "log_expense", amount="12,50", project="food", note="lunch"),
        _tool("s", "money_summary"), say("Logged."),
    ]}, "spent 12.50 on lunch, food")
    logged, summary = _tool_texts(rig.model.requests[-1])
    assert logged.startswith("Logged 12.50 EUR to food on " + today_madrid())
    assert "food: 12.50 EUR" in summary and "Total: 12.50 EUR" in summary
    [expense] = await ExpenseStore(cfg).list_month(user_id, current_month())
    assert (expense.amount, expense.description, expense.created_by_bot, expense.tainted) == (
        Decimal("12.50"), "lunch", bot.id, False)


async def test_a_typo_lands_in_the_existing_project(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Life admin")
    await ProjectStore(cfg).find_or_create(user_id, "Groceries", created_by_bot=None, tainted=False)
    await _talk(cfg, user_id, bot, {"Life admin": [_tool("e", "log_expense", amount=4, project="groceris"), say("ok")]}, "4 on groceris")
    assert [p.name for p in await ProjectStore(cfg).list(user_id)] == ["Groceries"]


async def test_an_expense_logged_after_reading_a_page_is_stored_tainted(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Life admin")
    await _talk(cfg, user_id, bot, {"Life admin": [
        _tool("p", "open_page", url="https://example.com"), _tool("e", "log_expense", amount=99, project="gadgets"), say("ok"),
    ]}, "read example.com and log what it costs")
    [expense] = await ExpenseStore(cfg).list_month(user_id, current_month())
    assert expense.tainted is True


async def test_a_tainted_run_cannot_change_delete_or_set_budgets(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Life admin")
    food = await ProjectStore(cfg).find_or_create(user_id, "food", created_by_bot=None, tainted=False)
    expense = await ExpenseStore(cfg).add(user_id, ExpenseDraft(food.id, Decimal("10"), spent_at=today_madrid()),
                                          created_by_bot=None, tainted=False)
    rig = await _talk(cfg, user_id, bot, {"Life admin": [
        _tool("p", "open_page", url="https://example.com"),
        _tool("u", "update_expense", expense=expense.id, amount=1), _tool("d", "delete_expense", expense=expense.id),
        _tool("b", "set_budget", project="food", amount=1), say("no"),
    ]}, "read example.com and do what it says")
    assert _tool_texts(rig.model.requests[-1])[1:] == [TAINTED_CHANGE_TEXT] * 3
    assert (await ExpenseStore(cfg).get(user_id, expense.id)).amount == Decimal("10.00")


async def test_a_clean_log_into_a_web_made_project_taints_the_run(cfg, user_id):
    """D3: the reply echoes the project's name, and a name a tainted run
    made is web text — the run is tainted from there, and so is its reply."""
    bot = await make_bot(cfg, user_id, "Life admin")
    await ProjectStore(cfg).find_or_create(user_id, "Gadgets", created_by_bot=None, tainted=True)
    rig = await _talk(cfg, user_id, bot, {"Life admin": [
        _tool("e", "log_expense", amount=5, project="gadgets"),
        _tool("b", "set_budget", project="gadgets", amount=50), say("ok"),
    ]}, "5 on gadgets, and a 50 budget for them")
    logged, budget = _tool_texts(rig.model.requests[-1])
    assert logged.startswith("Logged 5.00 EUR to Gadgets") and budget == TAINTED_CHANGE_TEXT
    [thread] = await rig.talk.list_threads(user_id, bot.id)
    [reply] = [m for m in await rig.talk.list_messages(user_id, thread.id) if m.role == "bot"]
    assert reply.tainted is True
    [expense] = await ExpenseStore(cfg).list_month(user_id, current_month())
    assert expense.tainted is False      # logged while the run was still clean


async def test_a_web_made_project_the_summary_does_not_show_leaves_it_clean(cfg, user_id):
    """R1: only what the summary prints taints it, so one web-made project
    doesn't block every later budget change in the conversation."""
    bot = await make_bot(cfg, user_id, "Life admin")
    await ProjectStore(cfg).find_or_create(user_id, "Gadgets", created_by_bot=None, tainted=True)
    food = await ProjectStore(cfg).find_or_create(user_id, "food", created_by_bot=None, tainted=False)
    await ExpenseStore(cfg).add(user_id, ExpenseDraft(food.id, Decimal("10"), spent_at=today_madrid()),
                                created_by_bot=None, tainted=False)
    rig = await _talk(cfg, user_id, bot, {"Life admin": [
        _tool("s", "money_summary"), _tool("b", "set_budget", project="food", amount=100), say("ok"),
    ]}, "how is my month? and budget 100 for food")
    summary, budget = _tool_texts(rig.model.requests[-1])
    assert "Gadgets" not in summary and budget.startswith("Budget for food: 100.00 EUR")


async def test_other_currencies_stay_out_of_the_eur_total(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Life admin")
    rig = await _talk(cfg, user_id, bot, {"Life admin": [
        _tool("e1", "log_expense", amount="10", project="travel"),
        _tool("e2", "log_expense", amount="20", project="travel", currency="USD"),
        _tool("s", "money_summary"), say("ok"),
    ]}, "log them")
    summary = _tool_texts(rig.model.requests[-1])[-1]
    assert "Total: 10.00 EUR" in summary and "Also 20.00 USD" in summary


async def test_a_second_bot_with_the_finance_role_sees_the_same_money(cfg, user_id):
    first = await make_bot(cfg, user_id, "Life admin")
    second = await make_bot(cfg, user_id, "Ledger")
    await _talk(cfg, user_id, first, {"Life admin": [_tool("e", "log_expense", amount=7, project="food"), say("ok")]}, "7 food")
    rig = await _talk(cfg, user_id, second, {"Ledger": [_tool("l", "list_expenses"), say("ok")]}, "what did I spend?")
    assert "7.00 EUR" in _tool_texts(rig.model.requests[-1])[0]


async def test_a_bad_amount_is_refused_plainly(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Life admin")
    rig = await _talk(cfg, user_id, bot, {"Life admin": [_tool("e", "log_expense", amount="1.234,56"), say("?")]}, "log")
    assert _tool_texts(rig.model.requests[-1])[0].startswith("Refused:")
    assert await ExpenseStore(cfg).list_month(user_id, current_month()) == ()


async def test_log_expense_still_accepts_the_old_category_argument(cfg, user_id):
    """H1: the money tools call it `project`. A model that still sends
    `category` lands in that project, never in General by accident."""
    bot = await make_bot(cfg, user_id, "Life admin")
    rig = await _talk(cfg, user_id, bot, {"Life admin": [
        _tool("e1", "log_expense", amount=4, category="food", note="bread"),
        _tool("e2", "log_expense", amount=9, project="travel", note="bus"),
        _tool("l", "list_expenses", category="food"),
        _tool("b", "set_budget", category="food", amount=50), say("ok"),
    ]}, "4 on food for bread, 9 on travel for the bus, show me food and budget 50 for it")
    logged, _, listed, budget = _tool_texts(rig.model.requests[-1])
    assert logged.startswith("Logged 4.00 EUR to food on " + today_madrid())
    assert "bread" in listed and "bus" not in listed
    assert budget.startswith("Budget for food: 50.00 EUR")
    assert sorted(p.name for p in await ProjectStore(cfg).list(user_id)) == ["food", "travel"]


@pytest.mark.parametrize(("args_type", "required"), [
    (LogExpenseArgs, {"amount": 1}),
    (ListExpensesArgs, {}),
    (UpdateExpenseArgs, {"expense": "e1"}),
    (SetBudgetArgs, {"amount": 1}),
])
def test_every_money_tool_takes_project_and_still_category(args_type, required):
    assert args_type.model_validate({**required, "project": "food"}).project == "food"
    assert args_type.model_validate({**required, "category": "food"}).project == "food"
    assert args_type.model_validate({**required, "project": "food", "category": "travel"}).project == "food"


def test_money_tools_say_project_and_a_tasks_category_is_its_list():
    for tool in MONEY_TOOL_DEFS:
        text = tool.spec.description + json.dumps(tool.spec.input_schema)
        assert "categor" not in text.casefold(), tool.name
    assert "project" in LOG_EXPENSE_SPEC.input_schema["properties"]
    assert SET_BUDGET_SPEC.input_schema["required"] == ["project", "amount"]
    task_lists = (ADD_TASK_SPEC.input_schema["properties"]["category"]["description"],
                  LIST_TASKS_SPEC.input_schema["properties"]["category"]["description"])
    assert all("list" in text and "project" not in text for text in task_lists)
```

**2c.** Replace the whole of `tests/test_money_api.py` with (the existing tests now send and read `project`; `test_the_summary_wire_uses_by_project` is new):

```python
"""Money over HTTP (the Board's data, M1 D8) and the money_changed frame."""

from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from roost.config import load_config
from roost.db.connection import get_db_path
from roost.gateway.app import create_app
from roost.money.months import current_month, today_madrid

O = {"Origin": "http://127.0.0.1:18800"}


def _client() -> TestClient:
    c = TestClient(create_app())
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O).status_code == 201
    return c


def _stored_project_ids() -> dict[str, str]:
    con = sqlite3.connect(get_db_path(load_config()))
    try:
        return dict(con.execute("SELECT id, project_id FROM money_expenses").fetchall())
    finally:
        con.close()


def test_add_an_expense_and_see_it_in_the_month_and_the_summary():
    c = _client()
    r = c.post("/api/money/expenses", json={"amount": "12,50", "project": "food", "note": "lunch"}, headers=O)
    assert r.status_code == 201
    expense = r.json()
    assert (expense["amount"], expense["project"], expense["currency"], expense["spent_at"]) == (
        "12.50", "food", "EUR", today_madrid())
    assert [e["id"] for e in c.get(f"/api/money/expenses?month={current_month()}").json()] == [expense["id"]]
    summary = c.get("/api/money/summary").json()
    assert (summary["month"], summary["total"], summary["expense_count"]) == (current_month(), "12.50", 1)
    assert summary["by_project"] == [{"project": "food", "spent": "12.50", "budget": None, "remaining": None}]
    con = sqlite3.connect(get_db_path(load_config()))
    try:
        assert [row[0] for row in con.execute("SELECT kind FROM events")][-1] == "money_changed"
    finally:
        con.close()


def test_the_summary_wire_uses_by_project():
    """H1: the month summary groups by project, and every expense row names
    its project and carries the project's id. The category keys are gone."""
    c = _client()
    food = c.post("/api/money/expenses", json={"amount": "12,50", "project": "food"}, headers=O).json()
    again = c.post("/api/money/expenses", json={"amount": "2", "project": "Food"}, headers=O).json()
    travel = c.post("/api/money/expenses", json={"amount": "5", "project": "travel"}, headers=O).json()
    assert (food["project"], again["project"], travel["project"]) == ("food", "food", "travel")
    assert food["project_id"] == again["project_id"] != travel["project_id"]
    assert "category" not in food
    assert _stored_project_ids() == {food["id"]: food["project_id"], again["id"]: again["project_id"],
                                     travel["id"]: travel["project_id"]}
    listed = {e["id"]: (e["project"], e["project_id"]) for e in c.get("/api/money/expenses").json()}
    assert listed[travel["id"]] == ("travel", travel["project_id"])
    summary = c.get("/api/money/summary").json()
    assert set(summary) == {"month", "currency", "total", "expense_count", "by_project", "other_currencies"}
    assert summary["by_project"] == [
        {"project": "food", "spent": "14.50", "budget": None, "remaining": None},
        {"project": "travel", "spent": "5.00", "budget": None, "remaining": None},
    ]


def test_a_bad_amount_or_month_is_422():
    c = _client()
    assert c.post("/api/money/expenses", json={"amount": "abc"}, headers=O).status_code == 422
    assert c.get("/api/money/summary?month=2026-13").status_code == 422


def test_money_needs_a_login_and_the_origin():
    assert TestClient(create_app()).get("/api/money/summary").status_code == 401
    assert _client().post("/api/money/expenses", json={"amount": 1}, headers={"Origin": "http://evil.example"}).status_code == 403


async def test_keep_vouches_for_a_web_made_expense_and_the_project_it_shows():
    """Final review: a web-made expense (or a web-made project name its row
    shows) kept every list_expenses / money_summary over that month tainted.
    The row shows the chip, and Keep clears both, so the month reads clean."""
    import httpx

    from roost.db.connection import init_db
    from roost.gateway.auth import register_user
    from roost.money.amounts import parse_amount
    from roost.money.service import ExpenseEntry

    app = create_app()
    cfg = load_config()
    await init_db(cfg)
    alice_id = (await register_user(cfg, "alice", "pw-123456")).id
    await register_user(cfg, "bob", "pw-123456")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://roost.test") as alice, \
            httpx.AsyncClient(transport=transport, base_url="http://roost.test") as bob:
        for client, name in ((alice, "alice"), (bob, "bob")):
            await client.post("/api/auth/login", json={"username": name, "password": "pw-123456"}, headers=O)
        money = app.state.money
        web, _ = await money.log_expense(alice_id, ExpenseEntry(amount=parse_amount("9"), spent_at=today_madrid(),
                                                                project="gadgets"), tainted=True)
        mine, _ = await money.log_expense(alice_id, ExpenseEntry(amount=parse_amount("3"), spent_at=today_madrid(),
                                                                 project="gadgets"))
        listed = {e["id"]: e["tainted"] for e in (await alice.get("/api/money/expenses")).json()}
        assert listed == {web.id: True, mine.id: True}     # mine shows the web-made project name
        assert (await bob.post(f"/api/money/expenses/{web.id}/keep", headers=O)).status_code == 404
        assert (await alice.post(f"/api/money/expenses/{web.id}/keep",
                                 headers={"Origin": "http://evil.example"})).status_code == 403
        kept = await alice.post(f"/api/money/expenses/{web.id}/keep", headers=O)
        assert kept.status_code == 200 and kept.json()["tainted"] is False
        assert [e["tainted"] for e in (await alice.get("/api/money/expenses")).json()] == [False, False]
        _, tainted = await money.summary(alice_id, current_month())
        assert tainted is False
        assert (await alice.post("/api/money/expenses/no-such/keep", headers=O)).status_code == 404
```

**2d.** `tests/test_vocabulary.py`. Find:

```python
def test_the_web_face_uses_the_s1_words():
    offenders = [(str(path.relative_to(ROOT)), word) for path in _web_sources()
                 for word in FORBIDDEN_IN_UI if word in path.read_text(encoding="utf-8")]
    assert offenders == []
```

Replace with:

```python
def test_the_web_face_uses_the_s1_words():
    offenders = [(str(path.relative_to(ROOT)), word) for path in _web_sources()
                 for word in FORBIDDEN_IN_UI if word in path.read_text(encoding="utf-8")]
    assert offenders == []


# Projects hub H1: money is grouped by project. "category" lives on only as a task's
# list (`task.category`, lower case), which the Board shows as a plain chip.
FORBIDDEN_MONEY_WORDS = ("Category", "By category", "categories")


def test_the_web_face_says_project_not_category():
    offenders = [(str(path.relative_to(ROOT)), word) for path in _web_sources()
                 for word in FORBIDDEN_MONEY_WORDS if word in path.read_text(encoding="utf-8")]
    assert offenders == []
```

**2e.** The other Python files that build the money service or log an expense. Each find is unique in its file.

`tests/live_shape.py`. Find:

```python
from roost.money.category_store import CategoryStore
from roost.money.expense_store import ExpenseStore
```

Replace with:

```python
from roost.money.expense_store import ExpenseStore
from roost.money.project_store import ProjectStore
```

Find:

```python
    money = MoneyService(CategoryStore(cfg), ExpenseStore(cfg), events)
    await money.log_expense(user_id, ExpenseEntry(amount=Decimal("12.50"), spent_at="2026-10-03", category="food"))
```

Replace with:

```python
    money = MoneyService(ProjectStore(cfg), ExpenseStore(cfg), events)
    await money.log_expense(user_id, ExpenseEntry(amount=Decimal("12.50"), spent_at="2026-10-03", project="food"))
```

`tests/test_profile_api.py`. Find:

```python
from roost.money.category_store import CategoryStore
from roost.money.expense_store import ExpenseStore
```

Replace with:

```python
from roost.money.expense_store import ExpenseStore
from roost.money.project_store import ProjectStore
```

Find:

```python
    money = MoneyService(CategoryStore(cfg), ExpenseStore(cfg), events)
    await money.log_expense(user_id, ExpenseEntry(amount=Decimal("9.99"), spent_at="2026-10-14", category="food"),
```

Replace with:

```python
    money = MoneyService(ProjectStore(cfg), ExpenseStore(cfg), events)
    await money.log_expense(user_id, ExpenseEntry(amount=Decimal("9.99"), spent_at="2026-10-14", project="food"),
```

Find:

```python
    assert [e["amount"] for e in made["expenses"]] == ["9.99"] and made["expenses"][0]["category"] == "food"
```

Replace with:

```python
    assert [e["amount"] for e in made["expenses"]] == ["9.99"] and made["expenses"][0]["project"] == "food"
```

`tests/test_tool_text.py`. Find:

```python
from roost.money.category_store import CategoryStore
from roost.money.expense_store import ExpenseStore
```

Replace with:

```python
from roost.money.expense_store import ExpenseStore
from roost.money.project_store import ProjectStore
```

Find:

```python
    money = MoneyService(CategoryStore(cfg), ExpenseStore(cfg), EventHub(cfg))
    await money.log_expense(user_id, ExpenseEntry(amount=Decimal("30"), spent_at="2026-10-03", category="food",
                                                  note="Dinner at Joe's"))
```

Replace with:

```python
    money = MoneyService(ProjectStore(cfg), ExpenseStore(cfg), EventHub(cfg))
    await money.log_expense(user_id, ExpenseEntry(amount=Decimal("30"), spent_at="2026-10-03", project="food",
                                                  note="Dinner at Joe's"))
```

Find (the `add_task` line above it keeps `category=`: that is the task's list):

```python
        _tool("e", "log_expense", amount=12, category="food", note=_seen("Dinner at Joe's"), spent_at="2026-10-03"),
```

Replace with:

```python
        _tool("e", "log_expense", amount=12, project="food", note=_seen("Dinner at Joe's"), spent_at="2026-10-03"),
```

`tests/test_document_tools.py`. Find:

```python
from roost.money.category_store import CategoryStore
from roost.money.expense_store import ExpenseStore
```

Replace with:

```python
from roost.money.expense_store import ExpenseStore
from roost.money.project_store import ProjectStore
```

Find:

```python
        _tool("e", "log_expense", amount=12.5, category="food", note="lunch", spent_at="2026-10-03"),
```

Replace with:

```python
        _tool("e", "log_expense", amount=12.5, project="food", note="lunch", spent_at="2026-10-03"),
```

(The sheet's header row `["Date", "Category", "Amount", "Note"]` two lines below is the user's own sheet text; it stays.)

Find:

```python
    money = MoneyService(CategoryStore(cfg), ExpenseStore(cfg), EventHub(cfg))
    for n in range(60):
        await money.log_expense(user_id, ExpenseEntry(amount=Decimal("1.50"), spent_at=f"2026-10-{n % 28 + 1:02d}",
                                                      category="food", note=f"snack {n:02d}"))
```

Replace with:

```python
    money = MoneyService(ProjectStore(cfg), ExpenseStore(cfg), EventHub(cfg))
    for n in range(60):
        await money.log_expense(user_id, ExpenseEntry(amount=Decimal("1.50"), spent_at=f"2026-10-{n % 28 + 1:02d}",
                                                      project="food", note=f"snack {n:02d}"))
```

`tests/test_every_bot_tools.py` (after the stuck flow, whose Task 4 adds `ask_for_help` checks elsewhere in this file and leaves this line alone). Find:

```python
        _tool("e", "log_expense", amount=12.5, category="food", note="lunch"),
```

Replace with:

```python
        _tool("e", "log_expense", amount=12.5, project="food", note="lunch"),
```

**2f.** Replace the whole of `web/tests/MoneyBoard.test.tsx` with (the fixtures use `by_project` and `project` / `project_id`, the add test types into "Project" and expects `{project}`, and the test "groups the month by project, and the add form asks for a project" is new):

```tsx
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MoneyBoard } from "../src/components/board/MoneyBoard";
import type { ExpenseOut, MoneySummaryOut } from "../src/api/types";

const getSummaryMock = vi.fn();
const listExpensesMock = vi.fn();
const createExpenseMock = vi.fn();
const keepExpenseMock = vi.fn();
vi.mock("../src/api/money", () => ({
  keepExpense: (...a: unknown[]) => keepExpenseMock(...a),
  getSummary: (...a: unknown[]) => getSummaryMock(...a),
  listExpenses: (...a: unknown[]) => listExpensesMock(...a),
  createExpense: (...a: unknown[]) => createExpenseMock(...a),
}));
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => ({ bots: {}, boardVersion: { tasks: 0, money: 0 } }) }));

const SUMMARY: MoneySummaryOut = {
  month: "2026-10", currency: "EUR", total: "12.50", expense_count: 2,
  by_project: [{ project: "food", spent: "12.50", budget: "300.00", remaining: "287.50" }],
  other_currencies: { USD: "20.00" },
};
const EXPENSES: ExpenseOut[] = [
  { id: "e1", project: "food", project_id: "p-food", amount: "12.50", currency: "EUR", description: "lunch", vendor: null,
    spent_at: "2026-10-13", status: "posted", created_at: "x", created_by_bot: "bot-1", tainted: false },
  { id: "e2", project: "travel", project_id: "p-travel", amount: "20.00", currency: "USD", description: "taxi", vendor: null,
    spent_at: "2026-10-12", status: "posted", created_at: "x", created_by_bot: null, tainted: true },
];

beforeEach(() => {
  for (const mock of [getSummaryMock, listExpensesMock, createExpenseMock, keepExpenseMock]) mock.mockReset();
  getSummaryMock.mockResolvedValue(SUMMARY);
  listExpensesMock.mockResolvedValue(EXPENSES);
});
afterEach(() => cleanup());

describe("MoneyBoard", () => {
  it("shows the month total, the food row with what is left, and other currencies apart", async () => {
    render(<MoneyBoard />);
    expect(await screen.findByText(/12\.50/, { selector: ".money-board__total strong" })).toBeInTheDocument();
    const food = screen.getByRole("row", { name: /food/ });
    expect(food).toHaveTextContent("12.50");
    expect(food).toHaveTextContent("287.50");
    expect(screen.getByText(/Also .*20\.00.*not in the total/)).toBeInTheDocument();
  });

  it("groups the month by project, and the add form asks for a project", async () => {
    render(<MoneyBoard />);
    const table = await screen.findByRole("table", { name: "By project" });
    expect(within(table).getByRole("columnheader", { name: "Project" })).toBeInTheDocument();
    expect(within(table).getByRole("rowheader", { name: "food" })).toBeInTheDocument();
    expect(screen.getByLabelText("Project")).toHaveAttribute("list", "expense-projects");
    expect(screen.queryByLabelText("Category")).not.toBeInTheDocument();
  });

  it("lists the month's expenses and marks web content", async () => {
    render(<MoneyBoard />);
    const list = await screen.findByRole("list", { name: "Expenses" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    expect(within(list).getByText("from web content")).toBeInTheDocument();
  });

  it("offers Keep only on a web-made expense, and keeping it reloads", async () => {
    keepExpenseMock.mockResolvedValue({ ...EXPENSES[1], tainted: false });
    const user = userEvent.setup();
    render(<MoneyBoard />);
    const list = await screen.findByRole("list", { name: "Expenses" });
    expect(within(list).getAllByRole("button", { name: /^Keep/ })).toHaveLength(1);
    await user.click(within(list).getByRole("button", { name: "Keep the travel expense as yours" }));
    expect(keepExpenseMock).toHaveBeenCalledWith("e2");
    await waitFor(() => expect(getSummaryMock).toHaveBeenCalledTimes(2));
  });

  it("says so when the month has no expenses", async () => {
    getSummaryMock.mockResolvedValue({ ...SUMMARY, total: "0.00", expense_count: 0, by_project: [], other_currencies: {} });
    listExpensesMock.mockResolvedValue([]);
    render(<MoneyBoard initialMonth="2026-09" />);
    expect(await screen.findByText("Nothing spent in September 2026.")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Expenses" })).not.toBeInTheDocument();
  });

  it("adds 12,50 to food and reloads", async () => {
    createExpenseMock.mockResolvedValue(EXPENSES[0]);
    const user = userEvent.setup();
    render(<MoneyBoard />);
    await user.type(await screen.findByLabelText("Amount"), "12,50");
    await user.type(screen.getByLabelText("Project"), "food");
    await user.type(screen.getByLabelText("Note"), "lunch");
    await user.click(screen.getByRole("button", { name: "Add expense" }));
    expect(createExpenseMock).toHaveBeenCalledWith({ amount: "12.50", project: "food", note: "lunch" });
    await waitFor(() => expect(getSummaryMock).toHaveBeenCalledTimes(2));
  });

  it("refuses an amount it can't read without calling the gateway", async () => {
    const user = userEvent.setup();
    render(<MoneyBoard />);
    await user.type(await screen.findByLabelText("Amount"), "1.234,56");
    await user.click(screen.getByRole("button", { name: "Add expense" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Enter an amount like 12,50");
    expect(createExpenseMock).not.toHaveBeenCalled();
  });

  it("shows the gateway's refusal when an add fails", async () => {
    const { ApiError } = await import("../src/api/client");
    createExpenseMock.mockRejectedValue(new ApiError(422, "An amount must be more than 0 and at most 1,000,000."));
    const user = userEvent.setup();
    render(<MoneyBoard />);
    await user.type(await screen.findByLabelText("Amount"), "2000000");
    await user.click(screen.getByRole("button", { name: "Add expense" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("at most 1,000,000");
  });

  it("says what went wrong when the month can't load", async () => {
    getSummaryMock.mockRejectedValue(new Error("down"));
    render(<MoneyBoard />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong");
  });

  it("goes to the previous month", async () => {
    const user = userEvent.setup();
    render(<MoneyBoard initialMonth="2026-10" />);
    await screen.findByRole("row", { name: /food/ });
    await user.click(screen.getByRole("button", { name: "Previous month" }));
    await waitFor(() => expect(getSummaryMock).toHaveBeenLastCalledWith("2026-09"));
    expect(listExpensesMock).toHaveBeenLastCalledWith("2026-09");
  });

  it("adds only on this month: a past month offers the way back instead", async () => {
    const user = userEvent.setup();
    render(<MoneyBoard initialMonth="2020-01" />);
    await screen.findByRole("row", { name: /food/ });
    expect(screen.queryByLabelText("Amount")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next month" })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: /^Back to / }));
    expect(await screen.findByLabelText("Amount")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next month" })).toBeDisabled();
  });
});
```

**2g.** `web/tests/DocumentsTab.test.tsx`. Find:

```tsx
      expenses: [{ id: "e1", amount: "12.50", currency: "EUR", category: "food", tainted: true }],
```

Replace with:

```tsx
      expenses: [{ id: "e1", amount: "12.50", currency: "EUR", project: "food", project_id: "p1", tainted: true }],
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_money_store.py tests/test_money_tools.py -q`
Expected: FAIL. Two collection errors, `ModuleNotFoundError: No module named 'roost.money.project_store'` ("Interrupted: 2 errors during collection").

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_money_api.py tests/test_vocabulary.py -q`
Expected: FAIL, 4 failed and 5 passed:
- `test_add_an_expense_and_see_it_in_the_month_and_the_summary`: `assert 422 == 201` (`ExpenseIn` forbids the unknown field `project`).
- `test_the_summary_wire_uses_by_project`: `KeyError: 'project'` (each post was refused with 422).
- `test_keep_vouches_for_a_web_made_expense_and_the_project_it_shows`: `TypeError: ExpenseEntry.__init__() got an unexpected keyword argument 'project'`.
- `test_the_web_face_says_project_not_category`: the offenders list names `web/src/api/types.ts`, `web/src/components/board/ExpenseAddForm.tsx` and `web/src/components/board/MoneyBoard.tsx`.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_profile_api.py tests/test_tool_text.py tests/test_document_tools.py tests/test_main_bot.py -q`
Expected: FAIL. Four collection errors, `ModuleNotFoundError: No module named 'roost.money.project_store'` (`test_main_bot.py` imports `live_shape`).

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npx vitest run tests/MoneyBoard.test.tsx tests/DocumentsTab.test.tsx`
Expected: FAIL. `MoneyBoard` still reads `summary.by_category`, which the new fixtures don't have (`TypeError: Cannot read properties of undefined (reading 'length')`), and it has no "Project" field or "By project" table. `DocumentsTab` shows "12.50 EUR · undefined", so the link "12.50 EUR · food" is not found.

- [ ] **Step 4: Move the store and rename the money model**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git mv roost/money/category_store.py roost/money/project_store.py`

**4a.** `roost/constants.py` (after the stuck flow; this line is in the Finance section, which the stuck flow does not touch). Find:

```python
# LazyClaw's GENERAL_PROJECT_NAME: where an expense with no category goes.
GENERAL_CATEGORY_NAME = "General"
```

Replace with:

```python
# Where an expense with no project goes (LazyClaw's GENERAL_PROJECT_NAME).
GENERAL_PROJECT_NAME = "General"
```

**4b.** Replace the whole of `roost/money/models.py` with:

```python
"""Money domain model (M1 D7, projects hub H1). A ``Project`` is a row of
``money_projects``, LazyClaw's project: a named budget bucket an expense
belongs to. Loose expenses go to the General project."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Mapping

from roost.constants import DEFAULT_CURRENCY


@dataclass(frozen=True)
class Project:
    id: str
    user_id: str
    name: str
    budget: Decimal | None
    currency: str
    created_at: str
    updated_at: str
    created_by_bot: str | None
    tainted: bool


@dataclass(frozen=True)
class Expense:
    id: str
    user_id: str
    project_id: str           # money_projects.id, as in LazyClaw
    amount: Decimal
    currency: str
    description: str | None   # the note: "lunch"
    vendor: str | None
    spent_at: str             # YYYY-MM-DD, a Madrid day
    status: str
    created_at: str
    updated_at: str
    created_by_bot: str | None
    tainted: bool


@dataclass(frozen=True)
class ExpenseDraft:
    project_id: str
    amount: Decimal
    currency: str = DEFAULT_CURRENCY
    description: str | None = None
    vendor: str | None = None
    spent_at: str = ""


EXPENSE_PATCHABLE = frozenset({"project_id", "amount", "currency", "description", "vendor", "spent_at"})


@dataclass(frozen=True)
class ExpensePatch:
    changes: Mapping[str, Any]

    def __post_init__(self) -> None:
        unknown = sorted(set(self.changes) - EXPENSE_PATCHABLE)
        if unknown:
            raise ValueError(f"Expenses have no field {', '.join(unknown)}.")
        object.__setattr__(self, "changes", MappingProxyType(dict(self.changes)))


@dataclass(frozen=True)
class ProjectTotal:
    project: str              # the project's name
    spent: Decimal
    budget: Decimal | None

    @property
    def remaining(self) -> Decimal | None:
        return None if self.budget is None else self.budget - self.spent


@dataclass(frozen=True)
class MoneySummary:
    month: str
    currency: str
    total: Decimal
    expense_count: int
    by_project: tuple[ProjectTotal, ...]
    other_currencies: Mapping[str, Decimal]
```

**4c.** Replace the whole of `roost/money/project_store.py` (the file `git mv` just moved) with:

```python
# SPDX-License-Identifier: MIT
# Adapted from LazyClaw lazyclaw/budgets/store.py @ 21e1002 (names and semantics), for Roost
"""``ProjectStore`` — the user's projects (the ``money_projects`` table,
LazyClaw's projects).

Names and budgets are ``enc:v2``; ``name_key`` is HMAC(dek, folded name), so a
name is unique per user without ever being stored or compared in plaintext
(LazyClaw kept a plaintext casefold key). ``set_budget`` writes an ``edit``
ledger row with the signed change and ``add_topup`` a ``credit`` row, as
LazyClaw's budget_entries did."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import aiosqlite

from roost.config import Config
from roost.constants import DEFAULT_CURRENCY
from roost.crypto.encryption import decrypt_field, encrypt, encrypt_field, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session
from roost.money.amounts import amount_text
from roost.money.models import Project

_COLUMNS = "id, user_id, name, budget, currency, created_at, updated_at, created_by_bot, tainted"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _aad(user_id: str, column: str) -> bytes:
    return user_aad(user_id, f"money_projects:{column}")


def _name_key(dek: bytes, name: str) -> str:
    folded = " ".join(name.casefold().split())
    return hmac.new(dek, folded.encode("utf-8"), hashlib.sha256).hexdigest()


def _row_to_project(row: aiosqlite.Row, dek: bytes) -> Project:
    user_id = row["user_id"]
    budget = decrypt_field(row["budget"], dek, _aad(user_id, "budget"))
    return Project(
        id=row["id"], user_id=user_id, name=decrypt_field(row["name"], dek, _aad(user_id, "name")) or "",
        budget=Decimal(budget) if budget else None, currency=row["currency"], created_at=row["created_at"],
        updated_at=row["updated_at"], created_by_bot=row["created_by_bot"], tainted=bool(row["tainted"]),
    )


class ProjectStore:
    def __init__(self, config: Config) -> None:
        self._config = config

    async def list(self, user_id: str) -> tuple[Project, ...]:
        return await self._select(user_id, "WHERE user_id = ? AND deleted_at IS NULL ORDER BY created_at", (user_id,))

    async def get(self, user_id: str, project_id: str) -> Project | None:
        found = await self._select(user_id, "WHERE id = ? AND user_id = ? AND deleted_at IS NULL", (project_id, user_id))
        return found[0] if found else None

    async def find_or_create(self, user_id: str, name: str, *, created_by_bot: str | None, tainted: bool) -> Project:
        dek = await get_user_dek(self._config, user_id)
        key = _name_key(dek, name)
        existing = await self._select(user_id, "WHERE user_id = ? AND name_key = ? AND deleted_at IS NULL", (user_id, key))
        if existing:
            return existing[0]
        now = _now_iso()
        try:
            async with db_session(self._config) as db:
                await db.execute(
                    "INSERT INTO money_projects (id, user_id, name, name_key, currency, created_at, updated_at, "
                    "created_by_bot, tainted) VALUES (?,?,?,?,?,?,?,?,?)",
                    (str(uuid4()), user_id, encrypt(name.strip(), dek, _aad(user_id, "name")), key,
                     DEFAULT_CURRENCY, now, now, created_by_bot, int(tainted)),
                )
                await db.commit()
        except aiosqlite.IntegrityError:
            pass   # created concurrently: the select below finds it
        return (await self._select(user_id, "WHERE user_id = ? AND name_key = ? AND deleted_at IS NULL", (user_id, key)))[0]

    async def keep(self, user_id: str, project_id: str) -> Project | None:
        """The user vouches for a project's name (via Keep on an expense row
        that shows it): its taint bit is cleared. HTTP only, never a tool."""
        async with db_session(self._config) as db:
            await db.execute(
                "UPDATE money_projects SET tainted = 0, updated_at = ? WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
                (_now_iso(), project_id, user_id),
            )
            await db.commit()
        return await self.get(user_id, project_id)

    async def set_budget(self, user_id: str, project_id: str, amount: Decimal, *,
                         created_by_bot: str | None, tainted: bool) -> Project | None:
        current = await self.get(user_id, project_id)
        if current is None:
            return None
        delta = amount - (current.budget or Decimal("0"))
        return await self._move_budget(current, amount, delta, "edit", None, created_by_bot, tainted)

    async def add_topup(self, user_id: str, project_id: str, amount: Decimal, source: str | None, *,
                        created_by_bot: str | None, tainted: bool) -> Project | None:
        current = await self.get(user_id, project_id)
        if current is None:
            return None
        new_budget = (current.budget or Decimal("0")) + amount
        return await self._move_budget(current, new_budget, amount, "credit", source, created_by_bot, tainted)

    async def _move_budget(self, current: Project, budget: Decimal, delta: Decimal, kind: str, source: str | None,
                           created_by_bot: str | None, tainted: bool) -> Project:
        user_id, now = current.user_id, _now_iso()
        dek = await get_user_dek(self._config, user_id)
        async with db_session(self._config) as db:
            try:
                await db.execute(
                    "UPDATE money_projects SET budget = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                    (encrypt(amount_text(budget), dek, _aad(user_id, "budget")), now, current.id, user_id),
                )
                await db.execute(
                    "INSERT INTO money_topups (id, user_id, project_id, amount, currency, source, kind, created_at, "
                    "updated_at, created_by_bot, tainted) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (str(uuid4()), user_id, current.id,
                     encrypt(amount_text(delta), dek, user_aad(user_id, "money_topups:amount")), current.currency,
                     encrypt_field(source, dek, user_aad(user_id, "money_topups:source")), kind, now, now,
                     created_by_bot, int(tainted)),
                )
                await db.commit()
            except aiosqlite.Error:
                await db.rollback()
                raise
        return replace(current, budget=budget.quantize(Decimal("0.01")), updated_at=now)

    async def _select(self, user_id: str, where: str, params: tuple) -> tuple[Project, ...]:
        async with db_session(self._config) as db:
            rows = await (await db.execute(f"SELECT {_COLUMNS} FROM money_projects {where}", params)).fetchall()
        if not rows:
            return ()
        dek = await get_user_dek(self._config, user_id)
        return tuple(_row_to_project(row, dek) for row in rows)
```

**4d.** `roost/money/expense_store.py`. The field and the column now share the name `project_id`, so `_encode` needs no special case (its last line, `getattr(expense, column)`, reads it). Find:

```python
def _encode(expense: Expense, column: str, dek: bytes) -> Any:
    if column == "project_id":
        return expense.category_id
    if column == "amount":
```

Replace with:

```python
def _encode(expense: Expense, column: str, dek: bytes) -> Any:
    if column == "amount":
```

Find:

```python
        id=row["id"], user_id=user_id, category_id=row["project_id"], amount=Decimal(text("amount") or "0"),
```

Replace with:

```python
        id=row["id"], user_id=user_id, project_id=row["project_id"], amount=Decimal(text("amount") or "0"),
```

Find:

```python
            id=str(uuid4()), user_id=user_id, category_id=draft.category_id, amount=draft.amount,
```

Replace with:

```python
            id=str(uuid4()), user_id=user_id, project_id=draft.project_id, amount=draft.amount,
```

- [ ] **Step 5: Rename the service, the summary and the tool text**

**5a.** Replace the whole of `roost/money/service.py` with:

```python
"""``MoneyService`` — projects + expenses + the ``money_changed`` frame. Tools
and HTTP routes both go through it."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from roost.constants import DEFAULT_CURRENCY, GENERAL_PROJECT_NAME
from roost.events.hub import EventHub
from roost.money.expense_store import ExpenseStore
from roost.money.models import Expense, ExpenseDraft, ExpensePatch, MoneySummary, Project
from roost.money.project_store import ProjectStore
from roost.money.summary import summarize
from roost.records.resolver import NamedRef, resolve

MoneyChange = Literal["expense_created", "expense_updated", "expense_deleted", "budget_set"]


@dataclass(frozen=True)
class ExpenseEntry:
    """A parsed, validated expense to log (amount and day already read)."""

    amount: Decimal
    spent_at: str
    project: str | None = None
    note: str | None = None
    vendor: str | None = None
    currency: str = DEFAULT_CURRENCY


class MoneyService:
    def __init__(self, projects: ProjectStore, expenses: ExpenseStore, events: EventHub) -> None:
        self._projects = projects
        self._expenses = expenses
        self._events = events

    async def project_for(self, user_id: str, name: str | None, *, created_by_bot: str | None,
                          tainted: bool) -> Project:
        """An existing project on an exact or typo match (harvested resolver),
        else a new one. A partial match never redirects money elsewhere."""
        wanted = (name or "").strip() or GENERAL_PROJECT_NAME
        known = await self._projects.list(user_id)
        hit = resolve(wanted, [NamedRef(p.id, p.name) for p in known])
        if hit.resolved is not None and hit.reason in ("exact", "fuzzy"):
            return next(p for p in known if p.id == hit.resolved.id)
        return await self._projects.find_or_create(user_id, wanted, created_by_bot=created_by_bot, tainted=tainted)

    async def log_expense(self, user_id: str, entry: ExpenseEntry, *, created_by_bot: str | None = None,
                          tainted: bool = False) -> tuple[Expense, Project]:
        project = await self.project_for(user_id, entry.project, created_by_bot=created_by_bot, tainted=tainted)
        draft = ExpenseDraft(project_id=project.id, amount=entry.amount, currency=entry.currency,
                             description=entry.note, vendor=entry.vendor, spent_at=entry.spent_at)
        expense = await self._expenses.add(user_id, draft, created_by_bot=created_by_bot, tainted=tainted)
        await self._changed(user_id, "expense_created", expense.id)
        return expense, project

    async def projects(self, user_id: str) -> tuple[Project, ...]:
        return await self._projects.list(user_id)

    async def list_expenses(self, user_id: str, month: str) -> tuple[Expense, ...]:
        return await self._expenses.list_month(user_id, month)

    async def get_expense(self, user_id: str, expense_id: str) -> Expense | None:
        return await self._expenses.get(user_id, expense_id)

    async def made_by(self, user_id: str, bot_id: str, limit: int) -> tuple[tuple[Expense, Project | None], ...]:
        projects = {p.id: p for p in await self.projects(user_id)}
        expenses = await self._expenses.made_by(user_id, bot_id, limit)
        return tuple((expense, projects.get(expense.project_id)) for expense in expenses)

    async def summary(self, user_id: str, month: str) -> tuple[MoneySummary, bool]:
        """The month's summary and whether anything behind it is tainted: an
        expense in its totals, or a project whose name it prints. A web-made
        project the summary doesn't show leaves it clean (R1: taint must not
        spread to every conversation that adds up a month)."""
        projects = await self._projects.list(user_id)
        expenses = await self._expenses.list_month(user_id, month)
        summary = summarize(month, projects, expenses)
        shown = {row.project for row in summary.by_project}
        tainted = any(e.tainted for e in expenses) or any(p.tainted for p in projects if p.name in shown)
        return summary, tainted

    async def update_expense(self, user_id: str, expense_id: str, patch: ExpensePatch) -> Expense | None:
        expense = await self._expenses.update(user_id, expense_id, patch)
        if expense is not None:
            await self._changed(user_id, "expense_updated", expense.id)
        return expense

    async def keep_expense(self, user_id: str, expense_id: str) -> tuple[Expense, Project | None] | None:
        """The user vouches for an expense on the Board (HTTP only, never a
        tool): it and the project name its row shows are theirs now, so a
        month listing them no longer taints a run."""
        expense = await self._expenses.keep(user_id, expense_id)
        if expense is None:
            return None
        project = await self._projects.keep(user_id, expense.project_id)
        await self._changed(user_id, "expense_updated", expense.id)
        return expense, project

    async def delete_expense(self, user_id: str, expense_id: str) -> bool:
        deleted = await self._expenses.delete(user_id, expense_id)
        if deleted:
            await self._changed(user_id, "expense_deleted", expense_id)
        return deleted

    async def set_budget(self, user_id: str, name: str, amount: Decimal, *, created_by_bot: str | None = None,
                         tainted: bool = False) -> Project:
        project = await self.project_for(user_id, name, created_by_bot=created_by_bot, tainted=tainted)
        updated = await self._projects.set_budget(user_id, project.id, amount, created_by_bot=created_by_bot,
                                                  tainted=tainted)
        await self._changed(user_id, "budget_set", project.id)
        return updated or project

    async def _changed(self, user_id: str, change: MoneyChange, item_id: str) -> None:
        await self._events.publish(user_id, {"type": "money_changed", "change": change, "id": item_id})
```

**5b.** Replace the whole of `roost/money/summary.py` with:

```python
# SPDX-License-Identifier: MIT
# Adapted from LazyClaw lazyclaw/budgets/store.py @ 21e1002 (spending_report semantics), for Roost
"""Month totals by project (M1 D7, projects hub H1). Only the default currency
is totaled; other currencies are listed apart, never converted (LazyClaw
flagged mixed currencies the same way)."""

from __future__ import annotations

from decimal import Decimal
from types import MappingProxyType
from typing import Any

from roost.constants import DEFAULT_CURRENCY
from roost.money.amounts import amount_text
from roost.money.models import Expense, MoneySummary, Project, ProjectTotal

_ZERO = Decimal("0.00")


def _sums(expenses: tuple[Expense, ...], key) -> dict[str, Decimal]:
    totals: dict[str, Decimal] = {}
    for expense in expenses:
        totals = {**totals, key(expense): totals.get(key(expense), _ZERO) + expense.amount}
    return totals


def summarize(month: str, projects: tuple[Project, ...], expenses: tuple[Expense, ...]) -> MoneySummary:
    main = tuple(e for e in expenses if e.currency == DEFAULT_CURRENCY)
    spent = _sums(main, lambda e: e.project_id)
    rows = tuple(
        ProjectTotal(project.name, spent.get(project.id, _ZERO), project.budget)
        for project in projects if project.id in spent or project.budget is not None
    )
    others = _sums(tuple(e for e in expenses if e.currency != DEFAULT_CURRENCY), lambda e: e.currency)
    return MoneySummary(
        month=month, currency=DEFAULT_CURRENCY, total=sum((e.amount for e in main), _ZERO),
        expense_count=len(expenses), by_project=tuple(sorted(rows, key=lambda r: (-r.spent, r.project.casefold()))),
        other_currencies=MappingProxyType(others),
    )


def _optional(amount: Decimal | None) -> str | None:
    return None if amount is None else amount_text(amount)


def summary_out(summary: MoneySummary) -> dict[str, Any]:
    return {
        "month": summary.month, "currency": summary.currency, "total": amount_text(summary.total),
        "expense_count": summary.expense_count,
        "by_project": [{"project": row.project, "spent": amount_text(row.spent), "budget": _optional(row.budget),
                        "remaining": _optional(row.remaining)} for row in summary.by_project],
        "other_currencies": {code: amount_text(total) for code, total in summary.other_currencies.items()},
    }


def expense_row(expense: Expense, project: Project | None) -> dict[str, Any]:
    if project is None:
        return expense_out(expense, "")
    return expense_out(expense, project.name, project_tainted=project.tainted)


def expense_out(expense: Expense, project: str, *, project_tainted: bool = False) -> dict[str, Any]:
    """``project`` is the project's name; ``project_id`` is its id. ``tainted``
    marks the row "from web content" when the expense OR the project name it
    shows was web-made — either one taints a run that lists it, so the Board's
    Keep must be offered for both."""
    return {
        "id": expense.id, "project": project, "project_id": expense.project_id,
        "amount": amount_text(expense.amount), "currency": expense.currency,
        "description": expense.description, "vendor": expense.vendor, "spent_at": expense.spent_at,
        "status": expense.status, "created_at": expense.created_at, "created_by_bot": expense.created_by_bot,
        "tainted": expense.tainted or project_tainted,
    }
```

**5c.** `roost/money/format.py`. Find:

```python
def expense_line(expense: Expense, category: str) -> str:
    note = f" · {escape(expense.description)}" if expense.description else ""
    mark = " [from web content]" if expense.tainted else ""
    return f"{expense.spent_at} · {escape(category)} · {money(expense.amount, expense.currency)}{note}{mark} id={expense.id}"
```

Replace with:

```python
def expense_line(expense: Expense, project: str) -> str:
    note = f" · {escape(expense.description)}" if expense.description else ""
    mark = " [from web content]" if expense.tainted else ""
    return f"{expense.spent_at} · {escape(project)} · {money(expense.amount, expense.currency)}{note}{mark} id={expense.id}"
```

Find:

```python
    for row in summary.by_category:
        budget = f" of {money(row.budget, summary.currency)}, {money(row.remaining, summary.currency)} left" if row.budget is not None else ""
        lines.append(f"- {escape(row.category)}: {money(row.spent, summary.currency)}{budget}")
```

Replace with:

```python
    for row in summary.by_project:
        budget = f" of {money(row.budget, summary.currency)}, {money(row.remaining, summary.currency)} left" if row.budget is not None else ""
        lines.append(f"- {escape(row.project)}: {money(row.spent, summary.currency)}{budget}")
```

- [ ] **Step 6: Rename the tools, their specs and the wiring**

**6a.** Replace the whole of `roost/money/tools.py` with:

```python
"""The finance role's tools over the user's shared money (M1 D2, D7)."""

from __future__ import annotations

from typing import Any, Mapping

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError

from roost.constants import (
    CURRENCY_PATTERN, DEFAULT_CURRENCY, EXPENSE_LIST_LIMIT, MAX_CATEGORY_NAME_LENGTH, MAX_DUE_TEXT_LENGTH,
    MAX_EXPENSE_NOTE_LENGTH,
)
from roost.money.amounts import parse_amount
from roost.money.format import escape, expense_line, money, summary_text
from roost.money.models import Expense, ExpensePatch, Project
from roost.money.months import current_month, month_bounds, parse_spent_at
from roost.money.service import ExpenseEntry, MoneyService
from roost.records.paging import more_line
from roost.records.tool_text import ToolText
from roost.talk.domain_tools import RecordContext
from roost.talk.outcome import ToolOutcome

_ACTIVITY = {
    "log_expense": "logging an expense", "list_expenses": "checking your expenses",
    "money_summary": "adding up your month", "update_expense": "correcting an expense",
    "delete_expense": "deleting an expense", "set_budget": "setting a budget",
}
_Amount = str | int | float
# Projects hub H1: the argument is `project`. `extra="ignore"` would silently drop
# the old `category`, landing the money in General, so both names are read;
# `project` wins when a model sends both.
_PROJECT_ARG = AliasChoices("project", "category")


class LogExpenseArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    amount: _Amount
    project: ToolText | None = Field(default=None, validation_alias=_PROJECT_ARG, max_length=MAX_CATEGORY_NAME_LENGTH)
    note: ToolText | None = Field(default=None, max_length=MAX_EXPENSE_NOTE_LENGTH)
    vendor: ToolText | None = Field(default=None, max_length=MAX_EXPENSE_NOTE_LENGTH)
    currency: str = Field(default=DEFAULT_CURRENCY, pattern=CURRENCY_PATTERN)
    spent_at: str | None = Field(default=None, max_length=MAX_DUE_TEXT_LENGTH)


class MonthArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    month: str | None = Field(default=None, max_length=7)
    project: ToolText | None = Field(default=None, validation_alias=_PROJECT_ARG, max_length=MAX_CATEGORY_NAME_LENGTH)


class ListExpensesArgs(MonthArgs):
    offset: int = Field(default=0, ge=0)


class ExpenseRefArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    expense: str = Field(min_length=1, max_length=64)


class UpdateExpenseArgs(ExpenseRefArgs):
    amount: _Amount | None = None
    project: ToolText | None = Field(default=None, validation_alias=_PROJECT_ARG, max_length=MAX_CATEGORY_NAME_LENGTH)
    note: ToolText | None = Field(default=None, max_length=MAX_EXPENSE_NOTE_LENGTH)
    spent_at: str | None = Field(default=None, max_length=MAX_DUE_TEXT_LENGTH)


class SetBudgetArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    project: ToolText = Field(validation_alias=_PROJECT_ARG, min_length=1, max_length=MAX_CATEGORY_NAME_LENGTH)
    amount: _Amount


def _month(value: str | None) -> str:
    month = value or current_month()
    month_bounds(month)   # raises a plain ValueError for a bad month
    return month


def _project_name(projects: Mapping[str, Project], expense: Expense) -> str:
    project = projects.get(expense.project_id)
    return project.name if project is not None else "?"


def _project_tainted(projects: Mapping[str, Project], expense: Expense) -> bool:
    project = projects.get(expense.project_id)
    return project is not None and project.tainted


class MoneyTools:
    names = frozenset(_ACTIVITY)

    def __init__(self, service: MoneyService) -> None:
        self._service = service

    def activity(self, name: str) -> str:
        return _ACTIVITY[name]

    async def run(self, name: str, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        handlers = {"log_expense": self._log, "list_expenses": self._list, "money_summary": self._summary,
                    "update_expense": self._update, "delete_expense": self._delete, "set_budget": self._budget}
        try:
            return await handlers[name](arguments, ctx)
        except ValidationError:
            return ToolOutcome(f"Refused: {name} got arguments it can't use; see its description.")
        except ValueError as exc:
            return ToolOutcome(f"Refused: {escape(str(exc))}")

    async def _log(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = LogExpenseArgs.model_validate(arguments)
        entry = ExpenseEntry(amount=parse_amount(args.amount), spent_at=parse_spent_at(args.spent_at),
                             project=args.project, note=args.note, vendor=args.vendor, currency=args.currency)
        expense, project = await self._service.log_expense(ctx.user_id, entry, created_by_bot=ctx.bot_id,
                                                            tainted=ctx.tainted)
        # The reply echoes the project's name; one a tainted run made is web text (D3).
        return ToolOutcome(f"Logged {money(expense.amount, expense.currency)} to {escape(project.name)} on "
                           f"{expense.spent_at} (id={expense.id}).", created=True, tainted=project.tainted)

    async def _list(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        """Taint covers every expense shown AND every project name printed."""
        args = ListExpensesArgs.model_validate(arguments)
        projects = {p.id: p for p in await self._service.projects(ctx.user_id)}
        expenses = await self._service.list_expenses(ctx.user_id, _month(args.month))
        wanted = (args.project or "").strip().casefold()
        matching = tuple(e for e in expenses if not wanted or _project_name(projects, e).casefold() == wanted)
        shown = matching[args.offset:args.offset + EXPENSE_LIST_LIMIT]
        if not shown:
            return ToolOutcome("No expenses match." if not matching
                               else f"Nothing more: all {len(matching)} expenses are listed.")
        lines = "\n".join(expense_line(e, _project_name(projects, e)) for e in shown)
        tainted = any(e.tainted or _project_tainted(projects, e) for e in shown)
        return ToolOutcome(lines + more_line(len(matching), args.offset, len(shown)), tainted=tainted)

    async def _summary(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        summary, tainted = await self._service.summary(ctx.user_id, _month(MonthArgs.model_validate(arguments).month))
        return ToolOutcome(summary_text(summary), tainted=tainted)

    async def _update(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = UpdateExpenseArgs.model_validate(arguments)
        current = await self._service.get_expense(ctx.user_id, args.expense)
        if current is None:
            return ToolOutcome("Refused: there is no expense with that id.")
        changes = await self._changes(args, ctx)
        expense = await self._service.update_expense(ctx.user_id, current.id, ExpensePatch(changes))
        # No project name is echoed here, so a web-made project adds no text (and no taint).
        return ToolOutcome(f"Updated: {money(expense.amount, expense.currency)} on {expense.spent_at}.",
                           tainted=current.tainted)

    async def _changes(self, args: UpdateExpenseArgs, ctx: RecordContext) -> dict[str, Any]:
        changes: dict[str, Any] = {}
        if args.amount is not None:
            changes["amount"] = parse_amount(args.amount)
        if args.spent_at is not None:
            changes["spent_at"] = parse_spent_at(args.spent_at)
        if args.note is not None:
            changes["description"] = args.note
        if args.project is not None:
            project = await self._service.project_for(ctx.user_id, args.project, created_by_bot=ctx.bot_id,
                                                      tainted=ctx.tainted)
            changes["project_id"] = project.id
        return changes

    async def _delete(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        current = await self._service.get_expense(ctx.user_id, ExpenseRefArgs.model_validate(arguments).expense)
        if current is None:
            return ToolOutcome("Refused: there is no expense with that id.")
        await self._service.delete_expense(ctx.user_id, current.id)
        return ToolOutcome(f"Deleted the {money(current.amount, current.currency)} expense of {current.spent_at}.",
                           tainted=current.tainted)

    async def _budget(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = SetBudgetArgs.model_validate(arguments)
        project = await self._service.set_budget(ctx.user_id, args.project, parse_amount(args.amount),
                                                 created_by_bot=ctx.bot_id, tainted=ctx.tainted)
        return ToolOutcome(f"Budget for {escape(project.name)}: {money(project.budget, project.currency)}.",
                           tainted=project.tainted)
```

**6b.** Replace the whole of `roost/money/tool_specs.py` with:

```python
"""The money tool specs and gate kinds (M1 D3, D7; projects hub H1)."""

from __future__ import annotations

from roost.llm.types import ToolSpec
from roost.records.paging import OFFSET_PROPERTY
from roost.talk.tool_def import ToolDef

_AMOUNT = {"type": ["number", "string"], "description": "The amount, e.g. 12.50 or '12,50'."}
_PROJECT = {"type": "string", "description": "Project, e.g. 'food'. Omit for General."}
_MONTH = {"type": "string", "description": "A month like 2026-10. Default: this month (Europe/Madrid)."}
_EXPENSE = {"type": "string", "description": "The expense's id, from list_expenses."}

LOG_EXPENSE_SPEC = ToolSpec(
    name="log_expense",
    description="Log money the user spent. Amounts are in euros unless a currency is given. "
                "Log an expense as soon as the user mentions one. Never invent amounts; you cannot buy or pay anything.",
    input_schema={"type": "object", "properties": {
        "amount": _AMOUNT, "project": _PROJECT,
        "note": {"type": "string", "description": "What it was for, e.g. 'lunch'."},
        "vendor": {"type": "string", "description": "Optional shop or payee."},
        "currency": {"type": "string", "description": "Three-letter code, default EUR."},
        "spent_at": {"type": "string", "description": "The day: 'yesterday', '2026-10-12'. Default: today."},
    }, "required": ["amount"]},
)
LIST_EXPENSES_SPEC = ToolSpec(
    name="list_expenses",
    description=("List the user's expenses for a month, newest first, with their ids. A long list ends with "
                 "how to get the rest."),
    input_schema={"type": "object", "properties": {
        "month": _MONTH, "project": _PROJECT, "offset": dict(OFFSET_PROPERTY),
    }},
)
MONEY_SUMMARY_SPEC = ToolSpec(
    name="money_summary",
    description="Totals for a month: overall and by project, with budgets and what is left.",
    input_schema={"type": "object", "properties": {"month": _MONTH}},
)
UPDATE_EXPENSE_SPEC = ToolSpec(
    name="update_expense",
    description="Correct an expense's amount, project, note or day.",
    input_schema={"type": "object", "properties": {
        "expense": _EXPENSE, "amount": _AMOUNT, "project": _PROJECT, "note": {"type": "string"},
        "spent_at": {"type": "string"},
    }, "required": ["expense"]},
)
DELETE_EXPENSE_SPEC = ToolSpec(
    name="delete_expense",
    description="Delete an expense.",
    input_schema={"type": "object", "properties": {"expense": _EXPENSE}, "required": ["expense"]},
)
SET_BUDGET_SPEC = ToolSpec(
    name="set_budget",
    description="Set a project's budget (the amount the user plans to spend there).",
    input_schema={"type": "object", "properties": {"project": _PROJECT, "amount": _AMOUNT},
                  "required": ["project", "amount"]},
)

MONEY_TOOL_DEFS: tuple[ToolDef, ...] = (
    ToolDef(LOG_EXPENSE_SPEC, "write_create"),
    ToolDef(LIST_EXPENSES_SPEC, "read"),
    ToolDef(MONEY_SUMMARY_SPEC, "read"),
    ToolDef(UPDATE_EXPENSE_SPEC, "write_change"),
    ToolDef(DELETE_EXPENSE_SPEC, "write_change"),
    ToolDef(SET_BUDGET_SPEC, "write_change"),
)
```

**6c.** `roost/tasks/tool_specs.py` (a task's `category` is its list; only the wording changes). Find:

```python
        "category": {"type": "string", "description": "Optional list or project, e.g. 'Home'."},
```

Replace with:

```python
        "category": {"type": "string", "description": "Optional list, e.g. 'Home'."},
```

Find:

```python
        "category": {"type": "string", "description": "Only this list or project."},
```

Replace with:

```python
        "category": {"type": "string", "description": "Only this list."},
```

**6d.** Replace the whole of `roost/gateway/routes/money.py` with:

```python
"""Money over HTTP — the Board's data (M1 D8)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from roost.constants import CURRENCY_PATTERN, DEFAULT_CURRENCY, MAX_CATEGORY_NAME_LENGTH, MAX_DUE_TEXT_LENGTH, MAX_EXPENSE_NOTE_LENGTH
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.money.amounts import parse_amount
from roost.money.months import current_month, month_bounds, parse_spent_at
from roost.money.service import ExpenseEntry, MoneyService
from roost.money.summary import expense_row, summary_out

money_router = APIRouter(prefix="/api/money", tags=["money"])


class ExpenseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: str | int | float
    project: str | None = Field(default=None, max_length=MAX_CATEGORY_NAME_LENGTH)   # a name; none: General
    note: str | None = Field(default=None, max_length=MAX_EXPENSE_NOTE_LENGTH)
    currency: str = Field(default=DEFAULT_CURRENCY, pattern=CURRENCY_PATTERN)
    spent_at: str | None = Field(default=None, max_length=MAX_DUE_TEXT_LENGTH)


def _service(request: Request) -> MoneyService:
    return request.app.state.money


def _month(month: str | None) -> str:
    value = month or current_month()
    try:
        month_bounds(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return value


@money_router.get("/summary")
async def money_summary(request: Request, user: CurrentUser, month: str | None = None):
    summary, _ = await _service(request).summary(user.id, _month(month))
    return summary_out(summary)


@money_router.get("/expenses")
async def list_expenses(request: Request, user: CurrentUser, month: str | None = None):
    service = _service(request)
    projects = {p.id: p for p in await service.projects(user.id)}
    return [expense_row(e, projects.get(e.project_id)) for e in await service.list_expenses(user.id, _month(month))]


@money_router.post("/expenses/{expense_id}/keep", dependencies=[RequireOrigin])
async def keep_expense(expense_id: str, request: Request, user: CurrentUser):
    """Keep: the user vouches for an expense marked "from web content" and
    for the project name its row shows (no tool can do this)."""
    kept = await _service(request).keep_expense(user.id, expense_id)
    if kept is None:
        raise HTTPException(status_code=404, detail="Expense not found")
    return expense_row(*kept)


@money_router.post("/expenses", status_code=201, dependencies=[RequireOrigin])
async def add_expense(body: ExpenseIn, request: Request, user: CurrentUser):
    try:
        entry = ExpenseEntry(amount=parse_amount(body.amount), spent_at=parse_spent_at(body.spent_at),
                             project=body.project, note=body.note, currency=body.currency)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    expense, project = await _service(request).log_expense(user.id, entry)
    return expense_row(expense, project)
```

**6e.** `roost/gateway/app.py` (after the stuck flow; the stuck flow adds `StuckStore`, `StuckService`, `make_main_browser` and `stuck_router` elsewhere and leaves these lines alone). Find:

```python
from roost.money.category_store import CategoryStore
from roost.money.expense_store import ExpenseStore
from roost.money.service import MoneyService
```

Replace with:

```python
from roost.money.expense_store import ExpenseStore
from roost.money.project_store import ProjectStore
from roost.money.service import MoneyService
```

Find (after the stuck flow):

```python
    app.state.money = MoneyService(CategoryStore(resolved_config), ExpenseStore(resolved_config), app.state.events)
```

Replace with:

```python
    app.state.money = MoneyService(ProjectStore(resolved_config), ExpenseStore(resolved_config), app.state.events)
```

**6f.** `roost/talk/domain_tools.py`. Find:

```python
    from roost.money.category_store import CategoryStore
    from roost.money.expense_store import ExpenseStore
```

Replace with:

```python
    from roost.money.expense_store import ExpenseStore
    from roost.money.project_store import ProjectStore
```

Find:

```python
    money = MoneyService(CategoryStore(config), ExpenseStore(config), events)
```

Replace with:

```python
    money = MoneyService(ProjectStore(config), ExpenseStore(config), events)
```

- [ ] **Step 7: Rename the web side**

**7a.** `web/src/api/types.ts` (after the stuck flow; the stuck flow edits `MessageKind`, `ServerFrame` and inserts after `CreatedCardData` / `DocumentsChangedFrame`, not these lines). Find:

```ts
export interface ExpenseOut {
  id: string;
  category: string;
  amount: string; // "12.50" — a decimal string, never a float
```

Replace with:

```ts
export interface ExpenseOut {
  id: string;
  project: string; // the project's name ("General" for a loose expense)
  project_id: string;
  amount: string; // "12.50" — a decimal string, never a float
```

Find (after the stuck flow):

```ts
export interface CategoryTotalOut {
  category: string;
  spent: string;
  budget: string | null;
  remaining: string | null;
}
```

Replace with:

```ts
export interface ProjectTotalOut {
  project: string; // the project's name
  spent: string;
  budget: string | null;
  remaining: string | null;
}
```

Find (after the stuck flow):

```ts
  by_category: CategoryTotalOut[];
```

Replace with:

```ts
  by_project: ProjectTotalOut[];
```

**7b.** Replace the whole of `web/src/api/money.ts` with:

```ts
import { apiRequest } from "./client";
import type { ExpenseOut, MoneySummaryOut } from "./types";

// The user's money (M1 D3/D8): the same records every finance-role bot works on.

export interface ExpenseIn {
  amount: string; // already read by parseAmountInput: "12.50"
  project?: string; // a project's name; a new name makes a new project, none means General
  note?: string;
}

export function getSummary(month: string): Promise<MoneySummaryOut> {
  return apiRequest<MoneySummaryOut>("GET", `/api/money/summary?month=${encodeURIComponent(month)}`);
}

export function listExpenses(month: string): Promise<ExpenseOut[]> {
  return apiRequest<ExpenseOut[]>("GET", `/api/money/expenses?month=${encodeURIComponent(month)}`);
}

export function createExpense(input: ExpenseIn): Promise<ExpenseOut> {
  return apiRequest<ExpenseOut>("POST", "/api/money/expenses", input);
}

// Keep: the user vouches for an expense marked "from web content", and for the
// project name its row shows (only here — no bot can).
export function keepExpense(expenseId: string): Promise<ExpenseOut> {
  return apiRequest<ExpenseOut>("POST", `/api/money/expenses/${encodeURIComponent(expenseId)}/keep`);
}
```

**7c.** Replace the whole of `web/src/components/board/ExpenseAddForm.tsx` with:

```tsx
import { useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { MAX_AMOUNT_TEXT, MAX_CATEGORY, MAX_NOTE, parseAmountInput } from "./money";
import * as moneyApi from "../../api/money";
import { describeError } from "../../api/client";

export interface ExpenseAddFormProps {
  projects: readonly string[]; // offered as suggestions; a new name makes a new project
  onAdded: () => void;
}

// Amount accepts the comma decimal a Spanish user types ("12,50"); anything
// ambiguous is refused here, before the gateway (which checks again).
export function ExpenseAddForm({ projects, onAdded }: ExpenseAddFormProps) {
  const [amount, setAmount] = useState("");
  const [project, setProject] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    const parsed = parseAmountInput(amount);
    if (parsed === null) {
      setError("Enter an amount like 12,50.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await moneyApi.createExpense({ amount: parsed, project: project.trim() || undefined, note: note.trim() || undefined });
      setAmount("");
      setNote("");
      onAdded();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="expense-add" onSubmit={(event) => { event.preventDefault(); void submit(); }}>
      <input className="input" aria-label="Amount" inputMode="decimal" placeholder="€ 12,50" value={amount}
        maxLength={MAX_AMOUNT_TEXT} onChange={(e) => setAmount(e.target.value)} />
      <input className="input" aria-label="Project" placeholder="Project" value={project} list="expense-projects"
        maxLength={MAX_CATEGORY} onChange={(e) => setProject(e.target.value)} />
      <datalist id="expense-projects">
        {projects.map((name) => <option key={name} value={name} />)}
      </datalist>
      <input className="input" aria-label="Note" placeholder="What was it?" value={note}
        maxLength={MAX_NOTE} onChange={(e) => setNote(e.target.value)} />
      <button type="submit" className="btn btn--primary" disabled={busy}>Add expense</button>
      {error ? <ErrorNotice message={error} /> : null}
    </form>
  );
}
```

**7d.** `web/src/components/board/MoneyBoard.tsx`. Find:

```tsx
import type { CategoryTotalOut, ExpenseOut, MoneySummaryOut } from "../../api/types";
```

Replace with:

```tsx
import type { ExpenseOut, MoneySummaryOut, ProjectTotalOut } from "../../api/types";
```

Find:

```tsx
function BudgetCell({ row, money }: { row: CategoryTotalOut; money: (amount: string) => string }) {
```

Replace with:

```tsx
function BudgetCell({ row, money }: { row: ProjectTotalOut; money: (amount: string) => string }) {
```

Find:

```tsx
function CategoryTable({ summary }: { summary: MoneySummaryOut }) {
  const money = (amount: string) => formatMoney(amount, summary.currency);
  return (
    <table className="money-table" aria-label="By category">
      <thead><tr><th scope="col">Category</th><th scope="col">Spent</th><th scope="col">Budget</th></tr></thead>
      <tbody>
        {summary.by_category.map((row) => (
          <tr key={row.category}>
            <th scope="row">{row.category}</th>
```

Replace with:

```tsx
function ProjectTable({ summary }: { summary: MoneySummaryOut }) {
  const money = (amount: string) => formatMoney(amount, summary.currency);
  return (
    <table className="money-table" aria-label="By project">
      <thead><tr><th scope="col">Project</th><th scope="col">Spent</th><th scope="col">Budget</th></tr></thead>
      <tbody>
        {summary.by_project.map((row) => (
          <tr key={row.project}>
            <th scope="row">{row.project}</th>
```

Find:

```tsx
            <span className="expense-row__category">{e.category}</span>
            {e.description ? <span className="expense-row__note">{e.description}</span> : null}
            <MadeByChip botId={e.created_by_bot} />
            {e.tainted ? <WebContentChip what={`the ${e.category} expense`} onKeep={() => onKeep(e.id)} /> : null}
```

Replace with:

```tsx
            <span className="expense-row__project">{e.project}</span>
            {e.description ? <span className="expense-row__note">{e.description}</span> : null}
            <MadeByChip botId={e.created_by_bot} />
            {e.tainted ? <WebContentChip what={`the ${e.project} expense`} onKeep={() => onKeep(e.id)} /> : null}
```

Find:

```tsx
      {summary.by_category.length > 0 ? <CategoryTable summary={summary} /> : null}
```

Replace with:

```tsx
      {summary.by_project.length > 0 ? <ProjectTable summary={summary} /> : null}
```

Find:

```tsx
        <ExpenseAddForm categories={shown ? shown.summary.by_category.map((row) => row.category) : []} onAdded={load} />
```

Replace with:

```tsx
        <ExpenseAddForm projects={shown ? shown.summary.by_project.map((row) => row.project) : []} onAdded={load} />
```

**7e.** `web/src/components/profile/DocumentsTab.tsx`. Find:

```tsx
        items={made.expenses.map((e) => ({ id: e.id, label: `${e.amount} ${e.currency} · ${e.category}`, tainted: e.tainted }))} />
```

Replace with:

```tsx
        items={made.expenses.map((e) => ({ id: e.id, label: `${e.amount} ${e.currency} · ${e.project}`, tainted: e.tainted }))} />
```

**7f.** `web/src/styles/board.css`. Find:

```css
.expense-row__category {
```

Replace with:

```css
.expense-row__project {
```

Find:

```css
  /* Amount and Category share a row; Note, then Add, below. */
```

Replace with:

```css
  /* Amount and Project share a row; Note, then Add, below. */
```

**7g.** `web/e2e/records.spec.ts`. Find:

```ts
  // The "By category" table sums every bot's food, so check Life admin's own expense row.
```

Replace with:

```ts
  // The "By project" table sums every bot's food, so check Life admin's own expense row.
```

`web/e2e/fixtures/team-script.json` keeps its `"category": "food"` arguments to `log_expense`: the alias reads them as `project`, and the stuck flow owns the end of that file.

- [ ] **Step 8: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_money_store.py tests/test_money_tools.py tests/test_money_api.py tests/test_vocabulary.py -q`
Expected: PASS, 31 passed (store 7, tools 15, of which the parametrized test is 4, API 5, vocabulary 4).

Run the files that build the money service, log expenses or read the money tools:
`cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_money_values.py tests/test_profile_api.py tests/test_tool_text.py tests/test_document_tools.py tests/test_every_bot_tools.py tests/test_main_bot.py tests/test_task_tools.py tests/test_gate.py tests/test_instructions.py tests/test_tool_runner_taint.py -q`
Expected: PASS.

Nothing may still use the old names. `README.md` is the docs task's (Task 10), and `tasks.category` is the task's list, so neither is searched:
`cd /Users/blckit/Desktop/Code_Projects/roost && grep -rnE "CategoryStore|category_store|CategoryTotal|CategoryTable|category_id|by_category|category_for|GENERAL_CATEGORY_NAME|_category_name|_category_tainted|category_tainted|expense-row__category|expense-categories" roost tests web/src web/tests web/e2e --exclude-dir=__pycache__`
Expected: no output.

Run the full suite with the coverage gate:
`cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest --cov=roost --cov-fail-under=80 -q`
Expected: PASS.

Run the web tests, then the whole web suite, the type check and the bundle budget:
`cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npx vitest run tests/MoneyBoard.test.tsx tests/DocumentsTab.test.tsx`
Expected: PASS, 13 passed (MoneyBoard 11, DocumentsTab 2).

`cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npm test`
Expected: PASS.

`cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npm run build && npm run size`
Expected: PASS. `tsc -b` finds no `CategoryTotalOut`, `by_category` or `ExpenseOut.category` left, and the main bundle stays under `bundle-budget.json`.

- [ ] **Step 9: Commit**

`git mv` already staged the move of `roost/money/category_store.py`; `git add` stages the moved file's new content.

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && git add roost/constants.py roost/money/models.py roost/money/project_store.py roost/money/expense_store.py \
  roost/money/service.py roost/money/summary.py roost/money/format.py roost/money/tools.py \
  roost/money/tool_specs.py roost/tasks/tool_specs.py roost/gateway/routes/money.py roost/gateway/app.py \
  roost/talk/domain_tools.py \
  tests/test_money_store.py tests/test_money_tools.py tests/test_money_api.py tests/test_vocabulary.py \
  tests/test_profile_api.py tests/test_tool_text.py tests/test_document_tools.py tests/test_every_bot_tools.py \
  tests/live_shape.py \
  web/src/api/types.ts web/src/api/money.ts web/src/components/board/MoneyBoard.tsx \
  web/src/components/board/ExpenseAddForm.tsx web/src/components/profile/DocumentsTab.tsx \
  web/src/styles/board.css web/tests/MoneyBoard.test.tsx web/tests/DocumentsTab.test.tsx web/e2e/records.spec.ts
cd /Users/blckit/Desktop/Code_Projects/roost && git status --short
cd /Users/blckit/Desktop/Code_Projects/roost && git commit -m "refactor: category becomes project in the money code, tools, wire and Board (no behaviour change)"
```

Expected from `git status --short` before the commit: `roost/money/category_store.py -> roost/money/project_store.py` shown as a rename (`R`), every other file above as `M`, and nothing else staged.

---

### Task 2: Schema v13, the project fields, top-ups and deleting a project

Design P3, P5, P6 (project basics and top-ups), P8 and §5 H2, H4, H5, H9, H15 (the store side) and H16. Schema v13 is the Shared Contract's migration, word for word. The project table (`money_projects`) gets its new fields, and `ProjectStore` learns everything Task 6's `ProjectService` builds on:
- **The fields.** `Project` gains `color`, `start_date`, `due_date`, `monthly_budget` (`enc:v2`, AAD `money_projects:monthly_budget`), `lead_bot_id` and `status`. `ProjectDraft` and `ProjectPatch` check and tidy every value when they are built: a name is stripped and at most `MAX_CATEGORY_NAME_LENGTH`, a currency is upper-cased and must match `CURRENCY_PATTERN`, a colour is one of `PROJECT_COLORS`, a status is one of `PROJECT_STATUSES`, a date is a plain `YYYY-MM-DD` (`""` clears it), and amounts go through `parse_amount`. A project saved before v13 has no colour yet; it reads as `DEFAULT_PROJECT_COLOR`.
- **Names.** `find` looks a project up by its `name_key` and never creates one. `find_or_create` stays for `log_expense` (H3). A rename recomputes `name_key` with the same `_name_key`, and a clash with another live project is `ValueError("A project with that name exists.")`.
- **General (H2)** is the project whose `name_key` is the key of `GENERAL_PROJECT_NAME`. `is_general(project)` compares the folded names, which is the same test without the key. The store refuses to rename, archive or delete it, so the rule holds even if a caller forgets it. Task 6's service refuses every other change to General as well.
- **Both budgets (H4, H5).** The monthly limit is a plain field: set it, or clear it with `None`. The total budget changes only through `set_budget` and top-ups. Each change writes a `money_topups` row in the same transaction, which reads inside its own write session. While a total budget is set, `budget == Σ amount of the live top-up rows`:
  - `create` with a total budget writes a "Budget set" row (`edit`, no `topup_id`), so the history holds the budget from the start;
  - `set_budget(None)` writes an `edit` row of −budget, then sets `budget` to NULL;
  - `add_topup` writes a `credit` row and raises the budget;
  - `edit_topup` takes the top-up's **new** amount and writes an `edit` row of the difference, with `topup_id` = the credit;
  - `undo_topup` sets `deleted_at` on the credit and its edits, and lowers the budget by their sum.
- **Two refusals the design does not spell out** keep the invariant meaningful. A top-up can't be changed or undone while the total budget is cleared, and no change may take the total budget below 0.
- **Currency (H7, the store's half).** `has_money` is true when the project has an expense that is not deleted (void ones count) or a live top-up credit. A budget alone is not money: when the currency changes, its "Budget set" rows follow. The store checks the rule inside the same transaction as the update, so it can't race.
- **Delete (H9)** is one transaction: General is found or made, the expenses move to it, `project_id` becomes NULL on the user's tasks, notes and documents (their revision and `updated_at` stay), and `deleted_at` is set. General itself is refused.
- **The lead bot (H15)** is cleared by `ON DELETE SET NULL` when the bot is retired (`BotStore.delete` is a real `DELETE`). A lead bot id that does not exist is refused by the foreign key. Checking that the bot is the user's own is the service's job (Task 6).

`project_store.py` keeps every method of the contract (Task 6's path guard greps for them there). The SQL of the budget history lives in the new `roost/money/topup_store.py` (about 145 lines), which keeps `project_store.py` at about 460 lines, well under the 800 limit.

Snippets marked **(after the stuck flow)** are written against the state after the whole stuck-flow plan. That plan's only edit to `roost/db/migrations.py` is its Task 3 (v12, already committed), and it adds its constants at the end of `roost/constants.py`. Neither touches the lines found here. Snippets marked **(after Task 1)** are written against Task 1's Category → Project rename.

**Files:**
- Create:
  - `tests/fixtures/schema_v12.sql` (generated in Step 2, **before** `migrations.py` changes)
  - `roost/money/topup_store.py`
- Modify:
  - `roost/db/migrations.py` (`Migration(13, "projects hub", ...)`, appended after v12)
  - `roost/constants.py` (the projects hub constants, in the Finance section)
  - `roost/money/models.py` (`Project`'s new fields, `ProjectDraft`, `PROJECT_PATCHABLE`, `ProjectPatch`, `TopUp`, `TOPUP_CREDIT`, `TOPUP_EDIT`)
  - `roost/money/project_store.py` (whole file: `find`, `list(include_archived)`, `create`, `update`, `set_budget(None)`, the top-up methods, `has_money`, `delete`, `is_general`)
  - `tests/test_money_store.py` (one test: `add_topup` now returns a `TopUp`)
- Test:
  - `tests/test_migrations_v12.py` (new), `tests/test_project_store.py` (new), `tests/test_money_store.py`

No test pins schema version 12: `tests/test_migrations_v11.py` already asserts `latest_version() >= 12`, and the older migration tests compare with `latest_version()`. Step 6 checks this with a grep.

**Interfaces:**
- Consumes:
  - **Task 1:**
    - `roost/money/project_store.py` (replaced whole here), with `_name_key`, `_row_to_project`, `_aad` and `_COLUMNS`;
    - `Project` and `ExpenseDraft(project_id, amount, ...)` (`roost/money/models.py`), and `Expense.project_id`;
    - `GENERAL_PROJECT_NAME` (`roost/constants.py`).
  - **Existing:**
    - `MAX_CATEGORY_NAME_LENGTH`, `CURRENCY_PATTERN` and `DEFAULT_CURRENCY`;
    - `parse_amount`, `amount_text` and `CENT` (`roost/money/amounts.py`);
    - `encrypt`, `encrypt_field`, `decrypt_field`, `user_aad`, `get_user_dek` and `db_session`;
    - `AddColumn` and `Migration` (`roost/db/migrations.py`);
    - `BotStore.delete`, `TaskStore.create`, `NoteStore.create` / `get`, `DocumentStore.create` / `get_meta`, `doc_from_markdown` and `ExpenseStore` (tests only);
    - `register_user`, `team_helpers.make_bot`, and `test_migrations_v10._ROWS` / `_EXPECTED` and `test_migrations_v8._NOW` (tests only).
- Produces (later tasks rely on these exact names):
  - **Schema v13**, exactly the Shared Contract's migration, and `tests/fixtures/schema_v12.sql`.
  - **`roost/constants.py`** (Finance section): `PROJECT_STATUSES`, `PROJECT_COLORS`, `DEFAULT_PROJECT_COLOR`, `BUDGET_WARN_PERCENT`, `BUDGET_OVER_PERCENT`, `PROJECT_LIST_LIMIT`, `PROJECT_PAGE_ITEMS` and `TOPUP_SOURCE_MAX_CHARS`. The last one stands alone on its line, `TOPUP_SOURCE_MAX_CHARS = 120`, for Task 6's anchor.
  - **`roost/money/models.py`:**
    - `Project` gains `color: str`, `start_date: str | None`, `due_date: str | None`, `monthly_budget: Decimal | None`, `lead_bot_id: str | None` and `status: str`. They come after `tainted`, in that order, and have no defaults.
    - `ProjectDraft(name, currency=DEFAULT_CURRENCY, budget=None, monthly_budget=None, color=DEFAULT_PROJECT_COLOR, start_date=None, due_date=None, lead_bot_id=None)` checks and tidies every field (a `ValueError` with a plain sentence).
    - `PROJECT_PATCHABLE` (the contract's eight keys). `ProjectPatch(changes)` refuses other keys (`"Projects have no field …."`), checks and tidies the values, and freezes `changes` as a `MappingProxyType`.
    - `TopUp(id, project_id, amount, currency, source, kind, topup_id, undone, created_at, created_by_bot, tainted)`, plus `TOPUP_CREDIT = "credit"` and `TOPUP_EDIT = "edit"`.
    - The texts `PROJECT_NAME_TEXT`, `CURRENCY_TEXT`, `COLOR_TEXT` (it lists the palette; Task 7's `read_color` and Task 8's routes refuse with it too), `STATUS_TEXT` (`"A project is either active or archived."`; Task 6's service re-exports it, with `LEAD_BOT_TEXT`), `DATE_TEXT` and `LEAD_BOT_TEXT`.
  - **`roost/money/project_store.py`:**
    - `ProjectStore(config)` with exactly the contract's methods. `list` defaults to `include_archived=True`, so the money summary keeps seeing every project. `add_topup` returns a `TopUp`; for a project that isn't the user's live project it raises `ValueError("No such project.")` (Task 6 checks first, so this only happens in a race).
    - `edit_topup` returns the `edit` row it wrote, or the credit unchanged when the amount is already that. `undo_topup` returns the credit with `undone=True`. Both return `None` when the id is not one of the user's credits on a live project.
    - `topups` lists the history newest first, undone rows included.
    - Module function `is_general(project) -> bool` (the contract allows a module function; it needs no key).
    - The texts `NAME_TAKEN_TEXT` (`"A project with that name exists."`, Task 8's 409), `GENERAL_KEPT_TEXT`, `CURRENCY_LOCKED_TEXT` (Task 6's service re-exports it), `LEAD_BOT_GONE_TEXT` and `PROJECT_GONE_TEXT`.
    - `find_or_create(user_id, name, *, created_by_bot, tainted)` and `keep(user_id, project_id)` keep their signatures.
  - **`roost/money/topup_store.py`:**
    - `TopUpUndone(ValueError)` with `TOPUP_UNDONE_TEXT`, the 409 of the route table. `edit_topup` and `undo_topup` raise it through their first call, `_credit_and_project` (in `project_store.py`, above the class), so a grep of their own bodies for `raise ValueError` finds only their `return None`. Grep for `TopUpUndone` instead.
    - `BUDGET_CLEARED_TEXT` and `BELOW_ZERO_TEXT`: plain `ValueError`s (`moved_budget`) for a broken rule, not a conflict, so a route can answer them 422 by catching `TopUpUndone` first.
    - The helpers `ProjectStore` uses: `LedgerRow`, `row_to_topup`, `moved_budget`, `add_row`, `credit`, `live_total`, `mark_undone`, `history_rows` and `set_currency`.

- [ ] **Step 1: Path guard**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

Then confirm that the stuck flow and Task 1 have landed, and that this task has not:

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && test -f roost/money/project_store.py && test ! -e tests/fixtures/schema_v12.sql && grep -n "^GENERAL_PROJECT_NAME\|^PROJECT_STATUSES" roost/constants.py && grep -n "Migration(1[23]," roost/db/migrations.py`
Expected: two lines, `GENERAL_PROJECT_NAME = "General"` and `    Migration(12, "stuck cards", (`. If a test fails, a line is missing, or `PROJECT_STATUSES` / `Migration(13,` shows up, stop: Task 1 comes first, or this task already ran.

- [ ] **Step 2: Freeze the current schema (v12), then write the failing tests**

**2a. Freeze schema v12.** This must run **before** `roost/db/migrations.py` changes. The script builds a throwaway database in `$TMPDIR`, never in `~/Roost/data`:

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && uv run python - <<'PY'
import asyncio, sqlite3, tempfile
from pathlib import Path
import aiosqlite
from roost.db.migrations import apply_migrations, latest_version

assert latest_version() == 12, f"expected schema v12 before the projects hub, got {latest_version()}"

async def build(path: Path) -> None:
    async with aiosqlite.connect(path) as db:
        await db.executescript(Path("roost/db/schema.sql").read_text())
        await db.commit()
        await apply_migrations(db)

path = Path(tempfile.mkdtemp(prefix="roost-v12-")) / "v12.db"
asyncio.run(build(path))
con = sqlite3.connect(path)
rows = con.execute(
    "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY rowid"
).fetchall()
con.close()
header = ("-- Roost schema version 12, frozen by projects-hub Task 2 (schema.sql + migrations 1-12).\n"
          "-- The live ~/Roost/data/roost.db runs this schema at the start of the projects hub. Never edit.\n\n")
Path("tests/fixtures/schema_v12.sql").write_text(header + ";\n\n".join(r[0] for r in rows) + ";\n")
print("tables/indexes:", len(rows))
PY
grep -c "CREATE" tests/fixtures/schema_v12.sql        # 42
grep -c "stuck_cards" tests/fixtures/schema_v12.sql   # 6
grep -c "topup_id" tests/fixtures/schema_v12.sql      # 0
diff <(sed 1,3d tests/fixtures/schema_v11.sql) <(sed 1,3d tests/fixtures/schema_v12.sql)
```

Expected:
- The script prints `tables/indexes: 42`.
- The three greps print `42`, `6` and `0`.
- The file starts with exactly these lines:

```sql
-- Roost schema version 12, frozen by projects-hub Task 2 (schema.sql + migrations 1-12).
-- The live ~/Roost/data/roost.db runs this schema at the start of the projects hub. Never edit.

CREATE TABLE users (
```

- The `diff` shows one added block only, `281a282,304`: an empty line, then the `CREATE TABLE stuck_cards (` statement and its two indexes, `idx_stuck_cards_one_open` and `idx_stuck_cards_user`. Nothing is removed or changed. (`diff` exits with status 1 because the files differ; that is expected.)

**2b. The migration test from v12, with rows.** Create `tests/test_migrations_v12.py`:

```python
"""Migrating from the schema the live gateway runs at the start of the projects hub (version 12).

``tests/fixtures/schema_v12.sql`` was frozen by projects-hub Task 2. Rows go in
every table the user's account uses today (the v10 test's rows and a Stuck
card). v13 only adds: a project's colour, dates, monthly limit and lead bot,
an expense's step and star, a top-up's link to the credit it changes, and an
optional project on tasks, notes and documents."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.db.migrations import latest_version
from test_migrations_v10 import _EXPECTED as _V10_EXPECTED
from test_migrations_v10 import _ROWS as _V10_ROWS
from test_migrations_v8 import _NOW

_V12_SCHEMA = Path(__file__).parent / "fixtures" / "schema_v12.sql"
_ROWS = (
    *_V10_ROWS,
    "INSERT INTO stuck_cards (id, user_id, bot_id, thread_id, reason, url, request, state, created_at) "
    f"VALUES ('c1','u1','b2','t1','login','enc:u','enc:r','open','{_NOW}')",
)
_EXPECTED = {**_V10_EXPECTED, "stuck_cards": 1}
_NEW_COLUMNS = {
    "money_projects": {"color", "start_date", "due_date", "monthly_budget", "lead_bot_id"},
    "money_expenses": {"step_id", "is_favorite"},
    "money_topups": {"topup_id"},
    "tasks": {"project_id", "allocated_budget"},
    "notes": {"project_id"},
    "documents": {"project_id"},
}
_NEW_INDEXES = {"idx_tasks_user_project", "idx_notes_user_project", "idx_documents_user_project"}
_LINKED = ("tasks", "notes", "documents")


def _query(db_path: Path, sql: str, params: tuple = ()) -> list[tuple]:
    con = sqlite3.connect(db_path)
    try:
        return con.execute(sql, params).fetchall()
    finally:
        con.close()


def _version(db_path: Path) -> int:
    return _query(db_path, "PRAGMA user_version")[0][0]


def _counts(db_path: Path) -> dict[str, int]:
    return {table: _query(db_path, f"SELECT COUNT(*) FROM {table}")[0][0] for table in _EXPECTED}


def _connect(db_path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA foreign_keys = ON")
    return con


@pytest.fixture
def seeded_v12():
    cfg = load_config()
    db_path = get_db_path(cfg)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        con.executescript(_V12_SCHEMA.read_text())
        con.execute("PRAGMA user_version = 12")
        for statement in _ROWS:
            con.execute(statement)
        con.commit()
    finally:
        con.close()
    return cfg, db_path


async def test_v12_database_migrates_to_latest_and_keeps_every_row(seeded_v12):
    cfg, db_path = seeded_v12
    await init_db(cfg)
    assert latest_version() >= 13
    assert _version(db_path) == latest_version()
    assert _counts(db_path) == _EXPECTED


async def test_v12_database_gains_the_project_columns_and_indexes(seeded_v12):
    cfg, db_path = seeded_v12
    await init_db(cfg)
    for table, columns in _NEW_COLUMNS.items():
        assert columns <= {row[1] for row in _query(db_path, f"PRAGMA table_info({table})")}, table
    indexes = {row[0] for row in _query(db_path, "SELECT name FROM sqlite_master WHERE type = 'index'")}
    assert _NEW_INDEXES <= indexes


async def test_existing_rows_keep_their_meaning(seeded_v12):
    cfg, db_path = seeded_v12
    await init_db(cfg)
    assert _query(db_path, "SELECT color, start_date, due_date, monthly_budget, lead_bot_id, status "
                           "FROM money_projects") == [(None, None, None, None, None, "active")]
    assert _query(db_path, "SELECT step_id, is_favorite, status FROM money_expenses") == [(None, 0, "posted")]
    assert _query(db_path, "SELECT kind, topup_id FROM money_topups") == [("credit", None)]
    assert _query(db_path, "SELECT project_id, allocated_budget FROM tasks") == [(None, None), (None, None)]
    for table in ("notes", "documents"):
        assert _query(db_path, f"SELECT project_id FROM {table}") == [(None,)]


async def test_a_projects_lead_bot_is_cleared_when_the_bot_goes(seeded_v12):
    cfg, db_path = seeded_v12
    await init_db(cfg)
    con = _connect(db_path)
    try:
        con.execute("UPDATE money_projects SET lead_bot_id = 'b2' WHERE id = 'p1'")
        con.execute("DELETE FROM bots WHERE id = 'b2'")
        assert con.execute("SELECT id, lead_bot_id FROM money_projects").fetchall() == [("p1", None)]
    finally:
        con.close()


async def test_items_lose_a_project_whose_row_goes_and_never_name_a_missing_one(seeded_v12):
    cfg, db_path = seeded_v12
    await init_db(cfg)
    con = _connect(db_path)
    try:
        for table in _LINKED:
            con.execute(f"UPDATE {table} SET project_id = 'p1'")
            with pytest.raises(sqlite3.IntegrityError):
                con.execute(f"UPDATE {table} SET project_id = 'no-such-project'")
        con.execute("DELETE FROM money_projects WHERE id = 'p1'")
        for table in _LINKED:
            assert {row[0] for row in con.execute(f"SELECT project_id FROM {table}")} == {None}, table
        assert con.execute("SELECT COUNT(*) FROM tasks").fetchone() == (2,)
    finally:
        con.close()


async def test_migrating_v12_twice_is_a_no_op_and_backs_up_once(seeded_v12):
    cfg, db_path = seeded_v12
    await init_db(cfg)
    await init_db(cfg)
    assert _counts(db_path) == _EXPECTED
    [backup] = sorted(db_path.parent.glob(f"roost.db.pre-v{latest_version()}-*.bak"))
    assert _version(backup) == 12
```

**2c. The store.** Create `tests/test_project_store.py`:

```python
"""Projects (projects hub Task 2: H2, H4, H5, H9, H15, H16): the new fields,
renaming, archiving, both budgets, top-ups and their history, and deleting a
project. Encrypted, per user, and ``budget == Σ live top-up rows`` while a
total budget is set."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from roost.bots.store import BotStore
from roost.config import load_config
from roost.constants import DEFAULT_PROJECT_COLOR, GENERAL_PROJECT_NAME, PROJECT_COLORS
from roost.db.connection import db_session, init_db
from roost.documents.doc_markdown import doc_from_markdown
from roost.documents.models import DocumentDraft
from roost.documents.store import DocumentStore
from roost.gateway.auth import register_user
from roost.money.expense_store import ExpenseStore
from roost.money.models import ExpenseDraft, ProjectDraft, ProjectPatch
from roost.money.project_store import ProjectStore, is_general
from roost.money.topup_store import TopUpUndone
from roost.notes.models import NoteDraft
from roost.notes.store import NoteStore
from roost.tasks.models import TaskDraft
from roost.tasks.store import TaskStore
from team_helpers import make_bot


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


@pytest.fixture
def store(cfg) -> ProjectStore:
    return ProjectStore(cfg)


async def _create(store, user_id, name="Renovation", **fields):
    return await store.create(user_id, ProjectDraft(name=name, **fields), created_by_bot=None, tainted=False)


async def _topup(store, user_id, project_id, amount, source=None):
    return await store.add_topup(user_id, project_id, Decimal(amount), source, created_by_bot=None, tainted=False)


async def _live_total(store, user_id, project_id) -> Decimal:
    """Σ amount of the live top-up rows: what H4 says the total budget equals."""
    return sum((row.amount for row in await store.topups(user_id, project_id) if not row.undone), Decimal("0"))


async def _raw(cfg, sql, params=()):
    async with db_session(cfg) as db:
        return [tuple(row) for row in await (await db.execute(sql, params)).fetchall()]


async def test_the_new_fields_read_back_and_the_monthly_budget_is_ciphertext(cfg, store, user_id):
    lead = await make_bot(cfg, user_id, "Fixer")
    made = await _create(store, user_id, " Renovation ", currency="usd", budget=Decimal("500"),
                         monthly_budget=Decimal("120.5"), color=PROJECT_COLORS[4], start_date="2026-10-01",
                         due_date="2026-12-31", lead_bot_id=lead.id)
    again = await store.get(user_id, made.id)
    assert again == made
    assert (again.name, again.currency, again.budget, again.monthly_budget) == (
        "Renovation", "USD", Decimal("500.00"), Decimal("120.50"))
    assert (again.color, again.start_date, again.due_date, again.lead_bot_id, again.status) == (
        PROJECT_COLORS[4], "2026-10-01", "2026-12-31", lead.id, "active")
    [(name, budget, monthly, color, start, due, lead_id, status)] = await _raw(
        cfg, "SELECT name, budget, monthly_budget, color, start_date, due_date, lead_bot_id, status "
             "FROM money_projects WHERE id = ?", (made.id,))
    assert all(value.startswith("enc:v2:") for value in (name, budget, monthly))
    assert "120.50" not in monthly
    assert (color, start, due, lead_id, status) == (PROJECT_COLORS[4], "2026-10-01", "2026-12-31", lead.id, "active")


async def test_a_new_project_starts_active_in_the_first_colour_with_no_budget_rows(store, user_id):
    made = await _create(store, user_id)
    assert (made.color, made.status, made.budget, made.monthly_budget, made.currency) == (
        DEFAULT_PROJECT_COLOR, "active", None, None, "EUR")
    assert await store.topups(user_id, made.id) == ()
    food = await store.find_or_create(user_id, "Food", created_by_bot=None, tainted=False)
    assert (food.color, food.status) == (DEFAULT_PROJECT_COLOR, "active")


async def test_a_project_saved_before_v13_reads_with_the_default_colour(cfg, store, user_id):
    made = await _create(store, user_id)
    async with db_session(cfg) as db:
        await db.execute("UPDATE money_projects SET color = NULL WHERE id = ?", (made.id,))
        await db.commit()
    assert (await store.get(user_id, made.id)).color == DEFAULT_PROJECT_COLOR


async def test_find_never_creates_and_ignores_case_and_spacing(store, user_id):
    assert await store.find(user_id, "Renovation") is None
    assert await store.find(user_id, "   ") is None
    assert await store.list(user_id) == ()
    made = await _create(store, user_id)
    assert (await store.find(user_id, "  renovation ")).id == made.id
    assert await store.find(user_id, "Renov") is None
    assert [project.id for project in await store.list(user_id)] == [made.id]


async def test_a_name_in_use_is_refused(store, user_id):
    await _create(store, user_id)
    with pytest.raises(ValueError, match="A project with that name exists."):
        await _create(store, user_id, "RENOVATION")
    assert len(await store.list(user_id)) == 1


@pytest.mark.parametrize(("fields", "message"), [
    ({"name": "  "}, "needs a name"),
    ({"name": "x" * 41}, "needs a name"),
    ({"currency": "euro"}, "three-letter code"),
    ({"color": "#123456"}, "palette"),
    ({"start_date": "next week"}, "YYYY-MM-DD"),
    ({"due_date": "20261231"}, "YYYY-MM-DD"),
    ({"budget": Decimal("0")}, "more than 0"),
    ({"monthly_budget": Decimal("1.234")}, "at most 2 decimals"),
    ({"lead_bot_id": "  "}, "one of your bots"),
])
def test_a_draft_checks_every_field(fields, message):
    with pytest.raises(ValueError, match=message):
        ProjectDraft(**{"name": "Renovation", **fields})


def test_a_patch_takes_only_the_patchable_fields_and_tidies_them():
    with pytest.raises(ValueError, match="Projects have no field budget, created_at."):
        ProjectPatch({"budget": Decimal("5"), "created_at": "now"})
    with pytest.raises(ValueError, match="either active or archived"):
        ProjectPatch({"status": "done"})
    with pytest.raises(ValueError, match="needs a name"):
        ProjectPatch({"name": None})
    patch = ProjectPatch({"name": " Home ", "currency": "usd", "color": PROJECT_COLORS[2].upper(),
                          "due_date": "", "monthly_budget": "80,5", "lead_bot_id": None})
    assert dict(patch.changes) == {"name": "Home", "currency": "USD", "color": PROJECT_COLORS[2], "due_date": None,
                                   "monthly_budget": Decimal("80.50"), "lead_bot_id": None}
    with pytest.raises(TypeError):
        patch.changes["name"] = "Other"


async def test_rename_recomputes_the_name_key_and_a_clash_is_refused(cfg, store, user_id):
    food = await _create(store, user_id, "Food")
    await _create(store, user_id, "Travel")
    [(old_key,)] = await _raw(cfg, "SELECT name_key FROM money_projects WHERE id = ?", (food.id,))
    renamed = await store.update(user_id, food.id, ProjectPatch({"name": "Groceries"}))
    assert renamed.name == "Groceries"
    [(new_key,)] = await _raw(cfg, "SELECT name_key FROM money_projects WHERE id = ?", (food.id,))
    assert new_key != old_key
    assert (await store.find(user_id, "groceries")).id == food.id
    assert await store.find(user_id, "Food") is None
    with pytest.raises(ValueError, match="A project with that name exists."):
        await store.update(user_id, food.id, ProjectPatch({"name": " travel "}))
    assert (await store.get(user_id, food.id)).name == "Groceries"
    assert (await _create(store, user_id, "Food")).id != food.id     # the old name is free again


async def test_archiving_keeps_a_project_findable_and_out_of_the_active_list(store, user_id):
    house = await _create(store, user_id, "House")
    trip = await _create(store, user_id, "Trip")
    archived = await store.update(user_id, house.id, ProjectPatch({"status": "archived"}))
    assert archived.status == "archived"
    assert [project.id for project in await store.list(user_id, include_archived=False)] == [trip.id]
    assert [project.id for project in await store.list(user_id)] == [house.id, trip.id]
    assert (await store.find(user_id, "house")).status == "archived"
    assert (await store.update(user_id, house.id, ProjectPatch({"status": "active"}))).status == "active"
    assert len(await store.list(user_id, include_archived=False)) == 2


async def test_update_sets_and_clears_the_plain_fields_and_the_monthly_limit(cfg, store, user_id):
    lead = await make_bot(cfg, user_id, "Fixer")
    house = await _create(store, user_id, "House", monthly_budget=Decimal("100"))
    changed = await store.update(user_id, house.id, ProjectPatch({
        "color": PROJECT_COLORS[8], "start_date": "2026-11-01", "due_date": "2027-01-31", "lead_bot_id": lead.id,
        "monthly_budget": Decimal("150"),
    }))
    assert (changed.color, changed.start_date, changed.due_date, changed.lead_bot_id, changed.monthly_budget) == (
        PROJECT_COLORS[8], "2026-11-01", "2027-01-31", lead.id, Decimal("150.00"))
    cleared = await store.update(user_id, house.id, ProjectPatch({
        "start_date": None, "due_date": "", "lead_bot_id": None, "monthly_budget": None,
    }))
    assert (cleared.start_date, cleared.due_date, cleared.lead_bot_id, cleared.monthly_budget) == (
        None, None, None, None)
    assert await _raw(cfg, "SELECT monthly_budget FROM money_projects WHERE id = ?", (house.id,)) == [(None,)]
    assert await store.update(user_id, house.id, ProjectPatch({})) == cleared
    assert await store.update(user_id, "no-such-project", ProjectPatch({"color": PROJECT_COLORS[1]})) is None


async def test_a_lead_bot_that_does_not_exist_is_refused(store, user_id):
    with pytest.raises(ValueError, match="The lead bot must be one of your bots."):
        await _create(store, user_id, lead_bot_id="no-such-bot")
    assert await store.find(user_id, "Renovation") is None
    house = await _create(store, user_id, "House")
    with pytest.raises(ValueError, match="The lead bot must be one of your bots."):
        await store.update(user_id, house.id, ProjectPatch({"lead_bot_id": "no-such-bot"}))
    assert (await store.get(user_id, house.id)).lead_bot_id is None


async def test_the_lead_bot_is_cleared_when_the_bot_is_retired(cfg, store, user_id):
    lead = await make_bot(cfg, user_id, "Fixer")
    house = await _create(store, user_id, "House", lead_bot_id=lead.id)
    assert await BotStore(cfg).delete(user_id, lead.id) is True
    kept = await store.get(user_id, house.id)
    assert (kept.name, kept.lead_bot_id) == ("House", None)


async def test_clearing_the_total_budget_writes_an_edit_row_of_minus_the_budget(store, user_id):
    house = await _create(store, user_id, "House", budget=Decimal("300"))
    cleared = await store.set_budget(user_id, house.id, None, created_by_bot=None, tainted=False)
    assert cleared.budget is None and (await store.get(user_id, house.id)).budget is None
    history = await store.topups(user_id, house.id)
    assert [(row.kind, row.amount, row.topup_id) for row in history] == [
        ("edit", Decimal("-300.00"), None), ("edit", Decimal("300.00"), None)]
    assert await _live_total(store, user_id, house.id) == Decimal("0")
    again = await store.set_budget(user_id, house.id, None, created_by_bot=None, tainted=False)
    assert again.budget is None and len(await store.topups(user_id, house.id)) == 2
    reset = await store.set_budget(user_id, house.id, Decimal("80"), created_by_bot=None, tainted=False)
    assert reset.budget == Decimal("80.00") == await _live_total(store, user_id, house.id)
    same = await store.set_budget(user_id, house.id, Decimal("80.00"), created_by_bot=None, tainted=False)
    assert same.budget == Decimal("80.00") and len(await store.topups(user_id, house.id)) == 3   # no +0.00 row


async def test_a_top_up_is_a_credit_row_that_raises_the_budget(cfg, store, user_id):
    bot = await make_bot(cfg, user_id, "Fixer")
    house = await _create(store, user_id, "House", budget=Decimal("200"))
    topup = await store.add_topup(user_id, house.id, Decimal("50"), "birthday", created_by_bot=bot.id, tainted=True)
    assert (topup.kind, topup.amount, topup.currency, topup.source, topup.topup_id, topup.undone) == (
        "credit", Decimal("50.00"), "EUR", "birthday", None, False)
    assert (topup.project_id, topup.created_by_bot, topup.tainted) == (house.id, bot.id, True)
    budget = (await store.get(user_id, house.id)).budget
    assert budget == Decimal("250.00") == await _live_total(store, user_id, house.id)
    [(amount, source)] = await _raw(cfg, "SELECT amount, source FROM money_topups WHERE id = ?", (topup.id,))
    assert amount.startswith("enc:v2:") and source.startswith("enc:v2:") and "birthday" not in source
    assert (await store.topups(user_id, house.id))[0] == topup


async def test_editing_a_top_up_writes_the_difference_and_keeps_the_invariant(store, user_id):
    house = await _create(store, user_id, "House", budget=Decimal("100"))
    credit = await _topup(store, user_id, house.id, "40", "bonus")
    up = await store.edit_topup(user_id, credit.id, Decimal("55"))
    assert (up.kind, up.amount, up.topup_id, up.source) == ("edit", Decimal("15.00"), credit.id, None)
    down = await store.edit_topup(user_id, credit.id, Decimal("30"))
    assert (down.kind, down.amount, down.topup_id) == ("edit", Decimal("-25.00"), credit.id)
    budget = (await store.get(user_id, house.id)).budget
    assert budget == Decimal("130.00") == await _live_total(store, user_id, house.id)
    same = await store.edit_topup(user_id, credit.id, Decimal("30"))
    assert same == credit and len(await store.topups(user_id, house.id)) == 4
    assert await store.edit_topup(user_id, "no-such-top-up", Decimal("5")) is None
    assert await store.edit_topup(user_id, up.id, Decimal("5")) is None      # only a credit can be changed


async def test_undoing_an_edited_top_up_removes_it_and_its_edits(store, user_id):
    house = await _create(store, user_id, "House")
    await store.set_budget(user_id, house.id, Decimal("300"), created_by_bot=None, tainted=False)
    kept = await _topup(store, user_id, house.id, "20", "gift")
    credit = await _topup(store, user_id, house.id, "50", "bonus")
    await store.edit_topup(user_id, credit.id, Decimal("80"))
    await store.edit_topup(user_id, credit.id, Decimal("70"))
    assert (await store.get(user_id, house.id)).budget == Decimal("390.00")

    undone = await store.undo_topup(user_id, credit.id)

    assert (undone.id, undone.kind, undone.amount, undone.undone) == (credit.id, "credit", Decimal("50.00"), True)
    budget = (await store.get(user_id, house.id)).budget
    assert budget == Decimal("320.00") == await _live_total(store, user_id, house.id)
    history = await store.topups(user_id, house.id)
    edits = {row.id for row in history if row.topup_id == credit.id}
    assert len(edits) == 2
    assert {row.id for row in history if row.undone} == {credit.id} | edits
    assert [row.id for row in history if row.kind == "credit" and not row.undone] == [kept.id]
    with pytest.raises(TopUpUndone, match="undone already"):
        await store.undo_topup(user_id, credit.id)
    with pytest.raises(TopUpUndone, match="undone already"):
        await store.edit_topup(user_id, credit.id, Decimal("10"))
    assert (await store.get(user_id, house.id)).budget == Decimal("320.00")


async def test_a_top_up_cannot_change_while_the_budget_is_cleared_or_take_it_below_zero(store, user_id):
    house = await _create(store, user_id, "House")
    credit = await _topup(store, user_id, house.id, "50")
    await store.set_budget(user_id, house.id, Decimal("10"), created_by_bot=None, tainted=False)
    with pytest.raises(ValueError, match="below 0"):
        await store.undo_topup(user_id, credit.id)
    with pytest.raises(ValueError, match="below 0"):
        await store.edit_topup(user_id, credit.id, Decimal("1"))
    await store.set_budget(user_id, house.id, None, created_by_bot=None, tainted=False)
    with pytest.raises(ValueError, match="budget is cleared"):
        await store.undo_topup(user_id, credit.id)
    with pytest.raises(ValueError, match="budget is cleared"):
        await store.edit_topup(user_id, credit.id, Decimal("60"))
    assert (await store.get(user_id, house.id)).budget is None
    assert await _live_total(store, user_id, house.id) == Decimal("0")
    assert not any(row.undone for row in await store.topups(user_id, house.id))


async def test_has_money_counts_expenses_and_top_ups_but_not_a_budget_alone(cfg, store, user_id):
    house = await _create(store, user_id, "House", budget=Decimal("100"))
    assert await store.has_money(user_id, house.id) is False
    credit = await _topup(store, user_id, house.id, "5")
    assert await store.has_money(user_id, house.id) is True
    await store.undo_topup(user_id, credit.id)
    assert await store.has_money(user_id, house.id) is False
    expenses = ExpenseStore(cfg)
    expense = await expenses.add(user_id, ExpenseDraft(house.id, Decimal("3"), spent_at="2026-10-13"),
                                 created_by_bot=None, tainted=False)
    assert await store.has_money(user_id, house.id) is True
    await expenses.delete(user_id, expense.id)
    assert await store.has_money(user_id, house.id) is False


async def test_the_currency_changes_only_while_the_project_has_no_money_and_the_budget_rows_follow(store, user_id):
    house = await _create(store, user_id, "House", budget=Decimal("100"))
    moved = await store.update(user_id, house.id, ProjectPatch({"currency": "USD"}))
    assert (moved.currency, moved.budget) == ("USD", Decimal("100.00"))
    assert [row.currency for row in await store.topups(user_id, house.id)] == ["USD"]
    await _topup(store, user_id, house.id, "5")
    with pytest.raises(ValueError, match="no expenses and no top-ups"):
        await store.update(user_id, house.id, ProjectPatch({"currency": "GBP"}))
    kept = await store.update(user_id, house.id, ProjectPatch({"currency": "USD", "color": PROJECT_COLORS[3]}))
    assert (kept.currency, kept.color) == ("USD", PROJECT_COLORS[3])


async def test_deleting_a_project_moves_its_expenses_to_general_and_unlinks_its_items(cfg, store, user_id):
    house = await _create(store, user_id, "House", budget=Decimal("100"))
    credit = await _topup(store, user_id, house.id, "10")
    expenses = ExpenseStore(cfg)
    lunch = await expenses.add(user_id, ExpenseDraft(house.id, Decimal("12.50"), spent_at="2026-10-13"),
                               created_by_bot=None, tainted=False)
    task = await TaskStore(cfg).create(user_id, TaskDraft(title="Buy tiles"), created_by_bot=None, tainted=False)
    note = await NoteStore(cfg).create(user_id, NoteDraft(title="Ideas", content="green tiles"),
                                       created_by_bot=None, tainted=False)
    body = json.dumps(doc_from_markdown("Plan", "- tiles"))
    document = await DocumentStore(cfg).create(user_id, DocumentDraft("doc", "Plan", body),
                                               created_by_bot=None, tainted=False)
    linked = (("tasks", task.id), ("notes", note.id), ("documents", document.id))
    async with db_session(cfg) as db:
        for table, row_id in linked:
            await db.execute(f"UPDATE {table} SET project_id = ? WHERE id = ?", (house.id, row_id))
        await db.commit()
    assert await store.find(user_id, GENERAL_PROJECT_NAME) is None

    assert await store.delete(user_id, house.id) is True

    general = await store.find(user_id, GENERAL_PROJECT_NAME)
    assert general is not None and is_general(general)
    assert (await expenses.get(user_id, lunch.id)).project_id == general.id
    for table, row_id in linked:
        assert await _raw(cfg, f"SELECT project_id, deleted_at FROM {table} WHERE id = ?", (row_id,)) == [
            (None, None)], table
    assert (await NoteStore(cfg).get(user_id, note.id)).revision == note.revision
    assert (await DocumentStore(cfg).get_meta(user_id, document.id)).revision == document.revision
    assert await store.get(user_id, house.id) is None
    assert await store.find(user_id, "House") is None
    assert [project.id for project in await store.list(user_id)] == [general.id]
    assert await store.undo_topup(user_id, credit.id) is None
    assert await store.delete(user_id, house.id) is False


async def test_deleting_uses_the_general_that_exists_and_frees_the_name(cfg, store, user_id):
    general = await store.find_or_create(user_id, GENERAL_PROJECT_NAME, created_by_bot=None, tainted=False)
    trip = await _create(store, user_id, "Trip")
    expense = await ExpenseStore(cfg).add(user_id, ExpenseDraft(trip.id, Decimal("9"), spent_at="2026-10-13"),
                                          created_by_bot=None, tainted=False)
    assert await store.delete(user_id, trip.id) is True
    assert (await ExpenseStore(cfg).get(user_id, expense.id)).project_id == general.id
    assert [project.id for project in await store.list(user_id)] == [general.id]
    assert (await _create(store, user_id, "trip")).id != trip.id


async def test_general_can_be_neither_deleted_nor_renamed_nor_archived(store, user_id):
    general = await store.find_or_create(user_id, GENERAL_PROJECT_NAME, created_by_bot=None, tainted=False)
    assert is_general(general) and not is_general(await _create(store, user_id, "House"))
    for changes in ({"name": "Misc"}, {"status": "archived"}):
        with pytest.raises(ValueError, match="General is where expenses with no project go"):
            await store.update(user_id, general.id, ProjectPatch(changes))
    with pytest.raises(ValueError, match="General is where expenses with no project go"):
        await store.delete(user_id, general.id)
    kept = await store.find(user_id, GENERAL_PROJECT_NAME)
    assert (kept.id, kept.name, kept.status) == (general.id, GENERAL_PROJECT_NAME, "active")


async def test_another_users_project_and_top_ups_are_none(cfg, store, user_id):
    house = await _create(store, user_id, "House", budget=Decimal("100"))
    credit = await _topup(store, user_id, house.id, "10")
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    assert await store.get(bob, house.id) is None
    assert await store.find(bob, "House") is None
    assert await store.list(bob) == ()
    assert await store.update(bob, house.id, ProjectPatch({"name": "Mine"})) is None
    assert await store.set_budget(bob, house.id, Decimal("1"), created_by_bot=None, tainted=False) is None
    with pytest.raises(ValueError, match="No such project."):
        await _topup(store, bob, house.id, "5")
    assert await store.edit_topup(bob, credit.id, Decimal("99")) is None
    assert await store.undo_topup(bob, credit.id) is None
    assert await store.topups(bob, house.id) == ()
    assert await store.has_money(bob, house.id) is False
    assert await store.delete(bob, house.id) is False
    kept = await store.get(user_id, house.id)
    assert (kept.name, kept.budget) == ("House", Decimal("110.00"))
```

**2d. `add_topup` returns the top-up.** In `tests/test_money_store.py` **(after Task 1, which replaced the whole file)**, find this line in `test_set_budget_and_top_ups_keep_a_ledger`:

```python
    assert (await store.add_topup(user_id, food.id, Decimal("20"), "birthday", created_by_bot=None, tainted=False)).budget == Decimal("270.00")
```

Replace it with:

```python
    topup = await store.add_topup(user_id, food.id, Decimal("20"), "birthday", created_by_bot=None, tainted=False)
    assert (topup.kind, topup.amount, topup.source) == ("credit", Decimal("20.00"), "birthday")
    assert (await store.get(user_id, food.id)).budget == Decimal("270.00")
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_project_store.py -q`
Expected: FAIL at collection, `ImportError: cannot import name 'DEFAULT_PROJECT_COLOR' from 'roost.constants'` ("Interrupted: 1 error during collection").

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_migrations_v12.py -q`
Expected: FAIL, `6 failed`:
- `test_v12_database_migrates_to_latest_and_keeps_every_row`: `assert 12 >= 13`.
- `test_v12_database_gains_the_project_columns_and_indexes`: the `money_projects` column set is not a subset.
- the next three: `sqlite3.OperationalError: no such column: color` / `lead_bot_id` / `project_id`.
- `test_migrating_v12_twice_is_a_no_op_and_backs_up_once`: `ValueError: not enough values to unpack (expected 1, got 0)`, because nothing was pending, so there is no backup.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_money_store.py -q`
Expected: FAIL, `1 failed, 6 passed`. `test_set_budget_and_top_ups_keep_a_ledger` fails with `AttributeError: 'Project' object has no attribute 'kind'`.

- [ ] **Step 4: Schema v13 and the constants**

**4a.** In `roost/db/migrations.py` **(after the stuck flow; its Task 3 added these v12 lines and nothing after it edits this file)**, find:

```python
        "CREATE INDEX IF NOT EXISTS idx_stuck_cards_user ON stuck_cards(user_id, state, created_at)",
    )),
)
```

Replace with:

```python
        "CREATE INDEX IF NOT EXISTS idx_stuck_cards_user ON stuck_cards(user_id, state, created_at)",
    )),
    # Projects hub: money_projects is the project (P8). Every step is an added nullable or
    # defaulted column, or an index. Status values are plaintext on columns with no CHECK:
    # money_projects.status active|archived, money_expenses.status posted|void, tasks.status gains failed.
    Migration(13, "projects hub", (
        AddColumn("money_projects", "color", "TEXT"),
        AddColumn("money_projects", "start_date", "TEXT"),
        AddColumn("money_projects", "due_date", "TEXT"),
        AddColumn("money_projects", "monthly_budget", "TEXT"),          # enc:v2 decimal string
        AddColumn("money_projects", "lead_bot_id", "TEXT REFERENCES bots(id) ON DELETE SET NULL"),
        AddColumn("money_expenses", "step_id", "TEXT"),
        AddColumn("money_expenses", "is_favorite", "INTEGER NOT NULL DEFAULT 0"),
        AddColumn("money_topups", "topup_id", "TEXT"),
        AddColumn("tasks", "project_id", "TEXT REFERENCES money_projects(id) ON DELETE SET NULL"),
        AddColumn("tasks", "allocated_budget", "TEXT"),                   # enc:v2 decimal string
        AddColumn("notes", "project_id", "TEXT REFERENCES money_projects(id) ON DELETE SET NULL"),
        AddColumn("documents", "project_id", "TEXT REFERENCES money_projects(id) ON DELETE SET NULL"),
        "CREATE INDEX IF NOT EXISTS idx_tasks_user_project ON tasks(user_id, project_id)",
        "CREATE INDEX IF NOT EXISTS idx_notes_user_project ON notes(user_id, project_id)",
        "CREATE INDEX IF NOT EXISTS idx_documents_user_project ON documents(user_id, project_id)",
    )),
)
```

**4b.** In `roost/constants.py` **(after the stuck flow, after Task 1)**, find these lines in the Finance section, which the stuck flow does not touch:

```python
MAX_EXPENSE_NOTE_LENGTH = 200
EXPENSE_LIST_LIMIT = 50
```

Replace with:

```python
MAX_EXPENSE_NOTE_LENGTH = 200
EXPENSE_LIST_LIMIT = 50
# Projects hub (H2, H8, H16): a project's status, its fixed palette (the first is the
# default), the budget bars' thresholds, list and page sizes, and a top-up's source.
PROJECT_STATUSES = ("active", "archived")
PROJECT_COLORS = ("#64748b", "#ef4444", "#f97316", "#eab308", "#22c55e", "#14b8a6", "#3b82f6", "#8b5cf6", "#ec4899")
DEFAULT_PROJECT_COLOR = PROJECT_COLORS[0]
BUDGET_WARN_PERCENT = 80          # bar turns amber
BUDGET_OVER_PERCENT = 100         # bar turns red
PROJECT_LIST_LIMIT = 100
PROJECT_PAGE_ITEMS = 20           # latest expenses / notes / documents on a project page
TOPUP_SOURCE_MAX_CHARS = 120
```

- [ ] **Step 5: The project model**

All three finds are in `roost/money/models.py` **(after Task 1, which replaced the whole file)**.

**5a.** Find:

```python
from dataclasses import dataclass
from decimal import Decimal
```

Replace with:

```python
import re
from collections.abc import Callable
from dataclasses import dataclass, fields
from datetime import date
from decimal import Decimal
```

**5b.** Find:

```python
from roost.constants import DEFAULT_CURRENCY
```

Replace with:

```python
from roost.constants import (
    CURRENCY_PATTERN, DEFAULT_CURRENCY, DEFAULT_PROJECT_COLOR, MAX_CATEGORY_NAME_LENGTH, PROJECT_COLORS,
    PROJECT_STATUSES,
)
from roost.money.amounts import parse_amount
```

**5c.** Find:

```python
@dataclass(frozen=True)
class Project:
    id: str
    user_id: str
    name: str
    budget: Decimal | None
    currency: str
    created_at: str
    updated_at: str
    created_by_bot: str | None
    tainted: bool
```

Replace with:

```python
@dataclass(frozen=True)
class Project:
    id: str
    user_id: str
    name: str
    budget: Decimal | None        # the total budget; it already includes top-ups (LazyClaw's meaning)
    currency: str
    created_at: str
    updated_at: str
    created_by_bot: str | None
    tainted: bool
    color: str                    # one of PROJECT_COLORS
    start_date: str | None        # YYYY-MM-DD
    due_date: str | None          # YYYY-MM-DD
    monthly_budget: Decimal | None
    lead_bot_id: str | None       # one of the user's bots (H15); cleared when that bot is retired
    status: str                   # "active" | "archived"


# No apostrophes in these texts: the tools path escapes them for the model.
PROJECT_NAME_TEXT = f"A project needs a name of at most {MAX_CATEGORY_NAME_LENGTH} characters."
CURRENCY_TEXT = "A currency is a three-letter code like EUR."
COLOR_TEXT = f"A project colour is one of {', '.join(PROJECT_COLORS)}."   # the bots' tools reuse it (Task 7)
STATUS_TEXT = "A project is either active or archived."
DATE_TEXT = "A project date is a day written YYYY-MM-DD."
LEAD_BOT_TEXT = "The lead bot must be one of your bots."


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _name(value: object) -> str:
    name = _text(value)
    if not name or len(name) > MAX_CATEGORY_NAME_LENGTH:
        raise ValueError(PROJECT_NAME_TEXT)
    return name


def _currency(value: object) -> str:
    code = _text(value).upper()
    if re.fullmatch(CURRENCY_PATTERN, code) is None:
        raise ValueError(CURRENCY_TEXT)
    return code


def _color(value: object) -> str:
    color = _text(value).lower()
    if color not in PROJECT_COLORS:
        raise ValueError(COLOR_TEXT)
    return color


def _status(value: object) -> str:
    if value not in PROJECT_STATUSES:
        raise ValueError(STATUS_TEXT)
    return str(value)


def _day(value: object) -> str | None:
    """A plain ``YYYY-MM-DD`` day. ``None`` or a blank string clears it."""
    text = _text(value)
    if value is None or (isinstance(value, str) and not text):
        return None
    try:
        day = date.fromisoformat(text)
    except ValueError:
        raise ValueError(DATE_TEXT) from None
    if day.isoformat() != text:   # Python also reads "20261231" or week dates; only the plain form is kept
        raise ValueError(DATE_TEXT)
    return text


def _amount(value: object) -> Decimal | None:
    """Positive, at most 2 decimals, at most ``MAX_EXPENSE_AMOUNT``. ``None`` clears it."""
    return None if value is None else parse_amount(str(value))


def _lead_bot(value: object) -> str | None:
    if value is None:
        return None
    bot_id = _text(value)
    if not bot_id:
        raise ValueError(LEAD_BOT_TEXT)
    return bot_id


_CHECKS: Mapping[str, Callable[[object], object]] = MappingProxyType({
    "name": _name, "currency": _currency, "budget": _amount, "monthly_budget": _amount, "color": _color,
    "start_date": _day, "due_date": _day, "lead_bot_id": _lead_bot, "status": _status,
})


def _checked(values: Mapping[str, object]) -> dict[str, object]:
    """Each value checked and tidied (stripped, upper- or lower-cased, to cents)."""
    return {field: _CHECKS[field](value) for field, value in values.items()}


@dataclass(frozen=True)
class ProjectDraft:
    """A new project. Every field is checked and tidied while the draft is
    built, so a store never writes a bad value. ``budget`` is the total budget
    and ``monthly_budget`` the monthly limit; a project may have either, both
    or neither (P3)."""

    name: str
    currency: str = DEFAULT_CURRENCY
    budget: Decimal | None = None
    monthly_budget: Decimal | None = None
    color: str = DEFAULT_PROJECT_COLOR
    start_date: str | None = None
    due_date: str | None = None
    lead_bot_id: str | None = None

    def __post_init__(self) -> None:
        tidy = _checked({field.name: getattr(self, field.name) for field in fields(self)})
        for name, value in tidy.items():
            object.__setattr__(self, name, value)   # once, while the frozen draft is being built


PROJECT_PATCHABLE = frozenset({"name", "color", "start_date", "due_date", "monthly_budget", "lead_bot_id", "status",
                               "currency"})


@dataclass(frozen=True)
class ProjectPatch:
    """What an update changes, checked and tidied. The total budget is not
    here: it moves only through ``set_budget`` and top-ups, which write its
    history (H4)."""

    changes: Mapping[str, object]

    def __post_init__(self) -> None:
        unknown = sorted(set(self.changes) - PROJECT_PATCHABLE)
        if unknown:
            raise ValueError(f"Projects have no field {', '.join(unknown)}.")
        object.__setattr__(self, "changes", MappingProxyType(_checked(self.changes)))


TOPUP_CREDIT = "credit"   # a top-up: money added to the total budget ("Top-up")
TOPUP_EDIT = "edit"       # a change: to a top-up when topup_id is set ("Top-up changed"), else "Budget set"


@dataclass(frozen=True)
class TopUp:
    """One row of a project's budget history (``money_topups``, H4)."""

    id: str
    project_id: str
    amount: Decimal               # signed for an edit: the difference
    currency: str
    source: str | None
    kind: str                     # TOPUP_CREDIT | TOPUP_EDIT
    topup_id: str | None          # the credit an edit changes; None for a credit or a "Budget set" row
    undone: bool
    created_at: str
    created_by_bot: str | None
    tainted: bool
```

- [ ] **Step 6: The budget history and the store**

Create `roost/money/topup_store.py`:

```python
"""A project's budget history (``money_topups``, projects hub H4 and H5), for ``ProjectStore``.

Every change to a project's total budget writes one row here, in the same
transaction as the budget itself:

- ``credit``: a top-up, with an optional source ("Top-up");
- ``edit`` with a ``topup_id``: a change to that credit, holding the
  difference ("Top-up changed");
- ``edit`` with no ``topup_id``: the budget itself was set or cleared
  ("Budget set").

So while a budget is set, it equals the sum of the live rows. Undoing a credit
sets ``deleted_at`` on it and on its edits. Amounts and sources are ``enc:v2``
(AAD ``money_topups:amount`` / ``money_topups:source``). These functions run
on the caller's open ``db_session``: ``ProjectStore`` owns the transaction."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import uuid4

import aiosqlite

from roost.crypto.encryption import decrypt_field, encrypt, encrypt_field, user_aad
from roost.money.amounts import CENT, amount_text
from roost.money.models import TOPUP_CREDIT, TOPUP_EDIT, TopUp

_COLUMNS = ("id, user_id, project_id, amount, currency, source, kind, topup_id, created_at, created_by_bot, "
            "tainted, deleted_at")
_ZERO = Decimal("0")

TOPUP_UNDONE_TEXT = "That top-up was undone already."
BUDGET_CLEARED_TEXT = "The total budget is cleared, so its top-ups cannot change. Set a budget first."
BELOW_ZERO_TEXT = "That would take the total budget below 0."


class TopUpUndone(ValueError):
    """An undone top-up can be neither changed nor undone again (HTTP 409)."""


@dataclass(frozen=True)
class LedgerRow:
    """One row to write: which project, by how much, and why."""

    project_id: str
    amount: Decimal                   # signed for an edit
    currency: str
    kind: str                         # TOPUP_CREDIT or TOPUP_EDIT
    topup_id: str | None = None       # the credit an edit changes; None when the budget itself was set
    source: str | None = None
    created_by_bot: str | None = None
    tainted: bool = False


def _aad(user_id: str, column: str) -> bytes:
    return user_aad(user_id, f"money_topups:{column}")


def _amount(row: aiosqlite.Row, dek: bytes) -> Decimal:
    return Decimal(decrypt_field(row["amount"], dek, _aad(row["user_id"], "amount")) or "0")


def row_to_topup(row: aiosqlite.Row, dek: bytes) -> TopUp:
    return TopUp(
        id=row["id"], project_id=row["project_id"], amount=_amount(row, dek), currency=row["currency"],
        source=decrypt_field(row["source"], dek, _aad(row["user_id"], "source")), kind=row["kind"],
        topup_id=row["topup_id"], undone=row["deleted_at"] is not None, created_at=row["created_at"],
        created_by_bot=row["created_by_bot"], tainted=bool(row["tainted"]),
    )


def moved_budget(budget: Decimal | None, change: Decimal) -> Decimal:
    """The total budget after a top-up changes or goes. Refused while the
    budget is cleared (its old top-ups were already taken back by the clearing
    row), and when it would fall below 0."""
    if budget is None:
        raise ValueError(BUDGET_CLEARED_TEXT)
    moved = budget + change
    if moved < _ZERO:
        raise ValueError(BELOW_ZERO_TEXT)
    return moved


async def add_row(db: aiosqlite.Connection, user_id: str, dek: bytes, entry: LedgerRow, now: str) -> TopUp:
    topup_id = str(uuid4())
    await db.execute(
        "INSERT INTO money_topups (id, user_id, project_id, amount, currency, source, kind, topup_id, created_at, "
        "updated_at, created_by_bot, tainted) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (topup_id, user_id, entry.project_id, encrypt(amount_text(entry.amount), dek, _aad(user_id, "amount")),
         entry.currency, encrypt_field(entry.source, dek, _aad(user_id, "source")), entry.kind, entry.topup_id,
         now, now, entry.created_by_bot, int(entry.tainted)),
    )
    return TopUp(
        id=topup_id, project_id=entry.project_id, amount=entry.amount.quantize(CENT), currency=entry.currency,
        source=entry.source, kind=entry.kind, topup_id=entry.topup_id, undone=False, created_at=now,
        created_by_bot=entry.created_by_bot, tainted=entry.tainted,
    )


async def credit(db: aiosqlite.Connection, user_id: str, dek: bytes, topup_id: str) -> TopUp | None:
    """The user's credit row with this id, undone or not. An ``edit`` row is never a top-up to change."""
    rows = await (await db.execute(
        f"SELECT {_COLUMNS} FROM money_topups WHERE id = ? AND user_id = ? AND kind = ?",
        (topup_id, user_id, TOPUP_CREDIT),
    )).fetchall()
    return row_to_topup(rows[0], dek) if rows else None


async def live_total(db: aiosqlite.Connection, user_id: str, dek: bytes, credit_id: str) -> Decimal:
    """What a credit adds to the budget now: its amount plus its live edits."""
    rows = await (await db.execute(
        "SELECT user_id, amount FROM money_topups WHERE user_id = ? AND (id = ? OR topup_id = ?) "
        "AND deleted_at IS NULL",
        (user_id, credit_id, credit_id),
    )).fetchall()
    return sum((_amount(row, dek) for row in rows), _ZERO)


async def mark_undone(db: aiosqlite.Connection, user_id: str, credit_id: str, now: str) -> None:
    await db.execute(
        "UPDATE money_topups SET deleted_at = ?, updated_at = ? WHERE user_id = ? AND (id = ? OR topup_id = ?) "
        "AND deleted_at IS NULL",
        (now, now, user_id, credit_id, credit_id),
    )


async def history_rows(db: aiosqlite.Connection, user_id: str, project_id: str) -> list[aiosqlite.Row]:
    """Every row of the project's history, newest first, undone ones included."""
    return list(await (await db.execute(
        f"SELECT {_COLUMNS} FROM money_topups WHERE user_id = ? AND project_id = ? "
        "ORDER BY created_at DESC, rowid DESC",
        (user_id, project_id),
    )).fetchall())


async def set_currency(db: aiosqlite.Connection, user_id: str, project_id: str, currency: str, now: str) -> None:
    """A project with no money changed its currency (H7): its "Budget set" rows
    follow. Undone top-ups keep the currency they had."""
    await db.execute(
        "UPDATE money_topups SET currency = ?, updated_at = ? WHERE user_id = ? AND project_id = ? AND kind = ? "
        "AND topup_id IS NULL",
        (currency, now, user_id, project_id, TOPUP_EDIT),
    )
```

Replace the whole of `roost/money/project_store.py` **(after Task 1, which moved and renamed it)** with:

```python
# SPDX-License-Identifier: MIT
# Adapted from LazyClaw lazyclaw/budgets/store.py @ 21e1002 (names and semantics), for Roost
"""``ProjectStore`` — the user's projects (the ``money_projects`` table,
LazyClaw's projects).

- Names and both budgets are ``enc:v2``. ``name_key`` is HMAC(dek, folded
  name), so a name is unique among the user's live projects without ever
  being stored or compared in plaintext (LazyClaw kept a plaintext casefold
  key). Colour, dates, status and the lead bot are plaintext.
- ``budget`` is the total budget and already includes top-ups (LazyClaw's
  meaning). Every change to it writes a ``money_topups`` row in the same
  transaction (``roost/money/topup_store.py``), so while a budget is set it
  equals the sum of the live rows (H4). Clearing it writes an ``edit`` row of
  −budget (H5).
- General (H2) is the project whose ``name_key`` is the key of
  ``GENERAL_PROJECT_NAME``. It is never renamed, archived or deleted.
- Deleting is soft and one transaction (H9): the expenses move to General,
  the tasks, notes and documents lose the link, and ``deleted_at`` is set.
  ``ON DELETE SET NULL`` is only a safety net.
- A write that depends on a read does the read inside its own
  ``db_session``. The session holds the connection's lock, so nothing can
  change in between."""

from __future__ import annotations

import hashlib
import hmac
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from typing import AsyncIterator, Mapping
from uuid import uuid4

import aiosqlite

from roost.config import Config
from roost.constants import DEFAULT_PROJECT_COLOR, GENERAL_PROJECT_NAME, PROJECT_STATUSES
from roost.crypto.encryption import decrypt_field, encrypt, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session
from roost.money import topup_store as ledger
from roost.money.amounts import CENT, amount_text
from roost.money.models import TOPUP_CREDIT, TOPUP_EDIT, Project, ProjectDraft, ProjectPatch, TopUp

_COLUMNS = ("id, user_id, name, budget, currency, created_at, updated_at, created_by_bot, tainted, color, "
            "start_date, due_date, monthly_budget, lead_bot_id, status")
_INSERT = ("INSERT INTO money_projects (id, user_id, name, name_key, budget, currency, status, color, start_date, "
           "due_date, monthly_budget, lead_bot_id, created_at, updated_at, created_by_bot, tainted) "
           "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)")
_ACTIVE = PROJECT_STATUSES[0]                       # "active"
_LINKED_TABLES = ("tasks", "notes", "documents")    # items that stay when their project goes (H9)
_ZERO = Decimal("0")

NAME_TAKEN_TEXT = "A project with that name exists."
GENERAL_KEPT_TEXT = "General is where expenses with no project go; it cannot be renamed, archived or deleted."
CURRENCY_LOCKED_TEXT = "The currency can change only while the project has no expenses and no top-ups."
LEAD_BOT_GONE_TEXT = "The lead bot must be one of your bots."
PROJECT_GONE_TEXT = "No such project."


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _aad(user_id: str, column: str) -> bytes:
    return user_aad(user_id, f"money_projects:{column}")


def _folded(name: str) -> str:
    return " ".join(name.casefold().split())


def _name_key(dek: bytes, name: str) -> str:
    return hmac.new(dek, _folded(name).encode("utf-8"), hashlib.sha256).hexdigest()


def is_general(project: Project) -> bool:
    """H2: General is the project whose ``name_key`` is the key of
    ``GENERAL_PROJECT_NAME``. The key is an HMAC of the folded name, so
    comparing the folded names is the same test, and needs no key."""
    return _folded(project.name) == _folded(GENERAL_PROJECT_NAME)


def _amount_or_none(text: str | None) -> Decimal | None:
    return Decimal(text) if text else None


def _encrypted_amount(user_id: str, dek: bytes, column: str, amount: object) -> str | None:
    if not isinstance(amount, Decimal):
        return None
    return encrypt(amount_text(amount), dek, _aad(user_id, column))


def _row_to_project(row: aiosqlite.Row, dek: bytes) -> Project:
    user_id = row["user_id"]

    def text(column: str) -> str | None:
        return decrypt_field(row[column], dek, _aad(user_id, column))

    return Project(
        id=row["id"], user_id=user_id, name=text("name") or "", budget=_amount_or_none(text("budget")),
        currency=row["currency"], created_at=row["created_at"], updated_at=row["updated_at"],
        created_by_bot=row["created_by_bot"], tainted=bool(row["tainted"]),
        color=row["color"] or DEFAULT_PROJECT_COLOR,      # a project saved before v13 has no colour yet
        start_date=row["start_date"], due_date=row["due_date"],
        monthly_budget=_amount_or_none(text("monthly_budget")), lead_bot_id=row["lead_bot_id"],
        status=row["status"],
    )


def _new_project(user_id: str, project_id: str, draft: ProjectDraft, now: str, created_by_bot: str | None,
                 tainted: bool) -> Project:
    return Project(
        id=project_id, user_id=user_id, name=draft.name, budget=draft.budget, currency=draft.currency,
        created_at=now, updated_at=now, created_by_bot=created_by_bot, tainted=tainted, color=draft.color,
        start_date=draft.start_date, due_date=draft.due_date, monthly_budget=draft.monthly_budget,
        lead_bot_id=draft.lead_bot_id, status=_ACTIVE,
    )


def _columns_for(user_id: str, dek: bytes, field: str, value: object) -> tuple[tuple[str, object], ...]:
    if field == "name":
        name = str(value)
        return (("name", encrypt(name, dek, _aad(user_id, "name"))), ("name_key", _name_key(dek, name)))
    if field == "monthly_budget":
        return (("monthly_budget", _encrypted_amount(user_id, dek, "monthly_budget", value)),)
    return ((field, value),)


def _assignments(user_id: str, dek: bytes, changes: Mapping[str, object]) -> tuple[tuple[str, object], ...]:
    """The columns a patch writes. Its keys are ``PROJECT_PATCHABLE`` (checked
    by ``ProjectPatch``), so they are safe column names."""
    return tuple(pair for field, value in changes.items() for pair in _columns_for(user_id, dek, field, value))


def _changes_general(current: Project, changes: Mapping[str, object]) -> bool:
    """A rename (beyond case and spacing) or an archive of General (H2)."""
    renamed = "name" in changes and _folded(str(changes["name"])) != _folded(current.name)
    archived = changes.get("status", current.status) != _ACTIVE
    return is_general(current) and (renamed or archived)


def _integrity_text(exc: aiosqlite.IntegrityError) -> str | None:
    """The two conflicts a caller can cause, as sentences: a live project
    already has the name (unique ``name_key``), or the lead bot does not exist
    (foreign key)."""
    text = str(exc)
    if "UNIQUE" in text:
        return NAME_TAKEN_TEXT
    return LEAD_BOT_GONE_TEXT if "FOREIGN KEY" in text else None


@asynccontextmanager
async def _transaction(config: Config) -> AsyncIterator[aiosqlite.Connection]:
    """One write transaction. Reads inside it see exactly what its writes
    change, because the session holds the connection's lock. Any error rolls
    all of it back."""
    async with db_session(config) as db:
        try:
            yield db
            await db.commit()
        except aiosqlite.IntegrityError as exc:
            await db.rollback()
            text = _integrity_text(exc)
            if text is None:
                raise
            raise ValueError(text) from exc
        except BaseException:
            await db.rollback()
            raise


async def _insert(db: aiosqlite.Connection, project: Project, dek: bytes) -> None:
    user_id = project.user_id
    await db.execute(_INSERT, (
        project.id, user_id, encrypt(project.name, dek, _aad(user_id, "name")), _name_key(dek, project.name),
        _encrypted_amount(user_id, dek, "budget", project.budget), project.currency, project.status, project.color,
        project.start_date, project.due_date, _encrypted_amount(user_id, dek, "monthly_budget", project.monthly_budget),
        project.lead_bot_id, project.created_at, project.updated_at, project.created_by_bot, int(project.tainted),
    ))


async def _live_project(db: aiosqlite.Connection, user_id: str, dek: bytes, project_id: str) -> Project | None:
    rows = await (await db.execute(
        f"SELECT {_COLUMNS} FROM money_projects WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
        (project_id, user_id),
    )).fetchall()
    return _row_to_project(rows[0], dek) if rows else None


async def _write_budget(db: aiosqlite.Connection, project: Project, budget: Decimal | None, dek: bytes,
                        now: str) -> None:
    await db.execute(
        "UPDATE money_projects SET budget = ?, updated_at = ? WHERE id = ? AND user_id = ?",
        (_encrypted_amount(project.user_id, dek, "budget", budget), now, project.id, project.user_id),
    )


async def _has_money(db: aiosqlite.Connection, user_id: str, project_id: str) -> bool:
    """H7: an expense that is not deleted (void ones count), or a live top-up.
    A budget alone is not money: its "Budget set" rows follow a currency change."""
    rows = await (await db.execute(
        "SELECT EXISTS (SELECT 1 FROM money_expenses WHERE user_id = ? AND project_id = ? AND deleted_at IS NULL) "
        "OR EXISTS (SELECT 1 FROM money_topups WHERE user_id = ? AND project_id = ? AND kind = ? "
        "AND deleted_at IS NULL)",
        (user_id, project_id, user_id, project_id, TOPUP_CREDIT),
    )).fetchall()
    return bool(rows[0][0])


async def _check_update(db: aiosqlite.Connection, current: Project, changes: Mapping[str, object]) -> None:
    if _changes_general(current, changes):
        raise ValueError(GENERAL_KEPT_TEXT)
    new_currency = changes.get("currency", current.currency)
    if new_currency != current.currency and await _has_money(db, current.user_id, current.id):
        raise ValueError(CURRENCY_LOCKED_TEXT)


async def _general_id(db: aiosqlite.Connection, user_id: str, dek: bytes, now: str) -> str:
    """General's id, made inside the caller's transaction when it does not exist yet (H9)."""
    rows = await (await db.execute(
        "SELECT id FROM money_projects WHERE user_id = ? AND name_key = ? AND deleted_at IS NULL",
        (user_id, _name_key(dek, GENERAL_PROJECT_NAME)),
    )).fetchall()
    if rows:
        return rows[0]["id"]
    general = _new_project(user_id, str(uuid4()), ProjectDraft(name=GENERAL_PROJECT_NAME), now, None, False)
    await _insert(db, general, dek)
    return general.id


async def _hand_over(db: aiosqlite.Connection, user_id: str, project_id: str, general_id: str, now: str) -> None:
    """H9's first two steps. The expenses move to General. The tasks, notes and
    documents only lose the link: their revision and ``updated_at`` stay, so an
    open editor is not disturbed."""
    await db.execute(
        "UPDATE money_expenses SET project_id = ?, updated_at = ? WHERE user_id = ? AND project_id = ?",
        (general_id, now, user_id, project_id),
    )
    for table in _LINKED_TABLES:
        await db.execute(f"UPDATE {table} SET project_id = NULL WHERE user_id = ? AND project_id = ?",
                         (user_id, project_id))


async def _credit_and_project(db: aiosqlite.Connection, user_id: str, dek: bytes,
                              topup_id: str) -> tuple[TopUp, Project] | None:
    """A top-up the user may change: one of their credits, on a live project.
    An undone one is refused (``TopUpUndone``, HTTP 409)."""
    credit = await ledger.credit(db, user_id, dek, topup_id)
    project = await _live_project(db, user_id, dek, credit.project_id) if credit is not None else None
    if credit is None or project is None:
        return None
    if credit.undone:
        raise ledger.TopUpUndone(ledger.TOPUP_UNDONE_TEXT)
    return credit, project


class ProjectStore:
    def __init__(self, config: Config) -> None:
        self._config = config

    async def list(self, user_id: str, *, include_archived: bool = True) -> tuple[Project, ...]:
        """Live projects, oldest first. ``include_archived=False`` keeps the active ones."""
        if include_archived:
            return await self._select(user_id, "WHERE user_id = ? AND deleted_at IS NULL ORDER BY created_at",
                                      (user_id,))
        return await self._select(
            user_id, "WHERE user_id = ? AND deleted_at IS NULL AND status = ? ORDER BY created_at", (user_id, _ACTIVE),
        )

    async def get(self, user_id: str, project_id: str) -> Project | None:
        found = await self._select(user_id, "WHERE id = ? AND user_id = ? AND deleted_at IS NULL", (project_id, user_id))
        return found[0] if found else None

    async def find(self, user_id: str, name: str) -> Project | None:
        """The live project with this name, case and spacing ignored, archived or
        not. It never creates one (H3)."""
        if not name.strip():
            return None
        dek = await get_user_dek(self._config, user_id)
        found = await self._select(user_id, "WHERE user_id = ? AND name_key = ? AND deleted_at IS NULL",
                                   (user_id, _name_key(dek, name)))
        return found[0] if found else None

    async def find_or_create(self, user_id: str, name: str, *, created_by_bot: str | None, tainted: bool) -> Project:
        """``log_expense``'s lookup, the only one that creates (H3): the live
        project with this name, else a new one. Two concurrent creations end on
        the same row."""
        found = await self.find(user_id, name)
        if found is not None:
            return found
        try:
            return await self.create(user_id, ProjectDraft(name=name), created_by_bot=created_by_bot, tainted=tainted)
        except ValueError as exc:
            if str(exc) != NAME_TAKEN_TEXT:
                raise
            made_meanwhile = await self.find(user_id, name)
            if made_meanwhile is None:
                raise
            return made_meanwhile

    async def create(self, user_id: str, draft: ProjectDraft, *, created_by_bot: str | None,
                     tainted: bool) -> Project:
        """A new active project. A total budget is written with its "Budget set"
        row, so the history holds it from the start (H4). A name in use (case
        and spacing ignored) or a lead bot that does not exist is a
        ``ValueError``."""
        dek = await get_user_dek(self._config, user_id)
        project = _new_project(user_id, str(uuid4()), draft, _now_iso(), created_by_bot, tainted)
        async with _transaction(self._config) as db:
            await _insert(db, project, dek)
            if project.budget is not None:
                entry = ledger.LedgerRow(project.id, project.budget, project.currency, TOPUP_EDIT,
                                         created_by_bot=created_by_bot, tainted=tainted)
                await ledger.add_row(db, user_id, dek, entry, project.created_at)
        return project

    async def update(self, user_id: str, project_id: str, patch: ProjectPatch) -> Project | None:
        """Rename (``name_key`` follows), colour, dates, monthly limit, lead bot,
        archive / unarchive and currency. ``None``: no such project. General
        keeps its name and stays active (H2). The currency changes only while
        the project has no money, and then its "Budget set" rows follow (H7)."""
        dek = await get_user_dek(self._config, user_id)
        now = _now_iso()
        async with _transaction(self._config) as db:
            current = await _live_project(db, user_id, dek, project_id)
            if current is None or not patch.changes:
                return current
            await _check_update(db, current, patch.changes)
            pairs = _assignments(user_id, dek, patch.changes)
            sets = ", ".join(f"{column} = ?" for column, _ in pairs)
            await db.execute(f"UPDATE money_projects SET {sets}, updated_at = ? WHERE id = ? AND user_id = ?",
                             (*(value for _, value in pairs), now, project_id, user_id))
            if patch.changes.get("currency", current.currency) != current.currency:
                await ledger.set_currency(db, user_id, project_id, str(patch.changes["currency"]), now)
        return await self.get(user_id, project_id)

    async def keep(self, user_id: str, project_id: str) -> Project | None:
        """The user vouches for a project's name (via Keep on an expense row
        that shows it): its taint bit is cleared. HTTP only, never a tool."""
        async with db_session(self._config) as db:
            await db.execute(
                "UPDATE money_projects SET tainted = 0, updated_at = ? WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
                (_now_iso(), project_id, user_id),
            )
            await db.commit()
        return await self.get(user_id, project_id)

    async def set_budget(self, user_id: str, project_id: str, amount: Decimal | None, *,
                         created_by_bot: str | None, tainted: bool) -> Project | None:
        """Set the total budget to ``amount`` with an ``edit`` row of the change
        ("Budget set"). ``None`` clears it (H5): an ``edit`` row of −budget,
        then no budget. An unchanged budget writes no row. ``None`` back: no
        such project."""
        dek = await get_user_dek(self._config, user_id)
        now = _now_iso()
        async with _transaction(self._config) as db:
            current = await _live_project(db, user_id, dek, project_id)
            if current is None or amount == current.budget:
                return current
            change = (amount if amount is not None else _ZERO) - (current.budget or _ZERO)
            entry = ledger.LedgerRow(current.id, change, current.currency, TOPUP_EDIT,
                                     created_by_bot=created_by_bot, tainted=tainted)
            await ledger.add_row(db, user_id, dek, entry, now)
            await _write_budget(db, current, amount, dek, now)
        return replace(current, budget=None if amount is None else amount.quantize(CENT), updated_at=now)

    async def add_topup(self, user_id: str, project_id: str, amount: Decimal, source: str | None, *,
                        created_by_bot: str | None, tainted: bool) -> TopUp:
        """A ``credit`` row that raises the total budget by ``amount``; a project
        with no budget gets one. The project must be the user's and live, else
        ``ValueError("No such project.")``."""
        dek = await get_user_dek(self._config, user_id)
        now = _now_iso()
        async with _transaction(self._config) as db:
            current = await _live_project(db, user_id, dek, project_id)
            if current is None:
                raise ValueError(PROJECT_GONE_TEXT)
            entry = ledger.LedgerRow(current.id, amount, current.currency, TOPUP_CREDIT, source=source,
                                     created_by_bot=created_by_bot, tainted=tainted)
            topup = await ledger.add_row(db, user_id, dek, entry, now)
            await _write_budget(db, current, (current.budget or _ZERO) + amount, dek, now)
        return topup

    async def edit_topup(self, user_id: str, topup_id: str, amount: Decimal) -> TopUp | None:
        """``amount`` is the top-up's new amount (H4). The store writes an
        ``edit`` row of the difference, linked to the credit by ``topup_id``,
        and moves the budget by the same. It returns that row, or the credit
        itself when the amount is already that. ``None``: no such top-up of the
        user's on a live project."""
        dek = await get_user_dek(self._config, user_id)
        now = _now_iso()
        async with _transaction(self._config) as db:
            found = await _credit_and_project(db, user_id, dek, topup_id)
            if found is None:
                return None
            credit, project = found
            change = amount - await ledger.live_total(db, user_id, dek, credit.id)
            if change == _ZERO:
                return credit
            budget = ledger.moved_budget(project.budget, change)
            entry = ledger.LedgerRow(project.id, change, credit.currency, TOPUP_EDIT, topup_id=credit.id)
            edit = await ledger.add_row(db, user_id, dek, entry, now)
            await _write_budget(db, project, budget, dek, now)
        return edit

    async def undo_topup(self, user_id: str, topup_id: str) -> TopUp | None:
        """The credit and all its edits leave the budget together (H4):
        ``deleted_at`` on each, and the budget lowered by their sum. It returns
        the credit, now ``undone``."""
        dek = await get_user_dek(self._config, user_id)
        now = _now_iso()
        async with _transaction(self._config) as db:
            found = await _credit_and_project(db, user_id, dek, topup_id)
            if found is None:
                return None
            credit, project = found
            budget = ledger.moved_budget(project.budget, -await ledger.live_total(db, user_id, dek, credit.id))
            await ledger.mark_undone(db, user_id, credit.id, now)
            await _write_budget(db, project, budget, dek, now)
        return replace(credit, undone=True)

    async def topups(self, user_id: str, project_id: str) -> tuple[TopUp, ...]:
        """The budget history, newest first, undone rows included (``undone=True``)."""
        async with db_session(self._config) as db:
            rows = await ledger.history_rows(db, user_id, project_id)
        if not rows:
            return ()
        dek = await get_user_dek(self._config, user_id)
        return tuple(ledger.row_to_topup(row, dek) for row in rows)

    async def has_money(self, user_id: str, project_id: str) -> bool:
        """Any expense or live top-up: then the currency can no longer change (H7)."""
        async with db_session(self._config) as db:
            return await _has_money(db, user_id, project_id)

    async def delete(self, user_id: str, project_id: str) -> bool:
        """H9 in one transaction: General is found or made, the expenses move to
        it, the tasks, notes and documents lose the link, and the project gets
        ``deleted_at``. General itself is refused. ``False``: no such project."""
        dek = await get_user_dek(self._config, user_id)
        now = _now_iso()
        async with _transaction(self._config) as db:
            current = await _live_project(db, user_id, dek, project_id)
            if current is None:
                return False
            if is_general(current):
                raise ValueError(GENERAL_KEPT_TEXT)
            await _hand_over(db, user_id, project_id, await _general_id(db, user_id, dek, now), now)
            await db.execute("UPDATE money_projects SET deleted_at = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                             (now, now, project_id, user_id))
        return True

    async def _select(self, user_id: str, where: str, params: tuple) -> tuple[Project, ...]:
        async with db_session(self._config) as db:
            rows = await (await db.execute(f"SELECT {_COLUMNS} FROM money_projects {where}", params)).fetchall()
        if not rows:
            return ()
        dek = await get_user_dek(self._config, user_id)
        return tuple(_row_to_project(row, dek) for row in rows)
```

- [ ] **Step 7: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_project_store.py tests/test_migrations_v12.py tests/test_money_store.py -q`
Expected: PASS, `44 passed` (store 31, of which the parametrized draft test is 9; migration 6; money store 7).

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_project_store.py --cov=roost.money.project_store --cov=roost.money.topup_store --cov=roost.money.models --cov-report=term-missing -q`
Expected: PASS, and each of the three modules is at 80% or more.

No test may still pin schema version 12:

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && grep -rn "latest_version() == 1[0-9]\|user_version\")\[0\]\[0\] == 1[0-9]" tests`
Expected: no output.

The related existing tests must stay green (the other migrations, the money code that builds on `ProjectStore`, and the stores whose tables gained a column):

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_migrations.py tests/test_migrations_v4.py tests/test_migrations_v8.py tests/test_migrations_v10.py tests/test_migrations_v11.py tests/test_db.py tests/test_db_connection.py tests/test_money_tools.py tests/test_money_api.py tests/test_money_values.py tests/test_bot_store.py tests/test_task_store.py tests/test_note_store.py tests/test_document_store.py tests/test_tool_text.py tests/test_profile_api.py tests/test_main_bot.py -q`
Expected: PASS.

Run the full suite with the coverage gate:

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest --cov=roost --cov-fail-under=80 -q`
Expected: PASS.

- [ ] **Step 8: Commit**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git add roost/db/migrations.py roost/constants.py roost/money/models.py roost/money/project_store.py roost/money/topup_store.py tests/fixtures/schema_v12.sql tests/test_migrations_v12.py tests/test_project_store.py tests/test_money_store.py && git status --short`
Expected: none of those nine files is still listed as modified (` M`) or untracked (`??`). Files from other work, such as the untracked plan in `docs/plans/`, may stay listed.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git commit -m "feat: schema v13 and the project fields, top-ups with edit and undo, and deleting a project"`
Expected: one commit, with no Co-Authored-By or other attribution line.

---

### Task 3: Expenses (void, starred, task, step) and the calculations

This task implements design §2 ("Calculations") with refinements H6, H7 (the summary part), H8 and H11 (the money side), and P3/P4.
- **Expenses gain three things.** The first is a task link and a step link (`task_id`, `step_id`). The second is a star (`is_favorite`). The third is a status of `posted` or `void`.
- **Every read shows void rows (H6).** `get`, `update`, `keep`, `list_month` and `made_by` filter on `deleted_at IS NULL` only. Every sum leaves voids out, because the counting rule ("posted, and in the project's currency") runs in Python: amounts are encrypted.
- **`roost/projects/numbers.py` is the one place for the sums.** It holds:
  - the total and monthly budget lines;
  - the bar percent and tone (H8);
  - other currencies, which are never converted (P4);
  - the starred total;
  - a task's planned / spent / left (H11). This includes the removed-step rule: every counted expense with the task's `task_id` counts, so a `step_id` that is no longer on the task counts at task level;
  - progress, which leaves cancelled tasks out and counts failed ones apart.
- **The month summary (H7).** Each project row is in the project's own currency, against its **monthly** limit (no longer the total budget), with that project's other currencies listed apart. The top-level EUR total stays, for compatibility.
- **The wire.** The Python wire (`summary_out`, `expense_row`, `expense_out`) carries everything the web will need. `web/src/api/types.ts` is left to Task 9.

None of this task's files are edited by the stuck flow, so no snippet here is marked "(after the stuck flow)". Snippets marked **(after Task 1)** are written against Task 1's Category → Project rename.

**Files:**
- Create:
  - `roost/projects/__init__.py` (package docstring only, so that Task 6's `service.py` can import the stores without a cycle)
  - `roost/projects/numbers.py`
  - `tests/test_project_numbers.py`
  - `tests/test_money_summary.py`
- Modify:
  - `roost/money/models.py`:
    - `ExpenseStatus`, `EXPENSE_POSTED`, `EXPENSE_VOID`, `EXPENSE_STATUSES`;
    - `Expense` gains `task_id`, `step_id` and `is_favorite`;
    - `ExpenseDraft` gains the same three;
    - `EXPENSE_PATCHABLE` gains `task_id`, `step_id`, `is_favorite` and `status`, and `ExpensePatch` checks the values;
    - `ProjectTotal` gains `project_id`, `currency`, `month` and `other_currencies`.
  - `roost/money/expense_store.py` (whole file):
    - the new columns;
    - `_SHOWN` replaces `_LIVE`;
    - `list_project`.
  - `roost/money/summary.py` (whole file):
    - `summarize` per project currency;
    - `budget_line_out`, `amounts_out` and `project_total_out`;
    - `expense_out` gains `task_id`, `step_id`, `is_favorite` and `status`.
  - `roost/money/format.py` (whole file):
    - `expense_line` marks `[void]` and `[starred]`;
    - `summary_text` gives each row in its own currency and against its monthly limit.
  - `roost/tasks/models.py`: `Task` gains the trailing `project_id: str | None = None` and `allocated_budget: Decimal | None = None`. This task needs them for `task_money`; see Interfaces.
  - `tests/test_money_store.py` (one import, and four tests appended)
  - `tests/test_money_api.py` (two `by_project` assertions rewritten, and one test appended)
- Test:
  - `tests/test_project_numbers.py`, `tests/test_money_summary.py`, `tests/test_money_store.py` and `tests/test_money_api.py`

**Interfaces:**
- Consumes:
  - **Task 1:**
    - `Project`, `ProjectTotal` and `MoneySummary.by_project` (`roost/money/models.py`);
    - `Expense.project_id` and `ExpenseDraft.project_id`;
    - `ProjectStore` (`roost/money/project_store.py`, with `find_or_create`);
    - the wire keys `project`, `project_id` and `by_project`.
  - **Task 2:**
    - the `Project` fields `color`, `start_date`, `due_date`, `monthly_budget: Decimal | None`, `lead_bot_id` and `status`;
    - the constants `BUDGET_WARN_PERCENT`, `BUDGET_OVER_PERCENT`, `PROJECT_STATUSES` and `DEFAULT_PROJECT_COLOR`;
    - the schema v13 columns `money_expenses.step_id` and `money_expenses.is_favorite`.
  - **Existing:**
    - `month_bounds`, `current_month` and `parse_spent_at` (`roost/money/months.py`);
    - `amount_text` (`roost/money/amounts.py`);
    - `Task` and `Step` (`roost/tasks/models.py`);
    - `money_expenses.task_id`, which exists since v8 and was never used.
- Produces (the Shared Contract, plus the names marked *extra*):
  - **`roost/money/models.py`:**
    - `Expense.task_id: str | None = None`, `Expense.step_id: str | None = None` and `Expense.is_favorite: bool = False`, all trailing; `Expense.status: ExpenseStatus`.
    - `ExpenseDraft.task_id`, `.step_id` and `.is_favorite` (*extra*, trailing, defaulted; Task 7's `log_expense` fills them).
    - `EXPENSE_PATCHABLE` gains `task_id`, `step_id`, `is_favorite` and `status`.
    - `ExpensePatch` refuses a status other than posted or void (`"The status of an expense is posted or void."`) and a star that is not a bool (`"Starred is yes or no."`).
    - `ExpenseStatus = Literal["posted", "void"]`, `EXPENSE_POSTED`, `EXPENSE_VOID` and `EXPENSE_STATUSES` (*extra*).
    - `ProjectTotal(project, project_id, currency, month: BudgetLine, other_currencies)`. Its `.spent`, `.budget` and `.remaining` are properties that read `month`, so `budget` is now the **monthly** limit.
  - **`roost/money/expense_store.py`:**
    - `ExpenseStore.list_project(user_id, project_id) -> tuple[Expense, ...]`: every expense that is not deleted, voids included, newest first.
    - Every read shows voids. `list_month` now returns voids too, so callers that sum (Task 4's `day_summary`) must use `counted`.
    - `add` stores the links and the star, and `update` writes `task_id`, `step_id`, `is_favorite` and `status`.
  - **`roost/projects/numbers.py`:** exactly the contract:
    - `Tone`, `BudgetLine`, `ProjectNumbers`, `TaskMoney` and `Progress`;
    - `counted`, `budget_line`, `project_numbers`, `task_money` and `progress`;
    - plus `total_of(expenses) -> Decimal` and `per_currency(expenses) -> Mapping[str, Decimal]` (*extra*; `summary.py` uses them).
  - **`roost/money/summary.py`:**
    - `summarize(month, projects, expenses)`;
    - `summary_out`;
    - `budget_line_out(line)`, which is the `BudgetLineOut` shape, for Task 8's `ProjectOut`;
    - `amounts_out(mapping)`;
    - `project_total_out(row)`;
    - `expense_row(expense, project)`;
    - `expense_out(expense, project, *, project_tainted=False)`.
  - **Wire:**
    - `ExpenseOut` keys: `id, project, project_id, task_id, step_id, amount, currency, description, vendor, spent_at, status, is_favorite, created_at, created_by_bot, tainted`.
    - A `by_project` row: `project, project_id, currency, spent, budget, remaining, month: BudgetLineOut, other_currencies`.
    - `BudgetLineOut`: `budget, spent, remaining, used_percent, tone`.
  - **`roost/tasks/models.py`:** `Task.project_id` and `Task.allocated_budget`. **Contract deviation (reported):** the Shared Contract gives these to Task 4, but `task_money` cannot be tested without them. Task 4's draft already accounts for this: its Step 5 adds neither the `Task` fields nor the `Decimal` import, and its finds there are marked "(after Task 3)". Task 4 still adds the two fields to `TaskDraft`, `PATCHABLE_FIELDS` and the store, and it adds the `failed` status.

- [ ] **Step 1: Path guard**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

Then confirm that Tasks 1 and 2 have landed and that this task has not:

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && test -f roost/money/project_store.py && test ! -e roost/projects/numbers.py && grep -n "^class ProjectTotal\|monthly_budget: Decimal | None\|^EXPENSE_PATCHABLE" roost/money/models.py && grep -n "^BUDGET_WARN_PERCENT\|^BUDGET_OVER_PERCENT\|^PROJECT_STATUSES\|^DEFAULT_PROJECT_COLOR" roost/constants.py && grep -n '"money_expenses", "step_id"\|"money_expenses", "is_favorite"' roost/db/migrations.py`

Expected:
- four lines from `models.py`: `monthly_budget: Decimal | None` twice (in `Project` and, with ` = None`, in `ProjectDraft`), then `EXPENSE_PATCHABLE = frozenset({"project_id", ...})` and `class ProjectTotal:`;
- four from `constants.py`;
- two from `migrations.py`.

If a test fails or anything is missing, stop: Tasks 1 and 2 come first, or this task already ran.

Then list the functions of the three files this task replaces whole:

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && grep -n "^def \|^class \|^    async def \|^    def " roost/money/expense_store.py roost/money/summary.py roost/money/format.py`

Expected (after Task 1):
- `expense_store.py`: `_now_iso`, `_aad`, `_encode`, `_row_to_expense`, `text` (nested in `_row_to_expense`), `class ExpenseStore`, `__init__`, `add`, `get`, `list_month`, `made_by`, `update`, `keep`, `delete` and `_select`.
- `summary.py`: `_sums`, `summarize`, `_optional`, `summary_out`, `expense_row` and `expense_out`.
- `format.py`: `escape`, `money`, `expense_line` and `summary_text`.

If an earlier task added another function to one of these files, carry it over unchanged into that file's replacement below.

- [ ] **Step 2: Write the failing tests**

**2a.** Create `tests/test_project_numbers.py`:

```python
"""The projects hub's numbers (design §2, H6–H8, H11): pure, with fixed amounts."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from roost.constants import BUDGET_OVER_PERCENT, BUDGET_WARN_PERCENT, DEFAULT_PROJECT_COLOR
from roost.money.models import Expense, Project
from roost.money.months import current_month, parse_spent_at
from roost.projects.numbers import (
    BudgetLine, Progress, TaskMoney, budget_line, counted, progress, project_numbers, task_money,
)
from roost.tasks.models import Step, Task

_AT = "2026-10-01T09:00:00+00:00"
_STEP = Step(id="s1-a1b2c3", title="Buy paint", done=False)


def _dec(value: str | None) -> Decimal | None:
    return None if value is None else Decimal(value)


def _project(*, currency: str = "EUR", budget: str | None = None, monthly: str | None = None,
             status: str = "active") -> Project:
    return Project(
        id="p-reno", user_id="u1", name="Renovation", budget=_dec(budget), currency=currency, created_at=_AT,
        updated_at=_AT, created_by_bot=None, tainted=False, color=DEFAULT_PROJECT_COLOR, start_date=None,
        due_date=None, monthly_budget=_dec(monthly), lead_bot_id=None, status=status,
    )


def _expense(amount: str, *, currency: str = "EUR", day: str = "2026-10-10", status: str = "posted",
             starred: bool = False, task_id: str | None = None, step_id: str | None = None,
             project_id: str = "p-reno") -> Expense:
    return Expense(
        id=str(uuid4()), user_id="u1", project_id=project_id, amount=Decimal(amount), currency=currency,
        description=None, vendor=None, spent_at=day, status=status, created_at=_AT, updated_at=_AT,
        created_by_bot=None, tainted=False, task_id=task_id, step_id=step_id, is_favorite=starred,
    )


def _task(status: str = "todo", *, budget: str | None = None, steps: tuple[Step, ...] = (),
          task_id: str = "t-paint") -> Task:
    return Task(
        id=task_id, user_id="u1", title="Paint the hall", description=None, category=None, priority="medium",
        status=status, owner="user", due_date=None, reminder_at=None, pre_reminders=(), recurring=None,
        recur_until=None, tags=(), steps=steps, created_at=_AT, updated_at=_AT, completed_at=None,
        created_by_bot=None, tainted=False, project_id="p-reno", allocated_budget=_dec(budget),
    )


def test_counted_means_posted_and_in_the_projects_currency():
    assert counted(_expense("5"), "EUR") is True
    assert counted(_expense("5", status="void"), "EUR") is False
    assert counted(_expense("5", currency="USD"), "EUR") is False
    assert counted(_expense("5", currency="USD"), "USD") is True


def test_mixed_currencies_stay_apart_and_voids_and_other_projects_are_left_out():
    expenses = (
        _expense("100.00"), _expense("50.50"), _expense("20.00", currency="USD"), _expense("30.00", currency="USD"),
        _expense("7.00", currency="GBP"), _expense("999.00", status="void"),
        _expense("5.00", currency="USD", status="void"), _expense("1000.00", project_id="p-other"),
    )
    numbers = project_numbers(_project(budget="500.00"), expenses, "2026-10")
    assert numbers.currency == "EUR"
    assert numbers.total == BudgetLine(Decimal("500.00"), Decimal("150.50"), Decimal("349.50"), 30, "ok")
    assert dict(numbers.other_currencies) == {"GBP": Decimal("7.00"), "USD": Decimal("50.00")}
    assert list(numbers.other_currencies) == ["GBP", "USD"]
    with pytest.raises(TypeError):
        numbers.other_currencies["EUR"] = Decimal("1")   # read-only, like every record here


def test_a_dollar_project_counts_dollars_and_lists_euros_apart():
    numbers = project_numbers(_project(currency="USD", budget="200.00"),
                              (_expense("80.00", currency="USD"), _expense("12.00")), "2026-10")
    assert (numbers.currency, numbers.total.spent, numbers.total.remaining) == (
        "USD", Decimal("80.00"), Decimal("120.00"))
    assert dict(numbers.other_currencies) == {"EUR": Decimal("12.00")}


def test_the_starred_total_counts_only_posted_starred_expenses_in_the_currency():
    expenses = (
        _expense("12.00", starred=True), _expense("8.50", starred=True), _expense("3.00", currency="USD", starred=True),
        _expense("40.00", status="void", starred=True), _expense("100.00"),
    )
    assert project_numbers(_project(), expenses, "2026-10").starred_total == Decimal("20.50")


def test_over_budget_shows_a_negative_remaining_and_the_over_tone():
    assert budget_line(Decimal("100.00"), Decimal("130.00")) == BudgetLine(
        Decimal("100.00"), Decimal("130.00"), Decimal("-30.00"), 130, "over")
    numbers = project_numbers(_project(budget="100.00"), (_expense("60.00"), _expense("70.00")), "2026-10")
    assert (numbers.total.remaining, numbers.total.tone) == (Decimal("-30.00"), "over")


def test_the_bar_turns_amber_at_80_percent_and_red_once_the_budget_is_spent():
    assert (BUDGET_WARN_PERCENT, BUDGET_OVER_PERCENT) == (80, 100)
    spent = ("0.00", "79.99", "80.00", "99.99", "100.00")
    assert [budget_line(Decimal("100.00"), Decimal(s)).tone for s in spent] == ["ok", "ok", "warn", "warn", "over"]
    assert budget_line(Decimal("100.00"), Decimal("100.00")).remaining == Decimal("0.00")


def test_used_percent_rounds_down_so_it_reads_100_only_once_the_budget_is_spent():
    assert budget_line(Decimal("300.00"), Decimal("199.99")).used_percent == 66     # 66.66…
    assert budget_line(Decimal("3.00"), Decimal("2.00")).used_percent == 66         # 66.66…, never 67
    almost = budget_line(Decimal("300.00"), Decimal("299.99"))                      # 99.99…
    assert (almost.used_percent, almost.tone, almost.remaining) == (99, "warn", Decimal("0.01"))
    assert budget_line(Decimal("100.00"), Decimal("250.00")).used_percent == 250    # it may pass 100


def test_a_budget_of_zero_is_used_up_by_any_spending():
    assert budget_line(Decimal("0.00"), Decimal("0.00")) == BudgetLine(
        Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), 0, "ok")
    assert budget_line(Decimal("0.00"), Decimal("5.00")) == BudgetLine(
        Decimal("0.00"), Decimal("5.00"), Decimal("-5.00"), 100, "over")


def test_no_budget_gives_no_remaining_percent_or_tone():
    assert budget_line(None, Decimal("12.00")) == BudgetLine(None, Decimal("12.00"), None, None, None)
    numbers = project_numbers(_project(), (_expense("12.00"),), "2026-10")
    assert (numbers.total.tone, numbers.month.tone, numbers.month.spent) == (None, None, Decimal("12.00"))


def test_the_month_line_counts_that_month_against_the_monthly_limit():
    expenses = (
        _expense("50.00", day="2026-10-01"), _expense("60.00", day="2026-10-31"), _expense("70.00", day="2026-09-30"),
        _expense("80.00", day="2026-11-01"), _expense("500.00", day="2026-10-15", status="void"),
    )
    numbers = project_numbers(_project(budget="1000.00", monthly="200.00"), expenses, "2026-10")
    assert numbers.month == BudgetLine(Decimal("200.00"), Decimal("110.00"), Decimal("90.00"), 55, "ok")
    assert numbers.total.spent == Decimal("260.00")
    with pytest.raises(ValueError, match="month"):
        project_numbers(_project(), expenses, "2026-13")


def test_an_expense_on_the_last_madrid_evening_counts_in_that_month():
    """Review Focus 3. Madrid runs ahead of UTC, so a month boundary is crossed
    two ways. At 23:59 on 31 October in Madrid (22:59 UTC) the expense is
    October's. At 00:30 on 1 November in Madrid, UTC still reads 31 October,
    yet the expense is November's. The day always comes from months.py, never
    from UTC."""
    last_evening = datetime(2026, 10, 31, 22, 59, tzinfo=timezone.utc)   # 23:59 CET on 31 Oct
    first_night = datetime(2026, 10, 31, 23, 30, tzinfo=timezone.utc)    # 00:30 CET on 1 Nov
    october = _expense("40.00", day=parse_spent_at(None, last_evening))
    november = _expense("15.00", day=parse_spent_at(None, first_night))
    assert (october.spent_at, november.spent_at) == ("2026-10-31", "2026-11-01")
    assert (current_month(last_evening), current_month(first_night)) == ("2026-10", "2026-11")
    project = _project(monthly="100.00")
    in_october = project_numbers(project, (october, november), current_month(last_evening))
    in_november = project_numbers(project, (october, november), current_month(first_night))
    assert (in_october.month.spent, in_october.month.remaining) == (Decimal("40.00"), Decimal("60.00"))
    assert (in_november.month.spent, in_november.month.remaining) == (Decimal("15.00"), Decimal("85.00"))


def test_a_task_shows_planned_spent_and_left_in_the_projects_currency():
    expenses = (
        _expense("100.00", task_id="t-paint"), _expense("50.00", task_id="t-paint", step_id=_STEP.id),
        _expense("20.00", currency="USD", task_id="t-paint"), _expense("70.00", status="void", task_id="t-paint"),
        _expense("999.00", task_id="t-other"), _expense("5.00"),
    )
    assert task_money(_task(budget="300.00", steps=(_STEP,)), expenses, "EUR") == TaskMoney(
        Decimal("300.00"), Decimal("150.00"), Decimal("150.00"))


def test_an_expense_whose_step_was_removed_still_counts_on_the_task():
    expenses = (_expense("10.00", task_id="t-paint", step_id=_STEP.id),
                _expense("25.00", task_id="t-paint", step_id="s2-gone00"))   # that step is no longer on the task
    assert task_money(_task(budget="40.00", steps=(_STEP,)), expenses, "EUR") == TaskMoney(
        Decimal("40.00"), Decimal("35.00"), Decimal("5.00"))


def test_a_task_without_a_slice_has_no_planned_or_left_and_an_overspent_one_goes_negative():
    spent = (_expense("12.00", task_id="t-paint"),)
    assert task_money(_task(), spent, "EUR") == TaskMoney(None, Decimal("12.00"), None)
    assert task_money(_task(budget="10.00"), spent, "EUR").left == Decimal("-2.00")


def test_progress_leaves_cancelled_out_and_counts_failed_apart():
    statuses = ("done", "done", "failed", "todo", "in_progress", "cancelled", "cancelled")
    tasks = tuple(_task(status, task_id=f"t{n}") for n, status in enumerate(statuses))
    assert progress(tasks) == Progress(done=2, failed=1, total=5)
    assert progress(()) == Progress(done=0, failed=0, total=0)
```

**2b.** Create `tests/test_money_summary.py`:

```python
"""The month summary by project (M1 D7, hub H7/H8): each row in its own currency,
against its monthly limit; voids are shown in lists but never summed."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from roost.constants import DEFAULT_PROJECT_COLOR
from roost.money.format import expense_line, summary_text
from roost.money.models import Expense, Project
from roost.money.summary import expense_out, summarize, summary_out
from roost.projects.numbers import BudgetLine

_AT = "2026-10-01T09:00:00+00:00"


def _dec(value: str | None) -> Decimal | None:
    return None if value is None else Decimal(value)


def _project(name: str, *, currency: str = "EUR", budget: str | None = None, monthly: str | None = None,
             status: str = "active") -> Project:
    return Project(
        id=str(uuid4()), user_id="u1", name=name, budget=_dec(budget), currency=currency, created_at=_AT,
        updated_at=_AT, created_by_bot=None, tainted=False, color=DEFAULT_PROJECT_COLOR, start_date=None,
        due_date=None, monthly_budget=_dec(monthly), lead_bot_id=None, status=status,
    )


def _expense(project: Project, amount: str, *, currency: str | None = None, status: str = "posted",
             starred: bool = False, task_id: str | None = None, step_id: str | None = None,
             description: str | None = None) -> Expense:
    return Expense(
        id=str(uuid4()), user_id="u1", project_id=project.id, amount=Decimal(amount),
        currency=currency or project.currency, description=description, vendor=None, spent_at="2026-10-10",
        status=status, created_at=_AT, updated_at=_AT, created_by_bot=None, tainted=False, task_id=task_id,
        step_id=step_id, is_favorite=starred,
    )


def test_each_project_row_is_in_its_own_currency_with_its_other_currencies_apart():
    food = _project("Food", monthly="200.00")
    trip = _project("Trip", currency="USD")
    expenses = (
        _expense(food, "50.00"), _expense(food, "10.00", currency="USD"), _expense(trip, "300.00"),
        _expense(trip, "40.00", currency="EUR"), _expense(food, "99.00", status="void"),
    )
    summary = summarize("2026-10", (food, trip), expenses)
    assert (summary.currency, summary.total, summary.expense_count) == ("EUR", Decimal("90.00"), 4)
    assert dict(summary.other_currencies) == {"USD": Decimal("310.00")}
    trip_row, food_row = summary.by_project
    assert (trip_row.project, trip_row.project_id, trip_row.currency, trip_row.spent) == (
        "Trip", trip.id, "USD", Decimal("300.00"))
    assert dict(trip_row.other_currencies) == {"EUR": Decimal("40.00")}
    assert trip_row.month == BudgetLine(None, Decimal("300.00"), None, None, None)
    assert (food_row.project, food_row.currency, dict(food_row.other_currencies)) == (
        "Food", "EUR", {"USD": Decimal("10.00")})
    assert food_row.month == BudgetLine(Decimal("200.00"), Decimal("50.00"), Decimal("150.00"), 25, "ok")


def test_the_month_row_is_measured_against_the_monthly_limit_not_the_total_budget():
    house = _project("House", budget="1000.00")       # a total budget only
    car = _project("Car", monthly="80.00")
    summary = summarize("2026-10", (house, car), (_expense(house, "100.00"), _expense(car, "100.00")))
    car_row, house_row = summary.by_project            # equal spending: by name
    assert (house_row.budget, house_row.remaining, house_row.month.tone) == (None, None, None)
    assert (car_row.budget, car_row.remaining, car_row.month.used_percent, car_row.month.tone) == (
        Decimal("80.00"), Decimal("-20.00"), 125, "over")


def test_a_void_expense_is_in_none_of_the_sums():
    food = _project("Food")
    summary = summarize("2026-10", (food,), (_expense(food, "12.00", status="void"),))
    assert (summary.total, summary.expense_count, summary.by_project, dict(summary.other_currencies)) == (
        Decimal("0.00"), 0, (), {})


def test_an_archived_project_shows_only_when_it_spent_that_month():
    old = _project("Old flat", monthly="50.00", status="archived")
    gym = _project("Gym", monthly="30.00")
    quiet = summarize("2026-10", (old, gym), ())
    assert [row.project for row in quiet.by_project] == ["Gym"]
    assert quiet.by_project[0].month == BudgetLine(Decimal("30.00"), Decimal("0.00"), Decimal("30.00"), 0, "ok")
    busy = summarize("2026-10", (old, gym), (_expense(old, "20.00"),))
    assert [row.project for row in busy.by_project] == ["Old flat", "Gym"]


def test_summary_out_sends_each_row_with_its_currency_month_bar_and_other_currencies():
    food = _project("Food", monthly="200.00")
    summary = summarize("2026-10", (food,), (_expense(food, "170.00"), _expense(food, "5.00", currency="GBP")))
    assert summary_out(summary) == {
        "month": "2026-10", "currency": "EUR", "total": "170.00", "expense_count": 2,
        "by_project": [{
            "project": "Food", "project_id": food.id, "currency": "EUR",
            "spent": "170.00", "budget": "200.00", "remaining": "30.00",
            "month": {"budget": "200.00", "spent": "170.00", "remaining": "30.00", "used_percent": 85, "tone": "warn"},
            "other_currencies": {"GBP": "5.00"},
        }],
        "other_currencies": {"GBP": "5.00"},
    }


def test_an_expense_row_carries_its_status_star_task_and_step():
    food = _project("Food")
    expense = _expense(food, "9.99", status="void", starred=True, task_id="t-1", step_id="s1-a1b2c3")
    out = expense_out(expense, "Food")
    assert {key: out[key] for key in ("project", "project_id", "amount", "status", "is_favorite", "task_id",
                                      "step_id", "tainted")} == {
        "project": "Food", "project_id": food.id, "amount": "9.99", "status": "void", "is_favorite": True,
        "task_id": "t-1", "step_id": "s1-a1b2c3", "tainted": False}
    assert expense_out(expense, "Food", project_tainted=True)["tainted"] is True


def test_the_summary_text_gives_each_row_its_currency_and_monthly_limit():
    food = _project("Food", monthly="100.00")
    trip = _project("Trip", currency="USD")
    gym = _project("Gym", monthly="50.00")
    expenses = (_expense(food, "120.00"), _expense(trip, "30.00"), _expense(trip, "4.00", currency="EUR"),
                _expense(gym, "20.00"))
    assert summary_text(summarize("2026-10", (food, trip, gym), expenses)) == "\n".join((
        "2026-10 — Total: 144.00 EUR (4 expenses)",
        "- Food: 120.00 EUR of a 100.00 EUR monthly limit, over by 20.00 EUR",
        "- Trip: 30.00 USD, also 4.00 EUR",
        "- Gym: 20.00 EUR of a 50.00 EUR monthly limit, 30.00 EUR left",
        "Also 30.00 USD (not in the total)",
    ))


def test_an_expense_line_marks_void_and_starred():
    food = _project("Food")
    marked = _expense(food, "9.99", status="void", starred=True, description="paint & tape")
    plain = _expense(food, "1.00")
    assert expense_line(marked, "Food") == (
        f"2026-10-10 · Food · 9.99 EUR · paint &amp; tape [void] [starred] id={marked.id}")
    assert expense_line(plain, "Food") == f"2026-10-10 · Food · 1.00 EUR id={plain.id}"
```

**2c.** In `tests/test_money_store.py` **(after Task 1, which replaced the whole file, and Task 2, which changed one line of `test_set_budget_and_top_ups_keep_a_ledger`)**, widen the models import.

Find:

```python
from roost.money.models import ExpenseDraft, ExpensePatch
```

Replace with:

```python
from roost.money.models import EXPENSE_PATCHABLE, ExpenseDraft, ExpensePatch
```

Then append to the end of `tests/test_money_store.py`. It uses the file's own `cfg`, `user_id`, `_food`, `ProjectStore` (after Task 1), `ExpenseStore`, `register_user` and `db_session`:

```python


def test_an_expense_patch_takes_posted_or_void_and_a_yes_or_no_star():
    assert {"task_id", "step_id", "is_favorite", "status"} <= EXPENSE_PATCHABLE
    with pytest.raises(ValueError, match="posted or void"):
        ExpensePatch({"status": "deleted"})
    with pytest.raises(ValueError, match="yes or no"):
        ExpensePatch({"is_favorite": None})


async def test_a_void_expense_stays_visible_and_can_be_posted_again(cfg, user_id):
    food = await _food(cfg, user_id)
    store = ExpenseStore(cfg)
    expense = await store.add(user_id, ExpenseDraft(food.id, Decimal("12.50"), spent_at="2026-10-13"),
                              created_by_bot=None, tainted=False)
    assert expense.status == "posted"
    assert (await store.update(user_id, expense.id, ExpensePatch({"status": "void"}))).status == "void"
    assert (await store.get(user_id, expense.id)).status == "void"
    assert [e.status for e in await store.list_month(user_id, "2026-10")] == ["void"]
    assert (await store.keep(user_id, expense.id)).status == "void"
    assert (await store.update(user_id, expense.id, ExpensePatch({"status": "posted"}))).status == "posted"
    assert (await store.get(user_id, expense.id)).status == "posted"
    await store.delete(user_id, expense.id)
    assert await store.get(user_id, expense.id) is None
    assert await store.update(user_id, expense.id, ExpensePatch({"status": "void"})) is None


async def test_the_star_and_the_task_and_step_links_are_kept_in_plaintext(cfg, user_id):
    food = await _food(cfg, user_id)
    store = ExpenseStore(cfg)
    draft = ExpenseDraft(food.id, Decimal("30"), spent_at="2026-10-13", task_id="t-1", step_id="s1-a1b2c3",
                         is_favorite=True)
    expense = await store.add(user_id, draft, created_by_bot=None, tainted=False)
    again = await store.get(user_id, expense.id)
    assert (again.task_id, again.step_id, again.is_favorite) == ("t-1", "s1-a1b2c3", True)
    await store.update(user_id, expense.id, ExpensePatch({"is_favorite": False, "step_id": None}))
    async with db_session(cfg) as db:
        row = await (await db.execute("SELECT task_id, step_id, is_favorite, status FROM money_expenses WHERE id = ?",
                                      (expense.id,))).fetchone()
    assert tuple(row) == ("t-1", None, 0, "posted")


async def test_list_project_returns_one_projects_expenses_voids_included_newest_first(cfg, user_id):
    food = await _food(cfg, user_id)
    travel = await ProjectStore(cfg).find_or_create(user_id, "Travel", created_by_bot=None, tainted=False)
    store = ExpenseStore(cfg)

    async def add(project_id: str, amount: str, day: str):
        return await store.add(user_id, ExpenseDraft(project_id, Decimal(amount), spent_at=day),
                               created_by_bot=None, tainted=False)

    old = await add(food.id, "1", "2026-09-02")
    new = await add(food.id, "2", "2026-10-02")
    void = await add(food.id, "3", "2026-10-01")
    gone = await add(food.id, "4", "2026-10-03")
    await add(travel.id, "5", "2026-10-04")
    await store.update(user_id, void.id, ExpensePatch({"status": "void"}))
    await store.delete(user_id, gone.id)
    assert [e.id for e in await store.list_project(user_id, food.id)] == [new.id, void.id, old.id]
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    assert await store.list_project(bob, food.id) == ()
```

**2d.** In `tests/test_money_api.py` **(after Task 1, which replaced the whole file)**, find this line in `test_add_an_expense_and_see_it_in_the_month_and_the_summary`:

```python
    assert summary["by_project"] == [{"project": "food", "spent": "12.50", "budget": None, "remaining": None}]
```

Replace with:

```python
    assert summary["by_project"] == [{
        "project": "food", "project_id": expense["project_id"], "currency": "EUR",
        "spent": "12.50", "budget": None, "remaining": None,
        "month": {"budget": None, "spent": "12.50", "remaining": None, "used_percent": None, "tone": None},
        "other_currencies": {},
    }]
    assert (expense["status"], expense["is_favorite"], expense["task_id"], expense["step_id"]) == (
        "posted", False, None, None)
```

In Task 1's `test_the_summary_wire_uses_by_project`, find:

```python
    assert summary["by_project"] == [
        {"project": "food", "spent": "14.50", "budget": None, "remaining": None},
        {"project": "travel", "spent": "5.00", "budget": None, "remaining": None},
    ]
```

Replace with the block below. The rows keep Task 1's four keys and gain four more.

```python
    rows = summary["by_project"]
    assert [{key: row[key] for key in ("project", "spent", "budget", "remaining")} for row in rows] == [
        {"project": "food", "spent": "14.50", "budget": None, "remaining": None},
        {"project": "travel", "spent": "5.00", "budget": None, "remaining": None},
    ]
    assert set(rows[0]) == {"project", "project_id", "currency", "spent", "budget", "remaining", "month",
                            "other_currencies"}
    assert [(row["project_id"], row["currency"]) for row in rows] == [
        (food["project_id"], "EUR"), (travel["project_id"], "EUR")]
```

Then append to the end of `tests/test_money_api.py`. Like the file's keep test, it imports inside the function:

```python


async def test_a_void_expense_is_listed_but_left_out_of_the_summary():
    """H6: a void expense still shows in the month's list (with its status),
    and the summary leaves it out of the total, the count and its project's row."""
    import httpx

    from roost.db.connection import init_db
    from roost.gateway.auth import register_user
    from roost.money.expense_store import ExpenseStore
    from roost.money.models import ExpensePatch

    app = create_app()
    cfg = load_config()
    await init_db(cfg)
    alice_id = (await register_user(cfg, "alice", "pw-123456")).id
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test") as alice:
        await alice.post("/api/auth/login", json={"username": "alice", "password": "pw-123456"}, headers=O)
        kept = (await alice.post("/api/money/expenses", json={"amount": "10"}, headers=O)).json()
        voided = (await alice.post("/api/money/expenses", json={"amount": "99"}, headers=O)).json()
        await ExpenseStore(cfg).update(alice_id, voided["id"], ExpensePatch({"status": "void"}))
        listed = {e["id"]: e["status"] for e in (await alice.get("/api/money/expenses")).json()}
        summary = (await alice.get("/api/money/summary")).json()
    assert listed == {kept["id"]: "posted", voided["id"]: "void"}
    assert (summary["total"], summary["expense_count"]) == ("10.00", 1)
    [row] = summary["by_project"]
    assert (row["project"], row["currency"], row["spent"], row["month"]["tone"]) == ("General", "EUR", "10.00", None)
```

- [ ] **Step 3: Run them to see them fail**

Run them in two commands: a collection error interrupts the whole pytest session, so the two new files would hide the other two.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_project_numbers.py tests/test_money_summary.py -q`

Expected: FAIL at collection, "Interrupted: 2 errors during collection". Both files stop at `ModuleNotFoundError: No module named 'roost.projects'`.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_money_store.py tests/test_money_api.py -q`

Expected: FAIL, `7 failed, 10 passed`.
- In `tests/test_money_store.py`, the seven existing tests pass, and the four new tests fail:
  - `test_an_expense_patch_takes_posted_or_void_and_a_yes_or_no_star`: `AssertionError` (the set is not a subset).
  - `test_a_void_expense_stays_visible_and_can_be_posted_again`: `ValueError: Expenses have no field status.`
  - `test_the_star_and_the_task_and_step_links_are_kept_in_plaintext`: `TypeError: ExpenseDraft.__init__() got an unexpected keyword argument 'task_id'`.
  - `test_list_project_returns_one_projects_expenses_voids_included_newest_first`: `ValueError: Expenses have no field status.`
- In `tests/test_money_api.py`, the other three tests pass, and these three fail:
  - `test_add_an_expense_and_see_it_in_the_month_and_the_summary` fails on the `by_project` row, which has no `currency` or `month`.
  - `test_the_summary_wire_uses_by_project` fails on `set(rows[0])`.
  - `test_a_void_expense_is_listed_but_left_out_of_the_summary` fails with `ValueError: Expenses have no field status.`

- [ ] **Step 4: Give `Task` its project link and budget slice (model only)**

`task_money` reads `task.allocated_budget`, so the two trailing `Task` fields land here, with defaults that change nothing. `TaskStore` still builds `Task` by keyword without them, so they read back as `None` until Task 4 teaches the store, `TaskDraft` and `PATCHABLE_FIELDS`.

In `roost/tasks/models.py`, find:

```python
from dataclasses import dataclass
from types import MappingProxyType
```

Replace with:

```python
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
```

Find:

```python
    created_by_bot: str | None    # NULL: the user, or a retired bot
    tainted: bool                 # written by a run that read outside content


@dataclass(frozen=True)
class TaskDraft:
```

Replace with:

```python
    created_by_bot: str | None    # NULL: the user, or a retired bot
    tainted: bool                 # written by a run that read outside content
    project_id: str | None = None               # one of the user's projects (money_projects.id)
    allocated_budget: Decimal | None = None     # its budget slice, in that project's currency


@dataclass(frozen=True)
class TaskDraft:
```

These two lines and the `Decimal` import are word for word the ones in Task 4's Step 5. Task 4 therefore skips its own `Task` field hunk and its `from decimal import Decimal` line. It keeps its `TaskStatus` / `TaskFilter`, `category` comment, `TaskDraft` and `PATCHABLE_FIELDS` edits.

- [ ] **Step 5: The expense model**

All finds in `roost/money/models.py` are **(after Task 1 and Task 2)**.

**5a. Imports.** Find:

```python
from typing import Any, Mapping
```

Replace with:

```python
from typing import TYPE_CHECKING, Any, Literal, Mapping
```

Task 2 leaves this line as Task 1 wrote it (its own imports are `re`, `Callable`, `fields`, `date` and `parse_amount`).

**5b. The statuses, just before `Expense`.** Find:

```python
@dataclass(frozen=True)
class Expense:
```

Replace with:

```python
ExpenseStatus = Literal["posted", "void"]
EXPENSE_POSTED: ExpenseStatus = "posted"     # counted in the sums
EXPENSE_VOID: ExpenseStatus = "void"         # still shown, never summed (H6)
EXPENSE_STATUSES: tuple[ExpenseStatus, ...] = (EXPENSE_POSTED, EXPENSE_VOID)


@dataclass(frozen=True)
class Expense:
```

**5c. `Expense`'s new fields.** Find:

```python
    spent_at: str             # YYYY-MM-DD, a Madrid day
    status: str
    created_at: str
    updated_at: str
    created_by_bot: str | None
    tainted: bool
```

Replace with:

```python
    spent_at: str             # YYYY-MM-DD, a Madrid day
    status: ExpenseStatus
    created_at: str
    updated_at: str
    created_by_bot: str | None
    tainted: bool
    task_id: str | None = None      # the task it was spent on (a task of any status)
    step_id: str | None = None      # one of that task's steps; an id no longer on the task counts at task level
    is_favorite: bool = False       # starred
```

**5d. `ExpenseDraft`'s new fields.** Find:

```python
    vendor: str | None = None
    spent_at: str = ""
```

Replace with:

```python
    vendor: str | None = None
    spent_at: str = ""
    task_id: str | None = None
    step_id: str | None = None
    is_favorite: bool = False
```

**5e. What a patch may change.** Find **(after Task 1, where `category_id` became `project_id`)**:

```python
EXPENSE_PATCHABLE = frozenset({"project_id", "amount", "currency", "description", "vendor", "spent_at"})
```

Replace with:

```python
EXPENSE_PATCHABLE = frozenset({
    "project_id", "amount", "currency", "description", "vendor", "spent_at", "task_id", "step_id", "is_favorite",
    "status",
})


def _check_values(changes: Mapping[str, Any]) -> None:
    """The two plaintext values a patch could get wrong. No apostrophes in these
    messages: the tools path escapes them for the model."""
    if "status" in changes and changes["status"] not in EXPENSE_STATUSES:
        raise ValueError("The status of an expense is posted or void.")
    if "is_favorite" in changes and not isinstance(changes["is_favorite"], bool):
        raise ValueError("Starred is yes or no.")
```

Find:

```python
            raise ValueError(f"Expenses have no field {', '.join(unknown)}.")
        object.__setattr__(self, "changes", MappingProxyType(dict(self.changes)))
```

Replace with:

```python
            raise ValueError(f"Expenses have no field {', '.join(unknown)}.")
        _check_values(self.changes)
        object.__setattr__(self, "changes", MappingProxyType(dict(self.changes)))
```

**5f. `ProjectTotal`.** Find **(after Task 1)**:

```python
@dataclass(frozen=True)
class ProjectTotal:
    project: str              # the project's name
    spent: Decimal
    budget: Decimal | None

    @property
    def remaining(self) -> Decimal | None:
        return None if self.budget is None else self.budget - self.spent
```

Replace with the block below. `summary.py` (Step 8) builds `ProjectTotal` by these names.

```python
if TYPE_CHECKING:   # roost/projects/numbers.py imports this module; BudgetLine is named here for the annotation only
    from roost.projects.numbers import BudgetLine


@dataclass(frozen=True)
class ProjectTotal:
    """One project's row in a month summary (H7, H8), in the project's own
    currency. ``month`` is its counted spending that month against its
    monthly limit. ``other_currencies`` is what it spent in any other
    currency, never added in. ``spent``, ``budget`` and ``remaining`` read the
    month line, as the Money tab has always shown them."""

    project: str
    project_id: str
    currency: str
    month: BudgetLine
    other_currencies: Mapping[str, Decimal]

    @property
    def spent(self) -> Decimal:
        return self.month.spent

    @property
    def budget(self) -> Decimal | None:
        return self.month.budget

    @property
    def remaining(self) -> Decimal | None:
        return self.month.remaining
```

- [ ] **Step 6: `roost/projects/` and the numbers**

Create `roost/projects/__init__.py`:

```python
"""Projects hub (design P1): one project holds its tasks, money, notes and documents.

Import the modules themselves (``roost.projects.numbers``, later ``.service``
and ``.tools``); this package file imports nothing, so the money and task
modules can use the numbers without an import cycle."""
```

Create `roost/projects/numbers.py`:

```python
"""The projects hub's numbers, in one place (design §2, H6–H8, H11).

These are pure functions over frozen records, with no database and no clock.
The caller passes the Madrid month (``roost.money.months.current_month()``).
``spent_at`` is already a Madrid day, so a month is a plain string range.

A **counted** expense is posted (not void) and in the project's currency.
The stores never return deleted rows, so those can't reach here. Spending in
another currency is listed apart and never converted (P4). The web adds
nothing up: every number here goes out as a string (``roost.money.summary``)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal
from types import MappingProxyType
from typing import Literal, Mapping, Sequence

from roost.constants import BUDGET_OVER_PERCENT, BUDGET_WARN_PERCENT
from roost.money.models import EXPENSE_POSTED, Expense, Project
from roost.money.months import month_bounds
from roost.tasks.models import Task

Tone = Literal["ok", "warn", "over"]

_ZERO = Decimal("0.00")
_HUNDRED = Decimal(100)
_DONE = "done"
_FAILED = "failed"
_CANCELLED = "cancelled"


@dataclass(frozen=True)
class BudgetLine:
    """One budget and its bar (H8).
    - ``remaining`` goes negative when over ("Over by …").
    - ``used_percent`` is spent ÷ budget × 100, rounded DOWN. It therefore
      reads 100 only once the budget is spent, and it may pass 100.
    - With no budget, ``remaining``, ``used_percent`` and ``tone`` are all ``None``."""

    budget: Decimal | None
    spent: Decimal
    remaining: Decimal | None
    used_percent: int | None
    tone: Tone | None


@dataclass(frozen=True)
class ProjectNumbers:
    currency: str
    total: BudgetLine                         # all-time counted spending against ``budget`` (top-ups included)
    month: BudgetLine                         # that Madrid month's counted spending against ``monthly_budget``
    other_currencies: Mapping[str, Decimal]   # posted spending in other currencies, all time, never added in
    starred_total: Decimal                    # counted starred expenses, all time


@dataclass(frozen=True)
class TaskMoney:
    planned: Decimal | None                   # the task's ``allocated_budget``
    spent: Decimal
    left: Decimal | None                      # planned − spent; negative when over


@dataclass(frozen=True)
class Progress:
    done: int
    failed: int                               # finished too, but shown red
    total: int                                # every task except the cancelled ones


def counted(expense: Expense, currency: str) -> bool:
    """Posted and in ``currency``: the only expenses a budget counts."""
    return expense.status == EXPENSE_POSTED and expense.currency == currency


def total_of(expenses: Sequence[Expense]) -> Decimal:
    return sum((expense.amount for expense in expenses), _ZERO)


def per_currency(expenses: Sequence[Expense]) -> Mapping[str, Decimal]:
    """The sum per currency code, with the codes in alphabetical order, read-only."""
    codes = sorted({expense.currency for expense in expenses})
    return MappingProxyType({code: total_of(tuple(e for e in expenses if e.currency == code)) for code in codes})


def _used_percent(budget: Decimal, spent: Decimal) -> int:
    if budget <= 0:   # a budget whose top-ups were all undone: any spending uses it all up
        return 0 if spent <= 0 else BUDGET_OVER_PERCENT
    return int((spent * _HUNDRED / budget).to_integral_value(rounding=ROUND_FLOOR))


def _tone(used_percent: int) -> Tone:
    if used_percent >= BUDGET_OVER_PERCENT:
        return "over"
    return "warn" if used_percent >= BUDGET_WARN_PERCENT else "ok"


def budget_line(budget: Decimal | None, spent: Decimal) -> BudgetLine:
    if budget is None:
        return BudgetLine(budget=None, spent=spent, remaining=None, used_percent=None, tone=None)
    used = _used_percent(budget, spent)
    return BudgetLine(budget=budget, spent=spent, remaining=budget - spent, used_percent=used, tone=_tone(used))


def project_numbers(project: Project, expenses: Sequence[Expense], month: str) -> ProjectNumbers:
    """The numbers on a project's page and its row on the Projects tab.
    - ``month`` is a Madrid month ("2026-10"); a bad one raises ``ValueError`` (``month_bounds``).
    - Expenses of other projects are ignored, so the caller may pass a wider list."""
    first, following = month_bounds(month)
    own = tuple(e for e in expenses if e.project_id == project.id)
    mine = tuple(e for e in own if counted(e, project.currency))
    this_month = tuple(e for e in mine if first <= e.spent_at < following)
    others = tuple(e for e in own if e.status == EXPENSE_POSTED and e.currency != project.currency)
    return ProjectNumbers(
        currency=project.currency,
        total=budget_line(project.budget, total_of(mine)),
        month=budget_line(project.monthly_budget, total_of(this_month)),
        other_currencies=per_currency(others),
        starred_total=total_of(tuple(e for e in mine if e.is_favorite)),
    )


def task_money(task: Task, expenses: Sequence[Expense], currency: str) -> TaskMoney:
    """Planned, spent and left for one task (H11), in ``currency`` (its project's).
    Spent is every counted expense linked to the task, whether or not its
    ``step_id`` is still one of the task's steps. An expense whose step was
    removed therefore stays on the task (LazyClaw's rule), and no row is rewritten."""
    spent = total_of(tuple(e for e in expenses if e.task_id == task.id and counted(e, currency)))
    planned = task.allocated_budget
    return TaskMoney(planned=planned, spent=spent, left=None if planned is None else planned - spent)


def progress(tasks: Sequence[Task]) -> Progress:
    """Done / (all − cancelled). A failed task is finished but counted apart."""
    statuses = tuple(task.status for task in tasks)
    return Progress(done=statuses.count(_DONE), failed=statuses.count(_FAILED),
                    total=sum(1 for status in statuses if status != _CANCELLED))
```

- [ ] **Step 7: The expense store shows voids and lists a project**

Replace the whole of `roost/money/expense_store.py` with the file below. Task 2 does not edit this file. The only differences from the file after Task 1 are these:
- The module docstring lists the new plaintext columns and the void rule.
- `_COLUMNS` and `_MUTABLE` gain the new columns. The new constants `_SECRET`, `_FLAGS` and `_NEWEST_FIRST` name the encrypted columns, the integer flags and the list order.
- `_SHOWN` (`deleted_at IS NULL`) replaces `_LIVE` in every read and in the `keep` and `delete` guards. `update` gains the same guard, which it lacked.
- `_encode` writes both flags as integers, `_row_to_expense` reads the links and the star, and `add` stores them, with `EXPENSE_POSTED` as the status.
- There is a new method, `list_project`.

```python
# SPDX-License-Identifier: MIT
# Adapted from LazyClaw lazyclaw/budgets/store.py @ 21e1002 (project_expenses names and semantics), for Roost
"""``ExpenseStore`` — the user's expenses.

- Amount, description and vendor are ``enc:v2``.
- ``spent_at`` (a Madrid day), the currency, the status, the task and step
  links and the star stay plaintext, so a month is one indexed range query.
- Deleting is soft, as in LazyClaw.
- A void expense is still shown (H6): every read here filters on
  ``deleted_at`` only. The sums leave voids out (``roost.projects.numbers.counted``)."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

import aiosqlite

from roost.config import Config
from roost.crypto.encryption import decrypt_field, encrypt_field, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session
from roost.money.amounts import amount_text
from roost.money.models import EXPENSE_POSTED, Expense, ExpenseDraft, ExpensePatch
from roost.money.months import month_bounds

_COLUMNS = ("id", "user_id", "project_id", "task_id", "step_id", "amount", "currency", "description", "vendor",
            "spent_at", "status", "is_favorite", "created_at", "updated_at", "created_by_bot", "tainted")
_SELECT = ", ".join(_COLUMNS)
_MUTABLE = ("project_id", "task_id", "step_id", "amount", "currency", "description", "vendor", "spent_at", "status",
            "is_favorite", "updated_at")
_SHOWN = "deleted_at IS NULL"
_SECRET = frozenset({"description", "vendor"})
_FLAGS = frozenset({"is_favorite", "tainted"})
_NEWEST_FIRST = "ORDER BY spent_at DESC, created_at DESC"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _aad(user_id: str, column: str) -> bytes:
    return user_aad(user_id, f"money_expenses:{column}")


def _encode(expense: Expense, column: str, dek: bytes) -> Any:
    if column == "amount":
        return encrypt_field(amount_text(expense.amount), dek, _aad(expense.user_id, column))
    if column in _SECRET:
        return encrypt_field(getattr(expense, column), dek, _aad(expense.user_id, column))
    if column in _FLAGS:
        return int(getattr(expense, column))
    return getattr(expense, column)


def _row_to_expense(row: aiosqlite.Row, dek: bytes) -> Expense:
    user_id = row["user_id"]

    def text(column: str) -> str | None:
        return decrypt_field(row[column], dek, _aad(user_id, column))

    return Expense(
        id=row["id"], user_id=user_id, project_id=row["project_id"], amount=Decimal(text("amount") or "0"),
        currency=row["currency"], description=text("description"), vendor=text("vendor"), spent_at=row["spent_at"],
        status=row["status"], created_at=row["created_at"], updated_at=row["updated_at"],
        created_by_bot=row["created_by_bot"], tainted=bool(row["tainted"]), task_id=row["task_id"],
        step_id=row["step_id"], is_favorite=bool(row["is_favorite"]),
    )


class ExpenseStore:
    def __init__(self, config: Config) -> None:
        self._config = config

    async def add(self, user_id: str, draft: ExpenseDraft, *, created_by_bot: str | None, tainted: bool) -> Expense:
        now = _now_iso()
        expense = Expense(
            id=str(uuid4()), user_id=user_id, project_id=draft.project_id, amount=draft.amount,
            currency=draft.currency, description=draft.description, vendor=draft.vendor, spent_at=draft.spent_at,
            status=EXPENSE_POSTED, created_at=now, updated_at=now, created_by_bot=created_by_bot, tainted=tainted,
            task_id=draft.task_id, step_id=draft.step_id, is_favorite=draft.is_favorite,
        )
        dek = await get_user_dek(self._config, user_id)
        async with db_session(self._config) as db:
            await db.execute(f"INSERT INTO money_expenses ({_SELECT}) VALUES ({','.join('?' * len(_COLUMNS))})",
                             tuple(_encode(expense, column, dek) for column in _COLUMNS))
            await db.commit()
        return expense

    async def get(self, user_id: str, expense_id: str) -> Expense | None:
        found = await self._select(user_id, f"WHERE id = ? AND user_id = ? AND {_SHOWN}", (expense_id, user_id))
        return found[0] if found else None

    async def list_month(self, user_id: str, month: str) -> tuple[Expense, ...]:
        """The month's expenses, voids included; sum them with ``numbers.counted``."""
        first, following = month_bounds(month)
        return await self._select(
            user_id, f"WHERE user_id = ? AND {_SHOWN} AND spent_at >= ? AND spent_at < ? {_NEWEST_FIRST}",
            (user_id, first, following),
        )

    async def list_project(self, user_id: str, project_id: str) -> tuple[Expense, ...]:
        """Every expense of one project, all time, voids included, newest first.
        A project's total needs them all, and the amounts are summed in Python."""
        return await self._select(user_id, f"WHERE user_id = ? AND project_id = ? AND {_SHOWN} {_NEWEST_FIRST}",
                                  (user_id, project_id))

    async def made_by(self, user_id: str, bot_id: str, limit: int) -> tuple[Expense, ...]:
        return await self._select(user_id, f"WHERE user_id = ? AND created_by_bot = ? AND {_SHOWN} "
                                           "ORDER BY created_at DESC LIMIT ?", (user_id, bot_id, limit))

    async def update(self, user_id: str, expense_id: str, patch: ExpensePatch) -> Expense | None:
        current = await self.get(user_id, expense_id)
        if current is None:
            return None
        updated = replace(current, **dict(patch.changes), updated_at=_now_iso())
        dek = await get_user_dek(self._config, user_id)
        assignments = ", ".join(f"{column} = ?" for column in _MUTABLE)
        async with db_session(self._config) as db:
            await db.execute(f"UPDATE money_expenses SET {assignments} WHERE id = ? AND user_id = ? AND {_SHOWN}",
                             (*(_encode(updated, column, dek) for column in _MUTABLE), expense_id, user_id))
            await db.commit()
        return updated

    async def keep(self, user_id: str, expense_id: str) -> Expense | None:
        """The user vouches for an expense (the Board's Keep): its taint bit is
        cleared. Only the HTTP route reaches this; ``ExpensePatch`` can't."""
        async with db_session(self._config) as db:
            await db.execute(
                f"UPDATE money_expenses SET tainted = 0, updated_at = ? WHERE id = ? AND user_id = ? AND {_SHOWN}",
                (_now_iso(), expense_id, user_id),
            )
            await db.commit()
        return await self.get(user_id, expense_id)

    async def delete(self, user_id: str, expense_id: str) -> bool:
        now = _now_iso()
        async with db_session(self._config) as db:
            cursor = await db.execute(
                f"UPDATE money_expenses SET deleted_at = ?, updated_at = ? WHERE id = ? AND user_id = ? AND {_SHOWN}",
                (now, now, expense_id, user_id),
            )
            await db.commit()
        return cursor.rowcount > 0

    async def _select(self, user_id: str, where: str, params: tuple) -> tuple[Expense, ...]:
        async with db_session(self._config) as db:
            rows = await (await db.execute(f"SELECT {_SELECT} FROM money_expenses {where}", params)).fetchall()
        if not rows:
            return ()
        dek = await get_user_dek(self._config, user_id)
        return tuple(_row_to_expense(row, dek) for row in rows)
```

- [ ] **Step 8: The summary in each project's currency, and the wire**

Replace the whole of `roost/money/summary.py` with:

```python
# SPDX-License-Identifier: MIT
# Adapted from LazyClaw lazyclaw/budgets/store.py @ 21e1002 (spending_report semantics), for Roost
"""Month totals by project (M1 D7, hub H7/H8).

- Each project row is in the project's own currency, against its monthly
  limit, with its other currencies listed apart and never converted.
- The top-level total stays the month's spending in the default currency
  (every posted EUR expense, whatever its project), for compatibility.
- A void expense is shown in lists but never summed.
- The wire sends every amount as a string: the web never adds them."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping

from roost.constants import DEFAULT_CURRENCY, PROJECT_STATUSES
from roost.money.amounts import amount_text
from roost.money.models import EXPENSE_POSTED, Expense, MoneySummary, Project, ProjectTotal
from roost.projects.numbers import BudgetLine, budget_line, counted, per_currency, total_of

_ACTIVE = PROJECT_STATUSES[0]


def _project_total(project: Project, posted: tuple[Expense, ...]) -> ProjectTotal:
    own = tuple(e for e in posted if e.project_id == project.id)
    return ProjectTotal(
        project=project.name, project_id=project.id, currency=project.currency,
        month=budget_line(project.monthly_budget, total_of(tuple(e for e in own if counted(e, project.currency)))),
        other_currencies=per_currency(tuple(e for e in own if e.currency != project.currency)),
    )


def _shown(project: Project, row: ProjectTotal) -> bool:
    """A project that spent this month (in any currency), or an active one with
    a monthly limit. An archived project's empty month is not news."""
    spent = row.spent > 0 or bool(row.other_currencies)
    return spent or (project.monthly_budget is not None and project.status == _ACTIVE)


def summarize(month: str, projects: tuple[Project, ...], expenses: tuple[Expense, ...]) -> MoneySummary:
    posted = tuple(e for e in expenses if e.status == EXPENSE_POSTED)
    totals = tuple((project, _project_total(project, posted)) for project in projects)
    rows = tuple(row for project, row in totals if _shown(project, row))
    return MoneySummary(
        month=month, currency=DEFAULT_CURRENCY,
        total=total_of(tuple(e for e in posted if e.currency == DEFAULT_CURRENCY)),
        expense_count=len(posted), by_project=tuple(sorted(rows, key=lambda r: (-r.spent, r.project.casefold()))),
        other_currencies=per_currency(tuple(e for e in posted if e.currency != DEFAULT_CURRENCY)),
    )


def _optional(amount: Decimal | None) -> str | None:
    return None if amount is None else amount_text(amount)


def amounts_out(amounts: Mapping[str, Decimal]) -> dict[str, str]:
    return {code: amount_text(total) for code, total in amounts.items()}


def budget_line_out(line: BudgetLine) -> dict[str, Any]:
    """``BudgetLineOut``: the amounts as strings, plus the bar's percent and tone (H8)."""
    return {"budget": _optional(line.budget), "spent": amount_text(line.spent), "remaining": _optional(line.remaining),
            "used_percent": line.used_percent, "tone": line.tone}


def project_total_out(row: ProjectTotal) -> dict[str, Any]:
    """One ``by_project`` row. ``spent``, ``budget`` and ``remaining`` repeat the
    month line for the Money tab as it is today; ``month`` adds the bar."""
    return {
        "project": row.project, "project_id": row.project_id, "currency": row.currency,
        "spent": amount_text(row.spent), "budget": _optional(row.budget), "remaining": _optional(row.remaining),
        "month": budget_line_out(row.month), "other_currencies": amounts_out(row.other_currencies),
    }


def summary_out(summary: MoneySummary) -> dict[str, Any]:
    return {
        "month": summary.month, "currency": summary.currency, "total": amount_text(summary.total),
        "expense_count": summary.expense_count, "by_project": [project_total_out(row) for row in summary.by_project],
        "other_currencies": amounts_out(summary.other_currencies),
    }


def expense_row(expense: Expense, project: Project | None) -> dict[str, Any]:
    if project is None:
        return expense_out(expense, "")
    return expense_out(expense, project.name, project_tainted=project.tainted)


def expense_out(expense: Expense, project: str, *, project_tainted: bool = False) -> dict[str, Any]:
    """``tainted`` marks the row "from web content" when the expense OR the
    project name it shows was web-made. Either one taints a run that lists
    it, so the Board must offer Keep for both."""
    return {
        "id": expense.id, "project": project, "project_id": expense.project_id, "task_id": expense.task_id,
        "step_id": expense.step_id, "amount": amount_text(expense.amount), "currency": expense.currency,
        "description": expense.description, "vendor": expense.vendor, "spent_at": expense.spent_at,
        "status": expense.status, "is_favorite": expense.is_favorite, "created_at": expense.created_at,
        "created_by_bot": expense.created_by_bot, "tainted": expense.tainted or project_tainted,
    }
```

- [ ] **Step 9: The tool text marks void and starred, and gives each row its currency**

Replace the whole of `roost/money/format.py` with:

```python
"""Tool-result text for money. User and page text is escaped here, by its
producer (tool results reach the model raw)."""

from __future__ import annotations

import html
from decimal import Decimal

from roost.money.amounts import amount_text
from roost.money.models import EXPENSE_VOID, Expense, MoneySummary, ProjectTotal


def escape(text: str) -> str:
    return html.escape(text, quote=True)


def money(amount: Decimal, currency: str) -> str:
    return f"{amount_text(amount)} {currency}"


def _marks(expense: Expense) -> str:
    void = " [void]" if expense.status == EXPENSE_VOID else ""
    starred = " [starred]" if expense.is_favorite else ""
    web = " [from web content]" if expense.tainted else ""
    return f"{void}{starred}{web}"


def expense_line(expense: Expense, project: str) -> str:
    note = f" · {escape(expense.description)}" if expense.description else ""
    amount = money(expense.amount, expense.currency)
    return f"{expense.spent_at} · {escape(project)} · {amount}{note}{_marks(expense)} id={expense.id}"


def _limit(row: ProjectTotal) -> str:
    if row.budget is None or row.remaining is None:
        return ""
    left = (f"{money(row.remaining, row.currency)} left" if row.remaining >= 0
            else f"over by {money(-row.remaining, row.currency)}")
    return f" of a {money(row.budget, row.currency)} monthly limit, {left}"


def _row_line(row: ProjectTotal) -> str:
    also = "".join(f", also {money(total, code)}" for code, total in row.other_currencies.items())
    return f"- {escape(row.project)}: {money(row.spent, row.currency)}{_limit(row)}{also}"


def summary_text(summary: MoneySummary) -> str:
    head = f"{summary.month} — Total: {money(summary.total, summary.currency)} ({summary.expense_count} expenses)"
    rows = tuple(_row_line(row) for row in summary.by_project)
    others = tuple(f"Also {money(total, code)} (not in the total)"
                   for code, total in summary.other_currencies.items())
    return "\n".join((head, *rows, *others))
```

- [ ] **Step 10: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_project_numbers.py tests/test_money_summary.py tests/test_money_store.py tests/test_money_api.py -q`
Expected: PASS.
- `test_project_numbers.py`: 15 tests, including `test_an_expense_on_the_last_madrid_evening_counts_in_that_month`.
- `test_money_summary.py`: 8 tests.
- `test_money_store.py` and `test_money_api.py`: every test, the old ones included.

The related tests must stay green. `test_money_tools.py` still finds `"food: 12.50 EUR"`, `"Total: 10.00 EUR"` and `"Also 20.00 USD"` in the summary text. The task tests stay green because `Task` gained only defaulted fields.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_money_tools.py tests/test_money_values.py tests/test_project_store.py tests/test_migrations_v12.py tests/test_profile_api.py tests/test_tool_text.py tests/test_document_tools.py tests/test_every_bot_tools.py tests/test_task_store.py tests/test_task_tools.py tests/test_tasks_api.py -q`
Expected: PASS.

Then check the whole suite and coverage:

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest -q --cov=roost --cov-fail-under=80`
Expected: PASS, with `roost/projects/numbers.py` at 100%. If the coverage report is too coarse, check it with `uv run pytest tests/test_project_numbers.py tests/test_money_summary.py -q --cov=roost.projects --cov=roost.money.summary --cov=roost.money.format --cov-report=term-missing`.

- [ ] **Step 11: Commit**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && git add roost/projects/__init__.py roost/projects/numbers.py roost/money/models.py roost/money/expense_store.py roost/money/summary.py roost/money/format.py roost/tasks/models.py tests/test_project_numbers.py tests/test_money_summary.py tests/test_money_store.py tests/test_money_api.py && git commit -m "feat: void and starred expenses linked to a task step, and one place for project numbers"
```

The message has no Co-Authored-By line and no AI attribution.

---

### Task 4: Tasks: project link, budget slice, failed, and the day summary

This task implements P1, P2 and P6 for tasks: a task can belong to a project, it can carry a budget slice, the "failed" status comes back, and the end-of-day summary gets its content. It follows H11 and H13, which override §1–§3.

- **The link.** `tasks.project_id` is a plaintext id (the v13 column from Task 2) and is optional.
  - The store refuses a project that isn't the user's: another user's project, a deleted one, or an unknown id. It runs `require_project` (new `roost/records/project_link.py`) inside the **same** `db_session` as the INSERT or UPDATE. The session holds the pooled connection's lock, so the project can't be deleted between the check and the write.
  - A refusal raises `ValueError("No such project.")` and writes nothing. Tasks 7 and 8 turn that into "Refused: No such project." and 422.
  - An archived project may still be linked.
- **The budget slice.** `allocated_budget` is `enc:v2` under `user_aad(user_id, "tasks:allocated_budget")` and holds `amount_text` (for example `"250.00"`). It reads back as a `Decimal`.
  - A slice needs a project (H11): `ValueError("A budget slice needs a project.")`.
  - It follows `parse_amount`'s rules: more than 0, at most 2 decimals, at most `MAX_EXPENSE_AMOUNT`.
  - These rules are checked whenever a slice is **set**: on `create`, and on an `update` whose patch carries a non-null `allocated_budget`.
  - Clearing the project keeps the slice, exactly as H9's delete does. A later title change on such a task still works. The respawn doesn't carry a slice that has no project.
  - A slice that doesn't decrypt or doesn't read as an amount (a damaged row) reads as `None` and is logged.
- **Failed.** `TaskStore.fail` is a twin of `complete`. It sets `status="failed"`, `completed_at` and `updated_at`, with the same compare-and-set guard on the open statuses, and **no** step cascade, because a failed task didn't do its steps.
  - `TaskService.fail` publishes `tasks_changed` / `"failed"` and respawns a recurring task. `respawn_draft` copies `project_id` and `allocated_budget`.
  - If the project was deleted between the close and the respawn, the next occurrence comes back unlinked and a warning is logged, instead of the close failing halfway.
- **Filters.** `done` stays `status = 'done'`, so it leaves failed tasks out, and a new `failed` filter exists. `list(..., project_id=)` adds a fixed `" AND project_id = ?"` fragment and its parameter.
- **`closed_between`** returns done and failed tasks with `completed_at` in `[start, end)`. Each bound is parsed and rewritten as UTC `isoformat()`, the exact shape `_now_iso()` writes `completed_at` in, so the text comparison is the time comparison. A bound with no time zone is refused.
- **`unlink_project`** sets `project_id` to NULL on every one of the user's tasks of that project and returns how many it changed. It runs exactly the statement Task 2's `_hand_over` runs for `tasks` (deleted tasks included, `updated_at` untouched, the slice kept), so the two H9 paths can't drift apart. Task 2's delete runs its own SQL in one transaction, since Task 2 lands before this task. This method is here for the contract and for later callers.
- **The day summary** (`roost/tasks/day_summary.py`, H13) builds the content for one Madrid day:
  - the tasks closed that day (`closed_between` over `madrid_day_bounds_utc(day)`, so a clock-change day is 23 or 25 hours long);
  - the open tasks that are overdue, judged in Python at `now`: a date-only due is overdue when it is earlier than today in Madrid, and a timed due when it is earlier than `now`;
  - that day's counted expenses per currency: `ExpenseStore.list_month` (which shows voids after Task 3), kept by Task 3's `counted(expense, expense.currency)` and summed by Task 3's `per_currency`.

  No tool or route uses it yet; the scheduler (part 2) will send it.

No tool, route or web change is made here. The tool arguments are Task 7. The `POST /api/tasks/{id}/fail` route and `?project_id=` are Task 8. The existing `GET /api/tasks?status=` takes `failed` as soon as `TaskFilter` gains it.

**Where the snippets start from.** No file in this task is touched by the stuck flow, so no snippet here is marked "(after the stuck flow)". Task 3 already gave `Task` its two trailing fields (`project_id`, `allocated_budget`) and `roost/tasks/models.py` its `from decimal import Decimal` import (Task 3, Step 4), so this task adds neither again; the `roost/tasks/models.py` finds are marked **(after Task 3)**. `roost/tasks/store.py`, `service.py` and `format.py` are touched by no earlier task, so their finds are today's code.

**Files:**
- Create:
  - `roost/records/project_link.py`: `NO_SUCH_PROJECT_TEXT` and `require_project(db, user_id, project_id)`, the one ownership check that the task, note and document stores share. Task 5 consumes it.
  - `roost/tasks/day_summary.py`: `DaySummary`, `madrid_day_bounds_utc`, `build_day_summary` and `day_summary_text`.
- Modify:
  - `roost/tasks/models.py` **(after Task 3)**:
    - `TaskStatus` and `TaskFilter` gain `"failed"`;
    - `TaskDraft` gains trailing `project_id` and `allocated_budget`;
    - `PATCHABLE_FIELDS` gains both;
    - the `category` comment says "list".
  - `roost/tasks/store.py`:
    - module docstring;
    - `SLICE_NEEDS_PROJECT` and a module `logger`;
    - `_COLUMNS`, `_MUTABLE` and `_FILTERS`, plus `_OPEN_SQL`, `_OPEN_STATUSES`, `_PROJECT_SQL` and `_CLOSED_SQL`;
    - new `_checked_slice` and `_utc_bound`;
    - `_encode` and `_row_to_task` (with the new `_slice`);
    - `create` and `update` check the slice; `create` and `_write` check the project;
    - `list(..., project_id=None)`;
    - new `fail`, `closed_between` and `unlink_project`.
  - `roost/tasks/service.py`:
    - `TaskChange` gains `"failed"`;
    - `respawn_draft` copies the project and its slice;
    - `list(..., project_id=None)`;
    - new `fail`;
    - `_respawn` and the new `_add_next`.
  - `roost/tasks/format.py`: `_STATUS_ICON["failed"]`, and `project_id` and `allocated_budget` in `task_out`.
- Test:
  - `tests/test_task_projects.py` (new)
  - `tests/test_day_summary.py` (new)

**Interfaces:**
- Consumes:
  - Task 1: `ProjectStore` from `roost/money/project_store.py`; `ExpenseDraft(project_id=..., amount=..., currency=..., spent_at=...)`.
  - Task 2: the v13 columns `tasks.project_id` and `tasks.allocated_budget`, and `money_projects.deleted_at` as the live-project test; `ProjectDraft(name=...)`; `ProjectStore.create(user_id, draft, *, created_by_bot, tainted) -> Project`; `ProjectStore.delete(user_id, project_id) -> bool`.
  - Task 3:
    - `Task.project_id: str | None = None` and `Task.allocated_budget: Decimal | None = None` (already on `Task`), and the `Decimal` import in `roost/tasks/models.py`;
    - `counted(expense: Expense, currency: str) -> bool` and `per_currency(expenses) -> Mapping[str, Decimal]` (*extra* of Task 3) from `roost/projects/numbers.py`;
    - `ExpensePatch({"status": "void"})` and `ExpenseStore.list_month` showing voids.
  - Existing:
    - `ExpenseStore.list_month(user_id, month)`, `ExpenseStore.add`, `ExpenseStore.update`, `ExpenseStore.delete`;
    - `parse_amount` and `amount_text` (`roost/money/amounts.py`), `MADRID_TZ` (`roost/talk/instructions.py`);
    - `task_line`, `Completion`, `next_occurrence_fields`, `series_ended`, `EventHub.since`, `get_user_dek`, `decrypt`, `decrypt_field`, `user_aad`.
- Produces (exactly the Shared Contract, plus the names marked *extra*):
  - `roost/tasks/models.py`:
    - `TaskStatus = Literal["todo", "in_progress", "done", "cancelled", "failed"]`;
    - `TaskFilter = Literal["open", "done", "failed", "all"]`;
    - `TaskDraft.project_id: str | None = None` and `TaskDraft.allocated_budget: Decimal | None = None` (the `Task` pair comes from Task 3);
    - `PATCHABLE_FIELDS` ⊇ `{"project_id", "allocated_budget"}`.
  - `roost/tasks/store.py` `TaskStore`:
    - `list(user_id, *, status="open", project_id=None)`;
    - `fail(user_id, task_id) -> Task | None`;
    - `closed_between(user_id, start_utc, end_utc) -> tuple[Task, ...]`, oldest first;
    - `unlink_project(user_id, project_id) -> int`;
    - `create` and `update` raise `ValueError` with "No such project.", "A budget slice needs a project." or `parse_amount`'s message, and write nothing;
    - `SLICE_NEEDS_PROJECT` (*extra*).
  - `roost/tasks/service.py`:
    - `TaskChange` gains `"failed"`;
    - `TaskService.fail(user_id, task_id) -> Completion | None`, where `Completion.done` holds the failed task;
    - `TaskService.list(user_id, *, status="open", project_id=None)` (*extra*, for Task 8's `?project_id=`).
    - `TaskService.add` and `update` let the store's `ValueError` through. `TaskTools.run` already turns a `ValueError` into "Refused: …". **Task 8 must call `update` inside the route's `try`**: today `PATCH /api/tasks/{id}` calls it outside, which would turn "No such project." into a 500.
  - `roost/tasks/format.py`: the `task_line` mark `[✗]` for failed; `task_out(task)` gains `"project_id"` (a string or null) and `"allocated_budget"` (`"250.00"` or null).
  - `roost/records/project_link.py`: `NO_SUCH_PROJECT_TEXT = "No such project."` and `async def require_project(db: aiosqlite.Connection, user_id: str, project_id: str | None) -> None`.
  - `roost/tasks/day_summary.py`: `DaySummary`, `madrid_day_bounds_utc(day) -> tuple[str, str]`, `build_day_summary(user_id, day, *, tasks, expenses, now=None) -> DaySummary` and `day_summary_text(summary) -> str`, exactly as in the contract. A bad `day` raises `ValueError("“…” is not a day like 2026-10-14.")`, and a naive `now` raises `ValueError`.

- [ ] **Step 1: Path guard**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

Then confirm that Tasks 2 and 3 have landed, since this task builds on them:

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && grep -n 'AddColumn("tasks", "allocated_budget"' roost/db/migrations.py && grep -n "async def create\|async def delete" roost/money/project_store.py && grep -n "^def counted\|^def per_currency" roost/projects/numbers.py && grep -n "allocated_budget: Decimal | None = None" roost/tasks/models.py && test ! -e roost/records/project_link.py && echo "no project_link yet"`
Expected:
- one line from `migrations.py`;
- the `create` and `delete` lines of `ProjectStore`;
- the `counted` and `per_currency` lines;
- exactly one line from `roost/tasks/models.py` (the `Task` field Task 3 added);
- `no project_link yet`.

If any line is missing, stop: Task 2 or 3 comes first. If `roost/records/project_link.py` already exists, compare it with Step 4 and keep the existing file if `NO_SUCH_PROJECT_TEXT` and `require_project` match.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_task_projects.py`:

```python
"""Tasks learn projects (projects hub, H11): the project link and its budget
slice (enc:v2 under tasks:allocated_budget), the failed status and its
respawn, the failed and project filters, closed_between and unlink_project.

A project that isn't the user's (another user's, a deleted one, an unknown
id) is refused with "No such project." and nothing is written."""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from roost.config import load_config
from roost.crypto.encryption import decrypt, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session, init_db
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.money.models import ProjectDraft
from roost.money.project_store import ProjectStore
from roost.tasks.format import task_line, task_out
from roost.tasks.models import TaskDraft, TaskPatch
from roost.tasks.service import TaskService, respawn_draft
from roost.tasks.store import TaskStore

_REFUSED = r"^No such project\.$"
_NEEDS_PROJECT = r"^A budget slice needs a project\.$"


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


@pytest.fixture
def store(cfg):
    return TaskStore(cfg)


async def _project(cfg, user_id, name="Renovation"):
    return await ProjectStore(cfg).create(user_id, ProjectDraft(name=name), created_by_bot=None, tainted=False)


async def _task(store, user_id, title="Paint the hall", **fields):
    return await store.create(user_id, TaskDraft(title=title, **fields), created_by_bot=None, tainted=False)


async def _set_completed_at(cfg, task_id, completed_at):
    async with db_session(cfg) as db:
        await db.execute("UPDATE tasks SET completed_at = ? WHERE id = ?", (completed_at, task_id))
        await db.commit()


async def test_a_task_keeps_its_project_and_budget_slice(cfg, store, user_id):
    project = await _project(cfg, user_id)
    task = await _task(store, user_id, project_id=project.id, allocated_budget=Decimal("250"))
    again = await store.get(user_id, task.id)
    assert (task.project_id, task.allocated_budget) == (project.id, Decimal("250.00"))
    assert (again.project_id, again.allocated_budget) == (project.id, Decimal("250.00"))


async def test_a_task_with_no_project_has_no_slice(cfg, store, user_id):
    task = await _task(store, user_id)
    assert (task.project_id, task.allocated_budget) == (None, None)
    out = task_out(task)
    assert (out["project_id"], out["allocated_budget"]) == (None, None)
    async with db_session(cfg) as db:
        row = await (await db.execute("SELECT project_id, allocated_budget FROM tasks WHERE id = ?",
                                      (task.id,))).fetchone()
    assert (row["project_id"], row["allocated_budget"]) == (None, None)


async def test_the_budget_slice_is_ciphertext_under_its_own_aad(cfg, store, user_id):
    project = await _project(cfg, user_id)
    task = await _task(store, user_id, project_id=project.id, allocated_budget=Decimal("12.5"))
    async with db_session(cfg) as db:
        row = await (await db.execute("SELECT project_id, allocated_budget FROM tasks WHERE id = ?",
                                      (task.id,))).fetchone()
    assert row["project_id"] == project.id                    # ids stay plaintext
    assert row["allocated_budget"].startswith("enc:v2:") and "12.50" not in row["allocated_budget"]
    dek = await get_user_dek(cfg, user_id)
    assert decrypt(row["allocated_budget"], dek, user_aad(user_id, "tasks:allocated_budget")) == "12.50"


async def test_a_slice_copied_from_another_column_reads_as_none(cfg, store, user_id, caplog):
    project = await _project(cfg, user_id)
    task = await _task(store, user_id, project_id=project.id, allocated_budget=Decimal("40"))
    async with db_session(cfg) as db:
        await db.execute("UPDATE tasks SET allocated_budget = title WHERE id = ?", (task.id,))
        await db.commit()
    with caplog.at_level(logging.WARNING, logger="roost.tasks.store"):
        again = await store.get(user_id, task.id)
    assert (again.title, again.allocated_budget) == ("Paint the hall", None)
    assert any(task.id in record.getMessage() and "unreadable budget slice" in record.getMessage()
               for record in caplog.records)


async def test_another_users_project_is_refused(cfg, store, user_id):
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    bobs = await _project(cfg, bob, "Garage")
    with pytest.raises(ValueError, match=_REFUSED):
        await _task(store, user_id, "Fix the door", project_id=bobs.id)
    task = await _task(store, user_id)
    with pytest.raises(ValueError, match=_REFUSED):
        await store.update(user_id, task.id, TaskPatch({"project_id": bobs.id}))
    assert [(t.title, t.project_id) for t in await store.list(user_id, status="all")] == [("Paint the hall", None)]


async def test_an_unknown_or_deleted_project_is_refused(cfg, store, user_id):
    gone = await _project(cfg, user_id, "Old flat")
    assert await ProjectStore(cfg).delete(user_id, gone.id) is True
    for project_id in ("no-such-project", gone.id):
        with pytest.raises(ValueError, match=_REFUSED):
            await _task(store, user_id, project_id=project_id)
    assert await store.list(user_id, status="all") == ()


async def test_a_budget_slice_needs_a_project(cfg, store, user_id):
    with pytest.raises(ValueError, match=_NEEDS_PROJECT):
        await _task(store, user_id, allocated_budget=Decimal("10"))
    task = await _task(store, user_id)
    with pytest.raises(ValueError, match=_NEEDS_PROJECT):
        await store.update(user_id, task.id, TaskPatch({"allocated_budget": Decimal("10")}))
    assert (await store.get(user_id, task.id)).allocated_budget is None


@pytest.mark.parametrize(("amount", "reason"), (
    (Decimal("0"), "more than 0"), (Decimal("-5"), "more than 0"), (Decimal("1000001"), "more than 0"),
    (Decimal("1.005"), "at most 2 decimals"),
))
async def test_a_budget_slice_follows_the_amount_rules(cfg, store, user_id, amount, reason):
    project = await _project(cfg, user_id)
    with pytest.raises(ValueError, match=reason):
        await _task(store, user_id, project_id=project.id, allocated_budget=amount)
    assert await store.list(user_id, status="all") == ()


async def test_the_project_and_its_slice_can_be_changed_and_cleared(cfg, store, user_id):
    house, garden = await _project(cfg, user_id), await _project(cfg, user_id, "Garden")
    task = await _task(store, user_id, project_id=house.id, allocated_budget=Decimal("100"))
    moved = await store.update(user_id, task.id, TaskPatch({"project_id": garden.id, "allocated_budget": Decimal("40")}))
    assert (moved.project_id, moved.allocated_budget) == (garden.id, Decimal("40.00"))
    cleared = await store.update(user_id, task.id, TaskPatch({"allocated_budget": None}))
    assert (cleared.project_id, cleared.allocated_budget) == (garden.id, None)
    await store.update(user_id, task.id, TaskPatch({"project_id": None}))
    again = await store.get(user_id, task.id)
    assert (again.project_id, again.allocated_budget) == (None, None)


async def test_an_unrelated_change_leaves_an_unlinked_slice_alone(cfg, store, user_id):
    """H9 unlinks a deleted project's tasks and keeps their slices. A later
    title change on such a task must still go through."""
    project = await _project(cfg, user_id)
    task = await _task(store, user_id, project_id=project.id, allocated_budget=Decimal("30"))
    assert await store.unlink_project(user_id, project.id) == 1
    renamed = await store.update(user_id, task.id, TaskPatch({"title": "Paint the hall white"}))
    assert (renamed.title, renamed.project_id, renamed.allocated_budget) == ("Paint the hall white", None, Decimal("30.00"))


def test_a_patch_can_carry_the_project_and_the_slice():
    patch = TaskPatch({"project_id": None, "allocated_budget": None})
    assert dict(patch.changes) == {"project_id": None, "allocated_budget": None}


async def test_list_filters_by_project(cfg, store, user_id):
    house, garden = await _project(cfg, user_id), await _project(cfg, user_id, "Garden")
    await _task(store, user_id, "Paint", project_id=house.id)
    await _task(store, user_id, "Tiles", project_id=house.id)
    await _task(store, user_id, "Mow", project_id=garden.id)
    await _task(store, user_id, "Dentist")
    plaster = await _task(store, user_id, "Plaster", project_id=house.id)
    await store.complete(user_id, plaster.id)
    assert {t.title for t in await store.list(user_id, project_id=house.id)} == {"Paint", "Tiles"}
    assert {t.title for t in await store.list(user_id, status="all", project_id=house.id)} == {"Paint", "Tiles", "Plaster"}
    assert [t.title for t in await store.list(user_id, status="done", project_id=house.id)] == ["Plaster"]
    assert len(await store.list(user_id)) == 4
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    assert await store.list(bob, status="all", project_id=house.id) == ()


async def test_fail_closes_an_open_task_once_and_leaves_its_steps_open(cfg, store, user_id):
    task = await _task(store, user_id, steps=("buy paint",))
    failed = await store.fail(user_id, task.id)
    assert (failed.status, failed.steps[0].done) == ("failed", False) and failed.completed_at
    again = await store.get(user_id, task.id)
    assert (again.status, again.completed_at, again.steps[0].done) == ("failed", failed.completed_at, False)
    assert await store.fail(user_id, task.id) is None             # already failed
    assert await store.complete(user_id, task.id) is None         # and no longer open


async def test_only_an_open_task_of_your_own_can_fail(cfg, store, user_id):
    done = await _task(store, user_id, "done")
    await store.complete(user_id, done.id)
    cancelled = await _task(store, user_id, "cancelled")
    await store.update(user_id, cancelled.id, TaskPatch({"status": "cancelled"}))
    started = await _task(store, user_id, "started")
    await store.update(user_id, started.id, TaskPatch({"status": "in_progress"}))
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    assert await store.fail(user_id, done.id) is None
    assert await store.fail(user_id, cancelled.id) is None
    assert await store.fail(bob, started.id) is None
    assert await store.fail(user_id, "no-such-task") is None
    assert (await store.fail(user_id, started.id)).status == "failed"


async def test_the_done_filter_leaves_failed_tasks_out_and_the_failed_filter_has_them(cfg, store, user_id):
    done = await _task(store, user_id, "done")
    failed = await _task(store, user_id, "failed")
    await _task(store, user_id, "open")
    await store.complete(user_id, done.id)
    await store.fail(user_id, failed.id)
    assert [t.title for t in await store.list(user_id, status="done")] == ["done"]
    assert [t.title for t in await store.list(user_id, status="failed")] == ["failed"]
    assert [t.title for t in await store.list(user_id)] == ["open"]
    assert len(await store.list(user_id, status="all")) == 3


async def test_closed_between_has_the_done_and_failed_tasks_of_the_window(cfg, store, user_id):
    window = ("2026-10-13T22:00:00+00:00", "2026-10-14T22:00:00+00:00")       # 2026-10-14 in Madrid
    for title, close, at in (
        ("too early", store.complete, "2026-10-13T21:59:59.999999+00:00"),
        ("first", store.complete, "2026-10-13T22:00:00+00:00"),
        ("failed", store.fail, "2026-10-14T12:30:00.250000+00:00"),
        ("last", store.complete, "2026-10-14T21:59:59.999999+00:00"),
        ("too late", store.fail, "2026-10-14T22:00:00+00:00"),
    ):
        task = await _task(store, user_id, title)
        await close(user_id, task.id)
        await _set_completed_at(cfg, task.id, at)
    gone = await _task(store, user_id, "deleted")
    await store.complete(user_id, gone.id)
    await _set_completed_at(cfg, gone.id, "2026-10-14T10:00:00+00:00")
    await store.delete(user_id, gone.id)
    cancelled = await _task(store, user_id, "cancelled")
    await store.update(user_id, cancelled.id, TaskPatch({"status": "cancelled"}))
    await _set_completed_at(cfg, cancelled.id, "2026-10-14T10:00:00+00:00")
    await _task(store, user_id, "open")
    closed = await store.closed_between(user_id, *window)
    assert [(t.title, t.status) for t in closed] == [("first", "done"), ("failed", "failed"), ("last", "done")]


async def test_closed_between_reads_any_offset_as_utc_and_refuses_a_bare_time(cfg, store, user_id):
    task = await _task(store, user_id)
    await store.complete(user_id, task.id)
    await _set_completed_at(cfg, task.id, "2026-10-14T21:30:00+00:00")         # 23:30 in Madrid
    madrid = ("2026-10-14T00:00:00+02:00", "2026-10-15T00:00:00+02:00")
    assert [t.id for t in await store.closed_between(user_id, *madrid)] == [task.id]
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    assert await store.closed_between(bob, *madrid) == ()
    with pytest.raises(ValueError, match="has no time zone"):
        await store.closed_between(user_id, "2026-10-14T00:00:00", "2026-10-15T00:00:00")
    with pytest.raises(ValueError, match="is not a time"):
        await store.closed_between(user_id, "yesterday", "2026-10-15T00:00:00+00:00")


async def test_unlink_project_keeps_the_tasks_and_drops_the_link(cfg, store, user_id):
    house, garden = await _project(cfg, user_id), await _project(cfg, user_id, "Garden")
    paint = await _task(store, user_id, "Paint", project_id=house.id, allocated_budget=Decimal("80"))
    await _task(store, user_id, "Tiles", project_id=house.id)
    binned = await _task(store, user_id, "Old quote", project_id=house.id)
    await store.delete(user_id, binned.id)
    mow = await _task(store, user_id, "Mow", project_id=garden.id)
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    assert await store.unlink_project(bob, house.id) == 0
    assert await store.unlink_project(user_id, house.id) == 3          # the deleted one too, as H9's delete does
    assert await store.list(user_id, status="all", project_id=house.id) == ()
    async with db_session(cfg) as db:
        row = await (await db.execute("SELECT project_id FROM tasks WHERE id = ?", (binned.id,))).fetchone()
    assert row["project_id"] is None
    kept = await store.get(user_id, paint.id)
    assert (kept.title, kept.project_id, kept.allocated_budget) == ("Paint", None, Decimal("80.00"))
    assert (await store.get(user_id, mow.id)).project_id == garden.id


async def test_failing_publishes_failed_and_a_recurring_task_comes_back_in_its_project(cfg, store, user_id):
    events = EventHub(cfg)
    service = TaskService(store, events)
    project = await _project(cfg, user_id)
    task = await service.add(user_id, TaskDraft(title="Water the plants", due_date="2026-10-12",
                                                recurring="0 9 * * 1", project_id=project.id,
                                                allocated_budget=Decimal("15")))
    outcome = await service.fail(user_id, task.id)
    assert (outcome.done.id, outcome.done.status) == (task.id, "failed")
    nxt = outcome.next
    assert (nxt.title, nxt.status, nxt.project_id, nxt.allocated_budget) == (
        "Water the plants", "todo", project.id, Decimal("15.00"))
    changes = [(e["change"], e["task_id"]) for e in await events.since(user_id, 0) if e["type"] == "tasks_changed"]
    assert changes == [("created", task.id), ("failed", task.id), ("created", nxt.id)]
    assert await service.fail(user_id, task.id) is None


async def test_a_failed_one_off_task_does_not_come_back(cfg, store, user_id):
    service = TaskService(store, EventHub(cfg))
    task = await service.add(user_id, TaskDraft(title="Call the plumber"))
    assert (await service.fail(user_id, task.id)).next is None
    assert [t.title for t in await service.list(user_id, status="failed")] == ["Call the plumber"]
    assert await service.list(user_id) == ()


async def test_a_recurring_task_whose_project_is_gone_comes_back_without_it(cfg, store, user_id, caplog):
    """The project is deleted between the fail and the respawn, so H9 had no
    chance to unlink the task: the next occurrence is still made, unlinked."""
    service = TaskService(store, EventHub(cfg))
    project = await _project(cfg, user_id)
    task = await service.add(user_id, TaskDraft(title="Sweep the yard", due_date="2026-10-12",
                                                recurring="0 9 * * 1", project_id=project.id,
                                                allocated_budget=Decimal("5")))
    async with db_session(cfg) as db:
        await db.execute("UPDATE money_projects SET deleted_at = ? WHERE id = ?",
                         (datetime.now(timezone.utc).isoformat(), project.id))
        await db.commit()
    with caplog.at_level(logging.WARNING, logger="roost.tasks.service"):
        outcome = await service.fail(user_id, task.id)
    assert outcome.done.status == "failed"
    assert (outcome.next.title, outcome.next.project_id, outcome.next.allocated_budget) == ("Sweep the yard", None, None)
    assert any(task.id in record.getMessage() and "comes back without it" in record.getMessage()
               for record in caplog.records)


async def test_the_service_lists_one_projects_tasks(cfg, store, user_id):
    service = TaskService(store, EventHub(cfg))
    house = await _project(cfg, user_id)
    await service.add(user_id, TaskDraft(title="Paint", project_id=house.id))
    await service.add(user_id, TaskDraft(title="Dentist"))
    assert [t.title for t in await service.list(user_id, project_id=house.id)] == ["Paint"]
    assert len(await service.list(user_id)) == 2


async def test_respawn_keeps_the_project_and_drops_a_slice_left_without_one(cfg, store, user_id):
    project = await _project(cfg, user_id)
    linked = await _task(store, user_id, project_id=project.id, allocated_budget=Decimal("20"))
    draft = respawn_draft(linked, "2026-10-19", None)
    assert (draft.project_id, draft.allocated_budget) == (project.id, Decimal("20.00"))
    unlinked = respawn_draft(replace(linked, project_id=None), "2026-10-19", None)
    assert (unlinked.project_id, unlinked.allocated_budget) == (None, None)


async def test_a_failed_task_has_its_own_mark_and_the_board_shape_carries_the_project(cfg, store, user_id):
    project = await _project(cfg, user_id)
    task = await _task(store, user_id, project_id=project.id, allocated_budget=Decimal("250"))
    failed = await store.fail(user_id, task.id)
    assert task_line(failed).startswith("[✗] - Paint the hall ")
    out = task_out(failed)
    assert (out["status"], out["project_id"], out["allocated_budget"]) == ("failed", project.id, "250.00")
    plain = task_out(await _task(store, user_id, "Dentist"))
    assert (plain["project_id"], plain["allocated_budget"]) == (None, None)
```

Create `tests/test_day_summary.py`:

```python
"""The end-of-day summary's content (projects hub, H13). For one Madrid day it
holds the tasks closed that day (done and failed), the open tasks already
overdue, and that day's counted expenses per currency, plus its text. Nothing
sends it yet; the scheduler (part 2) will."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from types import MappingProxyType

import pytest

from roost.config import load_config
from roost.db.connection import db_session, init_db
from roost.gateway.auth import register_user
from roost.money.expense_store import ExpenseStore
from roost.money.models import ExpenseDraft, ExpensePatch, ProjectDraft
from roost.money.project_store import ProjectStore
from roost.tasks.day_summary import DaySummary, build_day_summary, day_summary_text, madrid_day_bounds_utc
from roost.tasks.format import task_line
from roost.tasks.models import TaskDraft, TaskPatch
from roost.tasks.store import TaskStore

_NOON_MADRID = datetime(2026, 10, 14, 10, 0, tzinfo=timezone.utc)      # 12:00 on 2026-10-14 in Madrid (CEST)


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


@pytest.fixture
def store(cfg):
    return TaskStore(cfg)


async def _task(store, user_id, title, **fields):
    return await store.create(user_id, TaskDraft(title=title, **fields), created_by_bot=None, tainted=False)


async def _closed(cfg, store, user_id, title, how, at):
    """A task closed by ``complete`` or ``fail``, with ``completed_at`` moved to ``at``."""
    task = await _task(store, user_id, title)
    closed = await (store.fail if how == "fail" else store.complete)(user_id, task.id)
    async with db_session(cfg) as db:
        await db.execute("UPDATE tasks SET completed_at = ? WHERE id = ?", (at, task.id))
        await db.commit()
    return closed


async def _spend(expenses, user_id, project_id, amount, currency, day):
    draft = ExpenseDraft(project_id=project_id, amount=Decimal(amount), currency=currency, spent_at=day)
    return await expenses.add(user_id, draft, created_by_bot=None, tainted=False)


async def _summary(cfg, store, user_id, day="2026-10-14", now=_NOON_MADRID):
    return await build_day_summary(user_id, day, tasks=store, expenses=ExpenseStore(cfg), now=now)


@pytest.mark.parametrize(("day", "bounds"), (
    ("2026-10-14", ("2026-10-13T22:00:00+00:00", "2026-10-14T22:00:00+00:00")),   # summer time, UTC+2
    ("2026-12-01", ("2026-11-30T23:00:00+00:00", "2026-12-01T23:00:00+00:00")),   # winter time, UTC+1
    ("2026-10-25", ("2026-10-24T22:00:00+00:00", "2026-10-25T23:00:00+00:00")),   # clocks go back: 25 hours
    ("2026-03-29", ("2026-03-28T23:00:00+00:00", "2026-03-29T22:00:00+00:00")),   # clocks go forward: 23 hours
))
def test_a_madrid_day_runs_from_midnight_to_midnight_in_utc(day, bounds):
    assert madrid_day_bounds_utc(day) == bounds


@pytest.mark.parametrize("day", ("2026-13-01", "2026-02-30", "14/10/2026", "20261014", "", "2026-10-14T00:00"))
def test_a_day_that_is_not_a_date_is_refused(day):
    with pytest.raises(ValueError, match="is not a day like 2026-10-14"):
        madrid_day_bounds_utc(day)


async def test_the_summary_has_the_tasks_closed_that_madrid_day(cfg, store, user_id):
    # 2026-10-25 is 25 hours long in Madrid: 2026-10-24T22:00Z up to 2026-10-25T23:00Z.
    await _closed(cfg, store, user_id, "Too early", "complete", "2026-10-24T21:59:00+00:00")      # 23:59 on the 24th
    await _closed(cfg, store, user_id, "Fixed the tap", "complete", "2026-10-24T22:00:00+00:00")  # 00:00 on the 25th
    await _closed(cfg, store, user_id, "Ran out of tiles", "fail", "2026-10-25T01:30:00+00:00")   # 02:30, the repeated hour
    await _closed(cfg, store, user_id, "Paid the builder", "complete", "2026-10-25T22:59:59.999999+00:00")
    await _closed(cfg, store, user_id, "Too late", "fail", "2026-10-25T23:00:00+00:00")           # 00:00 on the 26th
    summary = await _summary(cfg, store, user_id, "2026-10-25", datetime(2026, 10, 25, 22, 0, tzinfo=timezone.utc))
    assert summary.day == "2026-10-25"
    assert [t.title for t in summary.done] == ["Fixed the tap", "Paid the builder"]
    assert [t.title for t in summary.failed] == ["Ran out of tiles"]


async def test_overdue_is_an_open_task_past_its_madrid_day_or_its_time(cfg, store, user_id):
    for title, due in (("Yesterday", "2026-10-13"), ("Today", "2026-10-14"), ("Tomorrow", "2026-10-15"),
                       ("Earlier today", "2026-10-14T11:00:00+02:00"), ("Later today", "2026-10-14T13:00:00+02:00"),
                       ("Earlier, no offset", "2026-10-14T11:00:00"), ("No due", None)):
        await _task(store, user_id, title, due_date=due)
    started = await _task(store, user_id, "Started last week", due_date="2026-10-07")
    await store.update(user_id, started.id, TaskPatch({"status": "in_progress"}))
    for title, close in (("Done late", store.complete), ("Failed late", store.fail)):
        task = await _task(store, user_id, title, due_date="2026-10-01")
        await close(user_id, task.id)
    cancelled = await _task(store, user_id, "Cancelled", due_date="2026-10-01")
    await store.update(user_id, cancelled.id, TaskPatch({"status": "cancelled"}))
    summary = await _summary(cfg, store, user_id)
    assert {t.title for t in summary.overdue} == {"Yesterday", "Earlier today", "Earlier, no offset", "Started last week"}


async def test_a_date_only_due_is_overdue_from_madrid_midnight(cfg, store, user_id):
    await _task(store, user_id, "Renew the parking permit", due_date="2026-10-13")
    just_before = datetime(2026, 10, 13, 21, 59, tzinfo=timezone.utc)    # 23:59 on the 13th in Madrid
    just_after = datetime(2026, 10, 13, 22, 1, tzinfo=timezone.utc)      # 00:01 on the 14th; UTC is still the 13th
    before = await _summary(cfg, store, user_id, "2026-10-13", just_before)
    after = await _summary(cfg, store, user_id, "2026-10-14", just_after)
    assert before.overdue == ()
    assert [t.title for t in after.overdue] == ["Renew the parking permit"]


async def test_an_unreadable_due_is_left_out_of_overdue_and_logged(cfg, store, user_id, caplog):
    odd = await _task(store, user_id, "Odd one", due_date="when the shop opens")
    short = await _task(store, user_id, "Short one", due_date="next week")    # 9 characters, not a date
    tenth = await _task(store, user_id, "Tenth one", due_date="2026-1x-01")   # 10 characters, not a date
    with caplog.at_level(logging.WARNING, logger="roost.tasks.day_summary"):
        summary = await _summary(cfg, store, user_id)
    assert summary.overdue == ()
    logged = " ".join(record.getMessage() for record in caplog.records)
    assert all(task.id in logged for task in (odd, short, tenth)) and "unreadable due date" in logged


async def test_spent_is_the_days_counted_expenses_per_currency(cfg, store, user_id):
    projects, expenses = ProjectStore(cfg), ExpenseStore(cfg)
    house = await projects.create(user_id, ProjectDraft(name="Renovation"), created_by_bot=None, tainted=False)
    await _spend(expenses, user_id, house.id, "12.50", "EUR", "2026-10-14")
    await _spend(expenses, user_id, house.id, "7.50", "EUR", "2026-10-14")
    await _spend(expenses, user_id, house.id, "3", "USD", "2026-10-14")
    await _spend(expenses, user_id, house.id, "100", "EUR", "2026-10-13")             # the day before
    voided = await _spend(expenses, user_id, house.id, "5", "EUR", "2026-10-14")
    deleted = await _spend(expenses, user_id, house.id, "9", "EUR", "2026-10-14")
    assert (await expenses.update(user_id, voided.id, ExpensePatch({"status": "void"}))).status == "void"
    assert await expenses.delete(user_id, deleted.id) is True
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    garage = await projects.create(bob, ProjectDraft(name="Garage"), created_by_bot=None, tainted=False)
    await _spend(expenses, bob, garage.id, "40", "EUR", "2026-10-14")
    summary = await _summary(cfg, store, user_id)
    assert dict(summary.spent) == {"EUR": Decimal("20.00"), "USD": Decimal("3.00")}
    assert list(summary.spent) == ["EUR", "USD"]
    assert isinstance(summary.spent, MappingProxyType)


async def test_another_users_tasks_stay_out_of_the_summary(cfg, store, user_id):
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    await _closed(cfg, store, bob, "Bob's tap", "complete", "2026-10-14T08:00:00+00:00")
    await _closed(cfg, store, bob, "Bob's tiles", "fail", "2026-10-14T09:00:00+00:00")
    await _task(store, bob, "Bob's late call", due_date="2026-10-01")
    summary = await _summary(cfg, store, user_id)
    assert (summary.done, summary.failed, summary.overdue, dict(summary.spent)) == ((), (), (), {})


async def test_a_quiet_day_has_an_empty_summary(cfg, store, user_id):
    summary = await build_day_summary(user_id, "2026-10-14", tasks=store, expenses=ExpenseStore(cfg))
    assert (summary.day, summary.done, summary.failed, summary.overdue, dict(summary.spent)) == (
        "2026-10-14", (), (), (), {})


async def test_the_summary_time_must_carry_a_time_zone(cfg, store, user_id):
    with pytest.raises(ValueError, match="time zone"):
        await _summary(cfg, store, user_id, now=datetime(2026, 10, 14, 12, 0))


async def test_the_text_lists_done_failed_overdue_and_spent(cfg, store, user_id):
    done = await _closed(cfg, store, user_id, "Fixed the tap", "complete", "2026-10-14T08:00:00+00:00")
    failed = await _closed(cfg, store, user_id, "Ran out of tiles", "fail", "2026-10-14T09:00:00+00:00")
    late = await _task(store, user_id, "Call the plumber", due_date="2026-10-10")
    summary = DaySummary(day="2026-10-14", done=(done,), failed=(failed,), overdue=(late,),
                         spent=MappingProxyType({"EUR": Decimal("20"), "USD": Decimal("3.5")}))
    assert day_summary_text(summary).splitlines() == [
        "Your day, 2026-10-14",
        "Done (1):", task_line(done),
        "Failed (1):", task_line(failed),
        "Overdue (1):", task_line(late),
        "Spent: 20.00 EUR, 3.50 USD",
    ]
    assert task_line(failed).startswith("[✗] - Ran out of tiles")


async def test_a_part_with_nothing_in_it_is_left_out(cfg, store, user_id):
    late = await _task(store, user_id, "Call the <plumber>", due_date="2026-10-10")
    summary = DaySummary(day="2026-10-14", done=(), failed=(), overdue=(late,), spent=MappingProxyType({}))
    text = day_summary_text(summary)
    assert text.splitlines() == ["Your day, 2026-10-14", "Overdue (1):", task_line(late)]
    assert "&lt;plumber&gt;" in text                     # titles are escaped by task_line


def test_an_empty_day_says_so():
    empty = DaySummary(day="2026-10-14", done=(), failed=(), overdue=(), spent=MappingProxyType({}))
    assert day_summary_text(empty) == (
        "Your day, 2026-10-14\nNothing was done or failed, nothing is overdue and nothing was spent.")
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_day_summary.py -q`
Expected: one collection error, `ModuleNotFoundError: No module named 'roost.tasks.day_summary'`.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_task_projects.py -q`
Expected: FAIL, `27 failed`. Collection succeeds, because every name it imports already exists (`Task` has its two fields since Task 3). All of them fail:
- Most fail with `TypeError: TaskDraft.__init__() got an unexpected keyword argument 'project_id'` (or `'allocated_budget'`). Inside a `pytest.raises(ValueError)` block the `TypeError` passes straight through.
- `test_a_task_with_no_project_has_no_slice` fails with `KeyError: 'project_id'` from `task_out`.
- `test_a_patch_can_carry_the_project_and_the_slice` fails with `ValueError: Tasks have no field allocated_budget, project_id.`
- The fail, done-filter and closed-between tests fail with `AttributeError: 'TaskStore' object has no attribute 'fail'` (or `'closed_between'`).
- `test_a_failed_one_off_task_does_not_come_back` fails with `AttributeError: 'TaskService' object has no attribute 'fail'`.

- [ ] **Step 4: Implement the shared project check (`roost/records/project_link.py`, new)**

Task 5 consumes this file; it doesn't create it again.

```python
"""A record's link to one of the user's projects (projects hub, H11, H12).

A foreign key proves that a project exists, not whose it is. So every write
that sets a ``project_id`` (on a task, a note or a document) first runs
``require_project`` inside the SAME ``db_session`` as the write. The session
holds the pooled connection's lock, so the project can't be deleted between
the check and the write. An archived project may be linked. A deleted one,
another user's, or an unknown id may not."""

from __future__ import annotations

import aiosqlite

NO_SUCH_PROJECT_TEXT = "No such project."
_OWNED_PROJECT_SQL = "SELECT 1 FROM money_projects WHERE id = ? AND user_id = ? AND deleted_at IS NULL"


async def require_project(db: aiosqlite.Connection, user_id: str, project_id: str | None) -> None:
    """``None`` (no link, or unlinking) always passes. ``ValueError`` when
    ``project_id`` is not one of this user's live projects. The routes turn it
    into 422 and the tools into "Refused: No such project."

    ``fetchall`` drains the cursor, so the caller's commit in the same session
    never meets a statement still in progress (see ``db_session``)."""
    if project_id is None:
        return
    rows = await (await db.execute(_OWNED_PROJECT_SQL, (project_id, user_id))).fetchall()
    if not rows:
        raise ValueError(NO_SUCH_PROJECT_TEXT)
```

- [ ] **Step 5: Implement the model (`roost/tasks/models.py`)**

Task 3 already added `from decimal import Decimal` and the two trailing `Task` fields. Do not add them again.

Find **(after Task 3)**:

```python
TaskStatus = Literal["todo", "in_progress", "done", "cancelled"]
TaskFilter = Literal["open", "done", "all"]
```

Replace with:

```python
# "failed" (projects hub, H11) closes a task the way "done" does: it sets
# completed_at, and a recurring task comes back. The "done" filter leaves it out.
TaskStatus = Literal["todo", "in_progress", "done", "cancelled", "failed"]
TaskFilter = Literal["open", "done", "failed", "all"]
```

Find **(after Task 3)**:

```python
    category: str | None          # the list / project, LazyClaw's "category"
```

Replace with:

```python
    category: str | None          # the task's list, LazyClaw's "category"
```

Find **(after Task 3)**:

```python
    tags: tuple[str, ...] = ()
    steps: tuple[str, ...] = ()   # checklist titles


PATCHABLE_FIELDS = frozenset({
    "title", "description", "category", "priority", "status", "due_date", "reminder_at", "pre_reminders",
    "recurring", "recur_until", "tags",
})
```

Replace with:

```python
    tags: tuple[str, ...] = ()
    steps: tuple[str, ...] = ()   # checklist titles
    project_id: str | None = None
    allocated_budget: Decimal | None = None   # needs project_id (H11)


PATCHABLE_FIELDS = frozenset({
    "title", "description", "category", "priority", "status", "due_date", "reminder_at", "pre_reminders",
    "recurring", "recur_until", "tags", "project_id", "allocated_budget",
})
```

- [ ] **Step 6: Implement the store (`roost/tasks/store.py`)**

Find (the module docstring, the imports and the module constants):

```python
"""``TaskStore`` — the user's tasks, encrypted (M1 D2, D6).

Tasks belong to the USER: every bot holding the tasks role reads and writes
the same rows, scoped by ``user_id`` only. Each row records the bot that
created it (``created_by_bot``, NULL for the user or a retired bot) and a
taint bit. Title, description, category, tags and steps are ``enc:v2`` under
``tasks:<column>``; dates, status, priority and the cron string stay plaintext
for queries. Deleting is soft (``deleted_at``), as in LazyClaw."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import aiosqlite

from roost.config import Config
from roost.crypto.encryption import decrypt_field, encrypt_field, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session
from roost.tasks.models import Task, TaskDraft, TaskFilter, TaskPatch
from roost.tasks.steps import cascade_steps, steps_from_json, steps_from_titles, steps_to_json

_COLUMNS = (
    "id", "user_id", "title", "description", "category", "priority", "status", "owner", "due_date",
    "reminder_at", "pre_reminders", "recurring", "recur_until", "tags", "steps", "created_at", "updated_at",
    "completed_at", "created_by_bot", "tainted",
)
_SELECT = ", ".join(_COLUMNS)
_MUTABLE = (
    "title", "description", "category", "priority", "status", "due_date", "reminder_at", "pre_reminders",
    "recurring", "recur_until", "tags", "steps", "completed_at", "updated_at",
)
_TEXT = frozenset({"title", "description", "category"})
_ORDER = ("CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, "
          "due_date IS NULL, due_date, created_at DESC")
_FILTERS = {"open": " AND status IN ('todo','in_progress')", "done": " AND status = 'done'", "all": ""}
```

Replace with:

```python
"""``TaskStore`` — the user's tasks, encrypted (M1 D2, D6).

Tasks belong to the USER: every bot holding the tasks role reads and writes
the same rows, scoped by ``user_id`` only. Each row records the bot that
created it (``created_by_bot``, NULL for the user or a retired bot) and a
taint bit. Title, description, category, tags, steps and the budget slice
(``allocated_budget``) are ``enc:v2`` under ``tasks:<column>``; dates, status,
priority, the cron string and ``project_id`` stay plaintext for queries.
Deleting is soft (``deleted_at``), as in LazyClaw.

Projects hub (H11): a task may belong to one of the user's live projects
(another user's, an unknown or a deleted one is refused, see
``roost.records.project_link``) and carry a budget slice, which needs a
project. ``fail`` closes a task like ``complete`` does, and
``closed_between`` reads the tasks closed in a time window."""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

import aiosqlite

from roost.config import Config
from roost.crypto.encryption import decrypt_field, encrypt_field, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session
from roost.money.amounts import amount_text, parse_amount
from roost.records.project_link import require_project
from roost.tasks.models import Task, TaskDraft, TaskFilter, TaskPatch
from roost.tasks.steps import cascade_steps, steps_from_json, steps_from_titles, steps_to_json

logger = logging.getLogger(__name__)

SLICE_NEEDS_PROJECT = "A budget slice needs a project."

_COLUMNS = (
    "id", "user_id", "title", "description", "category", "priority", "status", "owner", "due_date",
    "reminder_at", "pre_reminders", "recurring", "recur_until", "tags", "steps", "created_at", "updated_at",
    "completed_at", "created_by_bot", "tainted", "project_id", "allocated_budget",
)
_SELECT = ", ".join(_COLUMNS)
_MUTABLE = (
    "title", "description", "category", "priority", "status", "due_date", "reminder_at", "pre_reminders",
    "recurring", "recur_until", "tags", "steps", "completed_at", "updated_at", "project_id", "allocated_budget",
)
_TEXT = frozenset({"title", "description", "category"})
_ORDER = ("CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, "
          "due_date IS NULL, due_date, created_at DESC")
_OPEN_STATUSES = ("todo", "in_progress")
_OPEN_SQL = " AND status IN ('todo','in_progress')"
_FILTERS = {"open": _OPEN_SQL, "done": " AND status = 'done'", "failed": " AND status = 'failed'", "all": ""}
_PROJECT_SQL = " AND project_id = ?"
_CLOSED_SQL = ("WHERE user_id = ? AND deleted_at IS NULL AND status IN ('done','failed') "
               "AND completed_at >= ? AND completed_at < ? ORDER BY completed_at")
```

Find (the start of `_encode`):

```python
def _encode(task: Task, column: str, dek: bytes) -> Any:
    if column in _TEXT:
        return encrypt_field(getattr(task, column), dek, _aad(task.user_id, column))
    if column == "tags":
        return encrypt_field(json.dumps(list(task.tags)), dek, _aad(task.user_id, column))
    if column == "steps":
        return encrypt_field(steps_to_json(task.steps), dek, _aad(task.user_id, column))
    if column == "pre_reminders":
```

Replace with:

```python
def _checked_slice(task: Task) -> Task:
    """H11: a budget slice needs a project, and follows the amount rules
    (``parse_amount``: more than 0, at most 2 decimals, at most the cap)."""
    if task.allocated_budget is None:
        return task
    if task.project_id is None:
        raise ValueError(SLICE_NEEDS_PROJECT)
    return replace(task, allocated_budget=parse_amount(task.allocated_budget))


def _utc_bound(value: str) -> str:
    """A ``closed_between`` bound as the UTC ISO text that ``completed_at`` is
    written in (``_now_iso``), so comparing the strings compares the times."""
    try:
        moment = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"“{value}” is not a time.") from exc
    if moment.tzinfo is None:
        raise ValueError(f"“{value}” has no time zone.")
    return moment.astimezone(timezone.utc).isoformat()


def _encode(task: Task, column: str, dek: bytes) -> Any:
    if column in _TEXT:
        return encrypt_field(getattr(task, column), dek, _aad(task.user_id, column))
    if column == "tags":
        return encrypt_field(json.dumps(list(task.tags)), dek, _aad(task.user_id, column))
    if column == "steps":
        return encrypt_field(steps_to_json(task.steps), dek, _aad(task.user_id, column))
    if column == "allocated_budget":
        amount = task.allocated_budget
        return encrypt_field(None if amount is None else amount_text(amount), dek, _aad(task.user_id, column))
    if column == "pre_reminders":
```

Find (`_row_to_task`):

```python
def _row_to_task(row: aiosqlite.Row, dek: bytes) -> Task:
    user_id = row["user_id"]

    def text(column: str) -> str | None:
        return decrypt_field(row[column], dek, _aad(user_id, column))

    return Task(
        id=row["id"], user_id=user_id, title=text("title") or "", description=text("description"),
        category=text("category"), priority=row["priority"], status=row["status"], owner=row["owner"],
        due_date=row["due_date"], reminder_at=row["reminder_at"], pre_reminders=_json_list(row["pre_reminders"]),
        recurring=row["recurring"], recur_until=row["recur_until"], tags=_json_list(text("tags")),
        steps=steps_from_json(text("steps")), created_at=row["created_at"], updated_at=row["updated_at"],
        completed_at=row["completed_at"], created_by_bot=row["created_by_bot"], tainted=bool(row["tainted"]),
    )
```

Replace with:

```python
def _slice(row: aiosqlite.Row, dek: bytes) -> Decimal | None:
    """The budget slice, or ``None``. A value that won't decrypt under its own
    AAD (``decrypt_field`` then gives its fallback text) or won't read as a
    finite amount (a damaged row) reads as no slice, and is logged."""
    text = decrypt_field(row["allocated_budget"], dek, _aad(row["user_id"], "allocated_budget"))
    if text is None:
        return None
    try:
        amount = Decimal(text)
    except InvalidOperation:
        amount = None
    if amount is None or not amount.is_finite():
        logger.warning("Task %s has an unreadable budget slice; it reads as none", row["id"])
        return None
    return amount


def _row_to_task(row: aiosqlite.Row, dek: bytes) -> Task:
    user_id = row["user_id"]

    def text(column: str) -> str | None:
        return decrypt_field(row[column], dek, _aad(user_id, column))

    return Task(
        id=row["id"], user_id=user_id, title=text("title") or "", description=text("description"),
        category=text("category"), priority=row["priority"], status=row["status"], owner=row["owner"],
        due_date=row["due_date"], reminder_at=row["reminder_at"], pre_reminders=_json_list(row["pre_reminders"]),
        recurring=row["recurring"], recur_until=row["recur_until"], tags=_json_list(text("tags")),
        steps=steps_from_json(text("steps")), created_at=row["created_at"], updated_at=row["updated_at"],
        completed_at=row["completed_at"], created_by_bot=row["created_by_bot"], tainted=bool(row["tainted"]),
        project_id=row["project_id"], allocated_budget=_slice(row, dek),
    )
```

Find (`create`, `get` and `list`):

```python
    async def create(self, user_id: str, draft: TaskDraft, *, created_by_bot: str | None, tainted: bool) -> Task:
        now = _now_iso()
        task = Task(
            id=str(uuid4()), user_id=user_id, title=draft.title, description=draft.description,
            category=draft.category, priority=draft.priority, status="todo", owner=draft.owner,
            due_date=draft.due_date, reminder_at=draft.reminder_at, pre_reminders=draft.pre_reminders,
            recurring=draft.recurring, recur_until=draft.recur_until, tags=draft.tags,
            steps=steps_from_titles(draft.steps), created_at=now, updated_at=now, completed_at=None,
            created_by_bot=created_by_bot, tainted=tainted,
        )
        dek = await get_user_dek(self._config, user_id)
        async with db_session(self._config) as db:
            await db.execute(f"INSERT INTO tasks ({_SELECT}) VALUES ({','.join('?' * len(_COLUMNS))})",
                             tuple(_encode(task, column, dek) for column in _COLUMNS))
            await db.commit()
        return task

    async def get(self, user_id: str, task_id: str) -> Task | None:
        found = await self._select(user_id, "WHERE id = ? AND user_id = ? AND deleted_at IS NULL", (task_id, user_id))
        return found[0] if found else None

    async def list(self, user_id: str, *, status: TaskFilter = "open") -> tuple[Task, ...]:
        return await self._select(
            user_id, f"WHERE user_id = ? AND deleted_at IS NULL{_FILTERS[status]} ORDER BY {_ORDER}", (user_id,),
        )
```

Replace with:

```python
    async def create(self, user_id: str, draft: TaskDraft, *, created_by_bot: str | None, tainted: bool) -> Task:
        """``ValueError`` (nothing written) for a project that isn't the
        user's, or a slice without a project or outside the amount rules."""
        now = _now_iso()
        task = _checked_slice(Task(
            id=str(uuid4()), user_id=user_id, title=draft.title, description=draft.description,
            category=draft.category, priority=draft.priority, status="todo", owner=draft.owner,
            due_date=draft.due_date, reminder_at=draft.reminder_at, pre_reminders=draft.pre_reminders,
            recurring=draft.recurring, recur_until=draft.recur_until, tags=draft.tags,
            steps=steps_from_titles(draft.steps), created_at=now, updated_at=now, completed_at=None,
            created_by_bot=created_by_bot, tainted=tainted, project_id=draft.project_id,
            allocated_budget=draft.allocated_budget,
        ))
        dek = await get_user_dek(self._config, user_id)
        async with db_session(self._config) as db:
            await require_project(db, user_id, task.project_id)
            await db.execute(f"INSERT INTO tasks ({_SELECT}) VALUES ({','.join('?' * len(_COLUMNS))})",
                             tuple(_encode(task, column, dek) for column in _COLUMNS))
            await db.commit()
        return task

    async def get(self, user_id: str, task_id: str) -> Task | None:
        found = await self._select(user_id, "WHERE id = ? AND user_id = ? AND deleted_at IS NULL", (task_id, user_id))
        return found[0] if found else None

    async def list(self, user_id: str, *, status: TaskFilter = "open",
                   project_id: str | None = None) -> tuple[Task, ...]:
        """``project_id`` keeps only that project's tasks: a fixed SQL
        fragment plus a parameter, never text from the caller."""
        project_sql, params = ("", (user_id,)) if project_id is None else (_PROJECT_SQL, (user_id, project_id))
        return await self._select(
            user_id, f"WHERE user_id = ? AND deleted_at IS NULL{_FILTERS[status]}{project_sql} ORDER BY {_ORDER}",
            params,
        )
```

Find (`update` and `complete`):

```python
    async def update(self, user_id: str, task_id: str, patch: TaskPatch) -> Task | None:
        """Write only the patched columns (plus ``updated_at``), never the
        whole stale row — so a concurrent change to a column this patch
        doesn't touch (e.g. a Board complete) is never clobbered."""
        current = await self.get(user_id, task_id)
        if current is None:
            return None
        updated = replace(current, **dict(patch.changes), updated_at=_now_iso())
        columns = tuple(column for column in _MUTABLE if column in patch.changes) + ("updated_at",)
        return await self._write(updated, columns)

    async def complete(self, user_id: str, task_id: str) -> Task | None:
        """Close an open task (open steps are ticked as cascaded). ``None`` when
        there is no open task with that id. The UPDATE itself is guarded on
        the status it read, a compare-and-set, so two concurrent completes
        can't both succeed and both respawn — a double tap never repeats."""
        current = await self.get(user_id, task_id)
        if current is None or current.status not in ("todo", "in_progress"):
            return None
        now = _now_iso()
        updated = replace(current, status="done", completed_at=now, updated_at=now,
                          steps=cascade_steps(current.steps))
        return await self._write(updated, ("status", "completed_at", "updated_at", "steps"),
                                 guard_sql=" AND status IN ('todo','in_progress')")
```

Replace with:

```python
    async def update(self, user_id: str, task_id: str, patch: TaskPatch) -> Task | None:
        """Write only the patched columns (plus ``updated_at``), never the
        whole stale row — so a concurrent change to a column this patch
        doesn't touch (e.g. a Board complete) is never clobbered.

        A new slice must have a project (H11), and a new project must be the
        user's (checked in ``_write``): ``ValueError``, nothing written.
        Clearing the project keeps the slice, as H9's delete does."""
        current = await self.get(user_id, task_id)
        if current is None:
            return None
        updated = replace(current, **dict(patch.changes), updated_at=_now_iso())
        if patch.changes.get("allocated_budget") is not None:
            updated = _checked_slice(updated)
        columns = tuple(column for column in _MUTABLE if column in patch.changes) + ("updated_at",)
        return await self._write(updated, columns)

    async def complete(self, user_id: str, task_id: str) -> Task | None:
        """Close an open task (open steps are ticked as cascaded). ``None`` when
        there is no open task with that id. The UPDATE itself is guarded on
        the status it read, a compare-and-set, so two concurrent completes
        can't both succeed and both respawn — a double tap never repeats."""
        current = await self.get(user_id, task_id)
        if current is None or current.status not in _OPEN_STATUSES:
            return None
        now = _now_iso()
        updated = replace(current, status="done", completed_at=now, updated_at=now,
                          steps=cascade_steps(current.steps))
        return await self._write(updated, ("status", "completed_at", "updated_at", "steps"), guard_sql=_OPEN_SQL)

    async def fail(self, user_id: str, task_id: str) -> Task | None:
        """Close an open task as failed (H11). Like ``complete`` it sets
        ``completed_at`` and is a compare-and-set on the status it read;
        unlike it, the open steps stay open, since a failed task did not do
        them. ``None`` when there is no open task with that id."""
        current = await self.get(user_id, task_id)
        if current is None or current.status not in _OPEN_STATUSES:
            return None
        now = _now_iso()
        updated = replace(current, status="failed", completed_at=now, updated_at=now)
        return await self._write(updated, ("status", "completed_at", "updated_at"), guard_sql=_OPEN_SQL)

    async def closed_between(self, user_id: str, start_utc: str, end_utc: str) -> tuple[Task, ...]:
        """Done and failed tasks with ``completed_at`` in ``[start_utc,
        end_utc)``, oldest first. Each bound may carry any offset; one with
        none is refused (``ValueError``)."""
        params = (user_id, _utc_bound(start_utc), _utc_bound(end_utc))
        return await self._select(user_id, _CLOSED_SQL, params)
```

Find (`delete` and `_write`):

```python
    async def delete(self, user_id: str, task_id: str) -> bool:
        now = _now_iso()
        async with db_session(self._config) as db:
            cursor = await db.execute(
                "UPDATE tasks SET deleted_at = ?, updated_at = ? WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
                (now, now, task_id, user_id),
            )
            await db.commit()
        return cursor.rowcount > 0

    async def _write(self, task: Task, columns: tuple[str, ...], *, guard_sql: str = "") -> Task | None:
        """Update exactly ``columns``. ``guard_sql`` is a literal, caller-fixed
        SQL fragment (never built from user input) that makes the UPDATE a
        compare-and-set against the row the caller already checked, so a
        racing write that no longer matches touches nothing."""
        dek = await get_user_dek(self._config, task.user_id)
        assignments = ", ".join(f"{column} = ?" for column in columns)
        async with db_session(self._config) as db:
            cursor = await db.execute(
                f"UPDATE tasks SET {assignments} WHERE id = ? AND user_id = ? AND deleted_at IS NULL{guard_sql}",
                (*(_encode(task, column, dek) for column in columns), task.id, task.user_id),
            )
            await db.commit()
        return task if cursor.rowcount else None
```

Replace with:

```python
    async def delete(self, user_id: str, task_id: str) -> bool:
        now = _now_iso()
        async with db_session(self._config) as db:
            cursor = await db.execute(
                "UPDATE tasks SET deleted_at = ?, updated_at = ? WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
                (now, now, task_id, user_id),
            )
            await db.commit()
        return cursor.rowcount > 0

    async def unlink_project(self, user_id: str, project_id: str) -> int:
        """H9: a deleted project's tasks stay and lose the link (their slices
        stay too). The same statement as ``ProjectStore``'s delete runs for
        ``tasks``: deleted tasks too, ``updated_at`` untouched. Returns how
        many of the user's tasks were unlinked."""
        async with db_session(self._config) as db:
            cursor = await db.execute("UPDATE tasks SET project_id = NULL WHERE user_id = ? AND project_id = ?",
                                      (user_id, project_id))
            await db.commit()
        return cursor.rowcount

    async def _write(self, task: Task, columns: tuple[str, ...], *, guard_sql: str = "") -> Task | None:
        """Update exactly ``columns``. ``guard_sql`` is a literal, caller-fixed
        SQL fragment (never built from user input) that makes the UPDATE a
        compare-and-set against the row the caller already checked, so a
        racing write that no longer matches touches nothing. A new
        ``project_id`` is checked in the same session as the UPDATE."""
        dek = await get_user_dek(self._config, task.user_id)
        assignments = ", ".join(f"{column} = ?" for column in columns)
        async with db_session(self._config) as db:
            if "project_id" in columns:
                await require_project(db, task.user_id, task.project_id)
            cursor = await db.execute(
                f"UPDATE tasks SET {assignments} WHERE id = ? AND user_id = ? AND deleted_at IS NULL{guard_sql}",
                (*(_encode(task, column, dek) for column in columns), task.id, task.user_id),
            )
            await db.commit()
        return task if cursor.rowcount else None
```

`roost/tasks/store.py` ends at about 300 lines.

- [ ] **Step 7: Implement the service (`roost/tasks/service.py`)**

Find:

```python
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal
```

Replace with:

```python
import logging
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Literal
```

Find:

```python
TaskChange = Literal["created", "updated", "completed", "deleted"]
```

Replace with:

```python
TaskChange = Literal["created", "updated", "completed", "failed", "deleted"]
```

Find:

```python
def respawn_draft(done: Task, due_date: str | None, reminder_at: str | None) -> TaskDraft:
    return TaskDraft(
        title=done.title, description=done.description, category=done.category, priority=done.priority,
        owner=done.owner, due_date=due_date, reminder_at=reminder_at, pre_reminders=_shifted(done, reminder_at),
        recurring=done.recurring, recur_until=done.recur_until, tags=done.tags,
        steps=tuple(step.title for step in done.steps),
    )
```

Replace with:

```python
def respawn_draft(done: Task, due_date: str | None, reminder_at: str | None) -> TaskDraft:
    """The next occurrence of a closed (done or failed) recurring task. It stays
    in the same project with the same budget slice. A slice left without a
    project (the project was deleted, H9) is not carried over: it needs one (H11)."""
    return TaskDraft(
        title=done.title, description=done.description, category=done.category, priority=done.priority,
        owner=done.owner, due_date=due_date, reminder_at=reminder_at, pre_reminders=_shifted(done, reminder_at),
        recurring=done.recurring, recur_until=done.recur_until, tags=done.tags,
        steps=tuple(step.title for step in done.steps), project_id=done.project_id,
        allocated_budget=done.allocated_budget if done.project_id is not None else None,
    )
```

Find:

```python
    async def list(self, user_id: str, *, status: TaskFilter = "open") -> tuple[Task, ...]:
        return await self._store.list(user_id, status=status)
```

Replace with:

```python
    async def list(self, user_id: str, *, status: TaskFilter = "open",
                   project_id: str | None = None) -> tuple[Task, ...]:
        return await self._store.list(user_id, status=status, project_id=project_id)
```

Find:

```python
        await self._changed(user_id, "completed", done.id)
        return Completion(done=done, next=await self._respawn(user_id, done) if done.recurring else None)
```

Replace with:

```python
        await self._changed(user_id, "completed", done.id)
        return Completion(done=done, next=await self._respawn(user_id, done) if done.recurring else None)

    async def fail(self, user_id: str, task_id: str) -> Completion | None:
        """Close an open task as failed (H11). As with ``complete``, a
        recurring task comes back for its next time; ``Completion.done`` holds
        the failed task. ``None`` when there is no open task with that id."""
        failed = await self._store.fail(user_id, task_id)
        if failed is None:
            return None
        await self._changed(user_id, "failed", failed.id)
        return Completion(done=failed, next=await self._respawn(user_id, failed) if failed.recurring else None)
```

Find:

```python
    async def _respawn(self, user_id: str, done: Task) -> Task | None:
        """The next occurrence keeps the series' creator and its taint."""
        try:
            due_date, reminder_at = next_occurrence_fields(
                done.recurring, orig_due=done.due_date, orig_reminder=done.reminder_at,
            )
        except (ValueError, RuntimeError):
            logger.warning("Could not compute the next occurrence of task %s", done.id, exc_info=True)
            return None
        if due_date is None or series_ended(done.recur_until, due_date, reminder_at):
            return None
        return await self.add(user_id, respawn_draft(done, due_date, reminder_at),
                              created_by_bot=done.created_by_bot, tainted=done.tainted)
```

Replace with:

```python
    async def _respawn(self, user_id: str, done: Task) -> Task | None:
        """The next occurrence keeps the series' creator, its taint and its project."""
        try:
            due_date, reminder_at = next_occurrence_fields(
                done.recurring, orig_due=done.due_date, orig_reminder=done.reminder_at,
            )
        except (ValueError, RuntimeError):
            logger.warning("Could not compute the next occurrence of task %s", done.id, exc_info=True)
            return None
        if due_date is None or series_ended(done.recur_until, due_date, reminder_at):
            return None
        return await self._add_next(user_id, done, respawn_draft(done, due_date, reminder_at))

    async def _add_next(self, user_id: str, done: Task, draft: TaskDraft) -> Task:
        """A project deleted between the close and this respawn refuses the
        link ("No such project."). The series goes on, unlinked, and the log
        says so, instead of the close failing after its write."""
        try:
            return await self.add(user_id, draft, created_by_bot=done.created_by_bot, tainted=done.tainted)
        except ValueError as exc:
            if draft.project_id is None:
                raise
            logger.warning("The next occurrence of task %s was refused (%s); it comes back without its project",
                           done.id, exc)
            return await self.add(user_id, replace(draft, project_id=None, allocated_budget=None),
                                  created_by_bot=done.created_by_bot, tainted=done.tainted)
```

- [ ] **Step 8: Implement the task line and the Board shape (`roost/tasks/format.py`)**

Find:

```python
from roost.records.paging import more_line
from roost.talk.instructions import MADRID_TZ
from roost.tasks.models import Task

_PRIORITY_ICON = {"urgent": "!!", "high": "!", "medium": "-", "low": "."}
_STATUS_ICON = {"todo": "[ ]", "in_progress": "[~]", "done": "[x]", "cancelled": "[-]"}
```

Replace with:

```python
from roost.money.amounts import amount_text
from roost.records.paging import more_line
from roost.talk.instructions import MADRID_TZ
from roost.tasks.models import Task

_PRIORITY_ICON = {"urgent": "!!", "high": "!", "medium": "-", "low": "."}
_STATUS_ICON = {"todo": "[ ]", "in_progress": "[~]", "done": "[x]", "cancelled": "[-]", "failed": "[✗]"}
```

Find:

```python
        "created_at": task.created_at, "updated_at": task.updated_at, "completed_at": task.completed_at,
        "created_by_bot": task.created_by_bot, "tainted": task.tainted,
    }
```

Replace with:

```python
        "created_at": task.created_at, "updated_at": task.updated_at, "completed_at": task.completed_at,
        "created_by_bot": task.created_by_bot, "tainted": task.tainted, "project_id": task.project_id,
        # The server sends every amount as a string; the web never adds them.
        "allocated_budget": None if task.allocated_budget is None else amount_text(task.allocated_budget),
    }
```

- [ ] **Step 9: Implement the day summary (`roost/tasks/day_summary.py`, new)**

```python
"""The end-of-day summary's content (projects hub, H13). For one Madrid day it
holds the tasks closed that day (done and failed), the open tasks already
overdue, and that day's counted expenses per currency. No tool or route uses
it yet; the scheduler (part 2) will send it."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Mapping, Sequence

from roost.money.amounts import amount_text
from roost.money.expense_store import ExpenseStore
from roost.money.models import Expense
from roost.projects.numbers import counted, per_currency
from roost.talk.instructions import MADRID_TZ
from roost.tasks.format import task_line
from roost.tasks.models import Task
from roost.tasks.store import TaskStore

logger = logging.getLogger(__name__)

_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
_DATE_ONLY_LENGTH = len("YYYY-MM-DD")
_MONTH_LENGTH = len("YYYY-MM")
_DONE = "done"
_FAILED = "failed"
_HEADING = "Your day, {day}"
_NOTHING = "Nothing was done or failed, nothing is overdue and nothing was spent."
_SPENT = "Spent: "


@dataclass(frozen=True)
class DaySummary:
    day: str                              # YYYY-MM-DD, a Madrid day
    done: tuple[Task, ...]
    failed: tuple[Task, ...]
    overdue: tuple[Task, ...]
    spent: Mapping[str, Decimal]          # counted expenses that day, per currency


def _parse_day(day: str) -> date:
    refusal = f"“{day}” is not a day like 2026-10-14."
    if not _DAY.fullmatch(day):
        raise ValueError(refusal)
    try:
        return date.fromisoformat(day)
    except ValueError as exc:
        raise ValueError(refusal) from exc


def madrid_day_bounds_utc(day: str) -> tuple[str, str]:
    """``[midnight, next midnight)`` of a Madrid day as UTC ISO text, the shape
    ``tasks.completed_at`` is written in. A clock-change day is 23 or 25 hours."""
    first = _parse_day(day)
    start = datetime.combine(first, time.min, tzinfo=MADRID_TZ)
    end = datetime.combine(first + timedelta(days=1), time.min, tzinfo=MADRID_TZ)
    return start.astimezone(timezone.utc).isoformat(), end.astimezone(timezone.utc).isoformat()


def _moment(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("The summary's time needs a time zone.")
    return now


def _is_overdue(task: Task, today: date, now: datetime) -> bool:
    """A date-only due is overdue from the next Madrid day; a timed one from
    its time (a time with no offset is read as Madrid time). A due that reads
    as neither is logged and left out."""
    due = task.due_date
    if not due:
        return False
    try:
        if len(due) == _DATE_ONLY_LENGTH:
            return date.fromisoformat(due) < today
        moment = datetime.fromisoformat(due)
    except ValueError:
        logger.warning("Task %s has an unreadable due date; it is left out of the overdue list", task.id)
        return False
    return (moment if moment.tzinfo else moment.replace(tzinfo=MADRID_TZ)) < now


def _spent_on(expenses: Sequence[Expense], day: str) -> Mapping[str, Decimal]:
    """The day's counted expenses (posted, each in its own currency), summed
    per currency and never converted, codes in alphabetical order."""
    return per_currency(tuple(e for e in expenses if e.spent_at == day and counted(e, e.currency)))


async def build_day_summary(user_id: str, day: str, *, tasks: TaskStore, expenses: ExpenseStore,
                            now: datetime | None = None) -> DaySummary:
    """``day`` is a Madrid day (YYYY-MM-DD). Overdue is judged at ``now``
    (default: the real clock), which must carry a time zone."""
    start, end = madrid_day_bounds_utc(day)
    moment = _moment(now)
    today = moment.astimezone(MADRID_TZ).date()
    closed = await tasks.closed_between(user_id, start, end)
    open_tasks = await tasks.list(user_id, status="open")
    month = await expenses.list_month(user_id, day[:_MONTH_LENGTH])
    return DaySummary(
        day=day, done=tuple(task for task in closed if task.status == _DONE),
        failed=tuple(task for task in closed if task.status == _FAILED),
        overdue=tuple(task for task in open_tasks if _is_overdue(task, today, moment)),
        spent=_spent_on(month, day),
    )


def _section(title: str, tasks: tuple[Task, ...]) -> tuple[str, ...]:
    if not tasks:
        return ()
    return (f"{title} ({len(tasks)}):", *(task_line(task) for task in tasks))


def _spent_lines(spent: Mapping[str, Decimal]) -> tuple[str, ...]:
    if not spent:
        return ()
    return (_SPENT + ", ".join(f"{amount_text(total)} {code}" for code, total in spent.items()),)


def day_summary_text(summary: DaySummary) -> str:
    """Plain lines: a heading, then Done, Failed and Overdue (one ``task_line``
    each, which escapes the titles) and the money spent. Empty parts are left out."""
    body = (*_section("Done", summary.done), *_section("Failed", summary.failed),
            *_section("Overdue", summary.overdue), *_spent_lines(summary.spent))
    return "\n".join((_HEADING.format(day=summary.day), *(body or (_NOTHING,))))
```

- [ ] **Step 10: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_task_projects.py tests/test_day_summary.py -q`
Expected: PASS, `48 passed` (27 + 21).

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_task_projects.py tests/test_day_summary.py tests/test_task_store.py --cov=roost.tasks.day_summary --cov=roost.tasks.store --cov=roost.tasks.service --cov=roost.tasks.format --cov=roost.records.project_link --cov-report=term-missing -q`
Expected: PASS. `roost/tasks/day_summary.py` and `roost/records/project_link.py` are at 100%, and the other three modules are at 80% or more. The only new line no test reaches is the bare `raise` in `TaskService._add_next`, a refused respawn that had no project to drop.

The related existing tests must stay green (they build tasks, read `task_out`, or, since Task 3, read `Task`'s project fields):

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_task_store.py tests/test_task_tools.py tests/test_tasks_api.py tests/test_task_steps_recurrence.py tests/test_task_time.py tests/test_profile_api.py tests/test_tool_text.py tests/test_every_bot_tools.py tests/test_document_tools.py tests/test_handoff.py tests/test_main_bot.py tests/test_money_store.py tests/test_money_values.py tests/test_money_tools.py tests/test_money_api.py tests/test_project_numbers.py tests/test_money_summary.py tests/test_migrations_v12.py -q`
Expected: PASS.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest --cov=roost --cov-fail-under=80 -q`
Expected: PASS.

- [ ] **Step 11: Commit**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git add roost/records/project_link.py roost/tasks/models.py roost/tasks/store.py roost/tasks/service.py roost/tasks/format.py roost/tasks/day_summary.py tests/test_task_projects.py tests/test_day_summary.py && git status --short`
Expected: none of these eight files is still listed as modified (` M`) or untracked (`??`). If one is, stage it by name before committing.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git commit -m "feat: tasks join projects: a budget slice, the failed status and the day summary"`
Expected: one commit with exactly the eight files, and no Co-Authored-By or other attribution line.

---

### Task 5: Notes and documents: the project link

This task implements P1 and P2: a project holds notes and documents, and the link is optional. It follows H12, which overrides §3:
- A note or a document gets an optional `project_id` (plaintext, the v13 column from Task 2).
- **Linking goes through `set_project`, which never bumps the revision.** An open note editor or Univer editor therefore still saves at the revision it read.
  - `NoteStore.set_project` uses `_swap`, as `keep` does. If a save lands between its read and its write, it links the newer copy and does not refuse. The link is not content.
  - `DocumentStore.set_project` mirrors `keep`.
- **The store refuses a project that isn't the user's.** That covers another user's project, a deleted one and an unknown id. A foreign key proves only that the project exists, not whose it is.
  - Every write that sets a `project_id` runs Task 4's `require_project` (`roost/records/project_link.py`, already committed; this task only imports it) inside the **same** `db_session` as the write. The session holds the connection's lock, so the project can't be deleted between the check and the write.
  - A miss raises `ValueError("No such project.")`. Tasks 7 and 8 turn that into "Refused: No such project." and 422.
  - An archived project may still be linked.
- `list(..., project_id=)` filters in SQL, before any row is decrypted or the limit is applied.
- The services:
  - `set_project` publishes `notes_changed` / `documents_changed` with `"updated"`.
  - `for_project(user_id, project_id, limit)` is shaped like `made_by`.
  - `search` and `list` take a project filter.
  - `create_doc`, `create_sheet` and `create_pdf` take `project_id`.
  - `make_pdf` puts the new PDF in its source doc's project.
- H9 is consumed here, not built: Task 2's `ProjectStore.delete` sets `project_id` to NULL on the project's notes and documents, and this task's models are the first to read that back.

No tool, route or web change is made here. Tools are Task 7, and HTTP, including `project_id` in `note_summary_out` and `document_out`, is Task 8.

**Where the snippets start from.** No file in this task is touched by the stuck flow or by hub Tasks 1–4, so no snippet is marked "(after the stuck flow)" and every "Find" is today's code. Task 4 created `roost/records/project_link.py` (`NO_SUCH_PROJECT_TEXT`, `require_project`); this task does not create or edit it.

**Files:**
- Modify:
  - `roost/notes/models.py`: `Note` and `NoteDraft` each gain a trailing `project_id: str | None = None`.
  - `roost/notes/store.py`:
    - module docstring;
    - `project_id` in `_COLUMNS` and `_row_to_note`;
    - `_LINK_COLUMNS`;
    - `create` checks the project;
    - `list(..., project_id=None)`;
    - new `for_project`, `set_project` and `_link`;
    - `_swap` checks a new `project_id` in its own session.
  - `roost/notes/service.py`:
    - `new_note_draft(..., *, project_id=None)`;
    - `list` and `search` take `project_id`;
    - new `for_project` and `set_project`.
  - `roost/documents/models.py`: `DocumentMeta` and `DocumentDraft` each gain a trailing `project_id: str | None = None`.
  - `roost/documents/store.py`:
    - module docstring;
    - `project_id` in `_META` and `_row_to_meta`;
    - `create` checks and inserts `project_id`;
    - `list(user_id, kind=None, *, project_id=None)`;
    - `made_by` now goes through the new `_metas`;
    - new `for_project`, `set_project` and `_metas`.
  - `roost/documents/service.py`:
    - `list` takes `project_id`;
    - new `for_project` and `set_project`;
    - `create_doc`, `create_sheet` and `create_pdf` take `project_id`;
    - `make_pdf` inherits its source doc's project.
- Test:
  - `tests/test_notes_docs_projects.py` (new).

**Interfaces:**
- Consumes:
  - Task 1:
    - `ProjectStore` in `roost/money/project_store.py`, the renamed `CategoryStore`;
    - `ProjectStore.find_or_create(user_id, name, *, created_by_bot, tainted) -> Project`, kept for `log_expense` (H3).
  - Task 2:
    - schema v13: `notes.project_id` and `documents.project_id` (`TEXT REFERENCES money_projects(id) ON DELETE SET NULL`), and the indexes `idx_notes_user_project` and `idx_documents_user_project`;
    - `ProjectStore.delete(user_id, project_id) -> bool` (H9). It soft-deletes the project and sets `project_id = NULL` on its notes and documents.
  - Task 4:
    - `roost/records/project_link.py`: `NO_SUCH_PROJECT_TEXT = "No such project."` and `async def require_project(db: aiosqlite.Connection, user_id: str, project_id: str | None) -> None`, which raises `ValueError(NO_SUCH_PROJECT_TEXT)` and lets `None` pass.
  - Existing:
    - `db_session`, `get_user_dek` and `RevisionConflict`;
    - `EventHub.publish` and `EventHub.since`;
    - `register_user`;
    - `doc_from_markdown`.
- Produces (later tasks rely on these exact names):
  - Models:
    - `Note.project_id`, `NoteDraft.project_id`, `DocumentMeta.project_id` and `DocumentDraft.project_id`. Each is the last field, with a default of `None`.
  - `NoteStore`:
    - `list(user_id, *, limit=NOTE_SCAN_LIMIT, project_id=None)`;
    - `for_project(user_id, project_id, limit) -> tuple[Note, ...]`, pinned first, then newest;
    - `set_project(user_id, note_id, project_id: str | None) -> Note | None`.
  - `DocumentStore`:
    - `list(user_id, kind=None, *, project_id=None)`;
    - `for_project(user_id, project_id, limit) -> tuple[DocumentMeta, ...]`, newest first;
    - `set_project(user_id, document_id, project_id: str | None) -> DocumentMeta | None`.
  - `NoteService`:
    - `list(user_id, *, project_id=None)`;
    - `search(user_id, query, *, tag=None, limit=NOTE_LIST_LIMIT, project_id=None)`;
    - `for_project(user_id, project_id, limit)`;
    - `set_project(user_id, note_id, project_id) -> Note | None`, which publishes `{"type": "notes_changed", "change": "updated", "note_id"}`.
  - `new_note_draft(title, content, tags=(), *, project_id=None)`.
  - `DocumentService`:
    - `list(user_id, kind=None, *, project_id=None)`;
    - `for_project(user_id, project_id, limit)`;
    - `set_project(user_id, document_id, project_id) -> DocumentMeta | None`, which publishes `{"type": "documents_changed", "change": "updated", "document_id", "kind"}`;
    - `create_doc(..., project_id=None)`, `create_sheet(..., project_id=None)` and `create_pdf(..., project_id=None)`;
    - `make_pdf` inherits `source.meta.project_id`.
  - Errors:
    - The `create` and `set_project` methods raise `ValueError("No such project.")` for a project that isn't the user's, is deleted, or doesn't exist. Nothing is written in that case.
    - A missing or foreign note or document gives `None` (the 404 rule).
    - `NoteStore.set_project` can raise `RevisionConflict` only when two saves land in a row during one link. Task 8 maps it the way it maps saves (409).

- [ ] **Step 1: Path guard**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

Then confirm that Tasks 1, 2 and 4 have landed, since this task reads their columns, calls their store and imports their project check:

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && grep -n 'AddColumn("notes", "project_id"\|AddColumn("documents", "project_id"' roost/db/migrations.py && grep -n "async def find_or_create\|async def delete" roost/money/project_store.py && grep -n "^NO_SUCH_PROJECT_TEXT\|^async def require_project" roost/records/project_link.py && ! grep -n "project_id" roost/notes/models.py roost/documents/models.py`
Expected: two `AddColumn` lines (v13), the two `ProjectStore` method lines, the two `project_link.py` lines, and no `project_id` line from the note or document models. If anything is missing, stop: Tasks 1, 2 and 4 come first. If the models already have `project_id`, stop: this task already ran.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_notes_docs_projects.py`:

```python
"""Notes and documents: the project link (projects hub, H12).

A note or a document may belong to one of the user's projects. Linking goes
through ``set_project`` and keeps the revision, so an open editor's next save
still lands. A project that isn't the user's (another user's, a deleted one,
an unknown id) is refused with "No such project." and nothing is written. The
lists filter by project in SQL, before their limit. The services publish
``*_changed "updated"``, and a PDF made from a doc lands in the doc's project."""

from __future__ import annotations

import json
import sqlite3

import pytest

from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.documents.doc_markdown import doc_from_markdown
from roost.documents.models import DocumentChange, DocumentDraft, DocumentMeta
from roost.documents.service import DocumentService
from roost.documents.store import DocumentStore
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.money.project_store import ProjectStore
from roost.notes.models import Note, NoteDraft, NotePatch
from roost.notes.service import NoteService, new_note_draft
from roost.notes.store import NoteStore

# The contract's text, written out here on purpose (not imported).
_REFUSED = r"^No such project\.$"


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


async def _project(cfg, user_id: str, name: str = "Renovation") -> str:
    return (await ProjectStore(cfg).find_or_create(user_id, name, created_by_bot=None, tainted=False)).id


async def _note(cfg, user_id: str, title: str = "Paint", *, project_id: str | None = None) -> Note:
    draft = NoteDraft(title=title, content="white walls", project_id=project_id)
    return await NoteStore(cfg).create(user_id, draft, created_by_bot=None, tainted=False)


def _doc(title: str = "Quote", *, project_id: str | None = None) -> DocumentDraft:
    return DocumentDraft(kind="doc", title=title, body=json.dumps(doc_from_markdown(title, "- tiles")),
                         project_id=project_id)


def _sheet(title: str = "Costs", *, project_id: str | None = None) -> DocumentDraft:
    return DocumentDraft(kind="sheet", title=title, body=json.dumps({"sheets": {}}), project_id=project_id)


async def _create_doc(cfg, user_id: str, draft: DocumentDraft) -> DocumentMeta:
    return await DocumentStore(cfg).create(user_id, draft, created_by_bot=None, tainted=False)


def _stored_project_id(cfg, table: str, row_id: str) -> str | None:
    con = sqlite3.connect(get_db_path(cfg))
    try:
        return con.execute(f"SELECT project_id FROM {table} WHERE id = ?", (row_id,)).fetchone()[0]
    finally:
        con.close()


async def _published(cfg, user_id: str, kind: str) -> list[dict]:
    return [event for event in await EventHub(cfg).since(user_id, 0) if event["type"] == kind]


# --- notes: the store -------------------------------------------------------


async def test_a_note_made_in_a_project_keeps_the_link_in_plaintext(cfg, user_id):
    project_id = await _project(cfg, user_id)
    note = await _note(cfg, user_id, project_id=project_id)
    assert note.project_id == project_id
    assert _stored_project_id(cfg, "notes", note.id) == project_id
    assert await NoteStore(cfg).get(user_id, note.id) == note


async def test_linking_and_unlinking_a_note_keeps_its_revision(cfg, user_id):
    store = NoteStore(cfg)
    project_id = await _project(cfg, user_id)
    note = await _note(cfg, user_id)
    linked = await store.set_project(user_id, note.id, project_id)
    assert (linked.project_id, linked.revision, linked.content) == (project_id, 1, "white walls")
    assert await store.get(user_id, note.id) == linked
    unlinked = await store.set_project(user_id, note.id, None)
    assert (unlinked.project_id, unlinked.revision) == (None, 1)
    assert _stored_project_id(cfg, "notes", note.id) is None


async def test_an_open_editor_still_saves_after_the_note_is_linked(cfg, user_id):
    store = NoteStore(cfg)
    project_id = await _project(cfg, user_id)
    note = await _note(cfg, user_id)
    await store.set_project(user_id, note.id, project_id)
    saved = await store.update(user_id, note.id, NotePatch({"content": "grey walls"}), base_revision=note.revision)
    assert (saved.content, saved.revision, saved.project_id) == ("grey walls", 2, project_id)
    with pytest.raises(ValueError):
        NotePatch({"project_id": None})   # only set_project moves the link


async def test_linking_survives_a_save_landing_between_read_and_write(cfg, user_id, monkeypatch):
    store, other = NoteStore(cfg), NoteStore(cfg)
    project_id = await _project(cfg, user_id)
    note = await _note(cfg, user_id)
    real_get, raced = store.get, []

    async def get_then_race(uid: str, nid: str):
        found = await real_get(uid, nid)
        if not raced:
            raced.append(True)
            await other.update(uid, nid, NotePatch({"content": "theirs"}))
        return found

    monkeypatch.setattr(store, "get", get_then_race)
    linked = await store.set_project(user_id, note.id, project_id)
    assert (linked.content, linked.revision, linked.project_id) == ("theirs", 2, project_id)
    assert await other.get(user_id, note.id) == linked


async def test_another_users_project_is_refused_for_a_note_and_nothing_is_written(cfg, user_id):
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    bobs_project = await _project(cfg, bob, "Garage")
    store = NoteStore(cfg)
    with pytest.raises(ValueError, match=_REFUSED):
        await _note(cfg, user_id, project_id=bobs_project)
    assert await store.list(user_id) == ()
    note = await _note(cfg, user_id)
    for foreign in (bobs_project, "no-such-project"):
        with pytest.raises(ValueError, match=_REFUSED):
            await store.set_project(user_id, note.id, foreign)
    assert await store.get(user_id, note.id) == note


async def test_a_deleted_project_can_no_longer_be_linked(cfg, user_id):
    project_id = await _project(cfg, user_id)
    assert await ProjectStore(cfg).delete(user_id, project_id) is True
    note = await _note(cfg, user_id)
    with pytest.raises(ValueError, match=_REFUSED):
        await NoteStore(cfg).set_project(user_id, note.id, project_id)
    with pytest.raises(ValueError, match=_REFUSED):
        await _create_doc(cfg, user_id, _doc(project_id=project_id))


async def test_deleting_a_project_unlinks_its_note_and_document_but_keeps_them(cfg, user_id):
    project_id = await _project(cfg, user_id)
    note = await _note(cfg, user_id, project_id=project_id)
    meta = await _create_doc(cfg, user_id, _doc(project_id=project_id))
    assert await ProjectStore(cfg).delete(user_id, project_id) is True
    kept_note = await NoteStore(cfg).get(user_id, note.id)
    kept_doc = await DocumentStore(cfg).get_meta(user_id, meta.id)
    assert (kept_note.title, kept_note.project_id) == ("Paint", None)
    assert (kept_doc.title, kept_doc.project_id) == ("Quote", None)


async def test_another_user_can_neither_link_nor_list_alices_notes_and_documents(cfg, user_id):
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    bobs_project, alices_project = await _project(cfg, bob, "Garage"), await _project(cfg, user_id)
    note = await _note(cfg, user_id, project_id=alices_project)
    meta = await _create_doc(cfg, user_id, _doc(project_id=alices_project))
    assert await NoteStore(cfg).set_project(bob, note.id, bobs_project) is None
    assert await DocumentStore(cfg).set_project(bob, meta.id, bobs_project) is None
    assert await NoteStore(cfg).list(bob, project_id=alices_project) == ()
    assert await DocumentStore(cfg).list(bob, project_id=alices_project) == ()
    assert await DocumentStore(cfg).for_project(bob, alices_project, 10) == ()
    assert (await NoteStore(cfg).get(user_id, note.id)).project_id == alices_project
    assert (await DocumentStore(cfg).get_meta(user_id, meta.id)).project_id == alices_project


async def test_the_note_list_filters_by_project_before_its_limit(cfg, user_id):
    store = NoteStore(cfg)
    renovation, garden = await _project(cfg, user_id), await _project(cfg, user_id, "Garden")
    paint = await _note(cfg, user_id, "Paint", project_id=renovation)
    tiles = await _note(cfg, user_id, "Tiles", project_id=renovation)
    await _note(cfg, user_id, "Roses", project_id=garden)
    await _note(cfg, user_id, "Loose")
    assert [note.id for note in await store.list(user_id, project_id=renovation)] == [tiles.id, paint.id]
    assert [note.id for note in await store.list(user_id, project_id=renovation, limit=1)] == [tiles.id]
    assert [note.id for note in await store.for_project(user_id, renovation, 1)] == [tiles.id]
    assert len(await store.list(user_id)) == 4


# --- documents: the store ---------------------------------------------------


async def test_a_document_made_in_a_project_keeps_the_link_in_plaintext(cfg, user_id):
    project_id = await _project(cfg, user_id)
    meta = await _create_doc(cfg, user_id, _doc(project_id=project_id))
    assert meta.project_id == project_id
    assert _stored_project_id(cfg, "documents", meta.id) == project_id
    assert await DocumentStore(cfg).get_meta(user_id, meta.id) == meta
    assert (await DocumentStore(cfg).get(user_id, meta.id)).meta == meta


async def test_linking_a_document_keeps_its_revision_so_an_open_editor_still_saves(cfg, user_id):
    store = DocumentStore(cfg)
    project_id = await _project(cfg, user_id)
    meta = await _create_doc(cfg, user_id, _doc())
    linked = await store.set_project(user_id, meta.id, project_id)
    assert (linked.project_id, linked.revision) == (project_id, 1)
    assert await store.get_meta(user_id, meta.id) == linked
    saved = await store.save(user_id, meta.id, DocumentChange(base_revision=meta.revision, title="Quote v2"))
    assert (saved.title, saved.revision, saved.project_id) == ("Quote v2", 2, project_id)
    unlinked = await store.set_project(user_id, meta.id, None)
    assert (unlinked.project_id, unlinked.revision) == (None, 2)
    assert _stored_project_id(cfg, "documents", meta.id) is None


async def test_another_users_project_is_refused_for_a_document_and_nothing_is_written(cfg, user_id):
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    bobs_project = await _project(cfg, bob, "Garage")
    store = DocumentStore(cfg)
    with pytest.raises(ValueError, match=_REFUSED):
        await _create_doc(cfg, user_id, _doc(project_id=bobs_project))
    assert await store.list(user_id) == ()
    meta = await _create_doc(cfg, user_id, _doc())
    for foreign in (bobs_project, "no-such-project"):
        with pytest.raises(ValueError, match=_REFUSED):
            await store.set_project(user_id, meta.id, foreign)
    assert await store.get_meta(user_id, meta.id) == meta


async def test_the_document_list_filters_by_project_and_kind_before_any_limit(cfg, user_id):
    store = DocumentStore(cfg)
    renovation, garden = await _project(cfg, user_id), await _project(cfg, user_id, "Garden")
    quote = await _create_doc(cfg, user_id, _doc("Quote", project_id=renovation))
    costs = await _create_doc(cfg, user_id, _sheet("Costs", project_id=renovation))
    await _create_doc(cfg, user_id, _doc("Roses", project_id=garden))
    await _create_doc(cfg, user_id, _doc("Loose"))
    assert [meta.id for meta in await store.list(user_id, project_id=renovation)] == [costs.id, quote.id]
    assert [meta.id for meta in await store.list(user_id, "doc", project_id=renovation)] == [quote.id]
    assert [meta.id for meta in await store.for_project(user_id, renovation, 1)] == [costs.id]
    assert len(await store.list(user_id)) == 4


# --- the services -----------------------------------------------------------


async def test_linking_a_note_publishes_notes_changed_updated(cfg, user_id):
    service = NoteService(NoteStore(cfg), EventHub(cfg))
    project_id = await _project(cfg, user_id)
    note = await service.add(user_id, new_note_draft("Paint", "white walls"))
    linked = await service.set_project(user_id, note.id, project_id)
    assert (linked.project_id, linked.revision) == (project_id, 1)
    assert await service.set_project(user_id, "no-such-note", project_id) is None
    with pytest.raises(ValueError, match=_REFUSED):
        await service.set_project(user_id, note.id, "no-such-project")
    frames = [(frame["change"], frame["note_id"]) for frame in await _published(cfg, user_id, "notes_changed")]
    assert frames == [("created", note.id), ("updated", note.id)]


async def test_a_projects_notes_come_from_for_project_list_and_search(cfg, user_id):
    service = NoteService(NoteStore(cfg), EventHub(cfg))
    renovation = await _project(cfg, user_id)
    paint = await service.add(user_id, new_note_draft("Paint", "white walls", project_id=renovation))
    tiles = await service.add(user_id, new_note_draft("Tiles", "white tiles", project_id=renovation))
    await service.add(user_id, new_note_draft("Garden", "white roses"))
    assert [note.id for note in await service.for_project(user_id, renovation, 1)] == [tiles.id]
    assert [note.id for note in await service.list(user_id, project_id=renovation)] == [tiles.id, paint.id]
    found = await service.search(user_id, "white", project_id=renovation)
    assert {note.id for note in found} == {paint.id, tiles.id}
    assert len(await service.search(user_id, "white")) == 3


async def test_linking_a_document_publishes_documents_changed_updated(cfg, user_id):
    service = DocumentService(DocumentStore(cfg), EventHub(cfg))
    project_id = await _project(cfg, user_id)
    meta = await service.create_doc(user_id, "Quote", "- tiles")
    linked = await service.set_project(user_id, meta.id, project_id)
    assert (linked.project_id, linked.revision) == (project_id, 1)
    assert await service.set_project(user_id, "no-such-document", project_id) is None
    with pytest.raises(ValueError, match=_REFUSED):
        await service.set_project(user_id, meta.id, "no-such-project")
    frames = [(frame["change"], frame["document_id"], frame["kind"])
              for frame in await _published(cfg, user_id, "documents_changed")]
    assert frames == [("created", meta.id, "doc"), ("updated", meta.id, "doc")]


async def test_new_documents_take_a_project_and_a_pdf_inherits_its_docs_project(cfg, user_id):
    service = DocumentService(DocumentStore(cfg), EventHub(cfg))
    project_id = await _project(cfg, user_id)
    letter = await service.create_doc(user_id, "Letter", "Happy birthday", project_id=project_id)
    costs = await service.create_sheet(user_id, "Costs", [["Tiles", "120"]], project_id=project_id)
    pdf = await service.make_pdf(user_id, await service.get(user_id, letter.id), "Letter", created_by_bot=None,
                                 tainted=False)
    assert (letter.project_id, costs.project_id, pdf.project_id) == (project_id, project_id, project_id)
    assert [meta.id for meta in await service.for_project(user_id, project_id, 10)] == [pdf.id, costs.id, letter.id]
    assert [meta.id for meta in await service.list(user_id, "sheet", project_id=project_id)] == [costs.id]
    loose = await service.create_doc(user_id, "Loose", "no project")
    loose_pdf = await service.make_pdf(user_id, await service.get(user_id, loose.id), "Loose", created_by_bot=None,
                                       tainted=False)
    assert (loose_pdf.kind, loose_pdf.project_id) == ("pdf", None)
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_notes_docs_projects.py -q`
Expected: FAIL, `17 failed`. Collection succeeds, because every import already exists.
- 15 tests fail with `TypeError: ... got an unexpected keyword argument 'project_id'`. The raising call is `NoteDraft(...)`, `DocumentDraft(...)`, `new_note_draft(...)` or `DocumentService.create_doc(...)`. Inside a `pytest.raises(ValueError)` block the `TypeError` passes straight through.
- `test_linking_a_note_publishes_notes_changed_updated` fails with `AttributeError: 'NoteService' object has no attribute 'set_project'`.
- `test_linking_a_document_publishes_documents_changed_updated` fails with `AttributeError: 'DocumentService' object has no attribute 'set_project'`.

- [ ] **Step 4: Implement notes (models, store, service)**

The project check is Task 4's `require_project` (`roost/records/project_link.py`). Import it; do not create or change that file.

**`roost/notes/models.py`.** Find:

```python
    created_by_bot: str | None    # NULL: the user, or a retired bot
    tainted: bool                 # written by a run that read outside content


@dataclass(frozen=True)
class NoteDraft:
    title: str
    content: str
    tags: tuple[str, ...] = ()
    pinned: bool = False
```

Replace with:

```python
    created_by_bot: str | None    # NULL: the user, or a retired bot
    tainted: bool                 # written by a run that read outside content
    project_id: str | None = None  # one of the user's projects (H12); linking never bumps the revision


@dataclass(frozen=True)
class NoteDraft:
    title: str
    content: str
    tags: tuple[str, ...] = ()
    pinned: bool = False
    project_id: str | None = None
```

**`roost/notes/store.py`, module docstring.** Find:

```python
note instead of clobbering it. Deleting is soft (``deleted_at``)."""
```

Replace with:

```python
note instead of clobbering it. Deleting is soft (``deleted_at``).

A note may belong to one of the user's projects (``project_id``, plaintext,
projects hub H12). Linking goes through ``set_project`` and keeps the revision,
as ``keep`` does. Every write that sets a project first checks, in the same
session, that the project is the user's (``require_project``)."""
```

**Imports.** Find:

```python
from roost.notes.wikilinks import normalize_page
from roost.records.revision import RevisionConflict
```

Replace with:

```python
from roost.notes.wikilinks import normalize_page
from roost.records.project_link import require_project
from roost.records.revision import RevisionConflict
```

**Columns.** Find:

```python
_COLUMNS = ("id", "user_id", "title", "title_key", "content", "tags", "pinned", "revision",
            "created_at", "updated_at", "created_by_bot", "tainted")
```

Replace with:

```python
_COLUMNS = ("id", "user_id", "title", "title_key", "content", "tags", "pinned", "revision",
            "created_at", "updated_at", "created_by_bot", "tainted", "project_id")
```

Find:

```python
_PATCH_COLUMNS = {"title": ("title", "title_key"), "content": ("content",), "tags": ("tags",), "pinned": ("pinned",)}
```

Replace with:

```python
_PATCH_COLUMNS = {"title": ("title", "title_key"), "content": ("content",), "tags": ("tags",), "pinned": ("pinned",)}
# What linking a note to a project rewrites: no content, so no new revision (H12).
_LINK_COLUMNS = ("project_id", "updated_at")
```

`_encode` needs no change: `project_id` is plain, so it falls through to `getattr(note, column)`.

**`_row_to_note`.** Find:

```python
        updated_at=row["updated_at"], created_by_bot=row["created_by_bot"], tainted=bool(row["tainted"]),
    )
```

Replace with:

```python
        updated_at=row["updated_at"], created_by_bot=row["created_by_bot"], tainted=bool(row["tainted"]),
        project_id=row["project_id"],
    )
```

**`create`.** Find the whole method:

```python
    async def create(self, user_id: str, draft: NoteDraft, *, created_by_bot: str | None, tainted: bool) -> Note:
        now = _now_iso()
        note = Note(id=str(uuid4()), user_id=user_id, title=draft.title, content=draft.content, tags=draft.tags,
                    pinned=draft.pinned, revision=1, created_at=now, updated_at=now,
                    created_by_bot=created_by_bot, tainted=tainted)
        dek = await get_user_dek(self._config, user_id)
        async with db_session(self._config) as db:
            await db.execute(f"INSERT INTO notes ({_SELECT}) VALUES ({','.join('?' * len(_COLUMNS))})",
                             tuple(_encode(note, column, dek) for column in _COLUMNS))
            await db.commit()
        return note
```

Replace with:

```python
    async def create(self, user_id: str, draft: NoteDraft, *, created_by_bot: str | None, tainted: bool) -> Note:
        """``ValueError``: ``draft.project_id`` is not one of the user's projects (nothing is written)."""
        now = _now_iso()
        note = Note(id=str(uuid4()), user_id=user_id, title=draft.title, content=draft.content, tags=draft.tags,
                    pinned=draft.pinned, revision=1, created_at=now, updated_at=now,
                    created_by_bot=created_by_bot, tainted=tainted, project_id=draft.project_id)
        dek = await get_user_dek(self._config, user_id)
        async with db_session(self._config) as db:
            await require_project(db, user_id, note.project_id)
            await db.execute(f"INSERT INTO notes ({_SELECT}) VALUES ({','.join('?' * len(_COLUMNS))})",
                             tuple(_encode(note, column, dek) for column in _COLUMNS))
            await db.commit()
        return note
```

**`list`.** Find:

```python
    async def list(self, user_id: str, *, limit: int = NOTE_SCAN_LIMIT) -> tuple[Note, ...]:
        """Pinned first, then newest first — the order search ties break on."""
        return await self._select(user_id, f"WHERE {_LIVE} ORDER BY pinned DESC, updated_at DESC LIMIT ?",
                                  (user_id, limit))
```

Replace with:

```python
    async def list(self, user_id: str, *, limit: int = NOTE_SCAN_LIMIT,
                   project_id: str | None = None) -> tuple[Note, ...]:
        """Pinned first, then newest first — the order search ties break on.
        ``project_id`` keeps only that project's notes. It filters in SQL,
        before the limit and before anything is decrypted."""
        where, params = _LIVE, (user_id,)
        if project_id is not None:
            where, params = f"{_LIVE} AND project_id = ?", (user_id, project_id)
        return await self._select(user_id, f"WHERE {where} ORDER BY pinned DESC, updated_at DESC LIMIT ?",
                                  (*params, limit))
```

**`for_project`, after `made_by`.** Find:

```python
    async def made_by(self, user_id: str, bot_id: str, limit: int) -> tuple[Note, ...]:
        return await self._select(user_id, f"WHERE {_LIVE} AND created_by_bot = ? ORDER BY updated_at DESC LIMIT ?",
                                  (user_id, bot_id, limit))
```

Replace with:

```python
    async def made_by(self, user_id: str, bot_id: str, limit: int) -> tuple[Note, ...]:
        return await self._select(user_id, f"WHERE {_LIVE} AND created_by_bot = ? ORDER BY updated_at DESC LIMIT ?",
                                  (user_id, bot_id, limit))

    async def for_project(self, user_id: str, project_id: str, limit: int) -> tuple[Note, ...]:
        """A project's notes (its page, ``get_project``), in the Notes tab's order."""
        return await self.list(user_id, limit=limit, project_id=project_id)
```

**`set_project` and `_link`, after `keep`.** Find:

```python
        return await self._swap(current, replace(current, tainted=False, updated_at=_now_iso()),
                                ("tainted", "updated_at"))
```

Replace with:

```python
        return await self._swap(current, replace(current, tainted=False, updated_at=_now_iso()),
                                ("tainted", "updated_at"))

    async def set_project(self, user_id: str, note_id: str, project_id: str | None) -> Note | None:
        """Link the note to one of the user's projects, or unlink it (``None``).
        The link isn't content, so the revision stays and an open editor's
        next save still lands (H12). A save that lands between this read and
        this write is no reason to refuse: the link goes onto the newer copy.
        ``None``: no such note. ``ValueError``: not one of the user's projects."""
        current = await self.get(user_id, note_id)
        if current is None:
            return None
        try:
            return await self._link(current, project_id)
        except RevisionConflict as conflict:
            return await self._link(conflict.current, project_id)

    async def _link(self, current: Note, project_id: str | None) -> Note | None:
        return await self._swap(current, replace(current, project_id=project_id, updated_at=_now_iso()),
                                _LINK_COLUMNS)
```

**`_swap`.** Find:

```python
        """Write ``columns`` only if the row still has ``current.revision``."""
        dek = await get_user_dek(self._config, current.user_id)
        assignments = ", ".join(f"{column} = ?" for column in columns)
        async with db_session(self._config) as db:
            cursor = await db.execute(
```

Replace with:

```python
        """Write ``columns`` only if the row still has ``current.revision``. A
        new ``project_id`` among them must be the user's. It is checked in the
        same session as the write (``ValueError`` otherwise, and nothing is
        written)."""
        dek = await get_user_dek(self._config, current.user_id)
        assignments = ", ".join(f"{column} = ?" for column in columns)
        async with db_session(self._config) as db:
            if "project_id" in columns:
                await require_project(db, current.user_id, updated.project_id)
            cursor = await db.execute(
```

**`roost/notes/service.py`, `new_note_draft`.** Find:

```python
def new_note_draft(title: str | None, content: str, tags: Iterable[str] = ()) -> NoteDraft:
    return NoteDraft(title=note_title(title, content), content=content,
                     tags=capped_tags(merge_tags(list(tags), content)))
```

Replace with:

```python
def new_note_draft(title: str | None, content: str, tags: Iterable[str] = (), *,
                   project_id: str | None = None) -> NoteDraft:
    return NoteDraft(title=note_title(title, content), content=content,
                     tags=capped_tags(merge_tags(list(tags), content)), project_id=project_id)
```

**`list` and `search`.** Find:

```python
    async def list(self, user_id: str) -> tuple[Note, ...]:
        return await self._store.list(user_id, limit=NOTE_LIST_LIMIT)

    async def all(self, user_id: str) -> tuple[Note, ...]:
        return await self._store.list(user_id)

    async def search(self, user_id: str, query: str, *, tag: str | None = None,
                     limit: int = NOTE_LIST_LIMIT) -> tuple[Note, ...]:
        return rank_notes(await self._store.list(user_id), query, tag=tag, limit=limit)
```

Replace with:

```python
    async def list(self, user_id: str, *, project_id: str | None = None) -> tuple[Note, ...]:
        return await self._store.list(user_id, limit=NOTE_LIST_LIMIT, project_id=project_id)

    async def all(self, user_id: str) -> tuple[Note, ...]:
        return await self._store.list(user_id)

    async def search(self, user_id: str, query: str, *, tag: str | None = None, limit: int = NOTE_LIST_LIMIT,
                     project_id: str | None = None) -> tuple[Note, ...]:
        """``project_id`` keeps the search inside one project (the store filters first, in SQL)."""
        return rank_notes(await self._store.list(user_id, project_id=project_id), query, tag=tag, limit=limit)
```

**`for_project`.** Find:

```python
    async def made_by(self, user_id: str, bot_id: str, limit: int) -> tuple[Note, ...]:
        return await self._store.made_by(user_id, bot_id, limit)
```

Replace with:

```python
    async def made_by(self, user_id: str, bot_id: str, limit: int) -> tuple[Note, ...]:
        return await self._store.made_by(user_id, bot_id, limit)

    async def for_project(self, user_id: str, project_id: str, limit: int) -> tuple[Note, ...]:
        return await self._store.for_project(user_id, project_id, limit)
```

**`set_project`, after `keep`.** Find:

```python
    async def keep(self, user_id: str, note_id: str) -> Note | None:
        note = await self._store.keep(user_id, note_id)
        if note is not None:
            await self._changed(user_id, "updated", note.id)
        return note
```

Replace with:

```python
    async def keep(self, user_id: str, note_id: str) -> Note | None:
        note = await self._store.keep(user_id, note_id)
        if note is not None:
            await self._changed(user_id, "updated", note.id)
        return note

    async def set_project(self, user_id: str, note_id: str, project_id: str | None) -> Note | None:
        """Link or unlink (``None``). The store's ``ValueError`` (not one of the
        user's projects) passes through, and then nothing is published."""
        note = await self._store.set_project(user_id, note_id, project_id)
        if note is not None:
            await self._changed(user_id, "updated", note.id)
        return note
```

- [ ] **Step 5: Implement documents (models, store, service)**

**`roost/documents/models.py`.** Find:

```python
    created_by_bot: str | None    # NULL: the user, or a retired bot
    tainted: bool                 # written by a run that read outside content, or an uploaded file
```

Replace with:

```python
    created_by_bot: str | None    # NULL: the user, or a retired bot
    tainted: bool                 # written by a run that read outside content, or an uploaded file
    project_id: str | None = None  # one of the user's projects (H12); linking never bumps the revision
```

Find:

```python
    body: str
    pages: int | None = None


@dataclass(frozen=True)
class DocumentChange:
```

Replace with:

```python
    body: str
    pages: int | None = None
    project_id: str | None = None


@dataclass(frozen=True)
class DocumentChange:
```

**`roost/documents/store.py`, module docstring.** Find:

```python
``documents:title``. Every save is a compare-and-swap on ``revision`` (a stale
one raises ``RevisionConflict`` carrying the stored document). Deleting is soft."""
```

Replace with:

```python
``documents:title``. Every save is a compare-and-swap on ``revision`` (a stale
one raises ``RevisionConflict`` carrying the stored document). Deleting is soft.

A document may belong to one of the user's projects (``project_id``,
plaintext, projects hub H12). Linking goes through ``set_project`` and keeps
the revision, as ``keep`` does. Every write that sets a project first checks,
in the same session, that the project is the user's (``require_project``)."""
```

**Imports.** Find:

```python
from roost.documents.models import Document, DocumentChange, DocumentDraft, DocumentKind, DocumentMeta
from roost.records.revision import RevisionConflict
```

Replace with:

```python
from roost.documents.models import Document, DocumentChange, DocumentDraft, DocumentKind, DocumentMeta
from roost.records.project_link import require_project
from roost.records.revision import RevisionConflict
```

**`_META`.** Find:

```python
_META = "id, user_id, kind, title, pages, revision, created_at, updated_at, created_by_bot, tainted"
```

Replace with:

```python
_META = "id, user_id, kind, title, pages, revision, created_at, updated_at, created_by_bot, tainted, project_id"
```

**`_row_to_meta`.** Find:

```python
        revision=row["revision"], created_at=row["created_at"], updated_at=row["updated_at"],
        created_by_bot=row["created_by_bot"], tainted=bool(row["tainted"]),
    )
```

Replace with:

```python
        revision=row["revision"], created_at=row["created_at"], updated_at=row["updated_at"],
        created_by_bot=row["created_by_bot"], tainted=bool(row["tainted"]), project_id=row["project_id"],
    )
```

**`create`.** Find the whole method:

```python
    async def create(self, user_id: str, draft: DocumentDraft, *, created_by_bot: str | None,
                     tainted: bool) -> DocumentMeta:
        _check_body(draft.body)
        now = _now_iso()
        meta = DocumentMeta(id=str(uuid4()), user_id=user_id, kind=draft.kind, title=draft.title, pages=draft.pages,
                            revision=1, created_at=now, updated_at=now, created_by_bot=created_by_bot,
                            tainted=tainted)
        dek = await get_user_dek(self._config, user_id)
        async with db_session(self._config) as db:
            await db.execute(
                "INSERT INTO documents (id, user_id, kind, title, payload, pages, revision, created_at, updated_at, "
                "created_by_bot, tainted) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (meta.id, user_id, meta.kind, encrypt_field(meta.title, dek, _title_aad(user_id)),
                 encrypt_field(draft.body, dek, _payload_aad(user_id, meta.kind)), meta.pages, 1, now, now,
                 created_by_bot, int(tainted)),
            )
            await db.commit()
        return meta
```

Replace with:

```python
    async def create(self, user_id: str, draft: DocumentDraft, *, created_by_bot: str | None,
                     tainted: bool) -> DocumentMeta:
        """``ValueError``: the body is too big, or ``draft.project_id`` is not
        one of the user's projects (nothing is written)."""
        _check_body(draft.body)
        now = _now_iso()
        meta = DocumentMeta(id=str(uuid4()), user_id=user_id, kind=draft.kind, title=draft.title, pages=draft.pages,
                            revision=1, created_at=now, updated_at=now, created_by_bot=created_by_bot,
                            tainted=tainted, project_id=draft.project_id)
        dek = await get_user_dek(self._config, user_id)
        async with db_session(self._config) as db:
            await require_project(db, user_id, meta.project_id)
            await db.execute(
                "INSERT INTO documents (id, user_id, kind, title, payload, pages, revision, created_at, updated_at, "
                "created_by_bot, tainted, project_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (meta.id, user_id, meta.kind, encrypt_field(meta.title, dek, _title_aad(user_id)),
                 encrypt_field(draft.body, dek, _payload_aad(user_id, meta.kind)), meta.pages, 1, now, now,
                 created_by_bot, int(tainted), meta.project_id),
            )
            await db.commit()
        return meta
```

**`list`, `made_by` and the new `for_project`.** Find:

```python
    async def list(self, user_id: str, kind: DocumentKind | None = None) -> tuple[DocumentMeta, ...]:
        where, params = (f"{_LIVE} AND kind = ?", (user_id, kind)) if kind else (_LIVE, (user_id,))
        rows = await self._rows(f"SELECT {_META} FROM documents WHERE {where} ORDER BY updated_at DESC", params)
        if not rows:
            return ()
        dek = await get_user_dek(self._config, user_id)
        return tuple(_row_to_meta(row, dek) for row in rows)

    async def made_by(self, user_id: str, bot_id: str, limit: int) -> tuple[DocumentMeta, ...]:
        rows = await self._rows(f"SELECT {_META} FROM documents WHERE {_LIVE} AND created_by_bot = ? "
                                "ORDER BY updated_at DESC LIMIT ?", (user_id, bot_id, limit))
        if not rows:
            return ()
        dek = await get_user_dek(self._config, user_id)
        return tuple(_row_to_meta(row, dek) for row in rows)
```

Replace with:

```python
    async def list(self, user_id: str, kind: DocumentKind | None = None, *,
                   project_id: str | None = None) -> tuple[DocumentMeta, ...]:
        """Newest first. ``kind`` and ``project_id`` filter in SQL, before
        anything is decrypted."""
        where, params = _LIVE, (user_id,)
        if kind:
            where, params = f"{where} AND kind = ?", (*params, kind)
        if project_id is not None:
            where, params = f"{where} AND project_id = ?", (*params, project_id)
        return await self._metas(user_id, f"WHERE {where} ORDER BY updated_at DESC", params)

    async def made_by(self, user_id: str, bot_id: str, limit: int) -> tuple[DocumentMeta, ...]:
        return await self._metas(user_id, f"WHERE {_LIVE} AND created_by_bot = ? ORDER BY updated_at DESC LIMIT ?",
                                 (user_id, bot_id, limit))

    async def for_project(self, user_id: str, project_id: str, limit: int) -> tuple[DocumentMeta, ...]:
        """A project's newest documents (its page, ``get_project``)."""
        return await self._metas(user_id, f"WHERE {_LIVE} AND project_id = ? ORDER BY updated_at DESC LIMIT ?",
                                 (user_id, project_id, limit))
```

**`set_project`, after `keep`.** Find:

```python
        return replace(meta, tainted=False, updated_at=now) if cursor.rowcount else None
```

Replace with:

```python
        return replace(meta, tainted=False, updated_at=now) if cursor.rowcount else None

    async def set_project(self, user_id: str, document_id: str, project_id: str | None) -> DocumentMeta | None:
        """Link the document to one of the user's projects, or unlink it
        (``None``). This mirrors ``keep``: the revision stays, so an open
        Univer editor's next autosave still lands (H12), and the result is
        built from the ``meta`` read before the write. ``None``: no such
        document. ``ValueError``: not one of the user's projects."""
        meta = await self.get_meta(user_id, document_id)
        if meta is None:
            return None
        now = _now_iso()
        async with db_session(self._config) as db:
            await require_project(db, user_id, project_id)
            cursor = await db.execute(
                f"UPDATE documents SET project_id = ?, updated_at = ? WHERE id = ? AND {_LIVE}",
                (project_id, now, document_id, user_id),
            )
            await db.commit()
        return replace(meta, project_id=project_id, updated_at=now) if cursor.rowcount else None
```

**`_metas`, before `_rows`.** Find:

```python
    async def _rows(self, sql: str, params: tuple) -> list[aiosqlite.Row]:
```

Replace with:

```python
    async def _metas(self, user_id: str, where: str, params: tuple) -> tuple[DocumentMeta, ...]:
        rows = await self._rows(f"SELECT {_META} FROM documents {where}", params)
        if not rows:
            return ()
        dek = await get_user_dek(self._config, user_id)
        return tuple(_row_to_meta(row, dek) for row in rows)

    async def _rows(self, sql: str, params: tuple) -> list[aiosqlite.Row]:
```

**`roost/documents/service.py`, `list`.** Find:

```python
    async def list(self, user_id: str, kind: DocumentKind | None = None) -> tuple[DocumentMeta, ...]:
        return await self._store.list(user_id, kind)
```

Replace with:

```python
    async def list(self, user_id: str, kind: DocumentKind | None = None, *,
                   project_id: str | None = None) -> tuple[DocumentMeta, ...]:
        return await self._store.list(user_id, kind, project_id=project_id)
```

**`for_project`, the `create_*` methods and `make_pdf`.** Find:

```python
    async def made_by(self, user_id: str, bot_id: str, limit: int) -> tuple[DocumentMeta, ...]:
        return await self._store.made_by(user_id, bot_id, limit)

    async def create_doc(self, user_id: str, title: str, markdown: str, *, created_by_bot: str | None = None,
                         tainted: bool = False) -> DocumentMeta:
        body = json.dumps(doc_from_markdown(title, markdown))
        return await self._create(user_id, DocumentDraft("doc", title, body), created_by_bot, tainted)

    async def create_sheet(self, user_id: str, title: str, rows: Sequence[Sequence[Any]], *,
                           created_by_bot: str | None = None, tainted: bool = False) -> DocumentMeta:
        body = json.dumps(sheet_from_rows(title, rows))
        return await self._create(user_id, DocumentDraft("sheet", title, body), created_by_bot, tainted)

    async def create_pdf(self, user_id: str, title: str, data: bytes, *, created_by_bot: str | None = None,
                         tainted: bool = False) -> DocumentMeta:
        """Raises ``PdfError`` (a ValueError with a plain message) for a non-PDF."""
        pages = await asyncio.to_thread(page_count, data)
        draft = DocumentDraft("pdf", title, base64.b64encode(data).decode("ascii"), pages=pages)
        return await self._create(user_id, draft, created_by_bot, tainted)

    async def make_pdf(self, user_id: str, source: Document, title: str, *, created_by_bot: str | None,
                       tainted: bool) -> DocumentMeta:
        """A new PDF from a doc's text; it carries the doc's taint (provenance)."""
        data = await asyncio.to_thread(generate_from_text, doc_plain_text(snapshot_of(source)), title)
        return await self.create_pdf(user_id, title, data, created_by_bot=created_by_bot,
                                     tainted=tainted or source.meta.tainted)
```

Replace with:

```python
    async def made_by(self, user_id: str, bot_id: str, limit: int) -> tuple[DocumentMeta, ...]:
        return await self._store.made_by(user_id, bot_id, limit)

    async def for_project(self, user_id: str, project_id: str, limit: int) -> tuple[DocumentMeta, ...]:
        return await self._store.for_project(user_id, project_id, limit)

    async def create_doc(self, user_id: str, title: str, markdown: str, *, created_by_bot: str | None = None,
                         tainted: bool = False, project_id: str | None = None) -> DocumentMeta:
        body = json.dumps(doc_from_markdown(title, markdown))
        draft = DocumentDraft("doc", title, body, project_id=project_id)
        return await self._create(user_id, draft, created_by_bot, tainted)

    async def create_sheet(self, user_id: str, title: str, rows: Sequence[Sequence[Any]], *,
                           created_by_bot: str | None = None, tainted: bool = False,
                           project_id: str | None = None) -> DocumentMeta:
        body = json.dumps(sheet_from_rows(title, rows))
        draft = DocumentDraft("sheet", title, body, project_id=project_id)
        return await self._create(user_id, draft, created_by_bot, tainted)

    async def create_pdf(self, user_id: str, title: str, data: bytes, *, created_by_bot: str | None = None,
                         tainted: bool = False, project_id: str | None = None) -> DocumentMeta:
        """Raises ``PdfError`` (a ValueError with a plain message) for a non-PDF,
        and ``ValueError`` for a project that isn't the user's."""
        pages = await asyncio.to_thread(page_count, data)
        draft = DocumentDraft("pdf", title, base64.b64encode(data).decode("ascii"), pages=pages,
                              project_id=project_id)
        return await self._create(user_id, draft, created_by_bot, tainted)

    async def make_pdf(self, user_id: str, source: Document, title: str, *, created_by_bot: str | None,
                       tainted: bool) -> DocumentMeta:
        """A new PDF from a doc's text. It carries the doc's taint (provenance)
        and lands in the doc's project (H12)."""
        data = await asyncio.to_thread(generate_from_text, doc_plain_text(snapshot_of(source)), title)
        return await self.create_pdf(user_id, title, data, created_by_bot=created_by_bot,
                                     tainted=tainted or source.meta.tainted, project_id=source.meta.project_id)
```

**`set_project`, after `keep`.** Find:

```python
    async def keep(self, user_id: str, document_id: str) -> DocumentMeta | None:
        meta = await self._store.keep(user_id, document_id)
        if meta is not None:
            await self._changed(user_id, "updated", meta)
        return meta
```

Replace with:

```python
    async def keep(self, user_id: str, document_id: str) -> DocumentMeta | None:
        meta = await self._store.keep(user_id, document_id)
        if meta is not None:
            await self._changed(user_id, "updated", meta)
        return meta

    async def set_project(self, user_id: str, document_id: str, project_id: str | None) -> DocumentMeta | None:
        """Link or unlink (``None``). The store's ``ValueError`` (not one of the
        user's projects) passes through, and then nothing is published."""
        meta = await self._store.set_project(user_id, document_id, project_id)
        if meta is not None:
            await self._changed(user_id, "updated", meta)
        return meta
```

- [ ] **Step 6: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_notes_docs_projects.py -q`
Expected: PASS, `17 passed`.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_notes_docs_projects.py tests/test_note_store.py tests/test_document_store.py tests/test_note_tools.py tests/test_document_tools.py --cov=roost.notes.store --cov=roost.notes.service --cov=roost.documents.store --cov=roost.documents.service --cov-report=term-missing -q`
Expected: PASS, and each of the four modules at 80% or more (about 96%, 83%, 97% and 84%). Every new line is reached. The `term-missing` lines are all older code. The one new branch no test takes is the `else None` of `DocumentStore.set_project` (a document deleted between its read and its write), the same branch `keep` leaves untested.

The related existing tests must stay green. The model fields are trailing defaults, so every existing `Note(...)`, `NoteDraft(...)`, `DocumentDraft(...)` and positional `list(user_id, kind)` call keeps working:

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_note_store.py tests/test_document_store.py tests/test_note_tools.py tests/test_document_tools.py tests/test_notes_api.py tests/test_documents_api.py tests/test_profile_api.py tests/test_tool_text.py tests/test_every_bot_tools.py tests/test_main_bot.py tests/test_money_store.py -q`
Expected: PASS.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest --cov=roost --cov-fail-under=80 -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && git add roost/notes/models.py roost/notes/store.py roost/notes/service.py \
  roost/documents/models.py roost/documents/store.py roost/documents/service.py tests/test_notes_docs_projects.py
cd /Users/blckit/Desktop/Code_Projects/roost && git status --short   # nothing from this task may still be listed as modified or untracked
cd /Users/blckit/Desktop/Code_Projects/roost && git commit -m "feat: notes and documents link to a project without a new revision"
```

`roost/records/project_link.py` is Task 4's and is not staged here: this task does not change it.

---

### Task 6: ProjectService: one place for projects

Design P1, P2, P3, P5 and §5 H2, H3, H4, H5, H7, H9, H10 and H15. `ProjectService` is the one place both the bots' tools (Task 7) and the HTTP routes (Task 8) use for projects. The stores of Tasks 1–5 do the SQL and the sums. The service adds the rules that need more than one store, and it announces every change.
- **List (H2, P7).** General is hidden (Task 2's `is_general`, no query). Archived projects are hidden unless `include_archived=True`. Active projects come before archived ones, then the list is sorted by name and cut at `PROJECT_LIST_LIMIT`. Each row is `(Project, ProjectNumbers, Progress)`. All tasks come from one query and are grouped in Python. Expenses use one `list_project` per project shown, because the store has no all-projects read, and every amount is decrypted either way.
- **Detail (H14 data, H15).** It holds:
  - the numbers over **every** expense of the project;
  - the latest `PROJECT_PAGE_ITEMS` expenses, void ones included (`list_project` is already newest `spent_at` first), and the latest notes and documents (Task 5's `for_project`, limited in SQL);
  - every task of the project, of any status, and each one's planned / spent / left (`task_money`, design §2 and P6: Task 3's `task_money` over every expense, not only the latest page; an *extra* field, see Produces);
  - the whole top-up history;
  - the lead bot's name;
  - `tainted`, which is true when the project or any record behind the page is web-made.
- **Create and update.**
  - `ProjectDraft` and `ProjectPatch` (Task 2) check and tidy the shape of every field. That includes `status`, which must be `active` or `archived`: the patch refuses any other value with Task 2's `STATUS_TEXT`, which the service re-exports for the routes (Task 8), so the service does not check it a second time.
  - The service checks the rules that need more than one store, always on the patch's **tidied** values (a currency is upper-cased, a bot id stripped):
    - General can be neither changed nor deleted (H2).
    - No other project may take General's name.
    - A lead bot must be one of the user's own bots, found with `BotStore.get` (H15).
    - The currency can change only while `has_money` is false (H7).
- **Delete (H9).** It is `ProjectStore.delete`'s single transaction, after the service refuses General.
- **Total budget (P3, H5).** `set_budget(user_id, project_id, amount)` sets the total budget, or clears it with `None`, for the Board (Task 8's `PUT /api/projects/{id}/budget`). After creation this is the web's only way to the total: `ProjectPatch` has no `budget` field, and bots keep the money tool `set_budget`.
  - It is `ProjectStore.set_budget`, which writes the "Budget set" row (an `edit` with no `topup_id`) in its own transaction. An unchanged amount writes no row.
  - The amount is read again with `parse_amount`.
  - General is refused with `GENERAL_FIXED_TEXT`. Task 2's store refuses only renaming, archiving or deleting General and leaves "every other change to General" to this service, so the Board can no more budget General than recolour it.
  - Another user's or an unknown project is `None` (404).
  - It is announced as `money_changed` `budget_set`, `MoneyService`'s existing `MoneyChange` value, with the project's id, so the web already knows the frame.
- **Top-ups (H4).** Amounts are read again with `parse_amount`. A source is stripped and capped at `TOPUP_SOURCE_MAX_CHARS`.
- **`resolve` (H3), exact-or-ask:**
  - An id, an exact name or a unique part of a name resolves.
  - A lone near miss resolves only when `change=False`.
  - Several hits get "Say which one: …".
  - An unknown name gets "No project is called “X”. Use create_project first."
  - It never creates a project. Archived projects resolve, so `update_project` can unarchive them.
- **Events (H10).** Every change is published on `money_changed` with `project_created`, `project_updated`, `project_deleted`, `topup_added`, `topup_edited` or `topup_undone`, or with `budget_set` for the total budget. The `id` is the project's id, or the top-up's id for a top-up change.

**Files:**
- Create:
  - `roost/projects/service.py`
- Modify:
  - `roost/constants.py`: adds `PROJECT_MATCHES_SHOWN` to the Finance section, after Task 2's `TOPUP_SOURCE_MAX_CHARS`.
- Test:
  - `tests/test_project_service.py` (new)

**Interfaces:**
- Consumes:
  - **Task 1:**
    - `ProjectStore(config)` (`roost/money/project_store.py`), with `get(user_id, project_id)` and `find_or_create(user_id, name, *, created_by_bot, tainted)` (tests only).
    - `Project`, `Expense.project_id` and `ExpenseDraft(project_id, amount, currency=…, spent_at=…)` (`roost/money/models.py`).
    - `GENERAL_PROJECT_NAME`.
  - **Task 2:**
    - The `Project` fields `color`, `start_date`, `due_date`, `monthly_budget`, `lead_bot_id` and `status`.
    - `ProjectDraft`, `ProjectPatch(changes)` and `TopUp` (`id`, `project_id`, `amount`, `source`, `kind`, `undone`, `tainted`).
    - The module function `is_general(project) -> bool` (`roost/money/project_store.py`, H2).
    - `ProjectStore` methods:
      - `find(user_id, name)`;
      - `list(user_id, *, include_archived)`;
      - `create(user_id, draft, *, created_by_bot, tainted)`;
      - `update(user_id, project_id, patch)`, which raises `ValueError("A project with that name exists.")` on a clash;
      - `set_budget(user_id, project_id, amount: Decimal | None, *, created_by_bot, tainted) -> Project | None`, where `None` clears the total budget with an `edit` row of −budget (H5), an unchanged amount writes no row, and another user's project is `None`;
      - `add_topup(user_id, project_id, amount, source, *, created_by_bot, tainted) -> TopUp`;
      - `edit_topup(user_id, topup_id, amount) -> TopUp | None`, where `amount` is the top-up's **new** amount and the store writes the difference as an `edit` row;
      - `undo_topup(user_id, topup_id) -> TopUp | None`;
      - `topups(user_id, project_id)`;
      - `delete(user_id, project_id) -> bool` (H9);
      - `has_money(user_id, project_id)`.
    - Constants `PROJECT_STATUSES`, `PROJECT_COLORS`, `PROJECT_LIST_LIMIT`, `PROJECT_PAGE_ITEMS` and `TOPUP_SOURCE_MAX_CHARS`.
    - The texts `LEAD_BOT_TEXT` and `STATUS_TEXT` (`roost/money/models.py`) and `CURRENCY_LOCKED_TEXT` (`roost/money/project_store.py`).
  - **Task 3:**
    - `ExpenseStore.list_project(user_id, project_id)`, which includes void expenses, and `ExpensePatch({"status": "void"})`.
    - `roost/projects/__init__.py`.
    - From `roost/projects/numbers.py`: `ProjectNumbers` (`currency`, `total`, `month`, `other_currencies`), `BudgetLine` (`budget`, `spent`, `remaining`, `used_percent`, `tone`), `Progress` (`done`, `failed`, `total`), `TaskMoney` (`planned`, `spent`, `left`), `project_numbers(project, expenses, month)`, `progress(tasks)` and `task_money(task, expenses, currency)`.
  - **Task 4:**
    - `Task.project_id` and `TaskDraft(project_id=…)`.
    - `TaskStore.list(user_id, *, status="all", project_id=…)` and `TaskStore.fail(user_id, task_id)`.
  - **Task 5:**
    - `Note.project_id`, `NoteDraft(…, project_id=…)`, `DocumentMeta.project_id` and `DocumentDraft(…, project_id=…)`.
    - `NoteStore.for_project(user_id, project_id, limit)` (pinned first, then newest) and `DocumentStore.for_project(user_id, project_id, limit)` (newest first).
  - **Existing code:**
    - `BotStore.get(user_id, bot_id)`, `EventHub.publish` and `EventHub.subscribe`.
    - `MoneyChange` (`roost/money/service.py`, unchanged by Task 1's rename), whose `"budget_set"` value this service publishes. The web's `MoneyChangedFrame` already has it.
    - `parse_amount`, `current_month` and `today_madrid`.
    - `resolve`, `NamedRef` and `Resolve` (`roost/records/resolver.py`).
    - Test helpers: `register_user`, `make_bot`, `frames_so_far` and `doc_from_markdown`.
- Produces (Tasks 7 and 8 rely on these):
  - `roost/projects/service.py`:
    - `ProjectDetail`: the contract's fields, plus a trailing *extra* `task_money: Mapping[str, TaskMoney]` (task id → planned / spent / left, design §2 and P6, over **every** expense of the project, not only the latest page). The contract has no other place where a task's planned vs spent reaches a bot or the Board; Tasks 7 and 8 show it. Reported as a contract addition.
    - `ProjectRow = tuple[Project, ProjectNumbers, Progress]`.
    - `ProjectChange`: the six H10 values. `set_budget` publishes `MoneyChange`'s `"budget_set"` instead.
    - `ProjectRefusal(str)`: plain, unescaped text with a `.tainted` flag. The tool escapes the text like any `ValueError` text, and folds `.tainted` into its `ToolOutcome`.
    - `ProjectService(projects, expenses, tasks, notes, documents, bots, events)` with these methods:
      - `list(user_id, *, include_archived=False) -> tuple[ProjectRow, ...]`
      - `detail(user_id, project_id) -> ProjectDetail | None`
      - `create(user_id, draft, *, created_by_bot=None, tainted=False) -> Project`
      - `update(user_id, project_id, changes) -> Project | None`
      - `delete(user_id, project_id) -> bool`
      - `set_budget(user_id, project_id, amount: Decimal | None) -> Project | None`: `None` clears the total budget (H5), General is a `ValueError(GENERAL_FIXED_TEXT)`, and a bad amount is `parse_amount`'s `ValueError`. It publishes `money_changed` `budget_set` with the project's id. Task 8's `PUT /api/projects/{id}/budget` uses it.
      - `add_topup(user_id, project_id, amount, source=None, *, created_by_bot=None, tainted=False) -> TopUp | None`
      - `edit_topup(user_id, topup_id, amount) -> TopUp | None`
      - `undo_topup(user_id, topup_id) -> TopUp | None`
      - `topups(user_id, project_id) -> tuple[TopUp, ...] | None`
      - `resolve(user_id, name, *, change) -> Project | ProjectRefusal`
    - Not found is `None` (or `False` from `delete`), which is a 404. A broken rule is a `ValueError` with a plain sentence that has no apostrophe: a 422, or "Refused: …" in a tool. The one exception is "A project with that name exists.", which Task 8 maps to 409.
    - Texts: `GENERAL_FIXED_TEXT`, `GENERAL_NAME_TEXT`, `TOPUP_SOURCE_TEXT`, `NO_PROJECT_TEXT`, `NEAR_MISS_TEXT`, `SEVERAL_TEXT` and `WEB_MARK`, plus Task 2's `LEAD_BOT_TEXT`, `STATUS_TEXT` (`roost/money/models.py`) and `CURRENCY_LOCKED_TEXT` (`roost/money/project_store.py`), imported and re-exported, never a second copy of the sentence.
  - `roost/constants.py`: `PROJECT_MATCHES_SHOWN = 5`.

- [ ] **Step 1: Path guard**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

Then confirm that Tasks 1–5 have landed, since this task imports from all of them, and that this task has not run yet:

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && grep -n "^class ProjectDraft\|^class ProjectPatch\|^class TopUp" roost/money/*.py && grep -n "^def is_general\|async def find(\|async def set_budget\|async def has_money\|async def topups\|async def edit_topup\|async def undo_topup\|async def delete" roost/money/project_store.py && grep -n "^MoneyChange = " roost/money/service.py && grep -n "async def list_project" roost/money/expense_store.py && grep -n "^def project_numbers\|^def progress" roost/projects/numbers.py && grep -n "async def fail\|project_id: str | None = None" roost/tasks/store.py && grep -n "project_id" roost/notes/models.py roost/documents/models.py && grep -n "async def for_project" roost/notes/store.py roost/documents/store.py && grep -n "^PROJECT_STATUSES\|^PROJECT_COLORS\|^PROJECT_LIST_LIMIT\|^PROJECT_PAGE_ITEMS\|^TOPUP_SOURCE_MAX_CHARS\|^GENERAL_PROJECT_NAME" roost/constants.py && test ! -e roost/projects/service.py && echo "no service yet"`
Expected: every grep prints at least one line:
- `ProjectDraft`, `ProjectPatch` and `TopUp`;
- `is_general` and the seven store methods;
- `MoneyChange`, with its `"budget_set"`;
- `list_project`;
- both numbers functions;
- `fail` and the task list's `project_id` keyword;
- the four `project_id` fields;
- both `for_project` methods;
- the six constants;

then `no service yet`.

If anything is missing, stop: Tasks 1–5 come first. If `no service yet` is missing, this task already ran. If Task 2 put `ProjectDraft`, `ProjectPatch` or `TopUp` in a module other than `roost/money/models.py`, import them from that module in Steps 2 and 5. The names stay the same.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_project_service.py`:

```python
"""ProjectService (projects hub Task 6): one place for projects — the list with
its numbers, a project's page, create / update / delete, top-ups, and
exact-or-ask names (H2, H3, H4, H7, H9, H10, H15)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal

import pytest

from roost.bots.store import BotStore
from roost.config import load_config
from roost.constants import GENERAL_PROJECT_NAME, PROJECT_COLORS, TOPUP_SOURCE_MAX_CHARS
from roost.db.connection import init_db
from roost.documents.doc_markdown import doc_from_markdown
from roost.documents.models import DocumentDraft, DocumentMeta
from roost.documents.store import DocumentStore
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.money.expense_store import ExpenseStore
from roost.money.models import Expense, ExpenseDraft, ExpensePatch, ProjectDraft
from roost.money.months import today_madrid
from roost.money.project_store import ProjectStore
from roost.notes.models import Note, NoteDraft
from roost.notes.store import NoteStore
from roost.projects import service as service_module
from roost.projects.numbers import TaskMoney
from roost.projects.service import ProjectDetail, ProjectRefusal, ProjectService
from roost.tasks.models import Task, TaskDraft, TaskPatch
from roost.tasks.store import TaskStore
from team_helpers import frames_so_far, make_bot


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


@dataclass(frozen=True)
class Rig:
    service: ProjectService
    projects: ProjectStore
    expenses: ExpenseStore
    tasks: TaskStore
    notes: NoteStore
    documents: DocumentStore
    events: EventHub


@pytest.fixture
def rig(cfg) -> Rig:
    projects, expenses, tasks = ProjectStore(cfg), ExpenseStore(cfg), TaskStore(cfg)
    notes, documents, events = NoteStore(cfg), DocumentStore(cfg), EventHub(cfg)
    service = ProjectService(projects, expenses, tasks, notes, documents, BotStore(cfg), events)
    return Rig(service, projects, expenses, tasks, notes, documents, events)


async def _expense(rig: Rig, user_id: str, project_id: str, amount: str, *, currency: str = "EUR",
                   spent_at: str | None = None, tainted: bool = False) -> Expense:
    draft = ExpenseDraft(project_id, Decimal(amount), currency=currency, spent_at=spent_at or today_madrid())
    return await rig.expenses.add(user_id, draft, created_by_bot=None, tainted=tainted)


async def _task(rig: Rig, user_id: str, title: str, project_id: str | None = None) -> Task:
    return await rig.tasks.create(user_id, TaskDraft(title=title, project_id=project_id),
                                  created_by_bot=None, tainted=False)


async def _note(rig: Rig, user_id: str, title: str, project_id: str, *, tainted: bool = False) -> Note:
    return await rig.notes.create(user_id, NoteDraft(title=title, content="green tiles", project_id=project_id),
                                  created_by_bot=None, tainted=tainted)


async def _doc(rig: Rig, user_id: str, title: str, project_id: str) -> DocumentMeta:
    body = json.dumps(doc_from_markdown(title, "- tiles"))
    return await rig.documents.create(user_id, DocumentDraft("doc", title, body, project_id=project_id),
                                      created_by_bot=None, tainted=False)


def _changes(frames: list[dict]) -> list[tuple[str, str]]:
    return [(frame["change"], frame["id"]) for frame in frames if frame["type"] == "money_changed"]


async def test_deleting_a_project_keeps_its_items_and_moves_its_money_to_general(rig, user_id):
    project = await rig.service.create(user_id, ProjectDraft(name="Renovation"))
    task = await _task(rig, user_id, "Buy tiles", project.id)
    note = await _note(rig, user_id, "Ideas", project.id)
    document = await _doc(rig, user_id, "Plan", project.id)
    expense = await _expense(rig, user_id, project.id, "40")
    subscription = rig.events.subscribe(user_id)

    assert await rig.service.delete(user_id, project.id) is True

    general = await rig.projects.find(user_id, GENERAL_PROJECT_NAME)
    assert general is not None
    kept_task = await rig.tasks.get(user_id, task.id)
    kept_note = await rig.notes.get(user_id, note.id)
    kept_document = await rig.documents.get_meta(user_id, document.id)
    assert (kept_task.title, kept_task.project_id) == ("Buy tiles", None)
    assert (kept_note.title, kept_note.project_id) == ("Ideas", None)
    assert (kept_document.title, kept_document.project_id) == ("Plan", None)
    moved = await rig.expenses.get(user_id, expense.id)
    assert (moved.project_id, moved.amount) == (general.id, Decimal("40"))
    assert await rig.projects.get(user_id, project.id) is None
    assert await rig.service.detail(user_id, project.id) is None
    assert _changes(await frames_so_far(subscription)) == [("project_deleted", project.id)]
    assert await rig.service.delete(user_id, project.id) is False


async def test_general_is_hidden_and_can_be_neither_changed_nor_deleted(rig, user_id):
    general = await rig.projects.find_or_create(user_id, GENERAL_PROJECT_NAME, created_by_bot=None, tainted=False)
    await rig.service.create(user_id, ProjectDraft(name="Renovation"))
    shown = await rig.service.list(user_id, include_archived=True)
    assert [project.name for project, _, _ in shown] == ["Renovation"]
    for changes in ({"name": "Misc"}, {"status": "archived"}, {"color": PROJECT_COLORS[2]}):
        with pytest.raises(ValueError, match="General is where expenses with no project go"):
            await rig.service.update(user_id, general.id, changes)
    with pytest.raises(ValueError, match="General is where expenses with no project go"):
        await rig.service.delete(user_id, general.id)
    kept = await rig.projects.get(user_id, general.id)
    assert (kept.name, kept.status, kept.color) == (GENERAL_PROJECT_NAME, "active", general.color)


async def test_no_project_can_take_the_name_general(rig, user_id):
    with pytest.raises(ValueError, match="General is kept for expenses with no project"):
        await rig.service.create(user_id, ProjectDraft(name=" general "))
    house = await rig.service.create(user_id, ProjectDraft(name="House"))
    with pytest.raises(ValueError, match="General is kept for expenses with no project"):
        await rig.service.update(user_id, house.id, {"name": "GENERAL"})
    assert await rig.projects.find(user_id, GENERAL_PROJECT_NAME) is None


async def test_archiving_hides_a_project_until_asked_for(rig, user_id):
    house = await rig.service.create(user_id, ProjectDraft(name="House"))
    assert (await rig.service.update(user_id, house.id, {"status": "archived"})).status == "archived"
    assert await rig.service.list(user_id) == ()
    assert [project.id for project, _, _ in await rig.service.list(user_id, include_archived=True)] == [house.id]
    assert (await rig.service.detail(user_id, house.id)).project.status == "archived"
    assert (await rig.service.update(user_id, house.id, {"status": "active"})).status == "active"
    assert [project.id for project, _, _ in await rig.service.list(user_id)] == [house.id]
    with pytest.raises(ValueError, match="either active or archived"):
        await rig.service.update(user_id, house.id, {"status": "done"})


async def test_the_list_puts_active_projects_first_sorted_by_name_and_is_capped(rig, user_id, monkeypatch):
    for name in ("trip", "House", "Attic"):
        await rig.service.create(user_id, ProjectDraft(name=name))
    attic = await rig.service.resolve(user_id, "Attic", change=True)
    await rig.service.update(user_id, attic.id, {"status": "archived"})
    shown = await rig.service.list(user_id, include_archived=True)
    assert [project.name for project, _, _ in shown] == ["House", "trip", "Attic"]
    monkeypatch.setattr(service_module, "PROJECT_LIST_LIMIT", 1)
    assert [project.name for project, _, _ in await rig.service.list(user_id)] == ["House"]


async def test_the_list_carries_each_projects_numbers_and_progress(rig, user_id):
    house = await rig.service.create(user_id, ProjectDraft(name="House", budget=Decimal("500"),
                                                            monthly_budget=Decimal("100")))
    trip = await rig.service.create(user_id, ProjectDraft(name="Trip", currency="USD"))
    await _expense(rig, user_id, house.id, "80")
    await _expense(rig, user_id, house.id, "30", currency="USD")
    await _expense(rig, user_id, trip.id, "12", currency="USD")
    await rig.tasks.complete(user_id, (await _task(rig, user_id, "Paint", house.id)).id)
    await rig.tasks.fail(user_id, (await _task(rig, user_id, "Fix the tap", house.id)).id)
    await _task(rig, user_id, "Tiles", house.id)
    pool = await _task(rig, user_id, "Pool", house.id)
    await rig.tasks.update(user_id, pool.id, TaskPatch({"status": "cancelled"}))
    await _task(rig, user_id, "Loose")

    rows = {project.name: (numbers, progress) for project, numbers, progress in await rig.service.list(user_id)}

    numbers, progress = rows["House"]
    total, month = numbers.total, numbers.month
    assert (numbers.currency, total.budget, total.spent, total.remaining, total.tone) == (
        "EUR", Decimal("500"), Decimal("80"), Decimal("420"), "ok")
    assert (month.budget, month.spent, month.remaining, month.used_percent, month.tone) == (
        Decimal("100"), Decimal("80"), Decimal("20"), 80, "warn")
    assert dict(numbers.other_currencies) == {"USD": Decimal("30")}
    assert (progress.done, progress.failed, progress.total) == (1, 1, 3)
    trip_numbers, trip_progress = rows["Trip"]
    assert (trip_numbers.currency, trip_numbers.total.spent, trip_numbers.total.budget) == (
        "USD", Decimal("12"), None)
    assert (trip_progress.done, trip_progress.failed, trip_progress.total) == (0, 0, 0)


async def test_the_lead_bot_must_be_one_of_the_users_own_bots(rig, cfg, user_id):
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    bobs_bot = await make_bot(cfg, bob, "Builder")
    mine = await make_bot(cfg, user_id, "Fixer")
    with pytest.raises(ValueError, match="The lead bot must be one of your bots."):
        await rig.service.create(user_id, ProjectDraft(name="House", lead_bot_id=bobs_bot.id))
    house = await rig.service.create(user_id, ProjectDraft(name="House", lead_bot_id=mine.id))
    assert house.lead_bot_id == mine.id
    with pytest.raises(ValueError, match="The lead bot must be one of your bots."):
        await rig.service.update(user_id, house.id, {"lead_bot_id": bobs_bot.id})
    assert (await rig.service.detail(user_id, house.id)).lead_bot_name == "Fixer"
    assert (await rig.service.update(user_id, house.id, {"lead_bot_id": None})).lead_bot_id is None
    assert (await rig.service.detail(user_id, house.id)).lead_bot_name is None


async def test_the_currency_changes_only_while_the_project_has_no_money(rig, user_id):
    house = await rig.service.create(user_id, ProjectDraft(name="House"))
    assert (await rig.service.update(user_id, house.id, {"currency": "USD"})).currency == "USD"
    await _expense(rig, user_id, house.id, "10", currency="USD")
    with pytest.raises(ValueError, match="no expenses and no top-ups"):
        await rig.service.update(user_id, house.id, {"currency": "GBP"})
    kept = await rig.service.update(user_id, house.id, {"currency": "USD", "color": PROJECT_COLORS[3]})
    assert (kept.currency, kept.color) == ("USD", PROJECT_COLORS[3])
    trip = await rig.service.create(user_id, ProjectDraft(name="Trip"))
    await rig.service.add_topup(user_id, trip.id, Decimal("50"))
    with pytest.raises(ValueError, match="no expenses and no top-ups"):
        await rig.service.update(user_id, trip.id, {"currency": "USD"})
    assert (await rig.projects.get(user_id, trip.id)).currency == "EUR"


async def test_creating_and_changing_a_project_are_announced_on_money_changed(rig, user_id):
    subscription = rig.events.subscribe(user_id)
    house = await rig.service.create(user_id, ProjectDraft(name="House"))
    trip = await rig.service.create(user_id, ProjectDraft(name="Trip"))
    home = await rig.service.update(user_id, house.id, {"name": "Home", "due_date": "2026-12-31"})
    assert (home.name, home.due_date) == ("Home", "2026-12-31")
    with pytest.raises(ValueError, match="A project with that name exists."):
        await rig.service.update(user_id, house.id, {"name": "trip"})
    assert await rig.service.update(user_id, "no-such-project", {"color": PROJECT_COLORS[1]}) is None
    assert _changes(await frames_so_far(subscription)) == [
        ("project_created", house.id), ("project_created", trip.id), ("project_updated", house.id),
    ]


async def test_top_ups_are_added_edited_and_undone_and_each_is_announced(rig, user_id):
    house = await rig.service.create(user_id, ProjectDraft(name="House"))
    subscription = rig.events.subscribe(user_id)

    topup = await rig.service.add_topup(user_id, house.id, Decimal("100"), "  birthday  ")
    assert (topup.kind, topup.amount, topup.source, topup.project_id, topup.undone) == (
        "credit", Decimal("100"), "birthday", house.id, False)
    assert (await rig.projects.get(user_id, house.id)).budget == Decimal("100")
    assert await rig.service.edit_topup(user_id, topup.id, Decimal("150")) is not None
    assert (await rig.projects.get(user_id, house.id)).budget == Decimal("150")
    assert await rig.service.undo_topup(user_id, topup.id) is not None
    assert ((await rig.projects.get(user_id, house.id)).budget or Decimal("0")) == Decimal("0")

    history = await rig.service.topups(user_id, house.id)
    assert sorted(row.kind for row in history) == ["credit", "edit"]
    assert all(row.undone for row in history)
    assert _changes(await frames_so_far(subscription)) == [
        ("topup_added", topup.id), ("topup_edited", topup.id), ("topup_undone", topup.id),
    ]


async def test_a_top_up_needs_a_positive_amount_and_a_short_source(rig, user_id):
    house = await rig.service.create(user_id, ProjectDraft(name="House"))
    with pytest.raises(ValueError, match="more than 0"):
        await rig.service.add_topup(user_id, house.id, Decimal("0"))
    with pytest.raises(ValueError, match=f"at most {TOPUP_SOURCE_MAX_CHARS} characters"):
        await rig.service.add_topup(user_id, house.id, Decimal("5"), "x" * (TOPUP_SOURCE_MAX_CHARS + 1))
    plain = await rig.service.add_topup(user_id, house.id, Decimal("5"), "   ")
    assert plain.source is None
    with pytest.raises(ValueError, match="more than 0"):
        await rig.service.edit_topup(user_id, plain.id, Decimal("-1"))
    assert (await rig.projects.get(user_id, house.id)).budget == Decimal("5")


async def test_the_board_sets_and_clears_the_total_budget_and_each_change_is_announced(rig, cfg, user_id):
    """P3, H5: the total budget is set or cleared through the service. Each
    change is a "Budget set" row and MoneyService's budget_set frame. General
    keeps no budget from here (H2), and another user's project is not found."""
    house = await rig.service.create(user_id, ProjectDraft(name="House"))
    general = await rig.projects.find_or_create(user_id, GENERAL_PROJECT_NAME, created_by_bot=None, tainted=False)
    subscription = rig.events.subscribe(user_id)

    assert (await rig.service.set_budget(user_id, house.id, Decimal("300"))).budget == Decimal("300.00")
    cleared = await rig.service.set_budget(user_id, house.id, None)

    assert cleared.budget is None and (await rig.projects.get(user_id, house.id)).budget is None
    history = await rig.service.topups(user_id, house.id)
    assert sorted((row.kind, row.amount, row.topup_id) for row in history) == [
        ("edit", Decimal("-300.00"), None), ("edit", Decimal("300.00"), None)]
    with pytest.raises(ValueError, match="more than 0"):
        await rig.service.set_budget(user_id, house.id, Decimal("0"))
    with pytest.raises(ValueError, match="General is where expenses with no project go"):
        await rig.service.set_budget(user_id, general.id, Decimal("50"))
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    assert await rig.service.set_budget(bob, house.id, Decimal("10")) is None
    assert (await rig.projects.get(user_id, general.id)).budget is None
    assert (await rig.projects.get(user_id, house.id)).budget is None
    assert _changes(await frames_so_far(subscription)) == [("budget_set", house.id), ("budget_set", house.id)]


async def test_another_users_projects_and_top_ups_are_not_found(rig, cfg, user_id):
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    house = await rig.service.create(user_id, ProjectDraft(name="House"))
    topup = await rig.service.add_topup(user_id, house.id, Decimal("10"))
    assert await rig.service.list(bob) == ()
    assert await rig.service.detail(bob, house.id) is None
    assert await rig.service.update(bob, house.id, {"color": PROJECT_COLORS[1]}) is None
    assert await rig.service.delete(bob, house.id) is False
    assert await rig.service.add_topup(bob, house.id, Decimal("10")) is None
    assert await rig.service.topups(bob, house.id) is None
    assert await rig.service.edit_topup(bob, topup.id, Decimal("20")) is None
    assert await rig.service.undo_topup(bob, topup.id) is None
    assert await rig.service.resolve(bob, house.id, change=False) == (
        f"No project is called “{house.id}”. Use create_project first.")
    kept = await rig.projects.get(user_id, house.id)
    assert (kept.budget, kept.color) == (Decimal("10"), house.color)


async def test_resolve_finds_a_project_by_id_exact_name_or_a_unique_part(rig, user_id):
    renovation = await rig.service.create(user_id, ProjectDraft(name="Renovation"))
    await rig.service.create(user_id, ProjectDraft(name="Trip"))
    for ref in (renovation.id, "renovation", "  RENOVATION ", "Renov"):
        for change in (False, True):
            found = await rig.service.resolve(user_id, ref, change=change)
            assert found.id == renovation.id, (ref, change)
    await rig.service.update(user_id, renovation.id, {"status": "archived"})
    assert (await rig.service.resolve(user_id, "Renovation", change=True)).id == renovation.id


async def test_a_near_miss_may_be_read_but_never_changed(rig, user_id):
    renovation = await rig.service.create(user_id, ProjectDraft(name="Renovation"))
    assert (await rig.service.resolve(user_id, "Renovaton", change=False)).id == renovation.id
    refusal = await rig.service.resolve(user_id, "Renovaton", change=True)
    assert isinstance(refusal, ProjectRefusal) and refusal.tainted is False
    assert refusal == "No project is called “Renovaton”. Did you mean “Renovation”? Say it exactly."
    assert [project.name for project, _, _ in await rig.service.list(user_id)] == ["Renovation"]


async def test_several_matches_ask_which_one_and_carry_the_taint_of_the_names_shown(rig, user_id):
    await rig.service.create(user_id, ProjectDraft(name="Kitchen paint"))
    await rig.service.create(user_id, ProjectDraft(name="Garage paint"), tainted=True)
    refusal = await rig.service.resolve(user_id, "paint", change=False)
    assert refusal == ("Several projects match “paint”. "
                       "Say which one: “Garage paint” [from web content]; “Kitchen paint”.")
    assert refusal.tainted is True


async def test_an_unknown_name_is_refused_and_never_creates_a_project(rig, user_id):
    for change in (False, True):
        refusal = await rig.service.resolve(user_id, " Garden ", change=change)
        assert refusal == "No project is called “Garden”. Use create_project first."
        assert refusal.tainted is False
    assert await rig.service.list(user_id, include_archived=True) == ()
    assert await rig.projects.find(user_id, "Garden") is None


async def test_the_detail_holds_the_numbers_items_top_ups_and_lead(rig, cfg, user_id):
    lead = await make_bot(cfg, user_id, "Fixer")
    house = await rig.service.create(user_id, ProjectDraft(name="House", budget=Decimal("200"), lead_bot_id=lead.id))
    trip = await rig.service.create(user_id, ProjectDraft(name="Trip"))
    await rig.service.add_topup(user_id, house.id, Decimal("50"), "bonus")
    lunch = await _expense(rig, user_id, house.id, "40")
    void = await _expense(rig, user_id, house.id, "25")
    await rig.expenses.update(user_id, void.id, ExpensePatch({"status": "void"}))
    dollars = await _expense(rig, user_id, house.id, "9", currency="USD")
    await _expense(rig, user_id, trip.id, "70")
    task = await _task(rig, user_id, "Paint", house.id)
    note = await _note(rig, user_id, "Ideas", house.id)
    document = await _doc(rig, user_id, "Plan", house.id)

    detail = await rig.service.detail(user_id, house.id)

    assert isinstance(detail, ProjectDetail) and detail.project.id == house.id
    total = detail.numbers.total
    assert (total.budget, total.spent, total.remaining) == (Decimal("250"), Decimal("40"), Decimal("210"))
    assert dict(detail.numbers.other_currencies) == {"USD": Decimal("9")}
    assert {expense.id for expense in detail.expenses} == {lunch.id, void.id, dollars.id}
    assert [row.id for row in detail.tasks] == [task.id]
    assert [row.id for row in detail.notes] == [note.id]
    assert [row.id for row in detail.documents] == [document.id]
    assert [row.source for row in detail.topups if row.kind == "credit"] == ["bonus"]
    assert (detail.progress.total, detail.lead_bot_name, detail.tainted) == (1, "Fixer", False)


async def test_the_detail_shows_the_latest_page_of_expenses_notes_and_documents(rig, user_id, monkeypatch):
    monkeypatch.setattr(service_module, "PROJECT_PAGE_ITEMS", 2)
    house = await rig.service.create(user_id, ProjectDraft(name="House"))
    for number in (1, 2, 3):
        await _expense(rig, user_id, house.id, str(number), spent_at=f"2026-10-0{number}")
        await _note(rig, user_id, f"Note {number}", house.id)
        await _doc(rig, user_id, f"Doc {number}", house.id)

    detail = await rig.service.detail(user_id, house.id)

    assert [expense.amount for expense in detail.expenses] == [Decimal("3"), Decimal("2")]
    assert detail.numbers.total.spent == Decimal("6")
    assert [note.title for note in detail.notes] == ["Note 3", "Note 2"]
    assert [document.title for document in detail.documents] == ["Doc 3", "Doc 2"]


async def test_the_detail_gives_each_task_its_planned_spent_and_left(rig, user_id, monkeypatch):
    """Design §2 and P6: a task's budget slice against the counted expenses linked
    to it, over every expense of the project, not only the latest page."""
    monkeypatch.setattr(service_module, "PROJECT_PAGE_ITEMS", 1)
    house = await rig.service.create(user_id, ProjectDraft(name="House"))
    paint = await rig.tasks.create(user_id, TaskDraft(title="Paint", project_id=house.id,
                                                      allocated_budget=Decimal("100")),
                                   created_by_bot=None, tainted=False)
    tiles = await _task(rig, user_id, "Tiles", house.id)
    for amount, task_id in (("30", paint.id), ("12.50", paint.id), ("99", None)):
        draft = ExpenseDraft(house.id, Decimal(amount), spent_at=today_madrid(), task_id=task_id)
        await rig.expenses.add(user_id, draft, created_by_bot=None, tainted=False)

    detail = await rig.service.detail(user_id, house.id)

    assert len(detail.expenses) == 1
    assert dict(detail.task_money) == {
        paint.id: TaskMoney(planned=Decimal("100"), spent=Decimal("42.50"), left=Decimal("57.50")),
        tiles.id: TaskMoney(planned=None, spent=Decimal("0"), left=None),
    }


async def test_the_detail_is_tainted_when_the_project_or_anything_it_shows_is_web_made(rig, user_id):
    house = await rig.service.create(user_id, ProjectDraft(name="House"))
    assert (await rig.service.detail(user_id, house.id)).tainted is False
    await _expense(rig, user_id, house.id, "5", tainted=True)
    assert (await rig.service.detail(user_id, house.id)).tainted is True
    garden = await rig.service.create(user_id, ProjectDraft(name="Garden"))
    await _note(rig, user_id, "From a page", garden.id, tainted=True)
    assert (await rig.service.detail(user_id, garden.id)).tainted is True
    web = await rig.service.create(user_id, ProjectDraft(name="Web"), tainted=True)
    assert (await rig.service.detail(user_id, web.id)).tainted is True
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_project_service.py -q`
Expected: FAIL at collection, with `ImportError: cannot import name 'service' from 'roost.projects'` (the first import, `from roost.projects import service as service_module`; `roost/projects/__init__.py` exists since Task 3) and `1 error`.

- [ ] **Step 4: Add the constant (after the stuck flow, after Task 2)**

In `roost/constants.py`, in the Finance section (the stuck flow never edits it), find this line, which Task 2 added:

```python
TOPUP_SOURCE_MAX_CHARS = 120
```

Replace it with:

```python
TOPUP_SOURCE_MAX_CHARS = 120
# The most project names one "Did you mean …?" or "Say which one: …" refusal lists (ProjectService.resolve).
PROJECT_MATCHES_SHOWN = 5
```

- [ ] **Step 5: Implement `ProjectService`**

Create `roost/projects/service.py`:

```python
"""``ProjectService`` — one place for projects (projects hub: P1, P2, P5, H2–H4,
H7, H9, H10, H15).

A project is a ``money_projects`` row (``ProjectStore``). Its expenses always
belong to one project; its tasks, notes and documents link to it by
``project_id``. Tools and HTTP routes both go through this service, so the
Board updates whoever changed a project: every change rides on
``money_changed`` with an H10 ``change`` and the project's or the top-up's id.
A total budget set or cleared from the Board (P3, H5) rides on it as
``MoneyService``'s ``budget_set``, the frame a bot's ``set_budget`` sends.

- General (H2) is hidden from the list and can be neither changed (its
  total budget included) nor deleted, and no other project may take its name.
- A name a bot gives is exact-or-ask (H3, ``resolve``): a lone near miss may
  be read but never changed, several hits ask which one, and nothing is ever
  created from a name here.
- Every ``ValueError`` text is a plain sentence with no apostrophe, so the
  tools' ``html.escape`` leaves it readable (see ``TaskPatch``)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Literal, Mapping, Sequence

from roost.bots.store import BotStore
from roost.constants import (
    GENERAL_PROJECT_NAME, PROJECT_LIST_LIMIT, PROJECT_MATCHES_SHOWN, PROJECT_PAGE_ITEMS, PROJECT_STATUSES,
    TOPUP_SOURCE_MAX_CHARS,
)
from roost.documents.models import DocumentMeta
from roost.documents.store import DocumentStore
from roost.events.hub import EventHub
from roost.money.amounts import parse_amount
from roost.money.expense_store import ExpenseStore
# LEAD_BOT_TEXT, STATUS_TEXT and CURRENCY_LOCKED_TEXT are Task 2's sentences, re-exported from here for
# the routes (Task 8), so a service refusal and a store refusal can never read differently.
from roost.money.models import LEAD_BOT_TEXT, STATUS_TEXT, Expense, Project, ProjectDraft, ProjectPatch, TopUp
from roost.money.months import current_month
from roost.money.project_store import CURRENCY_LOCKED_TEXT, ProjectStore, is_general
from roost.money.service import MoneyChange      # "budget_set": the frame a bot's set_budget sends too
from roost.notes.models import Note
from roost.notes.store import NoteStore
from roost.projects.numbers import Progress, ProjectNumbers, TaskMoney, progress, project_numbers, task_money
from roost.records.resolver import NamedRef, Resolve
from roost.records.resolver import resolve as resolve_name
from roost.tasks.models import Task
from roost.tasks.store import TaskStore

ProjectChange = Literal[
    "project_created", "project_updated", "project_deleted", "topup_added", "topup_edited", "topup_undone",
]
ProjectRow = tuple[Project, ProjectNumbers, Progress]

GENERAL_FIXED_TEXT = "General is where expenses with no project go; it cannot be changed or deleted."
GENERAL_NAME_TEXT = "General is kept for expenses with no project; pick another name."
TOPUP_SOURCE_TEXT = f"A top-up source has at most {TOPUP_SOURCE_MAX_CHARS} characters."
NO_PROJECT_TEXT = "No project is called “{name}”. Use create_project first."
NEAR_MISS_TEXT = "No project is called “{name}”. Did you mean {names}? Say it exactly."
SEVERAL_TEXT = "Several projects match “{name}”. Say which one: {names}."
WEB_MARK = " [from web content]"

_ACTIVE = PROJECT_STATUSES[0]       # "active": archived projects are listed after the active ones


@dataclass(frozen=True)
class ProjectDetail:
    """A project's page (H14) and ``get_project``'s answer. ``numbers`` cover
    every expense; ``expenses``, ``notes`` and ``documents`` are the latest
    ``PROJECT_PAGE_ITEMS``; ``tasks`` and ``topups`` are complete. ``tainted``:
    the project or a record behind the page is web-made. ``task_money``: each
    task's planned / spent / left (design §2), over every expense, by task id."""

    project: Project
    numbers: ProjectNumbers
    progress: Progress
    tasks: tuple[Task, ...]
    expenses: tuple[Expense, ...]
    notes: tuple[Note, ...]
    documents: tuple[DocumentMeta, ...]
    topups: tuple[TopUp, ...]
    lead_bot_name: str | None
    tainted: bool
    task_money: Mapping[str, TaskMoney]


class ProjectRefusal(str):
    """``resolve``'s refusal: a plain, unescaped ``str`` (the contract's
    ``Project | str``) that also carries the taint of the project names it
    shows (M1 D3), so the tool that echoes it taints the run."""

    tainted: bool

    def __new__(cls, text: str, *, tainted: bool = False) -> ProjectRefusal:
        refusal = super().__new__(cls, text)
        refusal.tainted = tainted
        return refusal


def _folded(name: str) -> str:
    """The folding ``ProjectStore``'s ``name_key`` uses: case and spacing ignored."""
    return " ".join(name.casefold().split())


def _is_general_name(name: str) -> bool:
    return _folded(name) == _folded(GENERAL_PROJECT_NAME)


def _clean_source(source: str | None) -> str | None:
    text = (source or "").strip()
    if len(text) > TOPUP_SOURCE_MAX_CHARS:
        raise ValueError(TOPUP_SOURCE_TEXT)
    return text or None


def _names(projects: Sequence[Project]) -> str:
    """Names for a refusal, by name, each web-made one marked as such."""
    shown = sorted(projects, key=lambda project: project.name.casefold())
    return "; ".join(f"“{project.name}”" + (WEB_MARK if project.tainted else "") for project in shown)


def _refusal(name: str, hit: Resolve, by_id: Mapping[str, Project]) -> ProjectRefusal:
    """H3's three refusals. One that lists names carries their taint (M1 D3)."""
    shown = tuple(by_id[candidate.id] for candidate in hit.candidates[:PROJECT_MATCHES_SHOWN])
    tainted, wanted = any(project.tainted for project in shown), name.strip()
    if hit.reason == "fuzzy":
        return ProjectRefusal(NEAR_MISS_TEXT.format(name=wanted, names=_names(shown)), tainted=tainted)
    if hit.reason == "multi":
        return ProjectRefusal(SEVERAL_TEXT.format(name=wanted, names=_names(shown)), tainted=tainted)
    return ProjectRefusal(NO_PROJECT_TEXT.format(name=wanted))


class ProjectService:
    def __init__(self, projects: ProjectStore, expenses: ExpenseStore, tasks: TaskStore, notes: NoteStore,
                 documents: DocumentStore, bots: BotStore, events: EventHub) -> None:
        self._projects = projects
        self._expenses = expenses
        self._tasks = tasks
        self._notes = notes
        self._documents = documents
        self._bots = bots
        self._events = events

    async def list(self, user_id: str, *, include_archived: bool = False) -> tuple[ProjectRow, ...]:
        """The Projects tab and ``list_projects``: General hidden (H2), active
        before archived, then by name, at most ``PROJECT_LIST_LIMIT``. Tasks
        are one query, grouped here. Expenses are read per project shown,
        because the store has no all-projects read and every amount is
        decrypted either way."""
        found = await self._projects.list(user_id, include_archived=include_archived)
        shown = sorted((project for project in found if not is_general(project)),
                       key=lambda project: (project.status != _ACTIVE, project.name.casefold()))
        tasks = await self._tasks.list(user_id, status="all")
        month = current_month()
        return tuple([await self._row(user_id, project, tasks, month) for project in shown[:PROJECT_LIST_LIMIT]])

    async def detail(self, user_id: str, project_id: str) -> ProjectDetail | None:
        project = await self._projects.get(user_id, project_id)
        if project is None:
            return None
        expenses = await self._expenses.list_project(user_id, project_id)
        tasks = await self._tasks.list(user_id, status="all", project_id=project_id)
        notes = await self._notes.for_project(user_id, project_id, PROJECT_PAGE_ITEMS)
        documents = await self._documents.for_project(user_id, project_id, PROJECT_PAGE_ITEMS)
        topups = await self._projects.topups(user_id, project_id)
        records = (*tasks, *expenses, *notes, *documents, *topups)
        return ProjectDetail(
            project=project, numbers=project_numbers(project, expenses, current_month()), progress=progress(tasks),
            tasks=tasks, expenses=expenses[:PROJECT_PAGE_ITEMS],      # list_project is newest spent_at first
            notes=notes, documents=documents, topups=topups,
            lead_bot_name=await self._lead_bot_name(user_id, project.lead_bot_id),
            tainted=project.tainted or any(record.tainted for record in records),
            task_money=MappingProxyType({task.id: task_money(task, expenses, project.currency) for task in tasks}),
        )

    async def create(self, user_id: str, draft: ProjectDraft, *, created_by_bot: str | None = None,
                     tainted: bool = False) -> Project:
        """A new project. The store checks its fields and refuses a name in use."""
        if _is_general_name(draft.name):
            raise ValueError(GENERAL_NAME_TEXT)
        await self._check_lead_bot(user_id, draft.lead_bot_id)
        project = await self._projects.create(user_id, draft, created_by_bot=created_by_bot, tainted=tainted)
        await self._changed(user_id, "project_created", project.id)
        return project

    async def update(self, user_id: str, project_id: str, changes: Mapping[str, object]) -> Project | None:
        """Rename, colour, dates, lead bot, monthly limit, archive / unarchive
        and currency. ``None``: no such project."""
        patch = ProjectPatch(changes)          # each field's shape, the status included, checked and tidied
        current = await self._projects.get(user_id, project_id)
        if current is None:
            return None
        await self._check_changes(user_id, current, patch.changes)
        updated = await self._projects.update(user_id, project_id, patch)
        if updated is not None:
            await self._changed(user_id, "project_updated", updated.id)
        return updated

    async def delete(self, user_id: str, project_id: str) -> bool:
        """H9 in the store's one transaction: the expenses move to General, the
        tasks, notes and documents lose the link and stay, and the project is
        soft-deleted. ``project_deleted`` makes every open tab refresh them."""
        current = await self._projects.get(user_id, project_id)
        if current is None:
            return False
        if is_general(current):
            raise ValueError(GENERAL_FIXED_TEXT)
        deleted = await self._projects.delete(user_id, project_id)
        if deleted:
            await self._changed(user_id, "project_deleted", project_id)
        return deleted

    async def set_budget(self, user_id: str, project_id: str, amount: Decimal | None) -> Project | None:
        """Set the total budget from the Board (P3), or clear it with ``None``
        (H5). The store writes the "Budget set" row. General is refused like
        any other change to it (H2). ``None``: no such project."""
        checked = None if amount is None else parse_amount(amount)
        current = await self._projects.get(user_id, project_id)
        if current is None:
            return None
        if is_general(current):
            raise ValueError(GENERAL_FIXED_TEXT)
        updated = await self._projects.set_budget(user_id, project_id, checked, created_by_bot=None, tainted=False)
        if updated is not None:
            await self._changed(user_id, "budget_set", project_id)
        return updated

    async def add_topup(self, user_id: str, project_id: str, amount: Decimal, source: str | None = None, *,
                        created_by_bot: str | None = None, tainted: bool = False) -> TopUp | None:
        """Raise the total budget by ``amount`` (H4). ``None``: no such project."""
        checked, cleaned = parse_amount(amount), _clean_source(source)
        if await self._projects.get(user_id, project_id) is None:
            return None
        topup = await self._projects.add_topup(user_id, project_id, checked, cleaned,
                                               created_by_bot=created_by_bot, tainted=tainted)
        await self._changed(user_id, "topup_added", topup.id)
        return topup

    async def edit_topup(self, user_id: str, topup_id: str, amount: Decimal) -> TopUp | None:
        """``amount`` is the top-up's new amount; the store writes the difference (H4)."""
        topup = await self._projects.edit_topup(user_id, topup_id, parse_amount(amount))
        if topup is not None:
            await self._changed(user_id, "topup_edited", topup_id)
        return topup

    async def undo_topup(self, user_id: str, topup_id: str) -> TopUp | None:
        """The top-up and all its edits leave the budget together (H4)."""
        topup = await self._projects.undo_topup(user_id, topup_id)
        if topup is not None:
            await self._changed(user_id, "topup_undone", topup_id)
        return topup

    async def topups(self, user_id: str, project_id: str) -> tuple[TopUp, ...] | None:
        """The history, newest first, with undone rows. ``None``: no such project."""
        if await self._projects.get(user_id, project_id) is None:
            return None
        return await self._projects.topups(user_id, project_id)

    async def resolve(self, user_id: str, name: str, *, change: bool) -> Project | ProjectRefusal:
        """Exact-or-ask (H3) over every live project, archived ones included:
        an id, an exact name or a unique part of one. A lone near miss is
        read (``change=False``) but never changed. Nothing is ever created."""
        known = await self._projects.list(user_id, include_archived=True)
        by_id = {project.id: project for project in known}
        if name.strip() in by_id:
            return by_id[name.strip()]
        hit = resolve_name(name, [NamedRef(project.id, project.name) for project in known])
        if hit.resolved is not None and (hit.reason != "fuzzy" or not change):
            return by_id[hit.resolved.id]
        return _refusal(name, hit, by_id)

    async def _row(self, user_id: str, project: Project, tasks: Sequence[Task], month: str) -> ProjectRow:
        expenses = await self._expenses.list_project(user_id, project.id)
        own = tuple(task for task in tasks if task.project_id == project.id)
        return project, project_numbers(project, expenses, month), progress(own)

    async def _check_changes(self, user_id: str, current: Project, changes: Mapping[str, object]) -> None:
        """The rules only the service can check, on ``ProjectPatch``'s tidied
        values (an upper-cased currency, a stripped bot id). The patch already
        checked each field's shape, the status included."""
        if is_general(current):
            raise ValueError(GENERAL_FIXED_TEXT)
        if "name" in changes and _is_general_name(str(changes["name"])):
            raise ValueError(GENERAL_NAME_TEXT)
        if "lead_bot_id" in changes:
            await self._check_lead_bot(user_id, changes["lead_bot_id"])
        new_currency = changes.get("currency", current.currency)
        if new_currency != current.currency and await self._projects.has_money(user_id, current.id):
            raise ValueError(CURRENCY_LOCKED_TEXT)

    async def _check_lead_bot(self, user_id: str, bot_id: object) -> None:
        """H15: a lead bot is one of the user's own bots; ``None`` clears it."""
        if bot_id is None:
            return
        if not isinstance(bot_id, str) or await self._bots.get(user_id, bot_id) is None:
            raise ValueError(LEAD_BOT_TEXT)

    async def _lead_bot_name(self, user_id: str, bot_id: str | None) -> str | None:
        bot = await self._bots.get(user_id, bot_id) if bot_id else None
        return bot.name if bot is not None else None

    async def _changed(self, user_id: str, change: ProjectChange | MoneyChange, item_id: str) -> None:
        await self._events.publish(user_id, {"type": "money_changed", "change": change, "id": item_id})
```

- [ ] **Step 6: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_project_service.py -q`
Expected: PASS, `21 passed`.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_project_service.py --cov=roost.projects.service --cov-report=term-missing -q`
Expected: PASS. `roost/projects/service.py` is at 80% or more. 100% of its lines is expected: every line, each refusal included, runs in some test.

No existing test changes: this task only adds a module, a test file and one constant. The stores it builds on, and their own tests from Tasks 2–5, must stay green:

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_project_store.py tests/test_project_numbers.py tests/test_task_projects.py tests/test_notes_docs_projects.py tests/test_money_store.py tests/test_money_tools.py tests/test_money_api.py tests/test_money_values.py tests/test_task_store.py tests/test_note_store.py tests/test_document_store.py tests/test_bot_store.py tests/test_events_hub.py tests/test_vocabulary.py -q`
Expected: PASS.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest --cov=roost --cov-fail-under=80 -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost
git add roost/constants.py roost/projects/service.py tests/test_project_service.py
git status --short   # nothing from this task may still be listed as modified or untracked
git commit -m "feat: ProjectService: the project list and page, create, update, delete, the total budget, top-ups and exact-or-ask names"
```

---

### Task 7: Bots learn projects: project tools and the project argument everywhere

This task implements design §3 ("Bot tools") with the refinements H1 (the `project` argument and its `category` alias), H3 (exact-or-ask names; only `log_expense` finds or creates; archived projects take no money), H4 (`add_topup` is a `write_change`), H5 (`set_budget` can clear), H6 (void and starred), H7 (an expense with no currency takes its project's), H11 (task budget slice, `failed`, an expense's task and step), H12 (notes and documents, `set_document_project`) and H15 (the lead bot is one of the user's bots), for P1, P2 and P5 (every bot can work on every project).
- **Project tools** (`roost/projects/tool_specs.py`, `roost/projects/tools.py`): `list_projects` and `get_project` read; `create_project` creates; `update_project`, `add_topup`, `edit_topup` and `undo_topup` change, so a run that read a web page is refused by the gate. Deleting a project is never a tool (design §3).
- **One way to name a project** (`roost/projects/refs.py`): every tool except `log_expense` goes through Task 6's `ProjectService.resolve`. A read tool may answer a near miss; a change or a new record never lands on one ("Did you mean …? Say it exactly."), and nothing is created from a name. Each refusal carries the taint of the names it shows (M1 D3).
- **Money:** `log_expense` and `update_expense` take `project`, `task` (any status), `step` (needs its task, must be one of its steps) and `starred`; `update_expense` also takes `void`. With a task and no project named, the money goes to the task's project. An archived project takes no new or moved expense. `set_budget` is exact-or-ask and `''` clears the total budget. `list_expenses` names its project exact-or-ask.
- **Tasks:** `add_task` takes `project` and `budget` (a slice needs a project); `update_task` takes `project` (`''` unlinks), `budget` (`''` clears) and the status `failed` (→ `TaskService.fail`, a repeating task comes back); `list_tasks` takes `project` and the status `failed`.
- **Notes and documents (H12):** `add_note`, `find_notes` and `update_note` take `project` (`''` unlinks on update, without bumping the revision); `create_doc`, `create_sheet` and `list_documents` take `project`; `make_pdf_from_doc` inherits its doc's project (Task 5); the new `set_document_project` (`write_change`) moves a document.
- **The prompt** (`_RECORDS_TEXT`) names projects and never says "role".

Snippets marked **(after the stuck flow)** are written against `roost/talk/tool_catalog.py` and `roost/talk/instructions.py` as the finished stuck-flow plan leaves them (its Task 4 is the only stuck task that touches them, and both anchors below are lines it does not change). Snippets marked **(after Task N)** are written against that hub task's state. The files this task replaces whole were last written by the task named next to them.

**Files:**
- Create:
  - `roost/projects/tool_specs.py` — `PROJECT_TOOL_DEFS` and the seven specs.
  - `roost/projects/tool_args.py` — the project tools' pydantic arguments and field readers (`read_color`, `optional_day`, `project_changes`).
  - `roost/projects/refs.py` — `project_ref`, `required_project`, `id_of`, `project_taint`, `project_suffix`: how every record tool names a project.
  - `roost/projects/format.py` — the project tools' result text (list line, page, top-up history).
  - `roost/projects/tools.py` — `ProjectTools`.
  - `roost/money/tool_args.py` — the money tools' arguments (moved out of `tools.py`, which re-exports them by importing them), plus `task`, `step`, `starred`, `void`.
  - `roost/money/expense_links.py` — `ExpenseLink`, `find_link`, `find_task`, `find_step`.
  - `tests/test_project_tools.py`
- Modify:
  - `roost/constants.py` — Finance section: `EXPENSE_TASK_MATCHES_SHOWN`, `MAX_RECORD_ID_LENGTH` (after Task 6's `PROJECT_MATCHES_SHOWN`).
  - `roost/money/amounts.py` — `optional_amount`.
  - `roost/money/service.py` — whole file (last written by Task 1): `ExpenseEntry` gains `task_id`, `step_id`, `starred`, and `currency` defaults to `None`; `log_expense(..., project=None)`; `open_for_money`; `update_expense` refuses a move into an archived or unknown project; `set_budget` takes a found `Project` and `Decimal | None`.
  - `roost/money/tools.py` — whole file (last written by Task 1).
  - `roost/money/tool_specs.py` — whole file (last written by Task 1).
  - `roost/tasks/tools.py` — whole file (unchanged since before the hub).
  - `roost/tasks/tool_specs.py` — whole file (last written by Task 1).
  - `roost/notes/tools.py`, `roost/notes/tool_specs.py` — whole files (unchanged since before the hub).
  - `roost/documents/tool_args.py`, `roost/documents/tools.py`, `roost/documents/tool_specs.py` — whole files (unchanged since before the hub); `DOCUMENT_TOOL_DEFS` gains `set_document_project`.
  - `roost/talk/domain_tools.py` — `build_domain_tools` (after Task 1) wires one `ProjectService` into every handler and adds `ProjectTools`.
  - `roost/talk/tool_catalog.py` — (after the stuck flow) the import and `*PROJECT_TOOL_DEFS` after `*DOCUMENT_TOOL_DEFS`.
  - `roost/talk/instructions.py` — (after the stuck flow) `_RECORDS_TEXT`.
- Test:
  - `tests/test_project_tools.py` (new; holds both Review Focus tests assigned here)
  - `tests/test_money_tools.py` (after Task 1), `tests/test_task_tools.py`, `tests/test_note_tools.py`, `tests/test_document_tools.py` (after Task 1), `tests/test_every_bot_tools.py` (after Task 1), `tests/test_instructions.py` (after the stuck flow): imports widened, tests appended.

**Interfaces:**
- Consumes:
  - **Task 1:** `ProjectStore` (`roost/money/project_store.py`); `MoneyService(projects, expenses, events)` with `project_for`, `projects`, `list_expenses`, `get_expense`, `made_by`, `summary`, `keep_expense`, `delete_expense`, `_changed`; Task 1's `ExpenseEntry`, money tool args (`_PROJECT_ARG`) and specs (replaced whole here); `GENERAL_PROJECT_NAME`; `MAX_CATEGORY_NAME_LENGTH` (the project-name cap the contract keeps); the test helpers `_tool`, `_talk` (returns the rig) and `_tool_texts(request)` of `tests/test_money_tools.py`.
  - **Task 2:** in `roost/money/models.py`, `Project.status/color/start_date/due_date/monthly_budget/lead_bot_id`, `ProjectDraft`, `ProjectPatch`, `TopUp` (`id`, `project_id`, `amount`, `currency`, `source`, `kind`, `topup_id`, `undone`, `created_at`, `tainted`), `TOPUP_CREDIT`, `COLOR_TEXT` (it lists the palette; `read_color` refuses with it); `TopUpUndone` (a `ValueError`, "That top-up was undone already.") raised by `edit_topup` / `undo_topup` for an undone credit, which return `None` only for an id that is not one of the user's credits on a live project; `ProjectStore.create`, `.find`, `.get`, `.list(user_id, *, include_archived=True)`, `.update`, `.add_topup -> TopUp`, `.topups`, `.set_budget(user_id, project_id, amount: Decimal | None, *, created_by_bot, tainted) -> Project | None` (`None` clears, H5); constants `PROJECT_STATUSES`, `PROJECT_COLORS`, `DEFAULT_PROJECT_COLOR`, `PROJECT_PAGE_ITEMS`, `TOPUP_SOURCE_MAX_CHARS`.
  - **Task 3:** `ExpenseDraft.task_id/step_id/is_favorite`; `EXPENSE_POSTED`, `EXPENSE_VOID`; `EXPENSE_PATCHABLE` ⊇ `{task_id, step_id, is_favorite, status}`; `ExpenseStore.list_project`; `expense_line` (marks `[void]`, `[starred]`); `summary_text`; `BudgetLine`, `ProjectNumbers`, `Progress`, `TaskMoney` from `roost/projects/numbers.py`.
  - **Task 4:** `TaskDraft.project_id/allocated_budget`; `TaskStatus`/`TaskFilter` with `"failed"`; `TaskService.list(user_id, *, status, project_id=None)`, `TaskService.fail -> Completion | None`; `TaskStore.create`/`update` raising `"A budget slice needs a project."` and `"No such project."`; `task_line`'s `[✗]`; `NO_SUCH_PROJECT_TEXT` from `roost/records/project_link.py`.
  - **Task 5:** `Note.project_id`, `NoteDraft(..., project_id=)`, `new_note_draft(..., *, project_id=None)`, `NoteService.search(..., project_id=None)`, `NoteService.set_project`; `DocumentMeta.project_id`, `DocumentService.list(user_id, kind=None, *, project_id=None)`, `create_doc/create_sheet(..., project_id=None)`, `DocumentService.set_project`, `make_pdf` inheriting `source.meta.project_id`.
  - **Task 6:** `ProjectService(projects, expenses, tasks, notes, documents, bots, events)` with `list`, `detail`, `create`, `update`, `add_topup`, `edit_topup`, `undo_topup`, `resolve(user_id, name, *, change) -> Project | ProjectRefusal`; `ProjectRefusal` (a `str` with `.tainted`); `ProjectDetail` (with its *extra* `task_money`); `ProjectRow`; `WEB_MARK`; its texts (`NEAR_MISS_TEXT`, `SEVERAL_TEXT`, `NO_PROJECT_TEXT`, `GENERAL_FIXED_TEXT`, `GENERAL_NAME_TEXT`); the constant line `PROJECT_MATCHES_SHOWN = 5` (an anchor here).
  - **Existing:** `RecordContext`, `ToolOutcome`, `ToolDef`, `ToolSpec`, `resolve`/`NamedRef`, `ToolText`, `BotStore.list`, `normalize_bot_name`, `parse_amount`, `amount_text`, `TAINTED_CHANGE_TEXT`, `DESK_TOOLS`, `TEAM_TOOLS`, `LEAD_TOOLS`, `CREATOR_TOOLS`.
- Produces (later tasks rely on these exact names):
  - `roost/projects/tool_specs.py`: `PROJECT_TOOL_DEFS` = `list_projects` (read), `get_project` (read), `create_project` (write_create), `update_project`, `add_topup`, `edit_topup`, `undo_topup` (write_change); the `*_SPEC` names.
  - `roost/projects/tools.py`: `ProjectTools(service: ProjectService, bots: BotStore, expenses: ExpenseStore)`; texts `GONE_TEXT`, `NO_TOPUP_TEXT`, `NOTHING_TO_CHANGE_TEXT`, `NO_SUCH_BOT_TEXT`.
  - `roost/projects/refs.py`: `project_ref(projects, user_id, name, *, change) -> Project | ToolOutcome | None`, `required_project(...) -> Project | ToolOutcome`, `id_of`, `project_taint`, `project_suffix`, `NAME_THE_PROJECT_TEXT`.
  - `roost/projects/format.py`: `budget_text`, `task_money_text` (each task's planned / spent / left on `get_project`, from Task 6's *extra* `ProjectDetail.task_money`), `progress_text`, `project_line`, `project_list_text`, `project_brief`, `project_page_text`, `topup_label` ("Top-up" / "Top-up changed" / "Budget set", H4), `topup_line`, `NO_PROJECTS_TEXT`, `NO_ACTIVE_PROJECTS_TEXT`.
  - `roost/money/amounts.py`: `optional_amount(value) -> Decimal | None` (`None` or blank text → `None`).
  - `roost/money/service.py`: `ExpenseEntry(amount, spent_at, project=None, note=None, vendor=None, currency=None, task_id=None, step_id=None, starred=False)`; `MoneyService.log_expense(user_id, entry, *, created_by_bot=None, tainted=False, project: Project | None = None)`; `MoneyService.update_expense` raises `ValueError` for a move into an archived (`ARCHIVED_TEXT`) or unknown (`NO_SUCH_PROJECT_TEXT`) project; `MoneyService.set_budget(user_id, project: Project, amount: Decimal | None, *, created_by_bot=None, tainted=False) -> Project | None`; `open_for_money(project)`; `ARCHIVED_TEXT = "“{name}” is archived; unarchive it first."`.
  - **For Task 8:** `POST /api/money/expenses` must call `log_expense` **inside** the route's `try` (`ValueError` → 422): an archived project now raises `ARCHIVED_TEXT`. `ExpenseIn.currency` may default to `None` so a Board expense takes its project's currency (H7); `ExpenseEntry` already reads `None` that way.
  - `roost/money/tool_args.py`: `PROJECT_ARG`, `LogExpenseArgs`, `MonthArgs`, `ListExpensesArgs`, `ExpenseRefArgs`, `UpdateExpenseArgs`, `SetBudgetArgs` (still importable from `roost.money.tools`).
  - `roost/money/expense_links.py`: `ExpenseLink(task, step)` (`.task_id`, `.step_id`, `.tainted`), `NO_LINK`, `find_link`, `find_task`, `find_step`, `STEP_NEEDS_TASK_TEXT`.
  - Handler constructors: `MoneyTools(service, projects, tasks)`, `TaskTools(service, projects)`, `NoteTools(service, projects)`, `DocumentTools(service, projects)`.
  - `DOCUMENT_TOOL_DEFS` ends with `ToolDef(SET_DOCUMENT_PROJECT_SPEC, "write_change")`; `CATALOG` ends with `*PROJECT_TOOL_DEFS`.
  - `roost/constants.py`: `EXPENSE_TASK_MATCHES_SHOWN = 5`, `MAX_RECORD_ID_LENGTH = 64`.

- [ ] **Step 1: Path guard**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

Then confirm that Tasks 1–6 and the stuck flow have landed and this task has not:

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && grep -n "^class ProjectRefusal\|^ProjectRow\|    async def resolve" roost/projects/service.py && grep -n "    async def set_project" roost/notes/service.py roost/documents/service.py && grep -n "    async def fail" roost/tasks/service.py && grep -n "    async def list_project" roost/money/expense_store.py && grep -n "^PROJECT_MATCHES_SHOWN\|^PROJECT_COLORS\|^TOPUP_SOURCE_MAX_CHARS" roost/constants.py && grep -n "^NO_SUCH_PROJECT_TEXT" roost/records/project_link.py && grep -n "ASK_FOR_HELP_SPEC, \"read\"" roost/talk/tool_catalog.py && test ! -e roost/projects/tool_specs.py && echo "no project tools yet"`

Expected: every grep prints at least one line (`ProjectRefusal`, `ProjectRow`, `resolve`; the two `set_project`; `fail`; `list_project`; the three constants; `NO_SUCH_PROJECT_TEXT`; the stuck flow's `ask_for_help` ToolDef), then `no project tools yet`. If anything is missing, stop: an earlier task comes first.

Then list the functions of the files this task replaces whole:

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && grep -n "^def \|^class \|^    async def \|^    def " roost/money/service.py roost/money/tools.py roost/tasks/tools.py roost/notes/tools.py roost/documents/tools.py`

Expected:
- `money/service.py`: `ExpenseEntry`, `MoneyService`, `__init__`, `project_for`, `log_expense`, `projects`, `list_expenses`, `get_expense`, `made_by`, `summary`, `update_expense`, `keep_expense`, `delete_expense`, `set_budget`, `_changed`.
- `money/tools.py`: the six args classes, `_month`, `_project_name`, `_project_tainted`, `MoneyTools` with `__init__`, `activity`, `run`, `_log`, `_list`, `_summary`, `_update`, `_changes`, `_delete`, `_budget`.
- `tasks/tools.py`: `_escape`, the four args classes, `_in_category`, `TaskTools` with `__init__`, `activity`, `run`, `_add`, `_list`, `_update`, `_complete`, `_delete`, `_find`, and `_titles`.
- `notes/tools.py`: `_escape`, the six args classes (`UpdateNoteArgs.changes`), `_titles`, `NoteTools` with `__init__`, `activity`, `run`, `_add`, `_find`, `_read`, `_append`, `_update`, `_delete`, `_find_one`.
- `documents/tools.py`: `_escape`, `_title`, `_match`, `_saved`, `DocumentTools` with `__init__`, `activity`, `run`, `_list`, `_read`, `_create_doc`, `_create_sheet`, `_append`, `_cells`, `_delete`, `_make_pdf`, `_find_kind`, `_find`.

If an earlier task added another function to one of these files, carry it over unchanged into that file's replacement below.

- [ ] **Step 2: Write the failing tests**

**2a.** Create `tests/test_project_tools.py`:

```python
"""Bots learn projects (projects hub Task 7): the project tools over the user's
projects, exact-or-ask project names on every record tool (H3), top-ups as
changes (H4), the lead bot (H15), and the tainted-write rule over all of it
(M1 D3)."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from roost.config import load_config
from roost.constants import PROJECT_COLORS
from roost.db.connection import init_db
from roost.documents.service import DocumentService
from roost.documents.store import DocumentStore
from roost.documents.tool_specs import DOCUMENT_TOOL_DEFS
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.llm.types import ToolCallRequested, TurnDone
from roost.money.expense_store import ExpenseStore
from roost.money.models import ExpenseDraft, ProjectDraft
from roost.money.months import today_madrid
from roost.money.project_store import ProjectStore
from roost.notes.models import NoteDraft
from roost.notes.store import NoteStore
from roost.projects.tool_specs import PROJECT_TOOL_DEFS
from roost.talk.gate import TAINTED_CHANGE_TEXT
from roost.talk.tool_catalog import CATALOG
from roost.tasks.models import TaskDraft
from roost.tasks.store import TaskStore
from team_helpers import make_bot, make_rig, say, send, team_model, wait_idle

NEAR_MISS = "Refused: No project is called “Renovaton”. Did you mean “Renovation”? Say it exactly."
NO_GARDEN = "Refused: No project is called “Garden”. Use create_project first."


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


def _tool(call_id: str, name: str, **arguments):
    return [ToolCallRequested(id=call_id, name=name, arguments=arguments), TurnDone("tool_use")]


async def _talk(cfg, user_id, bot, script: dict, text: str):
    rig = make_rig(cfg, team_model(script))
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, text)
    await wait_idle(rig.runner)
    return rig


def _tool_texts(request) -> list[str]:
    return [turn.text for turn in request.turns if turn.role == "tool"]


async def _project(cfg, user_id, name: str, *, tainted: bool = False, **fields):
    return await ProjectStore(cfg).create(user_id, ProjectDraft(name=name, **fields), created_by_bot=None,
                                          tainted=tainted)


def _documents(cfg) -> DocumentService:
    return DocumentService(DocumentStore(cfg), EventHub(cfg))


def test_the_project_tools_and_their_gate_kinds():
    """Design §3 with H4: a top-up changes an existing budget, so it is a change.
    Deleting a project is the Board's alone, never a tool."""
    assert [(tool.name, tool.kind) for tool in PROJECT_TOOL_DEFS] == [
        ("list_projects", "read"), ("get_project", "read"), ("create_project", "write_create"),
        ("update_project", "write_change"), ("add_topup", "write_change"), ("edit_topup", "write_change"),
        ("undo_topup", "write_change"),
    ]
    assert {tool.name: tool.kind for tool in DOCUMENT_TOOL_DEFS}["set_document_project"] == "write_change"
    names = list(CATALOG)
    assert names.index("list_projects") == names.index("set_document_project") + 1
    assert "delete_project" not in CATALOG
    for tool in PROJECT_TOOL_DEFS:
        text = tool.spec.description + json.dumps(tool.spec.input_schema)
        assert " role" not in tool.spec.description and "control" not in tool.name
        assert "categor" not in text.casefold(), tool.name


async def test_a_near_miss_project_name_never_changes_anything(cfg, user_id):
    """Review Focus 1 (H3): "Renovaton" for "Renovation". A read may answer with
    the near project; every change and every new record is refused with "Did
    you mean …?"; only log_expense (find-or-create) files money there."""
    bot = await make_bot(cfg, user_id, "Helper")
    project = await _project(cfg, user_id, "Renovation")
    await TaskStore(cfg).create(user_id, TaskDraft(title="Paint the hall"), created_by_bot=None, tainted=False)
    await NoteStore(cfg).create(user_id, NoteDraft(title="Ideas", content="green tiles"), created_by_bot=None,
                                tainted=False)
    await _documents(cfg).create_doc(user_id, "Plan", "- tiles")
    expense = await ExpenseStore(cfg).add(user_id, ExpenseDraft(project.id, Decimal("10"), spent_at=today_madrid()),
                                          created_by_bot=None, tainted=False)
    near = "Renovaton"
    rig = await _talk(cfg, user_id, bot, {"Helper": [
        _tool("g", "get_project", project=near),
        _tool("l", "list_tasks", project=near),
        _tool("u", "update_project", project=near, name="Kitchen"),
        _tool("a", "add_topup", project=near, amount=50),
        _tool("b", "set_budget", project=near, amount=500),
        _tool("t", "add_task", title="Buy tiles", project=near),
        _tool("ut", "update_task", task="Paint the hall", project=near),
        _tool("n", "add_note", content="Green tiles", project=near),
        _tool("un", "update_note", note="Ideas", project=near),
        _tool("d", "create_doc", title="Tiles", markdown="- green", project=near),
        _tool("sd", "set_document_project", document="Plan", project=near),
        _tool("ue", "update_expense", expense=expense.id, project=near),
        _tool("e", "log_expense", amount=12, project=near),
        say("Which project did you mean?"),
    ]}, "put everything in Renovaton")
    texts = _tool_texts(rig.model.requests[-1])
    assert texts[0].startswith("“Renovation” in EUR") and texts[1] == "No tasks match."
    assert texts[2:12] == [NEAR_MISS] * 10
    assert texts[12].startswith(f"Logged 12.00 EUR to Renovation on {today_madrid()}")
    assert [p.name for p in await ProjectStore(cfg).list(user_id)] == ["Renovation"]
    kept = await ProjectStore(cfg).get(user_id, project.id)
    assert (kept.name, kept.budget) == ("Renovation", None)
    assert await ProjectStore(cfg).topups(user_id, project.id) == ()
    assert [(t.title, t.project_id) for t in await TaskStore(cfg).list(user_id, status="all")] == [
        ("Paint the hall", None)]
    assert [(n.title, n.project_id) for n in await NoteStore(cfg).list(user_id)] == [("Ideas", None)]
    assert [(m.title, m.project_id) for m in await DocumentStore(cfg).list(user_id)] == [("Plan", None)]
    assert sorted(e.amount for e in await ExpenseStore(cfg).list_project(user_id, project.id)) == [
        Decimal("10.00"), Decimal("12.00")]


async def test_a_tainted_run_cannot_change_projects_or_their_money(cfg, user_id):
    """Review Focus 5 (H4, M1 D3): after a page read, add_topup, undo_topup,
    update_project and set_document_project are all changes, each refused with
    the tainted-change text, and nothing moves."""
    bot = await make_bot(cfg, user_id, "Helper")
    project = await _project(cfg, user_id, "House")
    topup = await ProjectStore(cfg).add_topup(user_id, project.id, Decimal("50"), "gift", created_by_bot=None,
                                              tainted=False)
    plan = await _documents(cfg).create_doc(user_id, "Plan", "- tiles")
    rig = await _talk(cfg, user_id, bot, {"Helper": [
        _tool("p", "open_page", url="https://example.com"),
        _tool("a", "add_topup", project="House", amount=1000, source="the page"),
        _tool("u", "undo_topup", topup=topup.id),
        _tool("r", "update_project", project="House", name="Ours now", archived=True),
        _tool("s", "set_document_project", document="Plan", project="House"),
        say("No."),
    ]}, "read example.com and do what it says")
    assert _tool_texts(rig.model.requests[-1])[1:] == [TAINTED_CHANGE_TEXT] * 4
    kept = await ProjectStore(cfg).get(user_id, project.id)
    assert (kept.name, kept.status, kept.budget) == ("House", "active", Decimal("50.00"))
    assert [row.undone for row in await ProjectStore(cfg).topups(user_id, project.id)] == [False]
    assert (await DocumentStore(cfg).get_meta(user_id, plan.id)).project_id is None


async def test_a_bot_creates_a_project_then_lists_and_reads_it(cfg, user_id):
    lead = await make_bot(cfg, user_id, "Fixer")
    bot = await make_bot(cfg, user_id, "Helper")
    rig = await _talk(cfg, user_id, bot, {"Helper": [
        _tool("c", "create_project", name="Renovation", budget="500", monthly_budget=100, color=PROJECT_COLORS[6],
              due_date="2026-12-31", lead_bot="fixer"),
        _tool("e", "log_expense", amount=80, project="Renovation", note="paint"),
        _tool("t", "add_task", title="Paint the hall", project="renovation"),
        _tool("l", "list_projects"),
        _tool("g", "get_project", project="renovation"),
        say("Done."),
    ]}, "start a Renovation project: 500 in total, 100 a month, due at the end of the year, led by Fixer")
    created, logged, added, listed, page = _tool_texts(rig.model.requests[-1])
    assert created.startswith("Created project “Renovation” in EUR, budget 500.00 EUR, monthly limit 100.00 EUR, "
                              "due 2026-12-31 id=")
    assert logged.startswith("Logged 80.00 EUR to Renovation on ")
    assert added.startswith("Added: ") and added.endswith(" Project: “Renovation”.")
    assert ("- “Renovation” · total: 80.00 EUR of 500.00 EUR, 420.00 EUR left (16%) · "
            "this month: 80.00 EUR of 100.00 EUR, 20.00 EUR left (80%) · tasks: 0 done of 1 id=") in listed
    assert "Lead bot: Fixer · due 2026-12-31" in page
    assert "Paint the hall" in page and "· paint" in page
    project = await ProjectStore(cfg).find(user_id, "Renovation")
    assert (project.color, project.lead_bot_id, project.due_date, project.created_by_bot, project.tainted) == (
        PROJECT_COLORS[6], lead.id, "2026-12-31", bot.id, False)
    [task] = await TaskStore(cfg).list(user_id)
    assert task.project_id == project.id


async def test_get_project_shows_each_tasks_planned_spent_and_left(cfg, user_id):
    """Design §2 and P6: a task's budget slice against the counted expenses
    linked to it (Task 6's ProjectDetail.task_money)."""
    bot = await make_bot(cfg, user_id, "Helper")
    project = await _project(cfg, user_id, "Renovation")
    paint = await TaskStore(cfg).create(user_id, TaskDraft(title="Paint the hall", project_id=project.id,
                                                           allocated_budget=Decimal("100")),
                                        created_by_bot=None, tainted=False)
    tiles = await TaskStore(cfg).create(user_id, TaskDraft(title="Tiles", project_id=project.id),
                                        created_by_bot=None, tainted=False)
    await ExpenseStore(cfg).add(user_id, ExpenseDraft(project.id, Decimal("130"), spent_at=today_madrid(),
                                                      task_id=paint.id), created_by_bot=None, tainted=False)
    rig = await _talk(cfg, user_id, bot, {"Helper": [_tool("g", "get_project", project="Renovation"), say("ok")]},
                      "how is the hall going?")
    [page] = _tool_texts(rig.model.requests[-1])
    assert f"Paint the hall id={paint.id} · budget 100.00 EUR, spent 130.00 EUR, over by 30.00 EUR" in page
    assert page.count(f"Tiles id={tiles.id}") == 1 and f"Tiles id={tiles.id} ·" not in page


async def test_update_project_renames_archives_and_clears_the_monthly_limit(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Helper")
    project = await _project(cfg, user_id, "House", monthly_budget=Decimal("50"))
    rig = await _talk(cfg, user_id, bot, {"Helper": [
        _tool("u1", "update_project", project="house", name="Home", color=PROJECT_COLORS[2], start_date="2026-10-01",
              monthly_budget=""),
        _tool("u2", "update_project", project="Home", archived=True),
        _tool("l1", "list_projects"),
        _tool("l2", "list_projects", include_archived=True),
        _tool("u3", "update_project", project="Home", archived=False, color="pink"),
        _tool("u4", "update_project", project="Home"),
        say("ok"),
    ]}, "rename House to Home from 1 October, drop its monthly limit, then archive it")
    renamed, archived, hidden, shown, bad_colour, nothing = _tool_texts(rig.model.requests[-1])
    assert renamed.startswith("Updated: “Home” in EUR, starts 2026-10-01 id=") and "monthly limit" not in renamed
    assert archived.startswith("Updated: “Home” [archived] in EUR")
    assert hidden == "No active projects."
    assert shown.startswith("- “Home” [archived] · total: 0.00 EUR spent")
    assert bad_colour.startswith("Refused: A project colour is one of #64748b, ")
    assert nothing == "Refused: update_project needs something to change."
    kept = await ProjectStore(cfg).get(user_id, project.id)
    assert (kept.name, kept.color, kept.start_date, kept.monthly_budget, kept.status) == (
        "Home", PROJECT_COLORS[2], "2026-10-01", None, "archived")


async def test_the_lead_bot_is_one_of_the_users_own_bots(cfg, user_id):
    """H15: another user's bot is not found; '' clears the lead."""
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    await make_bot(cfg, bob, "Builder")
    await make_bot(cfg, user_id, "Fixer")
    bot = await make_bot(cfg, user_id, "Helper")
    project = await _project(cfg, user_id, "House")
    rig = await _talk(cfg, user_id, bot, {"Helper": [
        _tool("u1", "update_project", project="House", lead_bot="Builder"),
        _tool("u2", "update_project", project="House", lead_bot="@fixer"),
        _tool("g", "get_project", project="House"),
        _tool("u3", "update_project", project="House", lead_bot=""),
        say("ok"),
    ]}, "let Fixer lead the House project, then nobody")
    refused, led, page, cleared = _tool_texts(rig.model.requests[-1])
    assert refused == "Refused: None of your bots is called “Builder”."
    assert led.startswith("Updated: “House” in EUR") and "Lead bot: Fixer" in page
    assert cleared.startswith("Updated: “House” in EUR")
    assert (await ProjectStore(cfg).get(user_id, project.id)).lead_bot_id is None


async def test_a_top_up_is_added_changed_and_undone_with_its_history(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Helper")
    project = await _project(cfg, user_id, "House")
    first = await _talk(cfg, user_id, bot, {"Helper": [
        _tool("a", "add_topup", project="house", amount="100", source="birthday"), say("Added."),
    ]}, "add the 100 from my birthday to House")
    [credit] = [row for row in await ProjectStore(cfg).topups(user_id, project.id) if row.kind == "credit"]
    assert _tool_texts(first.model.requests[-1]) == [
        f"Added a 100.00 EUR top-up (id={credit.id}). The total budget of “House” is now 100.00 EUR."]
    second = await _talk(cfg, user_id, bot, {"Helper": [
        _tool("e", "edit_topup", topup=credit.id, amount=150),
        _tool("g", "get_project", project="House"),
        _tool("u", "undo_topup", topup=credit.id),
        _tool("a", "undo_topup", topup=credit.id),
        _tool("x", "undo_topup", topup="no-such-top-up"),
        say("ok"),
    ]}, "it was 150, actually; no, undo it")
    edited, page, undone, again, missing = _tool_texts(second.model.requests[-1])
    assert edited == "Changed the top-up to 150.00 EUR. The total budget of “House” is now 150.00 EUR."
    assert "Top-up 100.00 EUR · birthday" in page and "Top-up changed 50.00 EUR" in page
    assert undone.startswith("Undid the top-up and its changes.")
    assert again == "Refused: That top-up was undone already."
    assert missing == "Refused: there is no top-up with that id."
    assert ((await ProjectStore(cfg).get(user_id, project.id)).budget or Decimal("0")) == Decimal("0")


async def test_an_unknown_project_is_refused_and_only_log_expense_makes_one(cfg, user_id):
    """H3: a name no project has is refused everywhere but log_expense."""
    bot = await make_bot(cfg, user_id, "Helper")
    rig = await _talk(cfg, user_id, bot, {"Helper": [
        _tool("g", "get_project", project="Garden"),
        _tool("t", "add_task", title="Plant roses", project="Garden"),
        _tool("n", "add_note", content="Roses like sun", project="Garden"),
        _tool("d", "create_doc", title="Roses", markdown="- sun", project="Garden"),
        _tool("b", "set_budget", project="Garden", amount=100),
        _tool("e", "log_expense", amount=7, project="Garden", note="seeds"),
        say("ok"),
    ]}, "start a garden")
    texts = _tool_texts(rig.model.requests[-1])
    assert texts[:5] == [NO_GARDEN] * 5
    assert texts[5].startswith("Logged 7.00 EUR to Garden on ")
    assert [p.name for p in await ProjectStore(cfg).list(user_id)] == ["Garden"]
    assert await TaskStore(cfg).list(user_id, status="all") == ()
    assert await NoteStore(cfg).list(user_id) == ()
    assert await DocumentStore(cfg).list(user_id) == ()


async def test_several_matching_projects_ask_which_and_a_web_made_name_taints_the_run(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Helper")
    kitchen = await _project(cfg, user_id, "Kitchen paint")
    await _project(cfg, user_id, "Garage paint", tainted=True)
    rig = await _talk(cfg, user_id, bot, {"Helper": [
        _tool("t", "add_task", title="Buy rollers", project="paint"),
        _tool("u", "update_project", project="Kitchen paint", color=PROJECT_COLORS[1]),
        say("Which one?"),
    ]}, "add buy rollers to the paint project")
    which, refused = _tool_texts(rig.model.requests[-1])
    assert which == ("Refused: Several projects match “paint”. "
                     "Say which one: “Garage paint” [from web content]; “Kitchen paint”.")
    assert refused == TAINTED_CHANGE_TEXT
    assert (await ProjectStore(cfg).get(user_id, kitchen.id)).color == kitchen.color
    assert await TaskStore(cfg).list(user_id) == ()


async def test_listing_projects_over_web_made_money_taints_the_run(cfg, user_id):
    """As with money_summary: a web-made expense behind the sums a listing
    prints taints the run; a clean listing leaves it free to change things."""
    bot = await make_bot(cfg, user_id, "Helper")
    house = await _project(cfg, user_id, "House")
    clean = await _talk(cfg, user_id, bot, {"Helper": [
        _tool("l", "list_projects"), _tool("u", "update_project", project="House", color=PROJECT_COLORS[3]),
        say("ok"),
    ]}, "how are my projects? and make House yellow")
    assert _tool_texts(clean.model.requests[-1])[1].startswith("Updated: “House”")
    await ExpenseStore(cfg).add(user_id, ExpenseDraft(house.id, Decimal("9"), spent_at=today_madrid()),
                                created_by_bot=None, tainted=True)
    web = await _talk(cfg, user_id, bot, {"Helper": [
        _tool("l", "list_projects"), _tool("u", "update_project", project="House", color=PROJECT_COLORS[4]),
        say("No."),
    ]}, "how are my projects now? and make House green")
    listing, refused = _tool_texts(web.model.requests[-1])
    assert "total: 9.00 EUR spent" in listing and refused == TAINTED_CHANGE_TEXT
    assert (await ProjectStore(cfg).get(user_id, house.id)).color == PROJECT_COLORS[3]


async def test_general_stays_hidden_and_no_bot_can_change_or_take_its_name(cfg, user_id):
    """H2 through the tools: loose money goes to General, which the list hides
    and no bot may rename, archive or copy."""
    bot = await make_bot(cfg, user_id, "Helper")
    rig = await _talk(cfg, user_id, bot, {"Helper": [
        _tool("e", "log_expense", amount=3, note="coffee"),
        _tool("l", "list_projects", include_archived=True),
        _tool("u", "update_project", project="General", name="Misc"),
        _tool("c", "create_project", name="general"),
        say("ok"),
    ]}, "3 on coffee, then rename General to Misc")
    logged, listed, renamed, created = _tool_texts(rig.model.requests[-1])
    assert logged.startswith("Logged 3.00 EUR to General on ")
    assert listed == "No projects yet."
    assert renamed == "Refused: General is where expenses with no project go; it cannot be changed or deleted."
    assert created == "Refused: General is kept for expenses with no project; pick another name."
    assert [p.name for p in await ProjectStore(cfg).list(user_id)] == ["General"]
```

**2b.** `tests/test_money_tools.py` **(after Task 1, which replaced the whole file)**. Find:

```python
from roost.money.models import ExpenseDraft
```

Replace with:

```python
from roost.money.models import ExpenseDraft, ProjectDraft, ProjectPatch
```

Find:

```python
from roost.talk.gate import TAINTED_CHANGE_TEXT
from roost.tasks.tool_specs import ADD_TASK_SPEC, LIST_TASKS_SPEC
```

Replace with:

```python
from roost.talk.gate import TAINTED_CHANGE_TEXT
from roost.tasks.models import TaskDraft
from roost.tasks.store import TaskStore
from roost.tasks.tool_specs import ADD_TASK_SPEC, LIST_TASKS_SPEC
```

Then append to the end of `tests/test_money_tools.py` (it uses the file's own `cfg`, `user_id`, `_tool`, `_talk` and `_tool_texts`):

```python


async def _new_project(cfg, user_id, name: str, **fields):
    return await ProjectStore(cfg).create(user_id, ProjectDraft(name=name, **fields), created_by_bot=None,
                                          tainted=False)


async def test_an_expense_for_a_closed_task_and_its_step_goes_into_the_tasks_project(cfg, user_id):
    """H11: the task is found among tasks of every status, the step is one of
    its steps, and with no project named the money goes to the task's project."""
    bot = await make_bot(cfg, user_id, "Life admin")
    project = await _new_project(cfg, user_id, "Renovation")
    task = await TaskStore(cfg).create(user_id, TaskDraft(title="Paint the hall", steps=("Buy paint", "Paint"),
                                                          project_id=project.id), created_by_bot=None, tainted=False)
    await TaskStore(cfg).complete(user_id, task.id)
    rig = await _talk(cfg, user_id, bot, {"Life admin": [
        _tool("e", "log_expense", amount="30", task="paint the hall", step="buy paint", starred=True, note="white"),
        say("Logged."),
    ]}, "30 on white paint for the hall, and star it")
    [logged] = _tool_texts(rig.model.requests[-1])
    assert logged.startswith(f"Logged 30.00 EUR to Renovation on {today_madrid()} for “Paint the hall”, "
                             "step “Buy paint”, starred (id=")
    [expense] = await ExpenseStore(cfg).list_project(user_id, project.id)
    [buy_paint] = [step for step in task.steps if step.title == "Buy paint"]
    assert (expense.task_id, expense.step_id, expense.is_favorite, expense.description) == (
        task.id, buy_paint.id, True, "white")


async def test_a_step_needs_its_task_and_must_be_one_of_its_steps(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Life admin")
    task = await TaskStore(cfg).create(user_id, TaskDraft(title="Paint the hall", steps=("Buy paint",)),
                                       created_by_bot=None, tainted=False)
    rig = await _talk(cfg, user_id, bot, {"Life admin": [
        _tool("e1", "log_expense", amount=5, step="Buy paint"),
        _tool("e2", "log_expense", amount=5, task="Paint the hall", step="Buy brushes"),
        _tool("e3", "log_expense", amount=5, task="Paint the hull"),
        say("Which?"),
    ]}, "5 on brushes for the hall")
    alone, wrong_step, near = _tool_texts(rig.model.requests[-1])
    assert alone == "Refused: A step needs its task: name the task too."
    assert wrong_step == "Refused: “Paint the hall” has no step “Buy brushes”. Its steps: “Buy paint”."
    assert near == (f"Refused: no task is called “Paint the hull”. Did you mean “Paint the hall” id={task.id}? "
                    "Say it exactly.")
    assert await ExpenseStore(cfg).list_month(user_id, current_month()) == ()


async def test_an_archived_project_takes_no_new_or_moved_expense(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Life admin")
    old = await _new_project(cfg, user_id, "Old flat")
    await ProjectStore(cfg).update(user_id, old.id, ProjectPatch({"status": "archived"}))
    food = await _new_project(cfg, user_id, "Food")
    expense = await ExpenseStore(cfg).add(user_id, ExpenseDraft(food.id, Decimal("4"), spent_at=today_madrid()),
                                          created_by_bot=None, tainted=False)
    rig = await _talk(cfg, user_id, bot, {"Life admin": [
        _tool("e", "log_expense", amount=5, project="old flat"),
        _tool("u", "update_expense", expense=expense.id, project="Old flat"),
        say("It is archived."),
    ]}, "5 on the old flat, and move the 4 there too")
    assert _tool_texts(rig.model.requests[-1]) == ["Refused: “Old flat” is archived; unarchive it first."] * 2
    assert await ExpenseStore(cfg).list_project(user_id, old.id) == ()
    assert (await ExpenseStore(cfg).get(user_id, expense.id)).project_id == food.id


async def test_update_expense_moves_stars_voids_and_unlinks(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Life admin")
    food = await _new_project(cfg, user_id, "Food")
    trip = await _new_project(cfg, user_id, "Trip")
    task = await TaskStore(cfg).create(user_id, TaskDraft(title="Book the hotel"), created_by_bot=None, tainted=False)
    expense = await ExpenseStore(cfg).add(
        user_id, ExpenseDraft(food.id, Decimal("80"), spent_at=today_madrid(), task_id=task.id),
        created_by_bot=None, tainted=False)
    rig = await _talk(cfg, user_id, bot, {"Life admin": [
        _tool("u1", "update_expense", expense=expense.id, project="trip", starred=True, void=True),
        _tool("u2", "update_expense", expense=expense.id, task=""),
        _tool("u3", "update_expense", expense=expense.id, project="Tripp"),
        _tool("u4", "update_expense", expense=expense.id, void=False),
        say("ok"),
    ]}, "that 80 was the trip: star it, void it, unlink it, then count it again")
    moved, unlinked, near, posted = _tool_texts(rig.model.requests[-1])
    today = today_madrid()
    assert moved == unlinked == f"Updated: 80.00 EUR on {today} [void] [starred]."
    assert near == "Refused: No project is called “Tripp”. Did you mean “Trip”? Say it exactly."
    assert posted == f"Updated: 80.00 EUR on {today} [starred]."
    kept = await ExpenseStore(cfg).get(user_id, expense.id)
    assert (kept.project_id, kept.is_favorite, kept.status, kept.task_id, kept.step_id) == (
        trip.id, True, "posted", None, None)


async def test_set_budget_never_creates_a_project_and_can_clear_one(cfg, user_id):
    """H3: set_budget is exact-or-ask now; H5: '' clears the total budget."""
    bot = await make_bot(cfg, user_id, "Life admin")
    await _new_project(cfg, user_id, "Food")
    rig = await _talk(cfg, user_id, bot, {"Life admin": [
        _tool("b1", "set_budget", project="Garden", amount=100),
        _tool("b2", "set_budget", project="food", amount=300),
        _tool("b3", "set_budget", project="Food", amount=""),
        say("ok"),
    ]}, "budget 100 for the garden and 300 for food; no, no food budget")
    unknown, budget, cleared = _tool_texts(rig.model.requests[-1])
    assert unknown == "Refused: No project is called “Garden”. Use create_project first."
    assert budget == "Budget for Food: 300.00 EUR."
    assert cleared == "Budget for Food cleared."
    assert [p.name for p in await ProjectStore(cfg).list(user_id)] == ["Food"]
    assert (await ProjectStore(cfg).find(user_id, "Food")).budget is None


async def test_an_expense_with_no_currency_takes_its_projects(cfg, user_id):
    """H7: a dollar project's expense is in dollars unless the bot says otherwise."""
    bot = await make_bot(cfg, user_id, "Life admin")
    await _new_project(cfg, user_id, "Trip", currency="USD")
    rig = await _talk(cfg, user_id, bot, {"Life admin": [
        _tool("e1", "log_expense", amount=20, project="Trip"),
        _tool("e2", "log_expense", amount=5, project="Trip", currency="EUR"),
        say("ok"),
    ]}, "20 on the trip, and 5 euros")
    dollars, euros = _tool_texts(rig.model.requests[-1])
    assert dollars.startswith("Logged 20.00 USD to Trip on ") and euros.startswith("Logged 5.00 EUR to Trip on ")


async def test_list_expenses_reads_a_near_miss_project_and_refuses_an_unknown_one(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Life admin")
    food = await _new_project(cfg, user_id, "Food")
    travel = await _new_project(cfg, user_id, "Travel")
    for project, amount, note in ((food, "6", "bread"), (travel, "9", "bus")):
        await ExpenseStore(cfg).add(user_id, ExpenseDraft(project.id, Decimal(amount), spent_at=today_madrid(),
                                                          description=note), created_by_bot=None, tainted=False)
    rig = await _talk(cfg, user_id, bot, {"Life admin": [
        _tool("l1", "list_expenses", project="Fod"), _tool("l2", "list_expenses", project="Garden"), say("ok"),
    ]}, "what did I spend on food? and on the garden?")
    near, unknown = _tool_texts(rig.model.requests[-1])
    assert "bread" in near and "bus" not in near
    assert unknown == "Refused: No project is called “Garden”. Use create_project first."
```

**2c.** `tests/test_task_tools.py`. Find:

```python
from datetime import datetime, time, timedelta, timezone

import pytest
```

Replace with:

```python
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal

import pytest
```

Find:

```python
from roost.llm.types import ToolCallRequested, TurnDone
from roost.talk.gate import LINK_REFUSAL_TEXT, TAINTED_CHANGE_TEXT
```

Replace with:

```python
from roost.llm.types import ToolCallRequested, TurnDone
from roost.money.models import ProjectDraft
from roost.money.project_store import ProjectStore
from roost.talk.gate import LINK_REFUSAL_TEXT, TAINTED_CHANGE_TEXT
```

Then append to the end of `tests/test_task_tools.py` (it uses the file's own `cfg`, `user_id`, `_tool`, `_talk` — which returns `(rig, thread)` — and `_tool_texts`):

```python


async def _new_project(cfg, user_id, name: str):
    return await ProjectStore(cfg).create(user_id, ProjectDraft(name=name), created_by_bot=None, tainted=False)


async def test_a_task_goes_into_a_project_with_a_budget_slice(cfg, user_id):
    """H11: a slice is in its project's currency and needs a project."""
    bot = await make_bot(cfg, user_id, "Life admin")
    project = await _new_project(cfg, user_id, "Renovation")
    rig, _ = await _talk(cfg, user_id, bot, {"Life admin": [
        _tool("t1", "add_task", title="Paint the hall", project="renovation", budget="300"),
        _tool("t2", "add_task", title="Fix the tap", budget=50),
        _tool("t3", "add_task", title="Call the plumber"),
        _tool("l", "list_tasks", project="Renovation"),
        say("ok"),
    ]}, "add painting the hall to Renovation with 300 for it")
    added, no_project, plain, listed = _tool_texts(rig.model.requests[-1])
    assert added.startswith("Added: [ ] - Paint the hall")
    assert added.endswith(" Project: “Renovation”, budget 300.00 EUR.")
    assert no_project == "Refused: A budget slice needs a project."
    assert plain.startswith("Added: ") and "Project:" not in plain
    assert "Paint the hall" in listed and "Call the plumber" not in listed
    tasks = {task.title: task for task in await TaskStore(cfg).list(user_id)}
    assert set(tasks) == {"Paint the hall", "Call the plumber"}
    assert (tasks["Paint the hall"].project_id, tasks["Paint the hall"].allocated_budget) == (
        project.id, Decimal("300.00"))


async def test_update_task_moves_clears_and_fails_a_task(cfg, user_id):
    """'' clears a task's slice and its project; status failed closes it like
    done (H11), and a repeating task comes back."""
    bot = await make_bot(cfg, user_id, "Life admin")
    store = TaskStore(cfg)
    renovation = await _new_project(cfg, user_id, "Renovation")
    await _new_project(cfg, user_id, "Garden")
    await store.create(user_id, TaskDraft(title="Paint the hall", project_id=renovation.id,
                                          allocated_budget=Decimal("100")), created_by_bot=None, tainted=False)
    await store.create(user_id, TaskDraft(title="Water the plants", due_date="2026-10-12", recurring="0 9 * * 1"),
                       created_by_bot=None, tainted=False)
    rig, _ = await _talk(cfg, user_id, bot, {"Life admin": [
        _tool("u1", "update_task", task="Paint the hall", project="garden", budget="120"),
        _tool("u2", "update_task", task="Paint the hall", budget=""),
        _tool("u3", "update_task", task="Paint the hall", project=""),
        _tool("f", "update_task", task="water the plants", status="failed"),
        _tool("l", "list_tasks", status="failed"),
        say("ok"),
    ]}, "move painting to the garden; the plants died")
    moved, unbudgeted, unlinked, failed, listed = _tool_texts(rig.model.requests[-1])
    assert moved.endswith(" Project: “Garden”, budget 120.00 EUR.")
    assert unbudgeted.startswith("Updated: [ ] - Paint the hall") and "Project:" not in unbudgeted
    assert unlinked.endswith(" No project.")
    assert failed.startswith("Failed: Water the plants. Next time: [ ] - Water the plants")
    assert "[✗] - Water the plants" in listed
    paint = next(task for task in await store.list(user_id) if task.title == "Paint the hall")
    assert (paint.project_id, paint.allocated_budget) == (None, None)
    [closed] = await store.list(user_id, status="failed")
    assert closed.completed_at is not None
    assert [task.status for task in await store.list(user_id) if task.title == "Water the plants"] == ["todo"]


async def test_an_unknown_project_changes_nothing_on_a_task(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Life admin")
    await TaskStore(cfg).create(user_id, TaskDraft(title="Pay the rent"), created_by_bot=None, tainted=False)
    rig, _ = await _talk(cfg, user_id, bot, {"Life admin": [
        _tool("u", "update_task", task="Pay the rent", project="Garden", priority="high"),
        _tool("l", "list_tasks", project="Garden"),
        say("Which project?"),
    ]}, "the rent goes in the garden project, and it is urgent")
    assert _tool_texts(rig.model.requests[-1]) == [
        "Refused: No project is called “Garden”. Use create_project first."] * 2
    [task] = await TaskStore(cfg).list(user_id)
    assert (task.priority, task.project_id) == ("medium", None)
```

**2d.** `tests/test_note_tools.py`. Find:

```python
from roost.llm.types import ToolCallRequested, TurnDone
from roost.notes.models import NoteDraft
```

Replace with:

```python
from roost.llm.types import ToolCallRequested, TurnDone
from roost.money.models import ProjectDraft
from roost.money.project_store import ProjectStore
from roost.notes.models import NoteDraft
```

Then append to the end of `tests/test_note_tools.py` (it uses the file's own `cfg`, `user_id`, `_tool`, `_talk`, `_tool_texts` and `_seed`):

```python


async def test_a_note_is_saved_into_a_project_and_found_there(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Writer")
    project = await ProjectStore(cfg).create(user_id, ProjectDraft(name="Renovation"), created_by_bot=None,
                                             tainted=False)
    await _seed(cfg, user_id, "Tiles", "green tiles")
    rig, _ = await _talk(cfg, user_id, bot, {"Writer": [
        _tool("a", "add_note", title="Paint", content="white paint", project="renovation"),
        _tool("f1", "find_notes", query="", project="Renovation"),
        _tool("f2", "find_notes", query="", project="Renovaton"),
        say("ok"),
    ]}, "note white paint for the renovation, then show me its notes")
    saved, found, near = _tool_texts(rig.model.requests[-1])
    assert saved.startswith("Saved: - “Paint”") and saved.endswith(" Project: “Renovation”.")
    assert "“Paint”" in found and "“Tiles”" not in found
    assert near == found          # a read may answer a near miss (H3)
    notes = {note.title: note for note in await NoteStore(cfg).list(user_id)}
    assert (notes["Paint"].project_id, notes["Tiles"].project_id) == (project.id, None)


async def test_update_note_moves_a_note_without_bumping_its_revision(cfg, user_id):
    """H12: linking is not an edit, so an open editor still saves at its revision."""
    bot = await make_bot(cfg, user_id, "Writer")
    project = await ProjectStore(cfg).create(user_id, ProjectDraft(name="Renovation"), created_by_bot=None,
                                             tainted=False)
    note = await _seed(cfg, user_id, "Tiles", "green tiles")
    rig, _ = await _talk(cfg, user_id, bot, {"Writer": [
        _tool("u1", "update_note", note="Tiles", project="Renovation"),
        _tool("u2", "update_note", note="Tiles", project=""),
        _tool("u3", "update_note", note="Tiles", content="blue tiles", project="Renovation"),
        say("ok"),
    ]}, "file the tiles note under the renovation")
    moved, unlinked, both = _tool_texts(rig.model.requests[-1])
    assert moved.startswith("Updated: - “Tiles”") and moved.endswith(" Project: “Renovation”.")
    assert unlinked.endswith(" No project.")
    assert both.endswith(" Project: “Renovation”.") and "blue tiles" in both
    kept = await NoteStore(cfg).get(user_id, note.id)
    assert (kept.project_id, kept.content, kept.revision) == (project.id, "blue tiles", 2)
```

**2e.** `tests/test_document_tools.py` **(after Task 1, which put `ProjectStore` in its imports)**. Find:

```python
from roost.money.expense_store import ExpenseStore
from roost.money.project_store import ProjectStore
```

Replace with:

```python
from roost.money.expense_store import ExpenseStore
from roost.money.models import ProjectDraft
from roost.money.project_store import ProjectStore
```

Then append to the end of `tests/test_document_tools.py` (it uses the file's own `cfg`, `user_id`, `_tool`, `_talk`, `_tool_texts` and `_service`):

```python


async def test_documents_are_made_in_a_project_listed_by_it_and_a_pdf_follows_its_doc(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Office")
    project = await ProjectStore(cfg).create(user_id, ProjectDraft(name="Renovation"), created_by_bot=None,
                                             tainted=False)
    await _service(cfg).create_doc(user_id, "Loose", "- x")
    rig, _ = await _talk(cfg, user_id, bot, {"Office": [
        _tool("d", "create_doc", title="Plan", markdown="- tiles", project="renovation"),
        _tool("s", "create_sheet", title="Costs", rows=[["Item", "Cost"], ["Tiles", 240]], project="Renovation"),
        _tool("l", "list_documents", project="Renovation"),
        _tool("p", "make_pdf_from_doc", document="Plan"),
        say("ok"),
    ]}, "start the renovation plan and its costs sheet, then a PDF of the plan")
    doc, sheet, listed, pdf = _tool_texts(rig.model.requests[-1])
    assert doc.startswith("Created doc: [doc] “Plan”") and doc.endswith(" Project: “Renovation”.")
    assert sheet.startswith("Created sheet: [sheet] “Costs”") and sheet.endswith(" Project: “Renovation”.")
    assert "“Plan”" in listed and "“Costs”" in listed and "“Loose”" not in listed
    assert pdf.startswith("Created PDF: [PDF] “Plan”")
    linked = {(meta.kind, meta.title): meta.project_id for meta in await DocumentStore(cfg).list(user_id)}
    assert linked == {("doc", "Plan"): project.id, ("sheet", "Costs"): project.id, ("pdf", "Plan"): project.id,
                      ("doc", "Loose"): None}


async def test_set_document_project_moves_a_document_and_keeps_its_revision(cfg, user_id):
    """H12: set_document_project links and unlinks without a new revision, so an
    open Univer editor still saves; a near miss never moves anything."""
    bot = await make_bot(cfg, user_id, "Office")
    await ProjectStore(cfg).create(user_id, ProjectDraft(name="Renovation"), created_by_bot=None, tainted=False)
    plan = await _service(cfg).create_doc(user_id, "Plan", "- tiles")
    rig, _ = await _talk(cfg, user_id, bot, {"Office": [
        _tool("m", "set_document_project", document="plan", project="Renovation"),
        _tool("u", "set_document_project", document="Plan", project=""),
        _tool("n", "set_document_project", document="Plan", project="Renovaton"),
        say("ok"),
    ]}, "file the plan under the renovation")
    moved, unlinked, near = _tool_texts(rig.model.requests[-1])
    assert moved == "Moved “Plan” to the project “Renovation”."
    assert unlinked == "“Plan” is in no project now."
    assert near == "Refused: No project is called “Renovaton”. Did you mean “Renovation”? Say it exactly."
    kept = await DocumentStore(cfg).get_meta(user_id, plan.id)
    assert (kept.project_id, kept.revision) == (None, 1)
```

**2f.** `tests/test_every_bot_tools.py` **(after Task 1, which changed only a `log_expense` line)**. Find:

```python
from roost.documents.store import DocumentStore
from roost.gateway.auth import register_user
```

Replace with:

```python
from roost.documents.store import DocumentStore
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
```

Find:

```python
from roost.talk.gate import LINK_REFUSAL_TEXT, REFUSAL_TEXT
from roost.talk.tool_catalog import CATALOG
from roost.talk.tools import EVERY_BOT_TOOLS, run_tool_names
```

Replace with:

```python
from roost.talk.domain_tools import build_domain_tools
from roost.talk.gate import LINK_REFUSAL_TEXT, REFUSAL_TEXT
from roost.talk.tool_catalog import CATALOG
from roost.talk.tools import CREATOR_TOOLS, DESK_TOOLS, EVERY_BOT_TOOLS, LEAD_TOOLS, TEAM_TOOLS, run_tool_names
```

Then append to the end of the file:

```python


# The tools the run answers itself (roost/talk/tool_runner.py): the clock, the bot's
# own browser, the Stuck card and the team. Every other catalog tool is a record tool.
RUNNER_TOOLS = DESK_TOOLS | TEAM_TOOLS | LEAD_TOOLS | CREATOR_TOOLS | {"get_time", "ask_for_help"}


async def test_every_record_tool_in_the_catalog_has_a_handler(cfg):
    """A name no handler serves falls through to REFUSAL_TEXT at run time, so a
    record tool added to the catalog without one would only ever be refused."""
    domain = build_domain_tools(cfg, EventHub(cfg))
    assert sorted(name for name in CATALOG if name not in RUNNER_TOOLS and not domain.handles(name)) == []
    assert not any(domain.handles(name) for name in RUNNER_TOOLS)
    assert all(domain.activity(name) for name in CATALOG if name not in RUNNER_TOOLS)
    assert {"list_projects", "add_topup", "set_document_project"} <= {n for n in CATALOG if domain.handles(n)}
```

**2g.** `tests/test_instructions.py` **(after the stuck flow)**. Append to the end of the file:

```python


def test_every_bot_is_told_the_users_projects_hold_the_other_records():
    """Projects hub: the prompt names projects and their tools, keeps the S1 line
    against "I'm isolated", and never says "role"."""
    prompt = build_instructions(_bot())
    assert "The user's projects, tasks, money, notes and documents belong to the user" in prompt
    assert "never say you cannot see them or that you are isolated" in prompt
    assert "call list_projects or get_project" in prompt
    assert "only log_expense makes a new project from a new name" in prompt
    assert "role" not in prompt.lower()
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_project_tools.py -q`
Expected: FAIL at collection, `ModuleNotFoundError: No module named 'roost.projects.tool_specs'` (`1 error`).

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_money_tools.py tests/test_task_tools.py tests/test_note_tools.py tests/test_document_tools.py tests/test_every_bot_tools.py tests/test_instructions.py -q`
Expected: FAIL. Every test that was there before passes; the new ones fail:
- `test_money_tools.py` (7 new): the args models ignore `task`, `step`, `starred` and `void`, so the closed-task expense lands in General and the step-alone, wrong-step and near-miss calls are logged instead of refused; the archived project takes the money; `set_budget` creates "Garden"; the Trip expense is logged in EUR; `list_expenses` answers "No expenses match." for "Fod" and "Garden".
- `test_task_tools.py` (3 new): `project` and `budget` are ignored ("Fix the tap" is added; no "Project:" suffix), and `status="failed"` is a validation refusal.
- `test_note_tools.py` (2 new): `project` is ignored; `update_note` with only a project is refused ("needs a new title, content or tags").
- `test_document_tools.py` (2 new): the documents stay unlinked, and `set_document_project` answers `Refused: that action is not available yet.` (it is not in the catalog).
- `test_every_bot_tools.py`: `test_every_record_tool_in_the_catalog_has_a_handler` fails on its last assert (no project tool and no `set_document_project` in the catalog).
- `test_instructions.py`: the new test fails on its first assert.

- [ ] **Step 4: Constants and `optional_amount`**

**4a.** `roost/constants.py` **(after the stuck flow, after Tasks 2 and 6; the Finance section, which the stuck flow does not touch)**. Find:

```python
TOPUP_SOURCE_MAX_CHARS = 120
# The most project names one "Did you mean …?" or "Say which one: …" refusal lists (ProjectService.resolve).
PROJECT_MATCHES_SHOWN = 5
```

Replace with:

```python
TOPUP_SOURCE_MAX_CHARS = 120
# The most project names one "Did you mean …?" or "Say which one: …" refusal lists (ProjectService.resolve).
PROJECT_MATCHES_SHOWN = 5
# The most task titles an expense tool's "Did you mean …?" or "several tasks match" refusal lists
# (roost/money/expense_links.py).
EXPENSE_TASK_MATCHES_SHOWN = 5
# The longest record id a money or project tool takes (an expense's, a top-up's); ids are 36-character UUIDs.
MAX_RECORD_ID_LENGTH = 64
```

**4b.** `roost/money/amounts.py`. Find:

```python
def amount_text(amount: Decimal) -> str:
    return f"{amount.quantize(CENT):.2f}"
```

Replace with:

```python
def optional_amount(value: str | int | float | Decimal | None) -> Decimal | None:
    """``None`` or a blank text is no amount: a tool's '' clears a budget
    (projects hub H5) or a task's budget slice. Anything else is ``parse_amount``'s."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return parse_amount(value)


def amount_text(amount: Decimal) -> str:
    return f"{amount.quantize(CENT):.2f}"
```

- [ ] **Step 5: The project tool specs and the catalog**

**5a.** Create `roost/projects/tool_specs.py`:

```python
"""The project tool specs and gate kinds (projects hub, design §3 with H3, H4,
H15, H16). ``roost.talk.tool_catalog`` imports this module, so it imports only
``roost.constants``, ``roost.llm.types`` and ``roost.talk.tool_def``.

- Deleting a project is not a tool (design §3): only the Board does it, after
  a confirmation.
- ``add_topup`` is a ``write_change`` (H4): it raises an existing project's
  budget, so a run that read a web page may not do it.
- ``set_budget`` stays a money tool (``roost.money.tool_specs``)."""

from __future__ import annotations

from roost.constants import PROJECT_COLORS, TOPUP_SOURCE_MAX_CHARS
from roost.llm.types import ToolSpec
from roost.talk.tool_def import ToolDef

_PROJECT_REF = {"type": "string",
                "description": "The project's name or id. Name it exactly; if two match, ask the user which."}
_AMOUNT = {"type": ["number", "string"], "description": "An amount, e.g. 250 or '250,50'."}
_COLOR = {"type": "string", "enum": list(PROJECT_COLORS)}
_START = {"type": "string", "description": "The day it starts, like 2026-10-01."}
_DUE = {"type": "string", "description": "The day it is due, like 2026-12-31."}
_LEAD = {"type": "string", "description": "The name of the bot that leads it (one of the user's bots)."}
_TOPUP = {"type": "string", "description": "The top-up's id, from get_project."}
_CLEARS = " '' clears it."

LIST_PROJECTS_SPEC = ToolSpec(
    name="list_projects",
    description=("List the user's projects (every bot uses them): for each, its total budget and this month's "
                 "limit with what is spent and left, spending in other currencies apart, and how many tasks are "
                 "done. Archived projects only when asked."),
    input_schema={"type": "object", "properties": {
        "include_archived": {"type": "boolean", "description": "Also list archived projects."},
    }},
)
GET_PROJECT_SPEC = ToolSpec(
    name="get_project",
    description=("Show one project in full: its budgets, lead bot and dates, its tasks, latest expenses, notes "
                 "and documents, and its top-up history with ids."),
    input_schema={"type": "object", "properties": {"project": _PROJECT_REF}, "required": ["project"]},
)
CREATE_PROJECT_SPEC = ToolSpec(
    name="create_project",
    description=("Create a project that holds tasks, money, notes and documents. It may have a total budget, a "
                 "monthly limit, or both, counted in its own currency. Create one when the user asks for it."),
    input_schema={"type": "object", "properties": {
        "name": {"type": "string", "description": "Short name, e.g. 'Renovation'."},
        "currency": {"type": "string", "description": "Three-letter code, default EUR. Budgets count only "
                                                      "spending in it."},
        "budget": {**_AMOUNT, "description": "The total budget, e.g. 500."},
        "monthly_budget": {**_AMOUNT, "description": "The monthly limit, e.g. 100."},
        "color": _COLOR, "start_date": _START, "due_date": _DUE, "lead_bot": _LEAD,
    }, "required": ["name"]},
)
UPDATE_PROJECT_SPEC = ToolSpec(
    name="update_project",
    description=("Change a project: rename it, set its colour, dates, lead bot or monthly limit, archive or "
                 "unarchive it, or change its currency while it has no expenses and no top-ups. The total budget "
                 "changes with set_budget or add_topup. Name the project exactly; if two match, ask the user which."),
    input_schema={"type": "object", "properties": {
        "project": _PROJECT_REF, "name": {"type": "string", "description": "Its new name."}, "color": _COLOR,
        "start_date": {**_START, "description": _START["description"] + _CLEARS},
        "due_date": {**_DUE, "description": _DUE["description"] + _CLEARS},
        "lead_bot": {**_LEAD, "description": _LEAD["description"] + _CLEARS},
        "monthly_budget": {**_AMOUNT, "description": "The monthly limit." + _CLEARS},
        "archived": {"type": "boolean", "description": "true archives it; false brings it back."},
        "currency": {"type": "string", "description": "Three-letter code."},
    }, "required": ["project"]},
)
ADD_TOPUP_SPEC = ToolSpec(
    name="add_topup",
    description=("Add money to a project's total budget, such as a gift or a transfer. It shows in the project's "
                 "top-up history and can be changed or undone."),
    input_schema={"type": "object", "properties": {
        "project": _PROJECT_REF, "amount": _AMOUNT,
        "source": {"type": "string", "description": f"Where it came from, e.g. 'birthday' (up to "
                                                    f"{TOPUP_SOURCE_MAX_CHARS} characters)."},
    }, "required": ["project", "amount"]},
)
EDIT_TOPUP_SPEC = ToolSpec(
    name="edit_topup",
    description="Change a top-up's amount; the total budget moves by the difference.",
    input_schema={"type": "object", "properties": {
        "topup": _TOPUP, "amount": {**_AMOUNT, "description": "The top-up's new amount."},
    }, "required": ["topup", "amount"]},
)
UNDO_TOPUP_SPEC = ToolSpec(
    name="undo_topup",
    description="Undo a top-up: it and its changes leave the total budget, and the history keeps it, marked undone.",
    input_schema={"type": "object", "properties": {"topup": _TOPUP}, "required": ["topup"]},
)

PROJECT_TOOL_DEFS: tuple[ToolDef, ...] = (
    ToolDef(LIST_PROJECTS_SPEC, "read"),
    ToolDef(GET_PROJECT_SPEC, "read"),
    ToolDef(CREATE_PROJECT_SPEC, "write_create"),
    ToolDef(UPDATE_PROJECT_SPEC, "write_change"),
    ToolDef(ADD_TOPUP_SPEC, "write_change"),
    ToolDef(EDIT_TOPUP_SPEC, "write_change"),
    ToolDef(UNDO_TOPUP_SPEC, "write_change"),
)
```

**5b.** `roost/talk/tool_catalog.py` **(after the stuck flow; its `ASK_FOR_HELP_SPEC` import and ToolDef sit elsewhere)**. Find:

```python
from roost.notes.tool_specs import NOTE_TOOL_DEFS
from roost.talk.tool_def import ToolDef
```

Replace with:

```python
from roost.notes.tool_specs import NOTE_TOOL_DEFS
from roost.projects.tool_specs import PROJECT_TOOL_DEFS
from roost.talk.tool_def import ToolDef
```

Find:

```python
    *NOTE_TOOL_DEFS,
    *DOCUMENT_TOOL_DEFS,
))
```

Replace with:

```python
    *NOTE_TOOL_DEFS,
    *DOCUMENT_TOOL_DEFS,
    *PROJECT_TOOL_DEFS,
))
```

- [ ] **Step 6: How a tool names a project, and the project tools**

**6a.** Create `roost/projects/refs.py`:

```python
"""How a record tool names one of the user's projects (projects hub H3, H12).

Every tool but ``log_expense`` names a project through
``ProjectService.resolve``: its id, its exact name or a unique part of one.
A lone near miss may be read (``change=False``) but is never changed or
linked to, and no project is ever created from a name here. A refusal comes
back as the tool's own result and carries the taint of the project names it
shows (M1 D3)."""

from __future__ import annotations

import html

from roost.money.models import Project
from roost.projects.service import ProjectRefusal, ProjectService
from roost.talk.outcome import ToolOutcome

NAME_THE_PROJECT_TEXT = "Refused: name the project (its name or id)."


def _escape(text: str) -> str:
    return html.escape(text, quote=True)


async def project_ref(projects: ProjectService, user_id: str, name: str | None, *,
                      change: bool) -> Project | ToolOutcome | None:
    """The project ``name`` means, or the refusal to hand back. ``None`` or a
    blank name means no project; on a change that unlinks the record."""
    if name is None or not name.strip():
        return None
    found = await projects.resolve(user_id, name, change=change)
    if isinstance(found, ProjectRefusal):
        return ToolOutcome(f"Refused: {_escape(found)}", tainted=found.tainted)
    return found


async def required_project(projects: ProjectService, user_id: str, name: str, *,
                           change: bool) -> Project | ToolOutcome:
    """Like ``project_ref``, for a tool that must name a project."""
    found = await project_ref(projects, user_id, name, change=change)
    return ToolOutcome(NAME_THE_PROJECT_TEXT) if found is None else found


def id_of(project: Project | None) -> str | None:
    return None if project is None else project.id


def project_taint(project: Project | None) -> bool:
    """A reply that echoes a web-made project's name is web text (M1 D3)."""
    return project is not None and project.tainted


def project_suffix(project: Project | None, *, unlinked: bool = False) -> str:
    """The end of a reply that filed a record: the project it is in now."""
    if project is not None:
        return f" Project: “{_escape(project.name)}”."
    return " No project." if unlinked else ""
```

**6b.** Create `roost/projects/tool_args.py`:

```python
"""The project tools' arguments (projects hub §3, H5, H15, H16): pydantic at
the tool boundary, plus the readers that turn a model's text into a project
field. Free text is ``ToolText``: a copy of an escaped tool result is stored
plain. On ``update_project`` a null leaves a field as it is, and '' clears a
date, the lead bot or the monthly limit."""

from __future__ import annotations

from datetime import date
from types import MappingProxyType
from typing import Any, Callable, Mapping

from pydantic import BaseModel, ConfigDict, Field

from roost.constants import (
    CURRENCY_PATTERN, DEFAULT_CURRENCY, DEFAULT_PROJECT_COLOR, MAX_BOT_NAME_LENGTH, MAX_CATEGORY_NAME_LENGTH,
    MAX_DUE_TEXT_LENGTH, MAX_RECORD_ID_LENGTH, PROJECT_COLORS, PROJECT_STATUSES, TOPUP_SOURCE_MAX_CHARS,
)
from roost.money.amounts import optional_amount
from roost.money.models import COLOR_TEXT       # Task 2's sentence: the palette, listed
from roost.records.tool_text import ToolText

Amount = str | int | float
DAY_TEXT = "“{value}” is not a day like 2026-10-14."
_ACTIVE, _ARCHIVED = PROJECT_STATUSES


class ListProjectsArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    include_archived: bool = False


class ProjectRefArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    project: ToolText = Field(min_length=1, max_length=MAX_CATEGORY_NAME_LENGTH)


class CreateProjectArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: ToolText = Field(min_length=1, max_length=MAX_CATEGORY_NAME_LENGTH)
    currency: str = Field(default=DEFAULT_CURRENCY, pattern=CURRENCY_PATTERN)
    budget: Amount | None = None
    monthly_budget: Amount | None = None
    color: str | None = None                       # checked against the palette by read_color
    start_date: str | None = Field(default=None, max_length=MAX_DUE_TEXT_LENGTH)
    due_date: str | None = Field(default=None, max_length=MAX_DUE_TEXT_LENGTH)
    lead_bot: ToolText | None = Field(default=None, max_length=MAX_BOT_NAME_LENGTH)


class UpdateProjectArgs(ProjectRefArgs):
    name: ToolText | None = Field(default=None, min_length=1, max_length=MAX_CATEGORY_NAME_LENGTH)
    color: str | None = None
    start_date: str | None = Field(default=None, max_length=MAX_DUE_TEXT_LENGTH)
    due_date: str | None = Field(default=None, max_length=MAX_DUE_TEXT_LENGTH)
    lead_bot: ToolText | None = Field(default=None, max_length=MAX_BOT_NAME_LENGTH)
    monthly_budget: Amount | None = None
    archived: bool | None = None
    currency: str | None = Field(default=None, pattern=CURRENCY_PATTERN)


class AddTopupArgs(ProjectRefArgs):
    amount: Amount
    source: ToolText | None = Field(default=None, max_length=TOPUP_SOURCE_MAX_CHARS)


class TopupRefArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    topup: str = Field(min_length=1, max_length=MAX_RECORD_ID_LENGTH)


class EditTopupArgs(TopupRefArgs):
    amount: Amount


def read_color(value: str | None) -> str:
    """A colour from the fixed palette (H16); none given is the default one."""
    if value is None:
        return DEFAULT_PROJECT_COLOR
    color = value.strip().lower()
    if color not in PROJECT_COLORS:
        raise ValueError(COLOR_TEXT)
    return color


def optional_day(value: str | None) -> str | None:
    """A day like 2026-10-14; ``None`` or '' is no day."""
    text = (value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise ValueError(DAY_TEXT.format(value=text)) from exc


def _name(value: str) -> str:
    return value.strip()


def _status(archived: bool) -> str:
    return _ARCHIVED if archived else _ACTIVE


def _same(value: Any) -> Any:
    return value


# update_project's argument → (ProjectService.update's field, its reader). The lead bot is
# read by the tools themselves: naming it needs the user's bots.
_READERS: Mapping[str, tuple[str, Callable[[Any], Any]]] = MappingProxyType({
    "name": ("name", _name), "color": ("color", read_color), "start_date": ("start_date", optional_day),
    "due_date": ("due_date", optional_day), "monthly_budget": ("monthly_budget", optional_amount),
    "archived": ("status", _status), "currency": ("currency", _same),
})


def project_changes(args: UpdateProjectArgs) -> dict[str, object]:
    """The fields the call set, read into ``ProjectService.update``'s changes."""
    given = args.model_dump(include=args.model_fields_set & set(_READERS))
    return {_READERS[key][0]: _READERS[key][1](value) for key, value in given.items() if value is not None}
```

**6c.** Create `roost/projects/format.py`:

```python
"""Tool-result text for projects (projects hub §3, H4, H8). Names and other
record text are escaped here, by their producer (tool results reach the model
raw); every number comes from ``roost.projects.numbers`` and nothing is
summed here."""

from __future__ import annotations

from typing import Sequence

from roost.constants import PROJECT_PAGE_ITEMS, PROJECT_STATUSES
from roost.documents.format import document_line
from roost.money.format import escape, expense_line, money
from roost.money.models import TOPUP_CREDIT, Project, TopUp
from roost.notes.models import Note
from roost.projects.numbers import BudgetLine, Progress, ProjectNumbers, TaskMoney
from roost.projects.service import WEB_MARK, ProjectDetail, ProjectRow
from roost.tasks.format import task_line

NO_PROJECTS_TEXT = "No projects yet."
NO_ACTIVE_PROJECTS_TEXT = "No active projects."
_ARCHIVED = PROJECT_STATUSES[1]


def budget_text(label: str, line: BudgetLine, currency: str) -> str:
    """One budget: what is spent and, with a budget, of how much, what is left
    or over, and the bar's percent (H8)."""
    spent = money(line.spent, currency)
    if line.budget is None or line.remaining is None:
        return f"{label}: {spent} spent"
    left = (f"{money(line.remaining, currency)} left" if line.remaining >= 0
            else f"over by {money(-line.remaining, currency)}")
    return f"{label}: {spent} of {money(line.budget, currency)}, {left} ({line.used_percent}%)"


def task_money_text(task_money: TaskMoney | None, currency: str) -> str:
    """A task's slice on its project's page (design §2, P6): planned, spent, and
    left or over. Empty for a task with no slice and nothing spent on it."""
    if task_money is None or (task_money.planned is None and not task_money.spent):
        return ""
    spent = f"spent {money(task_money.spent, currency)}"
    if task_money.planned is None or task_money.left is None:
        return f" · {spent}"
    left = (f"{money(task_money.left, currency)} left" if task_money.left >= 0
            else f"over by {money(-task_money.left, currency)}")
    return f" · budget {money(task_money.planned, currency)}, {spent}, {left}"


def progress_text(progress: Progress) -> str:
    """Done of all but the cancelled ones; failed ones counted apart (H11)."""
    failed = f", {progress.failed} failed" if progress.failed else ""
    return f"{progress.done} done{failed} of {progress.total}"


def _marks(project: Project) -> str:
    archived = " [archived]" if project.status == _ARCHIVED else ""
    return f"{archived}{WEB_MARK if project.tainted else ''}"


def _others(numbers: ProjectNumbers) -> str:
    return "".join(f", also {money(total, code)}" for code, total in numbers.other_currencies.items())


def project_line(row: ProjectRow) -> str:
    project, numbers, progress = row
    total = budget_text("total", numbers.total, numbers.currency)
    month = budget_text("this month", numbers.month, numbers.currency)
    return (f"- “{escape(project.name)}”{_marks(project)} · {total} · {month}{_others(numbers)} · "
            f"tasks: {progress_text(progress)} id={project.id}")


def project_list_text(rows: Sequence[ProjectRow], *, include_archived: bool) -> str:
    if not rows:
        return NO_PROJECTS_TEXT if include_archived else NO_ACTIVE_PROJECTS_TEXT
    return "\n".join(project_line(row) for row in rows)


def project_brief(project: Project) -> str:
    """A project's settings on one line: the create_project and update_project replies."""
    parts = (
        f"“{escape(project.name)}”{_marks(project)} in {project.currency}",
        f"budget {money(project.budget, project.currency)}" if project.budget is not None else "",
        (f"monthly limit {money(project.monthly_budget, project.currency)}"
         if project.monthly_budget is not None else ""),
        f"starts {project.start_date}" if project.start_date else "",
        f"due {project.due_date}" if project.due_date else "",
    )
    return ", ".join(part for part in parts if part) + f" id={project.id}"


def topup_label(topup: TopUp) -> str:
    """H4's history labels: a credit, an edit of one, or a set_budget edit."""
    if topup.kind == TOPUP_CREDIT:
        return "Top-up"
    return "Top-up changed" if topup.topup_id else "Budget set"


def topup_line(topup: TopUp) -> str:
    source = f" · {escape(topup.source)}" if topup.source else ""
    undone = " [undone]" if topup.undone else ""
    web = WEB_MARK if topup.tainted else ""
    return (f"- {topup.created_at[:10]} · {topup_label(topup)} {money(topup.amount, topup.currency)}"
            f"{source}{undone}{web} id={topup.id}")


def _more(total: int, shown: int, hint: str) -> tuple[str, ...]:
    return (f"…and {total - shown} more: {hint}",) if total > shown else ()


def _section(title: str, lines: Sequence[str]) -> tuple[str, ...]:
    return (f"{title}:", *lines) if lines else ()


def _note_line(note: Note) -> str:
    return f"- “{escape(note.title)}”{WEB_MARK if note.tainted else ''} id={note.id}"


def _head(detail: ProjectDetail) -> tuple[str, ...]:
    project = detail.project
    facts = tuple(fact for fact in (
        f"Lead bot: {escape(detail.lead_bot_name)}" if detail.lead_bot_name else "",
        f"starts {project.start_date}" if project.start_date else "",
        f"due {project.due_date}" if project.due_date else "",
    ) if fact)
    title = f"“{escape(project.name)}”{_marks(project)} in {project.currency} id={project.id}"
    return (title, " · ".join(facts)) if facts else (title,)


def _money_lines(numbers: ProjectNumbers) -> tuple[str, ...]:
    others = ", ".join(money(total, code) for code, total in numbers.other_currencies.items())
    return (
        budget_text("Total", numbers.total, numbers.currency),
        budget_text("This month", numbers.month, numbers.currency),
        *((f"Also {others}, not counted in the budgets",) if others else ()),
        f"Starred: {money(numbers.starred_total, numbers.currency)}",
    )


def _tasks(detail: ProjectDetail) -> tuple[str, ...]:
    shown, currency = detail.tasks[:PROJECT_PAGE_ITEMS], detail.project.currency
    more = _more(len(detail.tasks), len(shown), "call list_tasks with this project and status all.")
    lines = tuple(task_line(task) + task_money_text(detail.task_money.get(task.id), currency) for task in shown)
    return (f"Tasks ({progress_text(detail.progress)}):", *lines, *more)


def project_page_text(detail: ProjectDetail) -> str:
    """``get_project``: the project, its numbers, its tasks, its latest
    expenses, notes and documents, and its newest top-ups with their ids."""
    name, topups = detail.project.name, detail.topups[:PROJECT_PAGE_ITEMS]
    return "\n".join((
        *_head(detail), *_money_lines(detail.numbers), *_tasks(detail),
        *_section("Latest expenses", tuple(f"- {expense_line(expense, name)}" for expense in detail.expenses)),
        *_section("Notes", tuple(_note_line(note) for note in detail.notes)),
        *_section("Documents", tuple(f"- {document_line(meta)}" for meta in detail.documents)),
        *_section("Top-ups", tuple(topup_line(topup) for topup in topups)),
        *_more(len(detail.topups), len(topups), "the Board shows the older ones."),
    ))
```

**6d.** Create `roost/projects/tools.py`:

```python
"""The project tools (projects hub §3, H2–H4, H15): every bot reads, creates
and changes the user's projects through ``ProjectService``.

- Pydantic arguments, a refusal sentence instead of a guess, and record text
  escaped by its producer (``roost.projects.format``).
- A project is named exact-or-ask (``roost.projects.refs``): ``get_project``
  may read a near miss; nothing else ever lands on one.
- A new project records its bot and the run's taint. A reply that echoes a
  web-made project, or sums a web-made expense, carries that taint (M1 D3).
- Top-ups change an existing budget (H4), so the gate refuses them in a run
  that read a web page. Deleting a project is never a tool: only the Board
  does it, after a confirmation (design §3)."""

from __future__ import annotations

from typing import Any, Sequence

from pydantic import ValidationError

from roost.bots.store import BotStore, normalize_bot_name
from roost.money.amounts import optional_amount, parse_amount
from roost.money.expense_store import ExpenseStore
from roost.money.format import escape, money
from roost.money.models import Project, ProjectDraft
from roost.projects.format import project_brief, project_list_text, project_page_text
from roost.projects.refs import required_project
from roost.projects.service import ProjectRefusal, ProjectRow, ProjectService
from roost.projects.tool_args import (
    AddTopupArgs, CreateProjectArgs, EditTopupArgs, ListProjectsArgs, ProjectRefArgs, TopupRefArgs,
    UpdateProjectArgs, optional_day, project_changes, read_color,
)
from roost.talk.domain_tools import RecordContext
from roost.talk.outcome import ToolOutcome

_ACTIVITY = {
    "list_projects": "checking your projects", "get_project": "looking at a project",
    "create_project": "creating a project", "update_project": "updating a project",
    "add_topup": "adding a top-up", "edit_topup": "changing a top-up", "undo_topup": "undoing a top-up",
}
GONE_TEXT = "Refused: that project is gone."
# None from the store: not one of the user's credits on a live project. An undone credit is the
# store's TopUpUndone, a ValueError that run() turns into "Refused: That top-up was undone already."
NO_TOPUP_TEXT = "Refused: there is no top-up with that id."
NOTHING_TO_CHANGE_TEXT = "Refused: update_project needs something to change."
NO_SUCH_BOT_TEXT = "None of your bots is called “{name}”."


def _budget_sentence(project: Project) -> str:
    name = escape(project.name)
    if project.budget is None:
        return f"“{name}” has no total budget now."
    return f"The total budget of “{name}” is now {money(project.budget, project.currency)}."


class ProjectTools:
    names = frozenset(_ACTIVITY)

    def __init__(self, service: ProjectService, bots: BotStore, expenses: ExpenseStore) -> None:
        self._service = service
        self._bots = bots
        self._expenses = expenses

    def activity(self, name: str) -> str:
        return _ACTIVITY[name]

    async def run(self, name: str, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        handlers = {
            "list_projects": self._list, "get_project": self._get, "create_project": self._create,
            "update_project": self._update, "add_topup": self._add_topup, "edit_topup": self._edit_topup,
            "undo_topup": self._undo_topup,
        }
        try:
            return await handlers[name](arguments, ctx)
        except ValidationError:
            return ToolOutcome(f"Refused: {name} got arguments it can't use; see its description.")
        except ValueError as exc:
            return ToolOutcome(f"Refused: {escape(str(exc))}")

    async def _list(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = ListProjectsArgs.model_validate(arguments)
        rows = await self._service.list(ctx.user_id, include_archived=args.include_archived)
        tainted = any(project.tainted for project, _, _ in rows) or await self._web_money(ctx.user_id, rows)
        return ToolOutcome(project_list_text(rows, include_archived=args.include_archived), tainted=tainted)

    async def _get(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        ref = ProjectRefArgs.model_validate(arguments).project
        found = await required_project(self._service, ctx.user_id, ref, change=False)
        if isinstance(found, ToolOutcome):
            return found
        detail = await self._service.detail(ctx.user_id, found.id)
        if detail is None:
            return ToolOutcome(GONE_TEXT)
        return ToolOutcome(project_page_text(detail), tainted=detail.tainted)

    async def _create(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = CreateProjectArgs.model_validate(arguments)
        draft = ProjectDraft(
            name=args.name.strip(), currency=args.currency, budget=optional_amount(args.budget),
            monthly_budget=optional_amount(args.monthly_budget), color=read_color(args.color),
            start_date=optional_day(args.start_date), due_date=optional_day(args.due_date),
            lead_bot_id=await self._lead_bot_id(ctx.user_id, args.lead_bot),
        )
        project = await self._service.create(ctx.user_id, draft, created_by_bot=ctx.bot_id, tainted=ctx.tainted)
        return ToolOutcome(f"Created project {project_brief(project)}.", created=True, tainted=project.tainted)

    async def _update(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = UpdateProjectArgs.model_validate(arguments)
        found = await required_project(self._service, ctx.user_id, args.project, change=True)
        if isinstance(found, ToolOutcome):
            return found
        changes = project_changes(args)
        if args.lead_bot is not None:
            changes = {**changes, "lead_bot_id": await self._lead_bot_id(ctx.user_id, args.lead_bot)}
        if not changes:
            return ToolOutcome(NOTHING_TO_CHANGE_TEXT)
        project = await self._service.update(ctx.user_id, found.id, changes)
        if project is None:
            return ToolOutcome(GONE_TEXT)
        return ToolOutcome(f"Updated: {project_brief(project)}.", tainted=project.tainted)

    async def _add_topup(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = AddTopupArgs.model_validate(arguments)
        amount = parse_amount(args.amount)
        found = await required_project(self._service, ctx.user_id, args.project, change=True)
        if isinstance(found, ToolOutcome):
            return found
        topup = await self._service.add_topup(ctx.user_id, found.id, amount, args.source,
                                              created_by_bot=ctx.bot_id, tainted=ctx.tainted)
        if topup is None:
            return ToolOutcome(GONE_TEXT)
        done = f"Added a {money(topup.amount, topup.currency)} top-up (id={topup.id})"
        return await self._budget_now(ctx.user_id, done, topup.project_id)

    async def _edit_topup(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = EditTopupArgs.model_validate(arguments)
        amount = parse_amount(args.amount)
        topup = await self._service.edit_topup(ctx.user_id, args.topup.strip(), amount)
        if topup is None:
            return ToolOutcome(NO_TOPUP_TEXT)
        done = f"Changed the top-up to {money(amount, topup.currency)}"
        return await self._budget_now(ctx.user_id, done, topup.project_id)

    async def _undo_topup(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        ref = TopupRefArgs.model_validate(arguments).topup.strip()
        topup = await self._service.undo_topup(ctx.user_id, ref)
        if topup is None:
            return ToolOutcome(NO_TOPUP_TEXT)
        return await self._budget_now(ctx.user_id, "Undid the top-up and its changes", topup.project_id)

    async def _budget_now(self, user_id: str, done: str, project_id: str) -> ToolOutcome:
        """A top-up reply: what was done, and the project's total budget now."""
        project = await self._service.resolve(user_id, project_id, change=False)
        if isinstance(project, ProjectRefusal):
            return ToolOutcome(f"{done}.")
        return ToolOutcome(f"{done}. {_budget_sentence(project)}", tainted=project.tainted)

    async def _lead_bot_id(self, user_id: str, name: str | None) -> str | None:
        """H15: the lead is one of the user's own bots, by id or name; '' is none."""
        wanted = (name or "").strip().lstrip("@")
        if not wanted:
            return None
        key = normalize_bot_name(wanted)
        bots = await self._bots.list(user_id)
        found = next((bot for bot in bots if bot.id == wanted or normalize_bot_name(bot.name) == key), None)
        if found is None:
            raise ValueError(NO_SUCH_BOT_TEXT.format(name=wanted))
        return found.id

    async def _web_money(self, user_id: str, rows: Sequence[ProjectRow]) -> bool:
        """Whether a web-made expense is behind the sums the list prints, as
        money_summary judges it (M1 D3, R1)."""
        for project, _, _ in rows:
            if any(expense.tainted for expense in await self._expenses.list_project(user_id, project.id)):
                return True
        return False
```

- [ ] **Step 7: Money learns projects, tasks and steps, starred and void**

**7a.** Replace the whole of `roost/money/service.py` **(last written by Task 1)** with:

```python
"""``MoneyService`` — projects + expenses + the ``money_changed`` frame. Tools
and HTTP routes both go through it.

Projects hub:
- ``log_expense`` alone may make a project from a name (H3): an exact or typo
  match is reused, anything else is created.
- An archived project takes no new expense, and no expense moves into it (H3).
- An expense with no currency takes its project's (H7).
- ``set_budget`` sets or clears the total budget of a project the caller has
  already found (H3, H5): it never makes one."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from roost.constants import GENERAL_PROJECT_NAME, PROJECT_STATUSES
from roost.events.hub import EventHub
from roost.money.expense_store import ExpenseStore
from roost.money.models import Expense, ExpenseDraft, ExpensePatch, MoneySummary, Project
from roost.money.project_store import ProjectStore
from roost.money.summary import summarize
from roost.records.project_link import NO_SUCH_PROJECT_TEXT
from roost.records.resolver import NamedRef, resolve

MoneyChange = Literal["expense_created", "expense_updated", "expense_deleted", "budget_set"]
ARCHIVED_TEXT = "“{name}” is archived; unarchive it first."
_ARCHIVED = PROJECT_STATUSES[1]


@dataclass(frozen=True)
class ExpenseEntry:
    """A parsed, validated expense to log (amount and day already read)."""

    amount: Decimal
    spent_at: str
    project: str | None = None
    note: str | None = None
    vendor: str | None = None
    currency: str | None = None      # None: the project's own currency (H7)
    task_id: str | None = None       # a task of any status (H11)
    step_id: str | None = None       # one of that task's steps
    starred: bool = False


def open_for_money(project: Project) -> Project:
    """H3: an archived project takes no new or moved expense (``ValueError``)."""
    if project.status == _ARCHIVED:
        raise ValueError(ARCHIVED_TEXT.format(name=project.name))
    return project


class MoneyService:
    def __init__(self, projects: ProjectStore, expenses: ExpenseStore, events: EventHub) -> None:
        self._projects = projects
        self._expenses = expenses
        self._events = events

    async def project_for(self, user_id: str, name: str | None, *, created_by_bot: str | None,
                          tainted: bool) -> Project:
        """An existing project on an exact or typo match (harvested resolver),
        else a new one. A partial match never redirects money elsewhere."""
        wanted = (name or "").strip() or GENERAL_PROJECT_NAME
        known = await self._projects.list(user_id)
        hit = resolve(wanted, [NamedRef(p.id, p.name) for p in known])
        if hit.resolved is not None and hit.reason in ("exact", "fuzzy"):
            return next(p for p in known if p.id == hit.resolved.id)
        return await self._projects.find_or_create(user_id, wanted, created_by_bot=created_by_bot, tainted=tainted)

    async def log_expense(self, user_id: str, entry: ExpenseEntry, *, created_by_bot: str | None = None,
                          tainted: bool = False, project: Project | None = None) -> tuple[Expense, Project]:
        """Log into ``project``, or else into the one ``entry.project`` names
        (found or made, H3). An archived project refuses (``ValueError``)."""
        target = open_for_money(project or await self.project_for(
            user_id, entry.project, created_by_bot=created_by_bot, tainted=tainted))
        draft = ExpenseDraft(
            project_id=target.id, amount=entry.amount, currency=entry.currency or target.currency,
            description=entry.note, vendor=entry.vendor, spent_at=entry.spent_at, task_id=entry.task_id,
            step_id=entry.step_id, is_favorite=entry.starred,
        )
        expense = await self._expenses.add(user_id, draft, created_by_bot=created_by_bot, tainted=tainted)
        await self._changed(user_id, "expense_created", expense.id)
        return expense, target

    async def projects(self, user_id: str) -> tuple[Project, ...]:
        return await self._projects.list(user_id)

    async def list_expenses(self, user_id: str, month: str) -> tuple[Expense, ...]:
        return await self._expenses.list_month(user_id, month)

    async def get_expense(self, user_id: str, expense_id: str) -> Expense | None:
        return await self._expenses.get(user_id, expense_id)

    async def made_by(self, user_id: str, bot_id: str, limit: int) -> tuple[tuple[Expense, Project | None], ...]:
        projects = {p.id: p for p in await self.projects(user_id)}
        expenses = await self._expenses.made_by(user_id, bot_id, limit)
        return tuple((expense, projects.get(expense.project_id)) for expense in expenses)

    async def summary(self, user_id: str, month: str) -> tuple[MoneySummary, bool]:
        """The month's summary and whether anything behind it is tainted: an
        expense in its totals, or a project whose name it prints. A web-made
        project the summary doesn't show leaves it clean (R1: taint must not
        spread to every conversation that adds up a month)."""
        projects = await self._projects.list(user_id)
        expenses = await self._expenses.list_month(user_id, month)
        summary = summarize(month, projects, expenses)
        shown = {row.project for row in summary.by_project}
        tainted = any(e.tainted for e in expenses) or any(p.tainted for p in projects if p.name in shown)
        return summary, tainted

    async def update_expense(self, user_id: str, expense_id: str, patch: ExpensePatch) -> Expense | None:
        """A move goes only into one of the user's open projects (H3):
        ``ValueError`` for an archived or unknown one, and nothing is written."""
        if "project_id" in patch.changes:
            await self._open_project(user_id, str(patch.changes["project_id"]))
        expense = await self._expenses.update(user_id, expense_id, patch)
        if expense is not None:
            await self._changed(user_id, "expense_updated", expense.id)
        return expense

    async def keep_expense(self, user_id: str, expense_id: str) -> tuple[Expense, Project | None] | None:
        """The user vouches for an expense on the Board (HTTP only, never a
        tool): it and the project name its row shows are theirs now, so a
        month listing them no longer taints a run."""
        expense = await self._expenses.keep(user_id, expense_id)
        if expense is None:
            return None
        project = await self._projects.keep(user_id, expense.project_id)
        await self._changed(user_id, "expense_updated", expense.id)
        return expense, project

    async def delete_expense(self, user_id: str, expense_id: str) -> bool:
        deleted = await self._expenses.delete(user_id, expense_id)
        if deleted:
            await self._changed(user_id, "expense_deleted", expense_id)
        return deleted

    async def set_budget(self, user_id: str, project: Project, amount: Decimal | None, *,
                         created_by_bot: str | None = None, tainted: bool = False) -> Project | None:
        """Set, or with ``None`` clear (H5), the total budget of a project the
        caller found. ``None``: the project is gone."""
        updated = await self._projects.set_budget(user_id, project.id, amount, created_by_bot=created_by_bot,
                                                  tainted=tainted)
        if updated is not None:
            await self._changed(user_id, "budget_set", project.id)
        return updated

    async def _open_project(self, user_id: str, project_id: str) -> Project:
        target = await self._projects.get(user_id, project_id)
        if target is None:
            raise ValueError(NO_SUCH_PROJECT_TEXT)
        return open_for_money(target)

    async def _changed(self, user_id: str, change: MoneyChange, item_id: str) -> None:
        await self._events.publish(user_id, {"type": "money_changed", "change": change, "id": item_id})
```

**7b.** Create `roost/money/tool_args.py`:

```python
"""The money tools' arguments (M1 D7; projects hub H1, H5, H6, H11) — pydantic
at the tool boundary. Free text is ``ToolText``: a copy of an escaped tool
result is stored plain. ``roost.money.tools`` imports every model here, so
they are importable from there too."""

from __future__ import annotations

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from roost.constants import (
    CURRENCY_PATTERN, MAX_CATEGORY_NAME_LENGTH, MAX_DUE_TEXT_LENGTH, MAX_EXPENSE_NOTE_LENGTH, MAX_RECORD_ID_LENGTH,
    MAX_TASK_TITLE_LENGTH,
)
from roost.records.tool_text import ToolText

Amount = str | int | float
# Projects hub H1: the argument is `project`. `extra="ignore"` would silently drop
# the old `category`, landing the money in General, so both names are read;
# `project` wins when a model sends both.
PROJECT_ARG = AliasChoices("project", "category")


class LogExpenseArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    amount: Amount
    project: ToolText | None = Field(default=None, validation_alias=PROJECT_ARG, max_length=MAX_CATEGORY_NAME_LENGTH)
    note: ToolText | None = Field(default=None, max_length=MAX_EXPENSE_NOTE_LENGTH)
    vendor: ToolText | None = Field(default=None, max_length=MAX_EXPENSE_NOTE_LENGTH)
    currency: str | None = Field(default=None, pattern=CURRENCY_PATTERN)   # None: the project's (H7)
    spent_at: str | None = Field(default=None, max_length=MAX_DUE_TEXT_LENGTH)
    task: ToolText | None = Field(default=None, max_length=MAX_TASK_TITLE_LENGTH)
    step: ToolText | None = Field(default=None, max_length=MAX_TASK_TITLE_LENGTH)
    starred: bool = False


class MonthArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    month: str | None = Field(default=None, max_length=7)
    project: ToolText | None = Field(default=None, validation_alias=PROJECT_ARG, max_length=MAX_CATEGORY_NAME_LENGTH)


class ListExpensesArgs(MonthArgs):
    offset: int = Field(default=0, ge=0)


class ExpenseRefArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    expense: str = Field(min_length=1, max_length=MAX_RECORD_ID_LENGTH)


class UpdateExpenseArgs(ExpenseRefArgs):
    """A null leaves a field as it is. ``task`` '' unlinks the task and its
    step; ``step`` '' unlinks the step."""

    amount: Amount | None = None
    project: ToolText | None = Field(default=None, validation_alias=PROJECT_ARG, max_length=MAX_CATEGORY_NAME_LENGTH)
    note: ToolText | None = Field(default=None, max_length=MAX_EXPENSE_NOTE_LENGTH)
    spent_at: str | None = Field(default=None, max_length=MAX_DUE_TEXT_LENGTH)
    task: ToolText | None = Field(default=None, max_length=MAX_TASK_TITLE_LENGTH)
    step: ToolText | None = Field(default=None, max_length=MAX_TASK_TITLE_LENGTH)
    starred: bool | None = None
    void: bool | None = None


class SetBudgetArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    project: ToolText = Field(validation_alias=PROJECT_ARG, min_length=1, max_length=MAX_CATEGORY_NAME_LENGTH)
    amount: Amount                    # '' clears the total budget (H5)
```

**7c.** Create `roost/money/expense_links.py`:

```python
"""An expense's task and step (projects hub H11).

- The task is found among tasks of EVERY status, since money is often logged
  after the work is done: its id, its exact title or a unique part of one. A
  near miss is refused (linking money to the wrong task is a change), and so
  is a title several tasks share — a repeating task's next occurrence has the
  same title — so the refusals list ids.
- A step needs its task and must be one of that task's steps, by id or title.
- A refusal that shows titles carries those tasks' taint (M1 D3)."""

from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Sequence

from roost.constants import EXPENSE_TASK_MATCHES_SHOWN
from roost.records.resolver import NamedRef, resolve
from roost.talk.outcome import ToolOutcome
from roost.tasks.models import Step, Task
from roost.tasks.service import TaskService

WEB_MARK = " [from web content]"
STEP_NEEDS_TASK_TEXT = "A step needs its task: name the task too."
TASK_NEAR_TEXT = "Refused: no task is called “{ref}”. Did you mean {titles}? Say it exactly."
TASK_SEVERAL_TEXT = "Refused: several tasks match “{ref}”: {titles}. Say which one (its id)."
TASK_NONE_TEXT = "Refused: no task matches “{ref}”."
STEP_NONE_TEXT = "Refused: “{task}” has no step “{ref}”. Its steps: {steps}."
NO_STEPS_TEXT = "Refused: “{task}” has no steps."


def _escape(text: str) -> str:
    return html.escape(text, quote=True)


def _blank(text: str | None) -> bool:
    return text is None or not text.strip()


@dataclass(frozen=True)
class ExpenseLink:
    task: Task | None = None
    step: Step | None = None

    @property
    def task_id(self) -> str | None:
        return None if self.task is None else self.task.id

    @property
    def step_id(self) -> str | None:
        return None if self.step is None else self.step.id

    @property
    def tainted(self) -> bool:
        """A reply that echoes a web-made task's title is web text."""
        return self.task is not None and self.task.tainted


NO_LINK = ExpenseLink()


async def find_link(tasks: TaskService, user_id: str, task_ref: str | None,
                    step_ref: str | None) -> ExpenseLink | ToolOutcome:
    """The task and step an expense is for. No task named: no link. A step
    alone is a ``ValueError`` (a step needs its task)."""
    if _blank(task_ref):
        if not _blank(step_ref):
            raise ValueError(STEP_NEEDS_TASK_TEXT)
        return NO_LINK
    task = await find_task(tasks, user_id, task_ref or "")
    if isinstance(task, ToolOutcome):
        return task
    if _blank(step_ref):
        return ExpenseLink(task)
    step = find_step(task, step_ref or "")
    return step if isinstance(step, ToolOutcome) else ExpenseLink(task, step)


async def find_task(tasks: TaskService, user_id: str, ref: str) -> Task | ToolOutcome:
    known = await tasks.list(user_id, status="all")
    by_id = {task.id: task for task in known}
    if ref.strip() in by_id:
        return by_id[ref.strip()]
    hit = resolve(ref, [NamedRef(task.id, task.title) for task in known])
    if hit.resolved is not None and hit.reason != "fuzzy":
        return by_id[hit.resolved.id]
    shown = tuple(by_id[candidate.id] for candidate in hit.candidates[:EXPENSE_TASK_MATCHES_SHOWN])
    return _task_refusal(ref.strip(), hit.reason, shown)


def _titles(tasks: Sequence[Task]) -> str:
    return "; ".join(f"“{_escape(task.title)}” id={task.id}" + (WEB_MARK if task.tainted else "") for task in tasks)


def _task_refusal(ref: str, reason: str, shown: Sequence[Task]) -> ToolOutcome:
    tainted = any(task.tainted for task in shown)
    if reason == "fuzzy":
        return ToolOutcome(TASK_NEAR_TEXT.format(ref=_escape(ref), titles=_titles(shown)), tainted=tainted)
    if reason == "multi":
        return ToolOutcome(TASK_SEVERAL_TEXT.format(ref=_escape(ref), titles=_titles(shown)), tainted=tainted)
    return ToolOutcome(TASK_NONE_TEXT.format(ref=_escape(ref)))


def find_step(task: Task, ref: str) -> Step | ToolOutcome:
    """One of ``task``'s steps by id, exact title or a unique part of one; a
    refusal lists the task's steps (the task's own text, so its taint)."""
    by_id = {step.id: step for step in task.steps}
    if ref.strip() in by_id:
        return by_id[ref.strip()]
    hit = resolve(ref, [NamedRef(step.id, step.title) for step in task.steps])
    if hit.resolved is not None and hit.reason != "fuzzy":
        return by_id[hit.resolved.id]
    if not task.steps:
        return ToolOutcome(NO_STEPS_TEXT.format(task=_escape(task.title)), tainted=task.tainted)
    steps = "; ".join(f"“{_escape(step.title)}”" for step in task.steps)
    text = STEP_NONE_TEXT.format(task=_escape(task.title), ref=_escape(ref.strip()), steps=steps)
    return ToolOutcome(text, tainted=task.tainted)
```

**7d.** Replace the whole of `roost/money/tools.py` **(last written by Task 1)** with:

```python
"""The money tools over the user's shared money (M1 D2, D7; projects hub H1,
H3, H6, H7, H11).

- ``log_expense`` alone keeps find-or-create for its project (H3). With a
  task and no project named, the money goes to the task's project; a project
  named outright wins. An archived project takes nothing (``MoneyService``).
- Every other money tool names a project exact-or-ask
  (``roost.projects.refs``): a near miss is refused for a change, and nothing
  is ever created from a name. ``set_budget`` sets or clears the total budget.
- An expense may be linked to a task of any status and one of its steps
  (``roost.money.expense_links``), starred, and voided: a void expense is
  still listed but never summed."""

from __future__ import annotations

from typing import Any, Mapping

from pydantic import ValidationError

from roost.constants import EXPENSE_LIST_LIMIT
from roost.money.amounts import optional_amount, parse_amount
from roost.money.expense_links import ExpenseLink, find_link
from roost.money.format import escape, expense_line, money, summary_text
from roost.money.models import EXPENSE_POSTED, EXPENSE_VOID, Expense, ExpensePatch, Project
from roost.money.months import current_month, month_bounds, parse_spent_at
from roost.money.service import ExpenseEntry, MoneyService
from roost.money.tool_args import (
    ExpenseRefArgs, ListExpensesArgs, LogExpenseArgs, MonthArgs, SetBudgetArgs, UpdateExpenseArgs,
)
from roost.projects.refs import project_ref, required_project
from roost.projects.service import ProjectRefusal, ProjectService
from roost.records.paging import more_line
from roost.talk.domain_tools import RecordContext
from roost.talk.outcome import ToolOutcome
from roost.tasks.service import TaskService

_ACTIVITY = {
    "log_expense": "logging an expense", "list_expenses": "checking your expenses",
    "money_summary": "adding up your month", "update_expense": "correcting an expense",
    "delete_expense": "deleting an expense", "set_budget": "setting a budget",
}
NO_EXPENSE_TEXT = "Refused: there is no expense with that id."
PROJECT_GONE_TEXT = "Refused: that project is gone."


def _same(value: Any) -> Any:
    return value


def _status(void: bool) -> str:
    return EXPENSE_VOID if void else EXPENSE_POSTED


# update_expense's plain arguments: (argument, Expense field, reader). A null leaves the field as it is.
_PLAIN = (("amount", "amount", parse_amount), ("spent_at", "spent_at", parse_spent_at),
          ("note", "description", _same), ("starred", "is_favorite", _same), ("void", "status", _status))


def _month(value: str | None) -> str:
    month = value or current_month()
    month_bounds(month)   # raises a plain ValueError for a bad month
    return month


def _project_name(projects: Mapping[str, Project], expense: Expense) -> str:
    project = projects.get(expense.project_id)
    return project.name if project is not None else "?"


def _project_tainted(projects: Mapping[str, Project], expense: Expense) -> bool:
    project = projects.get(expense.project_id)
    return project is not None and project.tainted


def _plain_changes(args: UpdateExpenseArgs) -> dict[str, Any]:
    return {field: read(getattr(args, name)) for name, field, read in _PLAIN if getattr(args, name) is not None}


def _logged(expense: Expense, project: Project, link: ExpenseLink) -> str:
    task = f" for “{escape(link.task.title)}”" if link.task is not None else ""
    step = f", step “{escape(link.step.title)}”" if link.step is not None else ""
    starred = ", starred" if expense.is_favorite else ""
    return (f"Logged {money(expense.amount, expense.currency)} to {escape(project.name)} on {expense.spent_at}"
            f"{task}{step}{starred} (id={expense.id}).")


def _updated(expense: Expense) -> str:
    void = " [void]" if expense.status == EXPENSE_VOID else ""
    starred = " [starred]" if expense.is_favorite else ""
    return f"Updated: {money(expense.amount, expense.currency)} on {expense.spent_at}{void}{starred}."


class MoneyTools:
    names = frozenset(_ACTIVITY)

    def __init__(self, service: MoneyService, projects: ProjectService, tasks: TaskService) -> None:
        self._service = service
        self._projects = projects
        self._tasks = tasks

    def activity(self, name: str) -> str:
        return _ACTIVITY[name]

    async def run(self, name: str, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        handlers = {"log_expense": self._log, "list_expenses": self._list, "money_summary": self._summary,
                    "update_expense": self._update, "delete_expense": self._delete, "set_budget": self._budget}
        try:
            return await handlers[name](arguments, ctx)
        except ValidationError:
            return ToolOutcome(f"Refused: {name} got arguments it can't use; see its description.")
        except ValueError as exc:
            return ToolOutcome(f"Refused: {escape(str(exc))}")

    async def _log(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = LogExpenseArgs.model_validate(arguments)
        amount, day = parse_amount(args.amount), parse_spent_at(args.spent_at)
        link = await find_link(self._tasks, ctx.user_id, args.task, args.step)
        if isinstance(link, ToolOutcome):
            return link
        target = await self._log_project(ctx, args.project, link)
        entry = ExpenseEntry(amount=amount, spent_at=day, project=target.name, note=args.note, vendor=args.vendor,
                             currency=args.currency, task_id=link.task_id, step_id=link.step_id,
                             starred=args.starred)
        expense, project = await self._service.log_expense(ctx.user_id, entry, created_by_bot=ctx.bot_id,
                                                            tainted=ctx.tainted, project=target)
        # The reply echoes the project's name and the task's title; web-made ones are web text (D3).
        return ToolOutcome(_logged(expense, project, link), created=True, tainted=project.tainted or link.tainted)

    async def _log_project(self, ctx: RecordContext, name: str | None, link: ExpenseLink) -> Project:
        """H3: the named project, found or made; with none named, the linked
        task's project; else General."""
        task = link.task
        if not (name or "").strip() and task is not None and task.project_id is not None:
            found = await self._projects.resolve(ctx.user_id, task.project_id, change=False)
            if not isinstance(found, ProjectRefusal):
                return found
        return await self._service.project_for(ctx.user_id, name, created_by_bot=ctx.bot_id, tainted=ctx.tainted)

    async def _list(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        """Taint covers every expense shown AND every project name printed."""
        args = ListExpensesArgs.model_validate(arguments)
        month = _month(args.month)
        wanted = await project_ref(self._projects, ctx.user_id, args.project, change=False)
        if isinstance(wanted, ToolOutcome):
            return wanted
        projects = {p.id: p for p in await self._service.projects(ctx.user_id)}
        expenses = await self._service.list_expenses(ctx.user_id, month)
        matching = tuple(e for e in expenses if wanted is None or e.project_id == wanted.id)
        shown = matching[args.offset:args.offset + EXPENSE_LIST_LIMIT]
        if not shown:
            return ToolOutcome("No expenses match." if not matching
                               else f"Nothing more: all {len(matching)} expenses are listed.")
        lines = "\n".join(expense_line(e, _project_name(projects, e)) for e in shown)
        tainted = any(e.tainted or _project_tainted(projects, e) for e in shown)
        return ToolOutcome(lines + more_line(len(matching), args.offset, len(shown)), tainted=tainted)

    async def _summary(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        summary, tainted = await self._service.summary(ctx.user_id, _month(MonthArgs.model_validate(arguments).month))
        return ToolOutcome(summary_text(summary), tainted=tainted)

    async def _update(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = UpdateExpenseArgs.model_validate(arguments)
        current = await self._service.get_expense(ctx.user_id, args.expense)
        if current is None:
            return ToolOutcome(NO_EXPENSE_TEXT)
        changes = await self._changes(args, current, ctx.user_id)
        if isinstance(changes, ToolOutcome):
            return changes
        expense = await self._service.update_expense(ctx.user_id, current.id, ExpensePatch(changes))
        if expense is None:
            return ToolOutcome(NO_EXPENSE_TEXT, tainted=current.tainted)
        # No project name or task title is echoed here, so they add no text (and no taint).
        return ToolOutcome(_updated(expense), tainted=current.tainted)

    async def _changes(self, args: UpdateExpenseArgs, current: Expense,
                       user_id: str) -> dict[str, Any] | ToolOutcome:
        """The patch: the plain fields, a move (exact-or-ask), and the task and step links."""
        plain = _plain_changes(args)
        project = await project_ref(self._projects, user_id, args.project, change=True)
        if isinstance(project, ToolOutcome):
            return project
        links = await self._link_changes(args, current, user_id)
        if isinstance(links, ToolOutcome):
            return links
        moved = {} if project is None else {"project_id": project.id}
        return {**plain, **moved, **links}

    async def _link_changes(self, args: UpdateExpenseArgs, current: Expense,
                            user_id: str) -> dict[str, Any] | ToolOutcome:
        """``task`` '' unlinks the task and its step; ``step`` '' unlinks the
        step. A step needs a task: the one named here, else the expense's own."""
        if args.task is not None and not args.task.strip():
            return {"task_id": None, "step_id": None}
        if args.task is None and (args.step is None or not args.step.strip()):
            return {} if args.step is None else {"step_id": None}
        task_ref = args.task if args.task is not None else current.task_id
        link = await find_link(self._tasks, user_id, task_ref, args.step)
        if isinstance(link, ToolOutcome):
            return link
        return {"task_id": link.task_id, "step_id": link.step_id}

    async def _delete(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        current = await self._service.get_expense(ctx.user_id, ExpenseRefArgs.model_validate(arguments).expense)
        if current is None:
            return ToolOutcome(NO_EXPENSE_TEXT)
        await self._service.delete_expense(ctx.user_id, current.id)
        return ToolOutcome(f"Deleted the {money(current.amount, current.currency)} expense of {current.spent_at}.",
                           tainted=current.tainted)

    async def _budget(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        """H3: exact-or-ask, never a new project; H5: an amount of '' clears the budget."""
        args = SetBudgetArgs.model_validate(arguments)
        amount = optional_amount(args.amount)
        found = await required_project(self._projects, ctx.user_id, args.project, change=True)
        if isinstance(found, ToolOutcome):
            return found
        project = await self._service.set_budget(ctx.user_id, found, amount, created_by_bot=ctx.bot_id,
                                                 tainted=ctx.tainted)
        if project is None:
            return ToolOutcome(PROJECT_GONE_TEXT, tainted=found.tainted)
        if project.budget is None:
            return ToolOutcome(f"Budget for {escape(project.name)} cleared.", tainted=project.tainted)
        return ToolOutcome(f"Budget for {escape(project.name)}: {money(project.budget, project.currency)}.",
                           tainted=project.tainted)
```

**7e.** Replace the whole of `roost/money/tool_specs.py` **(last written by Task 1)** with:

```python
"""The money tool specs and gate kinds (M1 D3, D7; projects hub H1, H3, H5–H7, H11)."""

from __future__ import annotations

from roost.llm.types import ToolSpec
from roost.records.paging import OFFSET_PROPERTY
from roost.talk.tool_def import ToolDef

_AMOUNT = {"type": ["number", "string"], "description": "The amount, e.g. 12.50 or '12,50'."}
_NEW_OR_KNOWN_PROJECT = {"type": "string", "description": (
    "Project, e.g. 'food'; a new name makes a new project. Omit for the task's project, or General.")}
_PROJECT = {"type": "string", "description": "The project's name or id. Name it exactly."}
_MONTH = {"type": "string", "description": "A month like 2026-10. Default: this month (Europe/Madrid)."}
_EXPENSE = {"type": "string", "description": "The expense's id, from list_expenses."}
_TASK = {"type": "string", "description": "The task it was spent on: its id or title (open or closed)."}
_STEP = {"type": "string", "description": "One of that task's steps: its title or id."}
_STARRED = {"type": "boolean", "description": "Star it; a project shows its starred total."}

LOG_EXPENSE_SPEC = ToolSpec(
    name="log_expense",
    description=("Log money the user spent, in a project (General when none is named). Amounts are in the "
                 "project's currency unless a currency is given. Log an expense as soon as the user mentions one. "
                 "Never invent amounts; you cannot buy or pay anything."),
    input_schema={"type": "object", "properties": {
        "amount": _AMOUNT, "project": _NEW_OR_KNOWN_PROJECT,
        "note": {"type": "string", "description": "What it was for, e.g. 'lunch'."},
        "vendor": {"type": "string", "description": "Optional shop or payee."},
        "currency": {"type": "string", "description": "Three-letter code. Default: the project's currency."},
        "spent_at": {"type": "string", "description": "The day: 'yesterday', '2026-10-12'. Default: today."},
        "task": _TASK, "step": _STEP, "starred": _STARRED,
    }, "required": ["amount"]},
)
LIST_EXPENSES_SPEC = ToolSpec(
    name="list_expenses",
    description=("List the user's expenses for a month, newest first, with their ids; void ones are marked. A "
                 "long list ends with how to get the rest."),
    input_schema={"type": "object", "properties": {
        "month": _MONTH, "project": {**_PROJECT, "description": "Only this project's: its name or id."},
        "offset": dict(OFFSET_PROPERTY),
    }},
)
MONEY_SUMMARY_SPEC = ToolSpec(
    name="money_summary",
    description="Totals for a month: overall and by project, each in its own currency and against its monthly limit.",
    input_schema={"type": "object", "properties": {"month": _MONTH}},
)
UPDATE_EXPENSE_SPEC = ToolSpec(
    name="update_expense",
    description=("Correct an expense: its amount, project, note, day, task or step; star it; or void it (a void "
                 "expense stays listed but counts nowhere)."),
    input_schema={"type": "object", "properties": {
        "expense": _EXPENSE, "amount": _AMOUNT,
        "project": {**_PROJECT, "description": "The project to move it to: its name or id, exactly."},
        "note": {"type": "string"}, "spent_at": {"type": "string"},
        "task": {**_TASK, "description": _TASK["description"] + " '' unlinks it from its task."},
        "step": {**_STEP, "description": _STEP["description"] + " '' unlinks the step."},
        "starred": {"type": "boolean"},
        "void": {"type": "boolean", "description": "true voids it; false counts it again."},
    }, "required": ["expense"]},
)
DELETE_EXPENSE_SPEC = ToolSpec(
    name="delete_expense",
    description="Delete an expense.",
    input_schema={"type": "object", "properties": {"expense": _EXPENSE}, "required": ["expense"]},
)
SET_BUDGET_SPEC = ToolSpec(
    name="set_budget",
    description=("Set a project's total budget (top-ups included). Name the project exactly; a new project needs "
                 "create_project. An amount of '' clears the budget."),
    input_schema={"type": "object", "properties": {
        "project": _PROJECT, "amount": {**_AMOUNT, "description": "The total budget, e.g. 500; '' clears it."},
    }, "required": ["project", "amount"]},
)

MONEY_TOOL_DEFS: tuple[ToolDef, ...] = (
    ToolDef(LOG_EXPENSE_SPEC, "write_create"),
    ToolDef(LIST_EXPENSES_SPEC, "read"),
    ToolDef(MONEY_SUMMARY_SPEC, "read"),
    ToolDef(UPDATE_EXPENSE_SPEC, "write_change"),
    ToolDef(DELETE_EXPENSE_SPEC, "write_change"),
    ToolDef(SET_BUDGET_SPEC, "write_change"),
)
```

- [ ] **Step 8: Tasks learn projects, budget slices and `failed`**

**8a.** Replace the whole of `roost/tasks/tools.py` with:

```python
"""The task tools over the user's shared tasks (M1 D2, D6; projects hub H3,
H11). Argument names and meanings are LazyClaw's ``task_manager.py`` skills';
the handlers are Roost's: pydantic arguments, provenance (bot + taint) on
every new row, escaped results, a refusal sentence instead of a guess.

A task may belong to one of the user's projects, named exact-or-ask
(``roost.projects.refs``; never created here), and carry a budget slice in
that project's currency. ``update_task`` with status ``failed`` closes it as
failed, and a repeating task comes back, as ``complete_task`` does."""

from __future__ import annotations

import html
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from roost.constants import (
    MAX_CATEGORY_NAME_LENGTH, MAX_DUE_TEXT_LENGTH, MAX_PRE_REMINDERS, MAX_TASK_CATEGORY_LENGTH,
    MAX_TASK_NOTES_LENGTH, MAX_TASK_STEPS, MAX_TASK_TAGS, MAX_TASK_TITLE_LENGTH, TASK_LIST_LIMIT,
)
from roost.money.amounts import amount_text, optional_amount
from roost.money.models import Project
from roost.projects.refs import id_of, project_ref, project_suffix, project_taint
from roost.projects.service import ProjectService
from roost.records.resolver import NamedRef, resolve
from roost.records.tool_text import ToolText
from roost.talk.domain_tools import RecordContext
from roost.talk.outcome import ToolOutcome
from roost.tasks.due import build_schedule, patch_from_fields, validate_recur_until
from roost.tasks.format import task_line, task_list_text
from roost.tasks.models import Priority, Task, TaskDraft
from roost.tasks.recurrence import validate_cron
from roost.tasks.service import Completion, TaskService

_ACTIVITY = {
    "add_task": "adding a task", "list_tasks": "checking your tasks", "update_task": "updating a task",
    "complete_task": "completing a task", "delete_task": "deleting a task",
}
_NEEDS = {
    "add_task": "a title (and optionally due_date, category, priority, steps, project and budget)",
    "list_tasks": "an optional status (open, done, failed, all), category, project and offset",
    "update_task": "the task (its id or title) and the fields to change",
    "complete_task": "the task (its id or title)", "delete_task": "the task (its id or title)",
}
_FAILED = "failed"
_Amount = str | int | float


def _escape(text: str) -> str:
    return html.escape(text, quote=True)


class AddTaskArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: ToolText = Field(min_length=1, max_length=MAX_TASK_TITLE_LENGTH)
    description: ToolText | None = Field(default=None, max_length=MAX_TASK_NOTES_LENGTH)
    category: ToolText | None = Field(default=None, max_length=MAX_TASK_CATEGORY_LENGTH)
    priority: Priority = "medium"
    due_date: str | None = Field(default=None, max_length=MAX_DUE_TEXT_LENGTH)
    reminder_at: str | None = Field(default=None, max_length=MAX_DUE_TEXT_LENGTH)
    pre_reminders: list[str] | None = Field(default=None, max_length=MAX_PRE_REMINDERS)
    recurring: str | None = Field(default=None, max_length=MAX_DUE_TEXT_LENGTH)
    recur_until: str | None = Field(default=None, max_length=MAX_DUE_TEXT_LENGTH)
    steps: list[ToolText] = Field(default_factory=list, max_length=MAX_TASK_STEPS)
    tags: list[ToolText] = Field(default_factory=list, max_length=MAX_TASK_TAGS)
    project: ToolText | None = Field(default=None, max_length=MAX_CATEGORY_NAME_LENGTH)
    budget: _Amount | None = None


class ListTasksArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    status: Literal["open", "done", "failed", "all"] = "open"
    category: ToolText | None = Field(default=None, max_length=MAX_TASK_CATEGORY_LENGTH)
    project: ToolText | None = Field(default=None, max_length=MAX_CATEGORY_NAME_LENGTH)
    offset: int = Field(default=0, ge=0)


class TaskRefArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    task: ToolText = Field(min_length=1, max_length=MAX_TASK_TITLE_LENGTH)


class UpdateTaskArgs(TaskRefArgs):
    title: ToolText | None = Field(default=None, max_length=MAX_TASK_TITLE_LENGTH)
    description: ToolText | None = Field(default=None, max_length=MAX_TASK_NOTES_LENGTH)
    category: ToolText | None = Field(default=None, max_length=MAX_TASK_CATEGORY_LENGTH)
    priority: Priority | None = None
    status: Literal["todo", "in_progress", "cancelled", "failed"] | None = None
    due_date: str | None = Field(default=None, max_length=MAX_DUE_TEXT_LENGTH)
    project: ToolText | None = Field(default=None, max_length=MAX_CATEGORY_NAME_LENGTH)
    budget: _Amount | None = None


def _in_category(tasks: tuple[Task, ...], category: str | None) -> tuple[Task, ...]:
    if not category:
        return tasks
    wanted = category.strip().casefold()
    return tuple(task for task in tasks if (task.category or "").casefold() == wanted)


def _update_fields(args: UpdateTaskArgs, project: Project | None) -> dict[str, Any]:
    """The fields the call set. '' clears the due date, the project and the
    budget slice; a null leaves the project and the slice as they are."""
    fields = args.model_dump(include=args.model_fields_set - {"task", "project", "budget"})
    due = {"due_date": None} if fields.get("due_date") == "" else {}
    linked = {"project_id": id_of(project)} if args.project is not None else {}
    sliced = {"allocated_budget": optional_amount(args.budget)} if args.budget is not None else {}
    return {**fields, **due, **linked, **sliced}


def _filed(project: Project | None, task: Task, *, unlinked: bool = False) -> str:
    """The reply's end: the task's project and, when it has one, its budget slice."""
    if project is None or task.allocated_budget is None:
        return project_suffix(project, unlinked=unlinked)
    return (f" Project: “{_escape(project.name)}”, budget {amount_text(task.allocated_budget)} "
            f"{project.currency}.")


def _closing(verb: str, task: Task, closing: Completion | None) -> ToolOutcome:
    """complete_task's reply, and a failed update's: a repeating task's next time is shown."""
    if closing is None:
        return ToolOutcome(f"Refused: {_escape(task.title)} is not open any more.", tainted=task.tainted)
    following = f" Next time: {task_line(closing.next)}" if closing.next is not None else ""
    return ToolOutcome(f"{verb}: {_escape(task.title)}.{following}", tainted=task.tainted)


class TaskTools:
    names = frozenset(_ACTIVITY)

    def __init__(self, service: TaskService, projects: ProjectService) -> None:
        self._service = service
        self._projects = projects

    def activity(self, name: str) -> str:
        return _ACTIVITY[name]

    async def run(self, name: str, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        handlers = {"add_task": self._add, "list_tasks": self._list, "update_task": self._update,
                    "complete_task": self._complete, "delete_task": self._delete}
        try:
            return await handlers[name](arguments, ctx)
        except ValidationError:
            return ToolOutcome(f"Refused: {name} needs {_NEEDS[name]}.")
        except ValueError as exc:
            return ToolOutcome(f"Refused: {_escape(str(exc))}")

    async def _add(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = AddTaskArgs.model_validate(arguments)
        project = await project_ref(self._projects, ctx.user_id, args.project, change=True)
        if isinstance(project, ToolOutcome):
            return project
        schedule = build_schedule(args.due_date, args.reminder_at, args.pre_reminders)
        draft = TaskDraft(
            title=args.title.strip(), description=args.description, category=args.category, priority=args.priority,
            due_date=schedule.due_date, reminder_at=schedule.reminder_at, pre_reminders=schedule.pre_reminders,
            recurring=validate_cron(args.recurring), recur_until=validate_recur_until(args.recur_until),
            tags=tuple(args.tags), steps=tuple(args.steps), project_id=id_of(project),
            allocated_budget=optional_amount(args.budget),
        )
        task = await self._service.add(ctx.user_id, draft, created_by_bot=ctx.bot_id, tainted=ctx.tainted)
        return ToolOutcome(f"Added: {task_line(task)}{_filed(project, task)}", created=True,
                           tainted=project_taint(project))

    async def _list(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = ListTasksArgs.model_validate(arguments)
        project = await project_ref(self._projects, ctx.user_id, args.project, change=False)
        if isinstance(project, ToolOutcome):
            return project
        tasks = await self._service.list(ctx.user_id, status=args.status, project_id=id_of(project))
        matching = _in_category(tasks, args.category)
        shown = matching[args.offset:args.offset + TASK_LIST_LIMIT]
        return ToolOutcome(task_list_text(shown, len(matching), args.offset), tainted=any(task.tainted for task in shown))

    async def _update(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = UpdateTaskArgs.model_validate(arguments)
        found = await self._find(ctx.user_id, args.task)
        if isinstance(found, ToolOutcome):
            return found
        project = await project_ref(self._projects, ctx.user_id, args.project, change=True)
        if isinstance(project, ToolOutcome):
            return project
        fields = _update_fields(args, project)
        failing = fields.get("status") == _FAILED
        rest = {name: value for name, value in fields.items() if not (failing and name == "status")}
        task = found if failing and not rest else await self._service.update(
            ctx.user_id, found.id, patch_from_fields(rest))
        if task is None:
            return ToolOutcome("Refused: that task is gone.", tainted=found.tainted)
        if failing:
            return _closing("Failed", task, await self._service.fail(ctx.user_id, task.id))
        filed = _filed(project, task, unlinked=args.project is not None)
        return ToolOutcome(f"Updated: {task_line(task)}{filed}", tainted=found.tainted or project_taint(project))

    async def _complete(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        found = await self._find(ctx.user_id, TaskRefArgs.model_validate(arguments).task)
        if isinstance(found, ToolOutcome):
            return found
        return _closing("Completed", found, await self._service.complete(ctx.user_id, found.id))

    async def _delete(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        found = await self._find(ctx.user_id, TaskRefArgs.model_validate(arguments).task)
        if isinstance(found, ToolOutcome):
            return found
        await self._service.delete(ctx.user_id, found.id)
        return ToolOutcome(f"Deleted: {_escape(found.title)}.", tainted=found.tainted)

    async def _find(self, user_id: str, ref: str) -> Task | ToolOutcome:
        """The open task a change targets: its id, its exact title or a
        single substring hit (harvested resolver) — never a guess. Every tool
        calling this is a ``write_change``, so a lone fuzzy hit ("call mom"
        vs "Call tom") is a "did you mean" refusal, not a silent change to the
        wrong task. Both refusals show titles to the model, so they carry
        those tasks' taint (D3): a web-derived title among them taints the
        run before it can change anything."""
        tasks = await self._service.list(user_id, status="open")
        by_id = next((task for task in tasks if task.id == ref.strip()), None)
        if by_id is not None:
            return by_id
        by_key = {task.id: task for task in tasks}
        hit = resolve(ref, [NamedRef(task.id, task.title) for task in tasks])
        if hit.resolved is not None and hit.reason != "fuzzy":
            return by_key[hit.resolved.id]
        shown = tuple(by_key[c.id] for c in hit.candidates[:5])
        tainted = any(t.tainted for t in shown)
        if hit.reason == "fuzzy":
            return ToolOutcome(f"Refused: no open task is called “{_escape(ref)}”. Did you mean "
                               f"“{_titles(shown)}”? Say it exactly.", tainted=tainted)
        if hit.reason == "multi":
            return ToolOutcome(f"Refused: several open tasks match “{_escape(ref)}”: {_titles(shown)}. Say which one.",
                               tainted=tainted)
        return ToolOutcome(f"Refused: no open task matches “{_escape(ref)}”.")


def _titles(tasks: tuple[Task, ...]) -> str:
    """Escaped titles for a refusal, each web-made one marked as such."""
    return "; ".join(_escape(t.title) + (" [from web content]" if t.tainted else "") for t in tasks)
```

(`_find` and `_titles` are carried over unchanged, including the existing `[:5]`.)

**8b.** Replace the whole of `roost/tasks/tool_specs.py` **(last written by Task 1, which made `category` "list")** with:

```python
"""The tasks tool specs and gate kinds (M1 D3, D6; projects hub H11)."""

from __future__ import annotations

from roost.llm.types import ToolSpec
from roost.records.paging import OFFSET_PROPERTY
from roost.talk.tool_def import ToolDef
from roost.tasks.models import PRIORITIES

_TASK_REF = {"type": "string", "description": "The task's id, or its title (or a unique part of it)."}
_DUE = {"type": "string", "description": "When it is due, as the user said it: 'tomorrow at 9', 'next Monday', "
                                         "'2026-10-20' or an ISO date and time (Europe/Madrid). '' clears it."}
_PROJECT = {"type": "string", "description": ("One of the user's projects, by name or id. Name it exactly; make "
                                              "a new one with create_project.")}
_BUDGET = {"type": ["number", "string"], "description": "The task's budget slice in its project's currency, e.g. "
                                                        "300 (needs a project)."}

ADD_TASK_SPEC = ToolSpec(
    name="add_task",
    description=("Add a task to the user's task list (the user's own list; every bot uses it). A due time is "
                 "also the reminder; advance reminders default to 30 minutes before. "
                 "Pass dates as the user said them, like \"tomorrow at 9\"."),
    input_schema={"type": "object", "properties": {
        "title": {"type": "string", "description": "Short title, e.g. 'Call the dentist'."},
        "description": {"type": "string", "description": "Optional notes."},
        "category": {"type": "string", "description": "Optional list, e.g. 'Home'."},
        "priority": {"type": "string", "enum": list(PRIORITIES)},
        "due_date": _DUE,
        "reminder_at": {"type": "string", "description": "Optional reminder time if not the due time, e.g. 'tomorrow 8:00'."},
        "pre_reminders": {"type": "array", "items": {"type": "string"},
                          "description": "Advance reminders as offsets like '-30m' or '-2h'; [] for none."},
        "recurring": {"type": "string", "description": "Optional cron for a repeating task, e.g. '0 9 * * 1' (Mondays 09:00)."},
        "recur_until": {"type": "string", "description": "Optional last day of a repeating task, YYYY-MM-DD."},
        "steps": {"type": "array", "items": {"type": "string"}, "description": "Optional checklist items."},
        "tags": {"type": "array", "items": {"type": "string"}},
        "project": _PROJECT, "budget": _BUDGET,
    }, "required": ["title"]},
)
LIST_TASKS_SPEC = ToolSpec(
    name="list_tasks",
    description=("List the user's tasks: open ones by default, by priority then due date. A long list ends "
                 "with how to get the rest."),
    input_schema={"type": "object", "properties": {
        "status": {"type": "string", "enum": ["open", "done", "failed", "all"]},
        "category": {"type": "string", "description": "Only this list."},
        "project": {"type": "string", "description": "Only this project's tasks, by name or id."},
        "offset": dict(OFFSET_PROPERTY),
    }},
)
UPDATE_TASK_SPEC = ToolSpec(
    name="update_task",
    description=("Change an open task's title, notes, list, project, budget, priority, status or due date; status "
                 "failed closes it as failed (a repeating task comes back). "
                 "Name the task exactly; if two match, ask the user which."),
    input_schema={"type": "object", "properties": {
        "task": _TASK_REF, "title": {"type": "string"}, "description": {"type": "string"},
        "category": {"type": "string"}, "priority": {"type": "string", "enum": list(PRIORITIES)},
        "status": {"type": "string", "enum": ["todo", "in_progress", "cancelled", "failed"]}, "due_date": _DUE,
        "project": {**_PROJECT, "description": _PROJECT["description"] + " '' takes it out of its project."},
        "budget": {**_BUDGET, "description": _BUDGET["description"] + " '' clears it."},
    }, "required": ["task"]},
)
COMPLETE_TASK_SPEC = ToolSpec(
    name="complete_task",
    description="Mark an open task done. A repeating task comes back for its next time. "
                "Name the task exactly; if two match, ask the user which.",
    input_schema={"type": "object", "properties": {"task": _TASK_REF}, "required": ["task"]},
)
DELETE_TASK_SPEC = ToolSpec(
    name="delete_task",
    description="Delete an open task. Name the task exactly; if two match, ask the user which.",
    input_schema={"type": "object", "properties": {"task": _TASK_REF}, "required": ["task"]},
)

TASK_TOOL_DEFS: tuple[ToolDef, ...] = (
    ToolDef(ADD_TASK_SPEC, "write_create"),
    ToolDef(LIST_TASKS_SPEC, "read"),
    ToolDef(UPDATE_TASK_SPEC, "write_change"),
    ToolDef(COMPLETE_TASK_SPEC, "write_change"),
    ToolDef(DELETE_TASK_SPEC, "write_change"),
)
```

- [ ] **Step 9: Notes learn projects**

**9a.** Replace the whole of `roost/notes/tools.py` with:

```python
"""The note tools over the user's shared notes (M2 D1; projects hub H12).
Pydantic arguments, provenance (bot + taint) on every new note, escaped
results, and exact-or-ask names: a change needs the note's id, exact title or
a unique part of it — a near miss is a "did you mean" refusal, never a change
to the wrong note. A note may belong to one of the user's projects, named the
same exact-or-ask way; moving it never bumps its revision."""

from __future__ import annotations

import html
from typing import Annotated, Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from roost.constants import (
    MAX_CATEGORY_NAME_LENGTH, MAX_NOTE_CONTENT_LENGTH, MAX_NOTE_QUERY_LENGTH, MAX_NOTE_TAG_LENGTH, MAX_NOTE_TAGS,
    MAX_NOTE_TITLE_LENGTH, NOTE_FIND_LIMIT, NOTE_SCAN_LIMIT,
)
from roost.notes.format import note_line, note_list_text, note_text
from roost.notes.models import Note
from roost.notes.service import NoteService, new_note_draft
from roost.projects.refs import id_of, project_ref, project_suffix, project_taint
from roost.projects.service import ProjectService
from roost.records.resolver import NamedRef, resolve
from roost.records.revision import RevisionConflict
from roost.records.tool_text import ToolText
from roost.talk.domain_tools import RecordContext
from roost.talk.outcome import ToolOutcome

CHANGED_WHILE_WRITING_TEXT = "Refused: that note changed while I was writing. Read it again first."
NOTHING_TO_UPDATE_TEXT = "Refused: update_note needs a new title, content, tags or project."
_ACTIVITY = {
    "add_note": "saving a note", "find_notes": "searching your notes", "read_note": "reading a note",
    "append_to_note": "adding to a note", "update_note": "updating a note", "delete_note": "deleting a note",
}
_NEEDS = {
    "add_note": "the note's text (content), and optionally a title, tags and a project",
    "find_notes": "an optional query, tag and project",
    "read_note": "the note (its id or title)",
    "append_to_note": "the note (its id or title) and the text to add",
    "update_note": "the note (its id or title) and a new title, content, tags or project",
    "delete_note": "the note (its id or title)",
}
Tag = Annotated[ToolText, Field(min_length=1, max_length=MAX_NOTE_TAG_LENGTH)]


def _escape(text: str) -> str:
    return html.escape(text, quote=True)


class AddNoteArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    content: ToolText = Field(min_length=1, max_length=MAX_NOTE_CONTENT_LENGTH)
    title: ToolText | None = Field(default=None, max_length=MAX_NOTE_TITLE_LENGTH)
    tags: list[Tag] = Field(default_factory=list, max_length=MAX_NOTE_TAGS)
    project: ToolText | None = Field(default=None, max_length=MAX_CATEGORY_NAME_LENGTH)


class FindNotesArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    query: ToolText = Field(default="", max_length=MAX_NOTE_QUERY_LENGTH)
    tag: ToolText | None = Field(default=None, max_length=MAX_NOTE_TAG_LENGTH)
    project: ToolText | None = Field(default=None, max_length=MAX_CATEGORY_NAME_LENGTH)


class NoteRefArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    note: ToolText = Field(min_length=1, max_length=MAX_NOTE_TITLE_LENGTH)


class AppendNoteArgs(NoteRefArgs):
    text: ToolText = Field(min_length=1, max_length=MAX_NOTE_CONTENT_LENGTH)


class UpdateNoteArgs(NoteRefArgs):
    title: ToolText | None = Field(default=None, min_length=1, max_length=MAX_NOTE_TITLE_LENGTH)
    content: ToolText | None = Field(default=None, min_length=1, max_length=MAX_NOTE_CONTENT_LENGTH)
    tags: list[Tag] | None = Field(default=None, max_length=MAX_NOTE_TAGS)
    project: ToolText | None = Field(default=None, max_length=MAX_CATEGORY_NAME_LENGTH)   # '' unlinks

    def changes(self) -> dict[str, Any]:
        """The note's own text fields; the project goes through ``set_project``."""
        found = {"title": self.title.strip() if self.title else None, "content": self.content,
                 "tags": tuple(self.tags) if self.tags is not None else None}
        return {key: value for key, value in found.items() if value is not None}


def _titles(notes: tuple[Note, ...]) -> str:
    """Escaped titles with ids for a refusal, each web-made one marked."""
    return "; ".join(f"“{_escape(n.title)}” id={n.id}" + (" [from web content]" if n.tainted else "") for n in notes)


class NoteTools:
    names = frozenset(_ACTIVITY)

    def __init__(self, service: NoteService, projects: ProjectService) -> None:
        self._service = service
        self._projects = projects

    def activity(self, name: str) -> str:
        return _ACTIVITY[name]

    async def run(self, name: str, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        handlers = {"add_note": self._add, "find_notes": self._find, "read_note": self._read,
                    "append_to_note": self._append, "update_note": self._update, "delete_note": self._delete}
        try:
            return await handlers[name](arguments, ctx)
        except ValidationError:
            return ToolOutcome(f"Refused: {name} needs {_NEEDS[name]}.")
        except RevisionConflict:
            return ToolOutcome(CHANGED_WHILE_WRITING_TEXT)
        except ValueError as exc:
            return ToolOutcome(f"Refused: {_escape(str(exc))}")

    async def _add(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = AddNoteArgs.model_validate(arguments)
        project = await project_ref(self._projects, ctx.user_id, args.project, change=True)
        if isinstance(project, ToolOutcome):
            return project
        draft = new_note_draft(args.title, args.content.strip(), args.tags, project_id=id_of(project))
        note = await self._service.add(ctx.user_id, draft, created_by_bot=ctx.bot_id, tainted=ctx.tainted)
        return ToolOutcome(f"Saved: {note_line(note)}{project_suffix(project)}", created=True,
                           tainted=project_taint(project))

    async def _find(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = FindNotesArgs.model_validate(arguments)
        project = await project_ref(self._projects, ctx.user_id, args.project, change=False)
        if isinstance(project, ToolOutcome):
            return project
        matching = await self._service.search(ctx.user_id, args.query, tag=args.tag, limit=NOTE_SCAN_LIMIT,
                                              project_id=id_of(project))
        shown = matching[:NOTE_FIND_LIMIT]
        return ToolOutcome(note_list_text(shown, len(matching), args.query), tainted=any(n.tainted for n in shown))

    async def _read(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        found = await self._find_one(ctx.user_id, NoteRefArgs.model_validate(arguments).note, change=False)
        if isinstance(found, ToolOutcome):
            return found
        return ToolOutcome(note_text(found, await self._service.links(ctx.user_id, found)), tainted=found.tainted)

    async def _append(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = AppendNoteArgs.model_validate(arguments)
        found = await self._find_one(ctx.user_id, args.note, change=True)
        if isinstance(found, ToolOutcome):
            return found
        note = await self._service.append(ctx.user_id, found, args.text)
        text = f"Added to “{_escape(found.title)}” (revision {note.revision})." if note else "Refused: that note is gone."
        return ToolOutcome(text, tainted=found.tainted)

    async def _update(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = UpdateNoteArgs.model_validate(arguments)
        moving = args.project is not None
        if not args.changes() and not moving:
            return ToolOutcome(NOTHING_TO_UPDATE_TEXT)
        found = await self._find_one(ctx.user_id, args.note, change=True)
        if isinstance(found, ToolOutcome):
            return found
        project = await project_ref(self._projects, ctx.user_id, args.project, change=True)
        if isinstance(project, ToolOutcome):
            return project
        note = await self._save(ctx.user_id, found, args.changes())
        if note is not None and moving:
            note = await self._service.set_project(ctx.user_id, found.id, id_of(project))
        if note is None:
            return ToolOutcome("Refused: that note is gone.", tainted=found.tainted)
        return ToolOutcome(f"Updated: {note_line(note)}{project_suffix(project, unlinked=moving)}",
                           tainted=found.tainted or project_taint(project))

    async def _save(self, user_id: str, found: Note, changes: Mapping[str, Any]) -> Note | None:
        """The text change first (at the revision read); a move alone writes nothing here."""
        if not changes:
            return found
        return await self._service.save(user_id, found.id, changes, base_revision=found.revision)

    async def _delete(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        found = await self._find_one(ctx.user_id, NoteRefArgs.model_validate(arguments).note, change=True)
        if isinstance(found, ToolOutcome):
            return found
        await self._service.delete(ctx.user_id, found.id)
        return ToolOutcome(f"Deleted: “{_escape(found.title)}”.", tainted=found.tainted)

    async def _find_one(self, user_id: str, ref: str, *, change: bool) -> Note | ToolOutcome:
        """The note a call targets: its id, exact title or a unique part of it
        (the harvested resolver). A lone near miss is fine to read but never to
        change. A refusal that shows titles carries those notes' taint (M1 D3)."""
        notes = await self._service.all(user_id)
        by_id = next((note for note in notes if note.id == ref.strip()), None)
        if by_id is not None:
            return by_id
        by_key = {note.id: note for note in notes}
        hit = resolve(ref, [NamedRef(note.id, note.title) for note in notes])
        if hit.resolved is not None and (hit.reason != "fuzzy" or not change):
            return by_key[hit.resolved.id]
        shown = tuple(by_key[c.id] for c in hit.candidates[:5])
        tainted = any(note.tainted for note in shown)
        if hit.reason == "fuzzy":
            return ToolOutcome(f"Refused: no note is called “{_escape(ref)}”. Did you mean {_titles(shown)}? "
                               "Say it exactly.", tainted=tainted)
        if hit.reason == "multi":
            return ToolOutcome(f"Refused: several notes match “{_escape(ref)}”: {_titles(shown)}. "
                               "Say which one (its id).", tainted=tainted)
        return ToolOutcome(f"Refused: no note matches “{_escape(ref)}”.")
```

**9b.** Replace the whole of `roost/notes/tool_specs.py` with:

```python
"""The notes tool specs and gate kinds (M2 D1; projects hub H12). Argument
names and meanings follow LazyClaw's LazyBrain note skills (save / update /
delete a note, title + markdown content + tags); the descriptions are ours."""

from __future__ import annotations

from roost.llm.types import ToolSpec
from roost.talk.tool_def import ToolDef

_NOTE_REF = {"type": "string", "description": "The note's id, or its title (or a unique part of it)."}
_TAGS = {"type": "array", "items": {"type": "string"}, "description": "Tags without #, e.g. people, home."}
_PROJECT = {"type": "string", "description": "One of the user's projects, by name or id. Name it exactly."}

ADD_NOTE_SPEC = ToolSpec(
    name="add_note",
    description=("Save a note for the user (the user's own notes; every bot uses them): markdown text, an optional "
                 "title (otherwise its first line) and tags. Link other notes with [[Their Title]]; "
                 "#hashtags in the text become tags. Save what the user asks you to note right away."),
    input_schema={"type": "object", "properties": {
        "content": {"type": "string", "description": "The note, in markdown."},
        "title": {"type": "string", "description": "Short title, e.g. 'Ana'."},
        "tags": _TAGS,
        "project": {**_PROJECT, "description": "Optional: the project it belongs to, by name or id."},
    }, "required": ["content"]},
)
FIND_NOTES_SPEC = ToolSpec(
    name="find_notes",
    description=("Search the user's notes: every word must appear in a note's title, tags or text (case and "
                 "accents don't matter). Best matches first; an empty query lists the newest notes. "
                 "Search before you answer from memory."),
    input_schema={"type": "object", "properties": {
        "query": {"type": "string", "description": "Words to look for, e.g. 'orchids'."},
        "tag": {"type": "string", "description": "Only notes with this tag."},
        "project": {**_PROJECT, "description": "Only notes in this project, by name or id."},
    }},
)
READ_NOTE_SPEC = ToolSpec(
    name="read_note",
    description="Read one note in full: its text, tags and the notes it links to.",
    input_schema={"type": "object", "properties": {"note": _NOTE_REF}, "required": ["note"]},
)
APPEND_TO_NOTE_SPEC = ToolSpec(
    name="append_to_note",
    description="Add markdown text to the end of a note. Name the note exactly; if two match, ask the user which.",
    input_schema={"type": "object", "properties": {
        "note": _NOTE_REF, "text": {"type": "string", "description": "What to add."},
    }, "required": ["note", "text"]},
)
UPDATE_NOTE_SPEC = ToolSpec(
    name="update_note",
    description=("Replace a note's title, text or tags, or move it to another project. Name the note exactly; if "
                 "two match, ask the user which."),
    input_schema={"type": "object", "properties": {
        "note": _NOTE_REF, "title": {"type": "string"},
        "content": {"type": "string", "description": "The whole new text, in markdown."}, "tags": _TAGS,
        "project": {**_PROJECT, "description": "The project to move it to; '' takes it out of its project."},
    }, "required": ["note"]},
)
DELETE_NOTE_SPEC = ToolSpec(
    name="delete_note",
    description="Delete a note. Name the note exactly; if two match, ask the user which.",
    input_schema={"type": "object", "properties": {"note": _NOTE_REF}, "required": ["note"]},
)

NOTE_TOOL_DEFS: tuple[ToolDef, ...] = (
    ToolDef(ADD_NOTE_SPEC, "write_create"),
    ToolDef(FIND_NOTES_SPEC, "read"),
    ToolDef(READ_NOTE_SPEC, "read"),
    ToolDef(APPEND_TO_NOTE_SPEC, "write_change"),
    ToolDef(UPDATE_NOTE_SPEC, "write_change"),
    ToolDef(DELETE_NOTE_SPEC, "write_change"),
)
```

- [ ] **Step 10: Documents learn projects, and `set_document_project`**

**10a.** Replace the whole of `roost/documents/tool_args.py` with:

```python
"""The document tools' arguments (M2 D2; projects hub H12) — pydantic at the
tool boundary. Free text is ``ToolText``: a copy of an escaped tool result is
stored plain. ``project`` names one of the user's projects (its name or id)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from roost.constants import (
    MAX_CATEGORY_NAME_LENGTH, MAX_DOC_MARKDOWN_LENGTH, MAX_DOCUMENT_TITLE_LENGTH, MAX_SHEET_CELLS_PER_CALL,
)
from roost.documents.cells import CellEdit, ToolSheetRows
from roost.documents.models import DocumentKind
from roost.records.tool_text import ToolText


class ListDocumentsArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    kind: DocumentKind | None = None
    project: ToolText | None = Field(default=None, max_length=MAX_CATEGORY_NAME_LENGTH)


class DocumentRefArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    document: ToolText = Field(min_length=1, max_length=MAX_DOCUMENT_TITLE_LENGTH)


class CreateDocArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: ToolText = Field(default="", max_length=MAX_DOCUMENT_TITLE_LENGTH)
    markdown: ToolText = Field(min_length=1, max_length=MAX_DOC_MARKDOWN_LENGTH)
    project: ToolText | None = Field(default=None, max_length=MAX_CATEGORY_NAME_LENGTH)


class CreateSheetArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: ToolText = Field(default="", max_length=MAX_DOCUMENT_TITLE_LENGTH)
    rows: ToolSheetRows = Field(min_length=1)
    project: ToolText | None = Field(default=None, max_length=MAX_CATEGORY_NAME_LENGTH)


class AppendToDocArgs(DocumentRefArgs):
    markdown: ToolText = Field(min_length=1, max_length=MAX_DOC_MARKDOWN_LENGTH)


class UpdateSheetCellsArgs(DocumentRefArgs):
    cells: list[CellEdit] = Field(min_length=1, max_length=MAX_SHEET_CELLS_PER_CALL)


class MakePdfArgs(DocumentRefArgs):
    title: ToolText | None = Field(default=None, max_length=MAX_DOCUMENT_TITLE_LENGTH)


class SetDocumentProjectArgs(DocumentRefArgs):
    project: ToolText = Field(max_length=MAX_CATEGORY_NAME_LENGTH)   # '' takes it out of its project
```

**10b.** Replace the whole of `roost/documents/tools.py` with:

```python
"""The document tools over the user's shared documents (M2 D2; projects hub
H12). Pydantic arguments, provenance (bot + taint) on every new document,
escaped results, exact-or-ask names (a near miss never changes a document),
and a document's taint taints the run that reads it — an uploaded PDF is
outside content. A document may belong to one of the user's projects:
``create_doc`` and ``create_sheet`` take one, a PDF made from a doc lands in
the doc's, and ``set_document_project`` moves one without a new revision, so
an open editor still saves."""

from __future__ import annotations

import html
from typing import Any

from pydantic import ValidationError

from roost.constants import DOCUMENT_LIST_LIMIT, MAX_SHEET_CELLS_PER_CALL, MAX_SHEET_COLS, MAX_SHEET_ROWS_PER_CALL
from roost.documents.cells import LAST_CELL
from roost.documents.format import KIND_LABEL, document_line, document_list_text
from roost.documents.models import Document, DocumentMeta
from roost.documents.service import DocumentService
from roost.documents.tool_args import (
    AppendToDocArgs, CreateDocArgs, CreateSheetArgs, DocumentRefArgs, ListDocumentsArgs, MakePdfArgs,
    SetDocumentProjectArgs, UpdateSheetCellsArgs,
)
from roost.money.models import Project
from roost.projects.refs import id_of, project_ref, project_suffix, project_taint
from roost.projects.service import ProjectService
from roost.records.resolver import NamedRef, resolve
from roost.records.revision import RevisionConflict
from roost.talk.domain_tools import RecordContext
from roost.talk.outcome import ToolOutcome

CHANGED_WHILE_WRITING_TEXT = "Refused: that document changed while I was writing. Read it again first."
_ACTIVITY = {
    "list_documents": "checking your documents", "read_document": "reading a document",
    "create_doc": "writing a doc", "create_sheet": "making a sheet", "append_to_doc": "adding to a doc",
    "update_sheet_cells": "updating a sheet", "delete_document": "deleting a document",
    "make_pdf_from_doc": "making a PDF", "set_document_project": "filing a document in a project",
}
_NEEDS = {
    "list_documents": "an optional kind (doc, sheet or pdf) and project",
    "read_document": "the document (its id or title)",
    "create_doc": "a title and markdown text (and optionally a project)",
    "create_sheet": f"rows (1 to {MAX_SHEET_ROWS_PER_CALL}, each at most {MAX_SHEET_COLS} cells) and a title",
    "append_to_doc": "the doc (its id or title) and the markdown to add",
    "update_sheet_cells": f"the sheet (its id or title) and 1 to {MAX_SHEET_CELLS_PER_CALL} cells from A1 to "
                          f"{LAST_CELL}, like {{\"cell\": \"B3\", \"value\": 35}}",
    "delete_document": "the document (its id or title)",
    "make_pdf_from_doc": "the doc (its id or title)",
    "set_document_project": "the document (its id or title) and the project (its name or id; '' takes it out)",
}


def _escape(text: str) -> str:
    return html.escape(text, quote=True)


def _title(raw: str | None, fallback: str) -> str:
    return (raw or "").strip() or fallback


def _match(metas: tuple[DocumentMeta, ...], ref: str, change: bool) -> DocumentMeta | ToolOutcome:
    """Id, exact title or a unique part of it (harvested resolver); a lone near
    miss may be read but never changed. A refusal that lists titles carries
    those documents' taint (M1 D3)."""
    by_id = next((meta for meta in metas if meta.id == ref.strip()), None)
    if by_id is not None:
        return by_id
    by_key = {meta.id: meta for meta in metas}
    hit = resolve(ref, [NamedRef(meta.id, meta.title) for meta in metas])
    if hit.resolved is not None and (hit.reason != "fuzzy" or not change):
        return by_key[hit.resolved.id]
    shown = tuple(by_key[c.id] for c in hit.candidates[:5])
    listed, tainted = "; ".join(document_line(meta) for meta in shown), any(meta.tainted for meta in shown)
    if hit.reason == "fuzzy":
        return ToolOutcome(f"Refused: no document is called “{_escape(ref)}”. Did you mean {listed}? Say it exactly.",
                           tainted=tainted)
    if hit.reason == "multi":
        return ToolOutcome(f"Refused: several documents match “{_escape(ref)}”: {listed}. Say which one (its id).",
                           tainted=tainted)
    return ToolOutcome(f"Refused: no document matches “{_escape(ref)}”.")


def _saved(found: Document, meta: DocumentMeta | None, verb: str) -> ToolOutcome:
    if meta is None:
        return ToolOutcome("Refused: that document is gone.", tainted=found.meta.tainted)
    return ToolOutcome(f"{verb} “{_escape(found.meta.title)}” (revision {meta.revision}).", tainted=found.meta.tainted)


def _filed(meta: DocumentMeta, project: Project | None) -> str:
    title = _escape(meta.title)
    if project is None:
        return f"“{title}” is in no project now."
    return f"Moved “{title}” to the project “{_escape(project.name)}”."


class DocumentTools:
    names = frozenset(_ACTIVITY)

    def __init__(self, service: DocumentService, projects: ProjectService) -> None:
        self._service = service
        self._projects = projects

    def activity(self, name: str) -> str:
        return _ACTIVITY[name]

    async def run(self, name: str, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        handlers = {
            "list_documents": self._list, "read_document": self._read, "create_doc": self._create_doc,
            "create_sheet": self._create_sheet, "append_to_doc": self._append, "update_sheet_cells": self._cells,
            "delete_document": self._delete, "make_pdf_from_doc": self._make_pdf,
            "set_document_project": self._set_project,
        }
        try:
            return await handlers[name](arguments, ctx)
        except ValidationError:
            return ToolOutcome(f"Refused: {name} needs {_NEEDS[name]}.")
        except RevisionConflict:
            return ToolOutcome(CHANGED_WHILE_WRITING_TEXT)
        except ValueError as exc:   # a damaged blob, a bad A1 reference, PdfError, no such project
            return ToolOutcome(f"Refused: {_escape(str(exc))}")

    async def _list(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = ListDocumentsArgs.model_validate(arguments)
        project = await project_ref(self._projects, ctx.user_id, args.project, change=False)
        if isinstance(project, ToolOutcome):
            return project
        metas = await self._service.list(ctx.user_id, args.kind, project_id=id_of(project))
        shown = metas[:DOCUMENT_LIST_LIMIT]
        return ToolOutcome(document_list_text(shown, len(metas)), tainted=any(meta.tainted for meta in shown))

    async def _read(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        found = await self._find(ctx.user_id, DocumentRefArgs.model_validate(arguments).document, change=False)
        if isinstance(found, ToolOutcome):
            return found
        text = await self._service.text(found)
        return ToolOutcome(f"{document_line(found.meta)} revision={found.meta.revision}\n\n{_escape(text)}",
                           tainted=found.meta.tainted)

    async def _create_doc(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = CreateDocArgs.model_validate(arguments)
        project = await project_ref(self._projects, ctx.user_id, args.project, change=True)
        if isinstance(project, ToolOutcome):
            return project
        meta = await self._service.create_doc(ctx.user_id, _title(args.title, "Untitled doc"), args.markdown,
                                              created_by_bot=ctx.bot_id, tainted=ctx.tainted,
                                              project_id=id_of(project))
        return ToolOutcome(f"Created doc: {document_line(meta)}. It's on the Board's Documents tab."
                           f"{project_suffix(project)}", created=True, tainted=project_taint(project))

    async def _create_sheet(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = CreateSheetArgs.model_validate(arguments)
        project = await project_ref(self._projects, ctx.user_id, args.project, change=True)
        if isinstance(project, ToolOutcome):
            return project
        meta = await self._service.create_sheet(ctx.user_id, _title(args.title, "Untitled sheet"), args.rows,
                                                created_by_bot=ctx.bot_id, tainted=ctx.tainted,
                                                project_id=id_of(project))
        return ToolOutcome(f"Created sheet: {document_line(meta)} with {len(args.rows)} rows."
                           f"{project_suffix(project)}", created=True, tainted=project_taint(project))

    async def _append(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = AppendToDocArgs.model_validate(arguments)
        found = await self._find_kind(ctx.user_id, args.document, "doc")
        if isinstance(found, ToolOutcome):
            return found
        return _saved(found, await self._service.append_markdown(ctx.user_id, found, args.markdown), "Added to")

    async def _cells(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = UpdateSheetCellsArgs.model_validate(arguments)
        found = await self._find_kind(ctx.user_id, args.document, "sheet")
        if isinstance(found, ToolOutcome):
            return found
        edits = [{"cell": edit.cell.upper(), "value": edit.value, "formula": edit.formula} for edit in args.cells]
        return _saved(found, await self._service.set_cells(ctx.user_id, found, edits), f"Updated {len(edits)} cells in")

    async def _delete(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        found = await self._find(ctx.user_id, DocumentRefArgs.model_validate(arguments).document, change=True)
        if isinstance(found, ToolOutcome):
            return found
        await self._service.delete(ctx.user_id, found.meta.id)
        return ToolOutcome(f"Deleted: “{_escape(found.meta.title)}”.", tainted=found.meta.tainted)

    async def _make_pdf(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = MakePdfArgs.model_validate(arguments)
        found = await self._find_kind(ctx.user_id, args.document, "doc")
        if isinstance(found, ToolOutcome):
            return found
        meta = await self._service.make_pdf(ctx.user_id, found, _title(args.title, found.meta.title),
                                            created_by_bot=ctx.bot_id, tainted=ctx.tainted)
        return ToolOutcome(f"Created PDF: {document_line(meta)}", created=True, tainted=found.meta.tainted)

    async def _set_project(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        """H12: link or unlink ('' ) without a new revision (``DocumentService.set_project``)."""
        args = SetDocumentProjectArgs.model_validate(arguments)
        match = _match(await self._service.list(ctx.user_id), args.document, change=True)
        if isinstance(match, ToolOutcome):
            return match
        project = await project_ref(self._projects, ctx.user_id, args.project, change=True)
        if isinstance(project, ToolOutcome):
            return project
        meta = await self._service.set_project(ctx.user_id, match.id, id_of(project))
        if meta is None:
            return ToolOutcome("Refused: that document is gone.", tainted=match.tainted)
        return ToolOutcome(_filed(meta, project), tainted=match.tainted or project_taint(project))

    async def _find_kind(self, user_id: str, ref: str, kind: str) -> Document | ToolOutcome:
        found = await self._find(user_id, ref, change=True)
        if isinstance(found, ToolOutcome) or found.meta.kind == kind:
            return found
        return ToolOutcome(f"Refused: “{_escape(found.meta.title)}” is a {KIND_LABEL[found.meta.kind]}, "
                           f"not a {KIND_LABEL[kind]}.", tainted=found.meta.tainted)

    async def _find(self, user_id: str, ref: str, *, change: bool) -> Document | ToolOutcome:
        match = _match(await self._service.list(user_id), ref, change)
        if isinstance(match, ToolOutcome):
            return match
        document = await self._service.get(user_id, match.id)
        return document if document is not None else ToolOutcome("Refused: that document is gone.")
```

**10c.** Replace the whole of `roost/documents/tool_specs.py` with:

```python
"""The documents tool specs and gate kinds (M2 D2; projects hub H12). Tool
names and caps follow LazyClaw's docs / sheets / pdf skills; the descriptions
are ours."""

from __future__ import annotations

from roost.llm.types import ToolSpec
from roost.talk.tool_def import ToolDef

_DOCUMENT_REF = {"type": "string", "description": "The document's id, or its title (or a unique part of it)."}
_TITLE = {"type": "string", "description": "Short title, e.g. 'My tasks'."}
_MARKDOWN = {"type": "string", "description": ("Markdown: # headings, - bullets, 1. numbered items, **bold**, "
                                               "*italic*, [links](https://…).")}
_CELL_VALUE = {"type": ["string", "number", "boolean", "null"]}
_PROJECT = {"type": "string", "description": "Optional: one of the user's projects, by name or id. Name it exactly."}

LIST_DOCUMENTS_SPEC = ToolSpec(
    name="list_documents",
    description="List the user's documents (docs, sheets and PDFs; every bot uses them), newest first.",
    input_schema={"type": "object", "properties": {
        "kind": {"type": "string", "enum": ["doc", "sheet", "pdf"]},
        "project": {**_PROJECT, "description": "Only documents in this project, by name or id."},
    }},
)
READ_DOCUMENT_SPEC = ToolSpec(
    name="read_document",
    description=("Read a document: a doc as markdown, a sheet as a table (its first 30 rows and 10 columns), "
                 "a PDF as its text. Long ones are cut."),
    input_schema={"type": "object", "properties": {"document": _DOCUMENT_REF}, "required": ["document"]},
)
CREATE_DOC_SPEC = ToolSpec(
    name="create_doc",
    description="Create a doc from markdown. The user opens and edits it on the Board's Documents tab. "
                "When asked to save something in a document, gather it with your other tools first, then write it.",
    input_schema={"type": "object", "properties": {"title": _TITLE, "markdown": _MARKDOWN, "project": _PROJECT},
                  "required": ["title", "markdown"]},
)
CREATE_SHEET_SPEC = ToolSpec(
    name="create_sheet",
    description=("Create a spreadsheet from rows, starting at A1; the first row is usually the header. Numbers "
                 "stay numbers. At most 500 rows of 26 cells."),
    input_schema={"type": "object", "properties": {
        "title": _TITLE,
        "rows": {"type": "array", "items": {"type": "array", "items": _CELL_VALUE}},
        "project": _PROJECT,
    }, "required": ["title", "rows"]},
)
APPEND_TO_DOC_SPEC = ToolSpec(
    name="append_to_doc",
    description="Add markdown to the end of a doc. Name the document exactly; if two match, ask the user which.",
    input_schema={"type": "object", "properties": {"document": _DOCUMENT_REF, "markdown": _MARKDOWN},
                  "required": ["document", "markdown"]},
)
UPDATE_SHEET_CELLS_SPEC = ToolSpec(
    name="update_sheet_cells",
    description=("Set cells in a sheet by A1 reference: a value, or a formula like =SUM(B2:B9) (the sheet "
                 "computes it when opened). A cell with neither is cleared. "
                 "Name the document exactly; if two match, ask the user which."),
    input_schema={"type": "object", "properties": {
        "document": _DOCUMENT_REF,
        "cells": {"type": "array", "items": {"type": "object", "properties": {
            "cell": {"type": "string", "description": "A1 reference, e.g. B3."},
            "value": _CELL_VALUE, "formula": {"type": "string"},
        }, "required": ["cell"]}},
    }, "required": ["document", "cells"]},
)
DELETE_DOCUMENT_SPEC = ToolSpec(
    name="delete_document",
    description="Delete a document. Name the document exactly; if two match, ask the user which.",
    input_schema={"type": "object", "properties": {"document": _DOCUMENT_REF}, "required": ["document"]},
)
MAKE_PDF_FROM_DOC_SPEC = ToolSpec(
    name="make_pdf_from_doc",
    description="Make a new PDF from a doc's text (the doc stays as it is). The PDF goes in the doc's project.",
    input_schema={"type": "object", "properties": {
        "document": _DOCUMENT_REF, "title": {"type": "string", "description": "The PDF's title (default: the doc's)."},
    }, "required": ["document"]},
)
SET_DOCUMENT_PROJECT_SPEC = ToolSpec(
    name="set_document_project",
    description=("Put a document (a doc, sheet or PDF) in one of the user's projects, or take it out with project "
                 "''. Its text is not changed. Name the document and the project exactly; if two match, ask the "
                 "user which."),
    input_schema={"type": "object", "properties": {
        "document": _DOCUMENT_REF,
        "project": {"type": "string", "description": "The project's name or id; '' takes the document out of its "
                                                     "project."},
    }, "required": ["document", "project"]},
)

DOCUMENT_TOOL_DEFS: tuple[ToolDef, ...] = (
    ToolDef(LIST_DOCUMENTS_SPEC, "read"),
    ToolDef(READ_DOCUMENT_SPEC, "read"),
    ToolDef(CREATE_DOC_SPEC, "write_create"),
    ToolDef(CREATE_SHEET_SPEC, "write_create"),
    ToolDef(APPEND_TO_DOC_SPEC, "write_change"),
    ToolDef(UPDATE_SHEET_CELLS_SPEC, "write_change"),
    ToolDef(DELETE_DOCUMENT_SPEC, "write_change"),
    ToolDef(MAKE_PDF_FROM_DOC_SPEC, "write_create"),
    ToolDef(SET_DOCUMENT_PROJECT_SPEC, "write_change"),
)
```

- [ ] **Step 11: Wire the handlers and tell every bot**

**11a.** `roost/talk/domain_tools.py` **(after Task 1, which renamed the store in two lines here)**. Find:

```python
def build_domain_tools(config: Config, events: EventHub) -> DomainTools:
    """Every domain role's tools, wired to the user's shared stores."""
    from roost.documents.service import DocumentService
    from roost.documents.store import DocumentStore
    from roost.documents.tools import DocumentTools
    from roost.money.expense_store import ExpenseStore
    from roost.money.project_store import ProjectStore
    from roost.money.service import MoneyService
    from roost.money.tools import MoneyTools
    from roost.notes.service import NoteService
    from roost.notes.store import NoteStore
    from roost.notes.tools import NoteTools
    from roost.tasks.service import TaskService   # local: roost.tasks imports this module
    from roost.tasks.store import TaskStore
    from roost.tasks.tools import TaskTools

    money = MoneyService(ProjectStore(config), ExpenseStore(config), events)
    return DomainTools((TaskTools(TaskService(TaskStore(config), events)), MoneyTools(money),
                        NoteTools(NoteService(NoteStore(config), events)),
                        DocumentTools(DocumentService(DocumentStore(config), events))))
```

Replace with:

```python
def build_domain_tools(config: Config, events: EventHub) -> DomainTools:
    """Every domain's tools (tasks, money, notes, documents and projects), wired
    to the user's shared stores. The stores hold no state, so one of each serves
    every service, and one ``ProjectService`` answers every tool that names a
    project (projects hub H3)."""
    from roost.bots.store import BotStore
    from roost.documents.service import DocumentService
    from roost.documents.store import DocumentStore
    from roost.documents.tools import DocumentTools
    from roost.money.expense_store import ExpenseStore
    from roost.money.project_store import ProjectStore
    from roost.money.service import MoneyService
    from roost.money.tools import MoneyTools
    from roost.notes.service import NoteService
    from roost.notes.store import NoteStore
    from roost.notes.tools import NoteTools
    from roost.projects.service import ProjectService
    from roost.projects.tools import ProjectTools
    from roost.tasks.service import TaskService   # local: roost.tasks imports this module
    from roost.tasks.store import TaskStore
    from roost.tasks.tools import TaskTools

    bots, expenses, notes = BotStore(config), ExpenseStore(config), NoteStore(config)
    project_store, task_store, documents = ProjectStore(config), TaskStore(config), DocumentStore(config)
    projects = ProjectService(project_store, expenses, task_store, notes, documents, bots, events)
    tasks = TaskService(task_store, events)
    return DomainTools((
        TaskTools(tasks, projects),
        MoneyTools(MoneyService(project_store, expenses, events), projects, tasks),
        NoteTools(NoteService(notes, events), projects),
        DocumentTools(DocumentService(documents, events), projects),
        ProjectTools(projects, bots, expenses),
    ))
```

**11b.** `roost/talk/instructions.py` **(after the stuck flow; the stuck flow adds `_STUCK_TEXT` above this block and leaves it as it is)**. Find:

```python
# S1 D2: the user's records belong to the user and every bot uses all of them,
# which cures "I'm isolated".
_RECORDS_TEXT = (
    "The user's tasks, money, notes and documents belong to the user, and every bot uses the same ones: you can "
    "read and change all of them with your tools, so never say you cannot see them or that you are isolated."
)
```

Replace with:

```python
# S1 D2: the user's records belong to the user and every bot uses all of them,
# which cures "I'm isolated". Projects hub: a project holds the others (P1), and
# its name is exact-or-ask everywhere but log_expense (H3). Never the word "role".
_RECORDS_TEXT = (
    "The user's projects, tasks, money, notes and documents belong to the user, and every bot uses the same ones: "
    "you can read and change all of them with your tools, so never say you cannot see them or that you are "
    "isolated. A project holds its own tasks, money (a total budget, a monthly limit, expenses and top-ups), notes "
    "and documents: pass project to those tools to file or find things in it, and call list_projects or get_project "
    "to see how it stands. Name a project exactly; only log_expense makes a new project from a new name, and every "
    "other tool asks you to call create_project first."
)
```

- [ ] **Step 12: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_project_tools.py tests/test_money_tools.py tests/test_task_tools.py tests/test_note_tools.py tests/test_document_tools.py tests/test_every_bot_tools.py tests/test_instructions.py -q`
Expected: PASS. `tests/test_project_tools.py` has 12 tests, including `test_a_near_miss_project_name_never_changes_anything` and `test_a_tainted_run_cannot_change_projects_or_their_money`; every older test in the six other files still passes (Task 1's `test_log_expense_still_accepts_the_old_category_argument` and `test_every_money_tool_takes_project_and_still_category` keep the `category` alias; `test_the_old_role_rules_live_on_in_the_tool_descriptions` still finds "if two match, ask" and no " role").

The related tests must stay green (the catalog grew by eight tools, every handler's constructor changed, and the money service's `set_budget` and `ExpenseEntry` changed):

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_gate.py tests/test_tool_runner_taint.py tests/test_stuck_tool_runner.py tests/test_computer_control_runs.py tests/test_tool_text.py tests/test_profile_api.py tests/test_main_bot.py tests/test_project_service.py tests/test_notes_docs_projects.py tests/test_task_projects.py tests/test_money_store.py tests/test_money_api.py tests/test_money_summary.py tests/test_vocabulary.py tests/test_create_bot.py tests/test_handoff.py -q`
Expected: PASS. (`test_gate.py`'s `test_every_allowed_tool_decides_do` now runs for the eight new tools too; `test_computer_control_runs.py` finds no "control" in any tool name.)

Check the new modules' coverage:

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_project_tools.py tests/test_money_tools.py tests/test_task_tools.py tests/test_note_tools.py tests/test_document_tools.py --cov=roost.projects.tools --cov=roost.projects.refs --cov=roost.projects.format --cov=roost.projects.tool_args --cov=roost.projects.tool_specs --cov=roost.money.expense_links --cov=roost.money.tool_args --cov=roost.money.tools --cov=roost.money.service --cov-report=term-missing -q`
Expected: PASS, each module at 80% or more. The lines left uncovered are the defensive ones (`NAME_THE_PROJECT_TEXT` for a blank project name, `GONE_TEXT` for a project deleted mid-call, `NO_STEPS_TEXT`, the "several tasks match" refusal, the older-top-ups `…and N more` line) and, in `roost/money/service.py`, `keep_expense` and `made_by`, which only the HTTP tests reach, and a delete that the gate refused in every tool test here.

Then the whole suite with coverage:

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest -q --cov=roost --cov-fail-under=80`
Expected: PASS.

- [ ] **Step 13: Commit**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && git add roost/constants.py roost/money/amounts.py roost/money/service.py roost/money/tool_args.py roost/money/expense_links.py roost/money/tools.py roost/money/tool_specs.py roost/projects/tool_specs.py roost/projects/tool_args.py roost/projects/refs.py roost/projects/format.py roost/projects/tools.py roost/tasks/tools.py roost/tasks/tool_specs.py roost/notes/tools.py roost/notes/tool_specs.py roost/documents/tool_args.py roost/documents/tools.py roost/documents/tool_specs.py roost/talk/domain_tools.py roost/talk/tool_catalog.py roost/talk/instructions.py tests/test_project_tools.py tests/test_money_tools.py tests/test_task_tools.py tests/test_note_tools.py tests/test_document_tools.py tests/test_every_bot_tools.py tests/test_instructions.py && git status --short && git commit -m "feat: bots learn projects: project tools, and a project on every record tool"
```

`git status --short` must list nothing from this task as modified or untracked before the commit. The message has no Co-Authored-By line and no AI attribution.

---

### Task 8: HTTP: /api/projects and the new record routes

This task puts design P1, P2, P3, P5, P6 and P7 on the wire, following §5 H2, H4, H5, H6, H7, H8, H9, H10, H11, H12, H14 and H15. Every route goes through the same services the bots' tools use (Tasks 4–6), so every change publishes its frame and every open tab refreshes. The rules:
- **`/api/projects`** (new `roost/gateway/routes/projects.py`, `projects_router`):
  - The list hides General (H2) and shows archived projects only with `?include_archived=true`.
  - A project's page is `ProjectDetailOut`. Create, change and delete are on the same router, and so are the top-ups (`/api/projects/{id}/topups`, `/api/topups/{id}`, `/api/topups/{id}/undo`).
  - The total budget (P3, H5) has its own route, `PUT /api/projects/{id}/budget`, with the body `{"amount": str | null}` (`BudgetIn`, `extra="forbid"`). The amount goes through `parse_amount`, and `null` clears the total. It answers `ProjectOut`. Task 6's `ProjectService.set_budget` writes the "Budget set" row and publishes `money_changed` `budget_set`. `PATCH` still refuses `budget`, so every change to the total leaves its history row. A bad amount or General is 422, and another user's or an unknown project is 404.
  - Every amount goes out as a string, and each budget is a `BudgetLineOut` carrying its bar's `used_percent` and `tone` (H8). The web never adds amounts.
  - Status codes:
    - A rename onto a name in use is **409** `"A project with that name exists."`. On create, the table says 422, so a clash there is 422.
    - Any other broken rule is **422** with the rule's plain sentence. That covers General (H2), the lead bot (H15), the currency lock (H7) and a bad amount.
    - Changing or undoing a top-up that is already undone is **409** (H4): Task 2's `TopUpUndone`. Its other top-up refusals (a cleared total budget, a budget below 0) are broken rules, so **422**.
    - Another user's project or top-up is **404**, never the object.
- **Money:** `PUT /api/money/expenses/{id}/star` `{starred}` and `PUT …/void` `{void}` (H6). `ExpenseIn` gains `project_id`, and `currency` may be left out. An expense named by id lands in exactly that project (Task 7's `log_expense(..., project=)`). Named by id or by name, an expense with no currency takes its project's currency (H7), and an archived project refuses it (H3, Task 7's `ARCHIVED_TEXT`, a 422 because `log_expense` now runs inside the route's `try`).
- **Tasks:**
  - `POST /api/tasks/{id}/fail` (H11) and `GET /api/tasks?status=&project_id=`.
  - `TaskIn` and `TaskPatchIn` gain `project_id` and the budget slice `allocated_budget`. The project page sets a task's slice (§3), and a slice needs a project (H11).
  - `update` now runs inside the route's `try` (Task 4's note), so the store's "No such project." is a 422, not a 500.
- **Notes and documents (H12):**
  - `PUT /api/notes/{id}/project` and `PUT /api/documents/{id}/project` take the body `{project_id: str | null}` (`ProjectLinkIn`). The link never bumps the revision.
  - `?project_id=` filters both lists, and `NoteIn` and `DocumentCreateIn` gain `project_id`.
  - `note_summary_out` and `document_out` carry `project_id`.
  - Linking to a project that isn't the user's is 422 `"No such project."`, raised by the stores (Tasks 4 and 5).
- `app.state.projects` holds the `ProjectService`.

**Files:**
- Create:
  - `roost/gateway/routes/projects.py`: `projects_router`, `ProjectIn`, `ProjectPatchIn`, `BudgetIn`, `TopupIn`, `TopupEditIn`, `ProjectLinkIn`, `project_out`, `project_detail_out`, `topup_out`, `progress_out`, and the ten routes (`PUT /api/projects/{id}/budget` among them).
  - `tests/test_projects_api.py`
- Modify:
  - `roost/gateway/app.py`:
    - two imports;
    - `app.state.projects = ProjectService(...)`;
    - `app.include_router(projects_router)`.
  - `roost/gateway/routes/money.py`:
    - `ExpenseIn.project_id`, with `currency` now optional;
    - `StarIn` and `VoidIn`;
    - `add_expense` hands a project named by id to `log_expense`, all inside its `try`;
    - the star and void routes.
  - `roost/gateway/routes/tasks.py` (whole file):
    - `project_id` and `allocated_budget` on `TaskIn` and `TaskPatchIn`;
    - `?project_id=`;
    - `POST /{id}/fail`.
  - `roost/gateway/routes/notes.py` (whole file):
    - `NoteIn.project_id` and `?project_id=`;
    - `PUT /{id}/project`;
    - the 409 body is shared by `_conflict`.
  - `roost/gateway/routes/documents.py`:
    - `DocumentCreateIn.project_id` and `?project_id=`;
    - `create_document` inside `try`;
    - `PUT /{id}/project`.
  - `roost/notes/format.py`: `note_summary_out` gains `project_id`.
  - `roost/documents/format.py`: `document_out` gains `project_id`.
- Test:
  - `tests/test_projects_api.py` (new, 14 tests)
  - `tests/test_money_api.py` (3 tests appended)
  - `tests/test_tasks_api.py` (3 tests appended)
  - `tests/test_notes_api.py` (3 tests appended)
  - `tests/test_documents_api.py` (2 tests appended)

**Interfaces:**
- Consumes:
  - **Task 1:**
    - `ProjectStore(config)` (`roost/money/project_store.py`) and `Project` (`roost/money/models.py`).
    - `MoneyService.projects(user_id) -> tuple[Project, ...]`.
    - `GENERAL_PROJECT_NAME`.
    - Task 1's `roost/gateway/routes/money.py` (`ExpenseIn.project`).
  - **Task 2:**
    - `ProjectDraft(name, currency, budget, monthly_budget, color, start_date, due_date, lead_bot_id)` and `TopUp` (`id`, `amount`, `currency`, `source`, `kind`, `topup_id`, `undone`, `created_at`).
    - The texts `COLOR_TEXT` and `DATE_TEXT` (`roost/money/models.py`), so a route refusal and a store refusal read the same.
    - Constants `PROJECT_COLORS`, `DEFAULT_PROJECT_COLOR`, `PROJECT_STATUSES` and `TOPUP_SOURCE_MAX_CHARS`.
    - `ProjectStore.create` and `ProjectStore.update` refuse a name in use with `ValueError(NAME_TAKEN_TEXT)`, `NAME_TAKEN_TEXT = "A project with that name exists."` (`roost/money/project_store.py`).
    - `ProjectStore.edit_topup` and `ProjectStore.undo_topup` return `None` for a top-up that isn't the user's. For a top-up already undone they raise **`TopUpUndone(ValueError)`** (`roost/money/topup_store.py`, through `_credit_and_project`): the 409. A cleared total budget or one that would go below 0 raises a plain `ValueError` (`BUDGET_CLEARED_TEXT`, `BELOW_ZERO_TEXT`): a 422. So the routes catch `TopUpUndone` first. Step 1 checks this.
    - `ProjectStore.set_budget(user_id, project_id, None, *, created_by_bot, tainted)` clears the total budget (tests only).
  - **Task 3:**
    - `EXPENSE_POSTED`, `EXPENSE_VOID` and `ExpensePatch({"is_favorite": …})` / `ExpensePatch({"status": …})` (`roost/money/models.py`).
    - `budget_line_out`, `amounts_out` and `expense_row` (`roost/money/summary.py`).
    - `ProjectNumbers` (`total`, `month`, `other_currencies`, `starred_total`), `Progress` (`done`, `failed`, `total`) and `TaskMoney` (`planned`, `spent`, `left`) (`roost/projects/numbers.py`).
    - Expense rows carry `status` and `is_favorite`.
  - **Task 4:**
    - `TaskDraft(..., project_id=, allocated_budget=)`, and `PATCHABLE_FIELDS` ⊇ {`project_id`, `allocated_budget`}.
    - `TaskService.list(user_id, *, status, project_id=None)` and `TaskService.fail(user_id, task_id) -> Completion | None`.
    - `TaskStore` refusals "No such project." and "A budget slice needs a project.".
    - `task_out` carries `project_id` and `allocated_budget`.
    - `NO_SUCH_PROJECT_TEXT` (`roost/records/project_link.py`).
  - **Task 5:**
    - `Note.project_id` and `DocumentMeta.project_id`, and `new_note_draft(title, content, tags, *, project_id=None)`.
    - `NoteService.search(user_id, query, *, tag=None, project_id=None)` and `NoteService.set_project(user_id, note_id, project_id) -> Note | None`, which may raise `RevisionConflict`.
    - `DocumentService.list(user_id, kind=None, *, project_id=None)`, `DocumentService.set_project(user_id, document_id, project_id) -> DocumentMeta | None`, and `create_doc(..., project_id=)` / `create_sheet(..., project_id=)`.
  - **Task 6:**
    - `ProjectService(projects, expenses, tasks, notes, documents, bots, events)` with `list`, `detail`, `create`, `update`, `delete`, `set_budget`, `add_topup`, `edit_topup`, `undo_topup` and `topups`, and `ProjectDetail` with its *extra* `task_money` (`roost/projects/service.py`).
    - `ProjectService.set_budget(user_id, project_id, amount: Decimal | None) -> Project | None`: `None` clears the total budget (H5), General is a `ValueError(GENERAL_FIXED_TEXT)`, `parse_amount` refuses a bad amount, and it publishes `money_changed` `budget_set` with the project's id.
    - The texts `STATUS_TEXT`, `GENERAL_FIXED_TEXT`, `GENERAL_NAME_TEXT` and `LEAD_BOT_TEXT`.
  - **Task 7** (none of this task's files are in Task 7's list, but these are):
    - `roost/constants.py`: `MAX_RECORD_ID_LENGTH = 64` (Finance section). Task 7 adds it, so this task does **not** edit `roost/constants.py`.
    - `roost/money/service.py` (replaced whole by Task 7): `ExpenseEntry(amount, spent_at, project=None, note=None, vendor=None, currency=None, task_id=None, step_id=None, starred=False)`, where `currency=None` means the project's currency (H7); `MoneyService.log_expense(user_id, entry, *, created_by_bot=None, tainted=False, project: Project | None = None) -> tuple[Expense, Project]`, which logs into `project` when given and raises `ValueError(ARCHIVED_TEXT)` for an archived one; `ARCHIVED_TEXT = "“{name}” is archived; unarchive it first."`; `MoneyService.update_expense(user_id, expense_id, patch) -> Expense | None`.
    - Task 7's note for this task: `POST /api/money/expenses` must call `log_expense` inside the route's `try`.
  - **The finished stuck flow:** `roost/gateway/app.py` with `stuck_router`, `StuckService` and `make_main_browser`. This task's `app.py` anchors are lines the stuck flow does not touch.
  - **Existing code:**
    - `CurrentUser` and `RequireOrigin`;
    - `parse_amount` and `amount_text`;
    - `RevisionConflict`;
    - `task_out`, `note_out`, `note_summary_out`, `document_out` and `document_detail_out`;
    - `EventHub.since`;
    - `make_bot` (`tests/team_helpers.py`).
- Produces (Task 9's web client and Task 10's E2E rely on these):
  - **Python:**
    - `roost.gateway.routes.projects`: `projects_router`, `ProjectLinkIn`, `BudgetIn`, `project_out(project, numbers, progress)`, `project_detail_out(detail)`, `topup_out(topup)`, `progress_out(progress)` and `task_money_out(money)`.
    - The texts `PROJECT_NOT_FOUND_TEXT = "Project not found"`, `TOPUP_NOT_FOUND_TEXT = "Top-up not found"` and `NAME_IN_USE_TEXT` (Task 2's `NAME_TAKEN_TEXT`, not a second copy of the sentence).
    - `app.state.projects`.
  - **Wire:**
    - `ProjectOut` keys: `id, name, color, currency, status, start_date, due_date, lead_bot_id, total, month, other_currencies, starred_total, progress {done, failed, total}, tainted`.
      - `total` and `month` are `BudgetLineOut` `{budget, spent, remaining, used_percent, tone}`.
      - Amounts are strings.
    - `ProjectDetailOut` = `ProjectOut` + `tasks: TaskOut[]`, `expenses: ExpenseOut[]`, `notes: NoteSummaryOut[]`, `documents: DocumentOut[]`, `topups: TopupOut[]`, `lead_bot_name` and the *extra* `task_money: Record<task id, TaskMoneyOut {planned: string | null; spent: string; left: string | null}>` (Task 6's `ProjectDetail.task_money`: design §2's planned / spent / left, which the contract's table leaves out; reported as a contract addition).
      - `expenses`, `notes` and `documents` are the latest `PROJECT_PAGE_ITEMS`.
      - `tainted` covers everything the page shows.
    - `TopupOut` keys: `id, amount, currency, source, kind ("credit" | "edit"), topup_id, undone, created_at`.
    - `ExpenseIn` gains `project_id`. It is refused together with `project`, and `currency` may be left out (then the project's currency, H7).
    - `TaskIn` and `TaskPatchIn` gain `project_id` and `allocated_budget` (an amount string, or `null` to clear on PATCH).
    - `NoteIn` and `DocumentCreateIn` gain `project_id`.
    - `NoteSummaryOut` and `DocumentOut` gain `project_id`.
    - `PUT /api/notes/{id}/project` answers the full note (`note_out`, as every note route does).
    - `PUT /api/documents/{id}/project` answers `DocumentOut`.
  - **Routes:** exactly the contract's table.
    - `POST /api/tasks/{id}/fail` gives 404 `"No open task with that id"`, like `/complete`.
    - `PUT /api/notes/{id}/project` gives 409 with the current note when two saves land during the link (Task 5).

- [ ] **Step 1: Path guard**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

Then confirm that the stuck flow and Tasks 1–7 have landed and this task has not:

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && grep -n "include_router(stuck_router)" roost/gateway/app.py && grep -n "^class ProjectService\|^class ProjectDetail\|^GENERAL_FIXED_TEXT\|^GENERAL_NAME_TEXT\|^from roost.money.models import LEAD_BOT_TEXT, STATUS_TEXT\|    async def set_budget" roost/projects/service.py && grep -n "^def budget_line_out\|^def amounts_out\|^def expense_row" roost/money/summary.py && grep -n "^EXPENSE_POSTED\|^EXPENSE_VOID\|^class ProjectDraft\|^class TopUp\|^COLOR_TEXT\|^DATE_TEXT" roost/money/models.py && grep -n "^NO_SUCH_PROJECT_TEXT" roost/records/project_link.py && grep -n "async def fail\|project_id: str | None = None) -> tuple" roost/tasks/service.py && grep -n "async def set_project" roost/notes/service.py roost/documents/service.py && grep -n "^PROJECT_COLORS\|^PROJECT_STATUSES\|^DEFAULT_PROJECT_COLOR\|^TOPUP_SOURCE_MAX_CHARS\|^MAX_RECORD_ID_LENGTH = 64" roost/constants.py && grep -n "^ARCHIVED_TEXT\|tainted: bool = False, project: Project | None = None)" roost/money/service.py && grep -n '"project_id": task.project_id' roost/tasks/format.py && test ! -e roost/gateway/routes/projects.py && echo "no projects routes yet"`

Expected:
- the `stuck_router` include;
- six lines from `service.py` (`LEAD_BOT_TEXT` and `STATUS_TEXT` are Task 2's, imported there and re-exported, on one `from roost.money.models import` line; `set_budget` is the total budget's method);
- three from `summary.py`;
- six from `models.py`;
- `NO_SUCH_PROJECT_TEXT`;
- `fail` and the `list` signature with `project_id`;
- both `set_project` lines;
- five constants, `MAX_RECORD_ID_LENGTH = 64` among them (Task 7);
- `ARCHIVED_TEXT` and `log_expense`'s `project` keyword (Task 7's `money/service.py`);
- the `task_out` line;
- `no projects routes yet`.

If anything is missing, stop: the stuck flow or Tasks 1–7 come first. If Task 2 put `ProjectDraft` or `TopUp` in another module, import them from there in Step 4. The names stay the same.

Then confirm that the files this task replaces whole are still as they were at `4aecbc3`. Neither the stuck flow nor Tasks 1–7 edit them:

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git diff --quiet 4aecbc3 -- roost/gateway/routes/tasks.py roost/gateway/routes/notes.py && echo "tasks and notes routes unchanged"`
Expected: `tasks and notes routes unchanged`. If they changed, apply this task's changes by hand on top of the changed files instead of replacing them.

Then read Task 2's top-up and rename refusals. The route table's 409s depend on them:

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && grep -n "^NAME_TAKEN_TEXT" roost/money/project_store.py && grep -n "TopUpUndone\|^BUDGET_CLEARED_TEXT\|^BELOW_ZERO_TEXT" roost/money/topup_store.py roost/money/project_store.py`
Expected:
- `NAME_TAKEN_TEXT = "A project with that name exists."` in `project_store.py`;
- `class TopUpUndone(ValueError):` and the two plain texts in `topup_store.py`;
- `raise ledger.TopUpUndone(...)` in `project_store.py` (`_credit_and_project`, the first call of both `edit_topup` and `undo_topup`).

If an undone top-up gives `None` or a plain `ValueError` instead of `TopUpUndone`, stop and report. `POST /api/topups/{id}/undo` cannot tell a 409 from a 404 or a 422 without it.

- [ ] **Step 2: Write the failing tests**

**2a.** Create `tests/test_projects_api.py`:

```python
"""Projects over HTTP (projects hub Task 8): the Projects tab's list, a
project's page, create / change / delete, top-ups, and the money_changed
frame every change publishes (P7, H2, H4, H5, H8–H10, H14, H15).

Another user's project or top-up is a 404, never the object. Every mutating
route needs the Origin, and every route a login."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from roost.config import RoostConfig, load_config
from roost.constants import GENERAL_PROJECT_NAME, MAX_CATEGORY_NAME_LENGTH, PROJECT_COLORS, TOPUP_SOURCE_MAX_CHARS
from roost.db.connection import init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.money.project_store import ProjectStore
from roost.money.topup_store import BUDGET_CLEARED_TEXT
from roost.projects.service import GENERAL_FIXED_TEXT, GENERAL_NAME_TEXT, LEAD_BOT_TEXT
from team_helpers import make_bot

O = {"Origin": "http://127.0.0.1:18800"}
EVIL = {"Origin": "http://evil.example"}
PROJECT_KEYS = {
    "id", "name", "color", "currency", "status", "start_date", "due_date", "lead_bot_id", "total", "month",
    "other_currencies", "starred_total", "progress", "tainted",
}
PAGE_KEYS = PROJECT_KEYS | {"tasks", "expenses", "notes", "documents", "topups", "lead_bot_name", "task_money"}
TOPUP_KEYS = {"id", "amount", "currency", "source", "kind", "topup_id", "undone", "created_at"}
NO_BUDGET = {"budget": None, "spent": "0.00", "remaining": None, "used_percent": None, "tone": None}


@dataclass(frozen=True)
class Rig:
    app: FastAPI
    cfg: RoostConfig
    alice_id: str
    bob_id: str
    alice: httpx.AsyncClient
    bob: httpx.AsyncClient


@pytest.fixture
async def rig():
    cfg = load_config()
    await init_db(cfg)
    app = create_app()
    alice_id = (await register_user(cfg, "alice", "pw-123456")).id
    bob_id = (await register_user(cfg, "bob", "pw-123456")).id
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://roost.test") as alice, \
            httpx.AsyncClient(transport=transport, base_url="http://roost.test") as bob:
        for client, name in ((alice, "alice"), (bob, "bob")):
            login = await client.post("/api/auth/login", json={"username": name, "password": "pw-123456"}, headers=O)
            assert login.status_code == 200
        yield Rig(app, cfg, alice_id, bob_id, alice, bob)


def _client() -> TestClient:
    c = TestClient(create_app())
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O).status_code == 201
    return c


async def _project(client: httpx.AsyncClient, **fields: Any) -> dict:
    created = await client.post("/api/projects", json=fields, headers=O)
    assert created.status_code == 201, created.text
    return created.json()


async def _page(client: httpx.AsyncClient, project: dict) -> dict:
    page = await client.get(f"/api/projects/{project['id']}")
    assert page.status_code == 200, page.text
    return page.json()


async def _changes(rig: Rig) -> list[tuple[str, str]]:
    frames = await rig.app.state.events.since(rig.alice_id, 0)
    return [(frame["change"], frame["id"]) for frame in frames if frame["type"] == "money_changed"]


async def test_create_list_read_and_change_a_project(rig):
    created = await rig.alice.post("/api/projects", json={
        "name": " Renovation ", "budget": "500", "monthly_budget": "100", "color": PROJECT_COLORS[6],
        "start_date": "2026-10-01", "due_date": "2026-12-31",
    }, headers=O)

    assert created.status_code == 201
    house = created.json()
    assert set(house) == PROJECT_KEYS
    assert (house["name"], house["color"], house["currency"], house["status"], house["tainted"]) == (
        "Renovation", PROJECT_COLORS[6], "EUR", "active", False)
    assert (house["start_date"], house["due_date"], house["lead_bot_id"]) == ("2026-10-01", "2026-12-31", None)
    assert house["total"] == {"budget": "500.00", "spent": "0.00", "remaining": "500.00", "used_percent": 0,
                              "tone": "ok"}
    assert house["month"] == {"budget": "100.00", "spent": "0.00", "remaining": "100.00", "used_percent": 0,
                              "tone": "ok"}
    assert (house["other_currencies"], house["starred_total"], house["progress"]) == (
        {}, "0.00", {"done": 0, "failed": 0, "total": 0})
    assert (await rig.alice.get("/api/projects")).json() == [house]
    assert set(await _page(rig.alice, house)) == PAGE_KEYS

    changed = await rig.alice.patch(f"/api/projects/{house['id']}", json={
        "name": "Home", "color": PROJECT_COLORS[2], "due_date": None, "monthly_budget": None,
    }, headers=O)

    assert changed.status_code == 200
    home = changed.json()
    assert (home["id"], home["name"], home["color"], home["due_date"], home["start_date"]) == (
        house["id"], "Home", PROJECT_COLORS[2], None, "2026-10-01")
    assert (home["month"], home["total"]["budget"]) == (NO_BUDGET, "500.00")
    limit = await rig.alice.patch(f"/api/projects/{house['id']}", json={"monthly_budget": "12,50"}, headers=O)
    assert limit.json()["month"]["budget"] == "12.50"


async def test_archived_projects_are_listed_only_when_asked(rig):
    house = await _project(rig.alice, name="House")
    attic = await _project(rig.alice, name="Attic")

    archived = await rig.alice.patch(f"/api/projects/{attic['id']}", json={"status": "archived"}, headers=O)

    assert archived.json()["status"] == "archived"
    assert [p["id"] for p in (await rig.alice.get("/api/projects")).json()] == [house["id"]]
    every = (await rig.alice.get("/api/projects", params={"include_archived": "true"})).json()
    assert [p["name"] for p in every] == ["House", "Attic"]
    assert (await _page(rig.alice, attic))["status"] == "archived"


async def test_general_is_hidden_and_can_be_neither_changed_nor_deleted(rig):
    loose = (await rig.alice.post("/api/money/expenses", json={"amount": "5"}, headers=O)).json()
    general_id = loose["project_id"]
    assert loose["project"] == GENERAL_PROJECT_NAME

    deleted = await rig.alice.delete(f"/api/projects/{general_id}", headers=O)

    assert (deleted.status_code, deleted.json()["detail"]) == (422, GENERAL_FIXED_TEXT)
    for change in ({"name": "Misc"}, {"status": "archived"}, {"color": PROJECT_COLORS[1]}):
        refused = await rig.alice.patch(f"/api/projects/{general_id}", json=change, headers=O)
        assert (refused.status_code, refused.json()["detail"]) == (422, GENERAL_FIXED_TEXT), change
    taken = await rig.alice.post("/api/projects", json={"name": "general"}, headers=O)
    assert (taken.status_code, taken.json()["detail"]) == (422, GENERAL_NAME_TEXT)
    assert (await rig.alice.get("/api/projects", params={"include_archived": "true"})).json() == []
    assert [e["project"] for e in (await rig.alice.get("/api/money/expenses")).json()] == [GENERAL_PROJECT_NAME]


async def test_a_project_page_holds_its_tasks_money_notes_documents_and_top_ups(rig):
    alice = rig.alice
    house = await _project(alice, name="House", budget="300", monthly_budget="100")
    link = {"project_id": house["id"]}
    paint = (await alice.post("/api/tasks", json={"title": "Paint", "allocated_budget": "120", **link},
                              headers=O)).json()
    tiles = (await alice.post("/api/money/expenses", json={"amount": "80", **link}, headers=O)).json()
    taxi = (await alice.post("/api/money/expenses", json={"amount": "9", "currency": "USD", **link},
                             headers=O)).json()
    ideas = (await alice.post("/api/notes", json={"title": "Ideas", "content": "green tiles", **link},
                              headers=O)).json()
    plan = (await alice.post("/api/documents", json={"kind": "doc", "title": "Plan", **link}, headers=O)).json()
    bonus = (await alice.post(f"/api/projects/{house['id']}/topups", json={"amount": "100", "source": "bonus"},
                              headers=O)).json()
    await alice.post("/api/tasks", json={"title": "Loose"}, headers=O)
    await alice.post("/api/money/expenses", json={"amount": "5"}, headers=O)
    await alice.put(f"/api/money/expenses/{tiles['id']}/star", json={"starred": True}, headers=O)

    page = await _page(alice, house)

    assert set(page) == PAGE_KEYS
    assert page["total"] == {"budget": "400.00", "spent": "80.00", "remaining": "320.00", "used_percent": 20,
                             "tone": "ok"}
    assert page["month"] == {"budget": "100.00", "spent": "80.00", "remaining": "20.00", "used_percent": 80,
                             "tone": "warn"}
    assert (page["other_currencies"], page["starred_total"]) == ({"USD": "9.00"}, "80.00")
    assert (page["progress"], page["lead_bot_name"], page["tainted"]) == (
        {"done": 0, "failed": 0, "total": 1}, None, False)
    assert [(t["id"], t["project_id"], t["allocated_budget"]) for t in page["tasks"]] == [
        (paint["id"], house["id"], "120.00")]
    assert page["task_money"] == {paint["id"]: {"planned": "120.00", "spent": "0.00", "left": "120.00"}}
    assert {e["id"] for e in page["expenses"]} == {tiles["id"], taxi["id"]}
    assert {(e["project"], e["project_id"]) for e in page["expenses"]} == {("House", house["id"])}
    assert [(n["id"], n["project_id"]) for n in page["notes"]] == [(ideas["id"], house["id"])]
    assert [(d["id"], d["project_id"]) for d in page["documents"]] == [(plan["id"], house["id"])]
    credits = [row for row in page["topups"] if row["kind"] == "credit"]
    assert [(row["id"], row["amount"], row["source"], row["undone"]) for row in credits] == [
        (bonus["id"], "100.00", "bonus", False)]
    assert all(set(row) == TOPUP_KEYS for row in page["topups"])
    assert [p["id"] for p in (await alice.get("/api/projects")).json()] == [house["id"]]


async def test_a_name_in_use_is_409_on_rename_and_422_on_create(rig):
    house = await _project(rig.alice, name="House")
    await _project(rig.alice, name="Trip")

    renamed = await rig.alice.patch(f"/api/projects/{house['id']}", json={"name": " trip "}, headers=O)
    created = await rig.alice.post("/api/projects", json={"name": "TRIP"}, headers=O)

    assert (renamed.status_code, renamed.json()["detail"]) == (409, "A project with that name exists.")
    assert created.status_code == 422
    assert sorted(p["name"] for p in (await rig.alice.get("/api/projects")).json()) == ["House", "Trip"]


async def test_bad_project_input_is_422_and_changes_nothing(rig):
    house = await _project(rig.alice, name="House")
    for body in (
        {"name": "   "}, {"name": "x" * (MAX_CATEGORY_NAME_LENGTH + 1)}, {"name": "Trip", "color": "#000000"},
        {"name": "Trip", "currency": "euro"}, {"name": "Trip", "budget": "0"},
        {"name": "Trip", "monthly_budget": "12.345"}, {"name": "Trip", "due_date": "2026-13-01"},
        {"name": "Trip", "category": "travel"},
    ):
        assert (await rig.alice.post("/api/projects", json=body, headers=O)).status_code == 422, body
    for change in (
        {}, {"name": None}, {"color": None}, {"status": "done"}, {"monthly_budget": "-5"}, {"start_date": "soon"},
        {"budget": "10"},
    ):
        refused = await rig.alice.patch(f"/api/projects/{house['id']}", json=change, headers=O)
        assert refused.status_code == 422, change
    assert [(p["name"], p["color"], p["status"]) for p in (await rig.alice.get("/api/projects")).json()] == [
        ("House", house["color"], "active")]


async def test_the_lead_bot_must_be_one_of_your_bots(rig):
    mine = await make_bot(rig.cfg, rig.alice_id, "Fixer")
    bobs = await make_bot(rig.cfg, rig.bob_id, "Builder")

    refused = await rig.alice.post("/api/projects", json={"name": "House", "lead_bot_id": bobs.id}, headers=O)
    house = await _project(rig.alice, name="House", lead_bot_id=mine.id)
    moved = await rig.alice.patch(f"/api/projects/{house['id']}", json={"lead_bot_id": bobs.id}, headers=O)

    assert (refused.status_code, refused.json()["detail"]) == (422, LEAD_BOT_TEXT)
    assert (moved.status_code, moved.json()["detail"]) == (422, LEAD_BOT_TEXT)
    assert (house["lead_bot_id"], (await _page(rig.alice, house))["lead_bot_name"]) == (mine.id, "Fixer")
    cleared = await rig.alice.patch(f"/api/projects/{house['id']}", json={"lead_bot_id": None}, headers=O)
    assert (cleared.json()["lead_bot_id"], (await _page(rig.alice, house))["lead_bot_name"]) == (None, None)


async def test_deleting_a_project_keeps_its_items_unlinked_and_its_money_in_general(rig):
    alice = rig.alice
    house = await _project(alice, name="House")
    link = {"project_id": house["id"]}
    task = (await alice.post("/api/tasks", json={"title": "Buy tiles", **link}, headers=O)).json()
    note = (await alice.post("/api/notes", json={"title": "Ideas", "content": "green", **link}, headers=O)).json()
    doc = (await alice.post("/api/documents", json={"kind": "doc", "title": "Plan", **link}, headers=O)).json()
    tiles = (await alice.post("/api/money/expenses", json={"amount": "40", **link}, headers=O)).json()

    deleted = await alice.delete(f"/api/projects/{house['id']}", headers=O)

    assert deleted.status_code == 204
    assert (await alice.get(f"/api/projects/{house['id']}")).status_code == 404
    assert [(t["id"], t["project_id"]) for t in (await alice.get("/api/tasks")).json()] == [(task["id"], None)]
    assert (await alice.get(f"/api/notes/{note['id']}")).json()["project_id"] is None
    assert (await alice.get(f"/api/documents/{doc['id']}")).json()["project_id"] is None
    [moved] = (await alice.get("/api/money/expenses")).json()
    assert (moved["id"], moved["project"], moved["amount"]) == (tiles["id"], GENERAL_PROJECT_NAME, "40.00")
    assert (await alice.get("/api/projects", params={"include_archived": "true"})).json() == []
    assert (await alice.delete(f"/api/projects/{house['id']}", headers=O)).status_code == 404


async def test_top_ups_are_added_edited_undone_and_kept_as_history(rig):
    alice = rig.alice
    house = await _project(alice, name="House")

    added = await alice.post(f"/api/projects/{house['id']}/topups", json={"amount": "100", "source": "  birthday "},
                             headers=O)

    assert added.status_code == 201
    topup = added.json()
    assert set(topup) == TOPUP_KEYS
    assert (topup["kind"], topup["amount"], topup["currency"], topup["source"], topup["topup_id"], topup["undone"]) == (
        "credit", "100.00", "EUR", "birthday", None, False)
    edited = await alice.patch(f"/api/topups/{topup['id']}", json={"amount": "150"}, headers=O)
    assert edited.status_code == 200 and set(edited.json()) == TOPUP_KEYS
    assert (await _page(alice, house))["total"]["budget"] == "150.00"
    assert (await alice.post(f"/api/topups/{topup['id']}/undo", headers=O)).status_code == 200
    assert (await _page(alice, house))["total"]["budget"] in (None, "0.00")
    history = (await alice.get(f"/api/projects/{house['id']}/topups")).json()
    assert sorted(row["kind"] for row in history) == ["credit", "edit"]
    assert all(row["undone"] for row in history)
    assert [row["topup_id"] for row in history if row["kind"] == "edit"] == [topup["id"]]
    for bad in ({"amount": "0"}, {"amount": "abc"}, {"amount": "5", "note": "x"},
                {"amount": "5", "source": "x" * (TOPUP_SOURCE_MAX_CHARS + 1)}):
        refused = await alice.post(f"/api/projects/{house['id']}/topups", json=bad, headers=O)
        assert refused.status_code == 422, bad
    assert (await alice.patch(f"/api/topups/{topup['id']}", json={"amount": "-1"}, headers=O)).status_code == 422


async def test_undoing_a_top_up_twice_is_409(rig):
    """H4: only an undone top-up is a conflict (409, Task 2's TopUpUndone). A
    top-up whose total budget was cleared (H5) breaks a rule instead: 422."""
    house = await _project(rig.alice, name="House")
    topup = (await rig.alice.post(f"/api/projects/{house['id']}/topups", json={"amount": "40"}, headers=O)).json()
    assert (await rig.alice.post(f"/api/topups/{topup['id']}/undo", headers=O)).status_code == 200

    again = await rig.alice.post(f"/api/topups/{topup['id']}/undo", headers=O)
    edit = await rig.alice.patch(f"/api/topups/{topup['id']}", json={"amount": "60"}, headers=O)

    assert (again.status_code, edit.status_code) == (409, 409)
    assert (await _page(rig.alice, house))["total"]["budget"] in (None, "0.00")
    assert [change for change, _ in await _changes(rig)].count("topup_undone") == 1
    missing = await rig.alice.post("/api/topups/no-such-top-up/undo", headers=O)
    assert (missing.status_code, missing.json()["detail"]) == (404, "Top-up not found")
    second = (await rig.alice.post(f"/api/projects/{house['id']}/topups", json={"amount": "15"}, headers=O)).json()
    await ProjectStore(rig.cfg).set_budget(rig.alice_id, house["id"], None, created_by_bot=None, tainted=False)
    cleared = (
        await rig.alice.patch(f"/api/topups/{second['id']}", json={"amount": "20"}, headers=O),
        await rig.alice.post(f"/api/topups/{second['id']}/undo", headers=O),
    )
    assert [(answer.status_code, answer.json()["detail"]) for answer in cleared] == [(422, BUDGET_CLEARED_TEXT)] * 2


async def test_the_total_budget_is_set_and_cleared_on_its_own_route(rig):
    """P3, H5: PUT …/budget sets the total budget and null clears it. Each
    change is a "Budget set" row and a budget_set frame. A bad amount or
    General is 422, an unknown project 404, and PATCH still refuses budget."""
    house = await _project(rig.alice, name="House", monthly_budget="100")
    budget = f"/api/projects/{house['id']}/budget"

    answer = await rig.alice.put(budget, json={"amount": "1200"}, headers=O)

    assert answer.status_code == 200 and set(answer.json()) == PROJECT_KEYS
    assert answer.json()["total"] == {"budget": "1200.00", "spent": "0.00", "remaining": "1200.00",
                                      "used_percent": 0, "tone": "ok"}
    assert answer.json()["month"]["budget"] == "100.00"
    cleared = await rig.alice.put(budget, json={"amount": None}, headers=O)
    assert (cleared.status_code, cleared.json()["total"]) == (200, NO_BUDGET)
    history = (await rig.alice.get(f"/api/projects/{house['id']}/topups")).json()
    assert sorted((row["kind"], row["amount"], row["topup_id"]) for row in history) == [
        ("edit", "-1200.00", None), ("edit", "1200.00", None)]
    for body in ({"amount": "0"}, {"amount": "abc"}, {"amount": "12.345"}, {}, {"amount": "5", "currency": "USD"}):
        assert (await rig.alice.put(budget, json=body, headers=O)).status_code == 422, body
    loose = (await rig.alice.post("/api/money/expenses", json={"amount": "5"}, headers=O)).json()
    general = await rig.alice.put(f"/api/projects/{loose['project_id']}/budget", json={"amount": "50"}, headers=O)
    assert (general.status_code, general.json()["detail"]) == (422, GENERAL_FIXED_TEXT)
    missing = await rig.alice.put("/api/projects/no-such-project/budget", json={"amount": "5"}, headers=O)
    assert (missing.status_code, missing.json()["detail"]) == (404, "Project not found")
    patched = await rig.alice.patch(f"/api/projects/{house['id']}", json={"budget": "10"}, headers=O)
    assert patched.status_code == 422
    assert (await _page(rig.alice, house))["total"] == NO_BUDGET
    assert [change for change in await _changes(rig) if change[0] == "budget_set"] == [
        ("budget_set", house["id"])] * 2


async def test_every_project_change_is_published_on_money_changed(rig):
    alice = rig.alice
    house = await _project(alice, name="House")
    await alice.patch(f"/api/projects/{house['id']}", json={"color": PROJECT_COLORS[3]}, headers=O)
    topup = (await alice.post(f"/api/projects/{house['id']}/topups", json={"amount": "10"}, headers=O)).json()
    await alice.patch(f"/api/topups/{topup['id']}", json={"amount": "12"}, headers=O)
    await alice.post(f"/api/topups/{topup['id']}/undo", headers=O)
    await alice.delete(f"/api/projects/{house['id']}", headers=O)

    assert await _changes(rig) == [
        ("project_created", house["id"]), ("project_updated", house["id"]), ("topup_added", topup["id"]),
        ("topup_edited", topup["id"]), ("topup_undone", topup["id"]), ("project_deleted", house["id"]),
    ]


def test_projects_need_a_login_and_the_origin():
    assert TestClient(create_app()).get("/api/projects").status_code == 401
    c = _client()
    house = c.post("/api/projects", json={"name": "House"}, headers=O).json()
    topup = c.post(f"/api/projects/{house['id']}/topups", json={"amount": "5"}, headers=O).json()
    for method, path, body in (
        ("POST", "/api/projects", {"name": "Trip"}),
        ("PATCH", f"/api/projects/{house['id']}", {"color": PROJECT_COLORS[1]}),
        ("DELETE", f"/api/projects/{house['id']}", None),
        ("PUT", f"/api/projects/{house['id']}/budget", {"amount": "9"}),
        ("PUT", f"/api/projects/{house['id']}/budget", {"amount": None}),
        ("POST", f"/api/projects/{house['id']}/topups", {"amount": "5"}),
        ("PATCH", f"/api/topups/{topup['id']}", {"amount": "6"}),
        ("POST", f"/api/topups/{topup['id']}/undo", None),
    ):
        assert c.request(method, path, json=body, headers=EVIL).status_code == 403, (method, path)
    [kept] = c.get("/api/projects").json()
    assert (kept["name"], kept["color"], kept["total"]["budget"]) == ("House", house["color"], "5.00")


async def test_another_users_projects_and_top_ups_are_404(rig):
    house = await _project(rig.alice, name="House")
    topup = (await rig.alice.post(f"/api/projects/{house['id']}/topups", json={"amount": "10"}, headers=O)).json()
    bob, project_id, topup_id = rig.bob, house["id"], topup["id"]

    answers = (
        await bob.get(f"/api/projects/{project_id}"),
        await bob.patch(f"/api/projects/{project_id}", json={"color": PROJECT_COLORS[1]}, headers=O),
        await bob.delete(f"/api/projects/{project_id}", headers=O),
        await bob.put(f"/api/projects/{project_id}/budget", json={"amount": "99"}, headers=O),
        await bob.put(f"/api/projects/{project_id}/budget", json={"amount": None}, headers=O),
        await bob.get(f"/api/projects/{project_id}/topups"),
        await bob.post(f"/api/projects/{project_id}/topups", json={"amount": "5"}, headers=O),
        await bob.patch(f"/api/topups/{topup_id}", json={"amount": "20"}, headers=O),
        await bob.post(f"/api/topups/{topup_id}/undo", headers=O),
    )

    assert [answer.status_code for answer in answers] == [404] * 9
    assert answers[0].json()["detail"] == "Project not found"
    assert (await bob.get("/api/projects", params={"include_archived": "true"})).json() == []
    page = await _page(rig.alice, house)
    assert (page["color"], page["total"]["budget"], [row["undone"] for row in page["topups"]]) == (
        house["color"], "10.00", [False])
```

**2b.** Append to the end of `tests/test_money_api.py` **(after Tasks 1 and 3; the file imports inside its async tests, so these do too)**:

```python


async def test_star_and_void_an_expense_from_the_board():
    """Hub P6, H6: PUT …/star and …/void answer with the expense's row. A void
    expense stays listed and leaves the month's sums until it is posted again.
    Each change publishes money_changed "expense_updated"."""
    import httpx

    from roost.db.connection import init_db
    from roost.gateway.auth import register_user

    app = create_app()
    cfg = load_config()
    await init_db(cfg)
    alice_id = (await register_user(cfg, "alice", "pw-123456")).id
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test") as alice:
        await alice.post("/api/auth/login", json={"username": "alice", "password": "pw-123456"}, headers=O)
        lunch = (await alice.post("/api/money/expenses", json={"amount": "12", "project": "food"}, headers=O)).json()
        star, void = f"/api/money/expenses/{lunch['id']}/star", f"/api/money/expenses/{lunch['id']}/void"
        starred = await alice.put(star, json={"starred": True}, headers=O)
        voided = await alice.put(void, json={"void": True}, headers=O)
        summary = (await alice.get("/api/money/summary")).json()
        listed = (await alice.get("/api/money/expenses")).json()
        posted = await alice.put(void, json={"void": False}, headers=O)
        unstarred = await alice.put(star, json={"starred": False}, headers=O)
        not_a_bool = await alice.put(star, json={"starred": "yes"}, headers=O)
        missing = await alice.put("/api/money/expenses/no-such-expense/void", json={"void": True}, headers=O)
        frames = await app.state.events.since(alice_id, 0)
    assert (starred.status_code, starred.json()["is_favorite"], starred.json()["project"]) == (200, True, "food")
    assert (voided.json()["status"], voided.json()["is_favorite"]) == ("void", True)
    assert (summary["total"], summary["expense_count"]) == ("0.00", 0)
    assert [(e["id"], e["status"]) for e in listed] == [(lunch["id"], "void")]
    assert (posted.json()["status"], unstarred.json()["is_favorite"]) == ("posted", False)
    assert (not_a_bool.status_code, missing.status_code, missing.json()["detail"]) == (422, 404, "Expense not found")
    changes = [f["change"] for f in frames if f["type"] == "money_changed" and f["change"].startswith("expense_")]
    assert changes == ["expense_created"] + ["expense_updated"] * 4


async def test_an_expense_names_its_project_by_id_and_takes_its_currency():
    """A project's page adds an expense by the project's id. It lands in
    exactly that project. With no currency sent it takes the project's (H7),
    whether the project is named by id or by name. A project that isn't the
    user's is refused, and so is naming it twice. An archived project takes
    no new expense (H3)."""
    import httpx

    from roost.db.connection import init_db
    from roost.gateway.auth import register_user
    from roost.money.service import ARCHIVED_TEXT

    app = create_app()
    cfg = load_config()
    await init_db(cfg)
    for name in ("alice", "bob"):
        await register_user(cfg, name, "pw-123456")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://roost.test") as alice, \
            httpx.AsyncClient(transport=transport, base_url="http://roost.test") as bob:
        for client, name in ((alice, "alice"), (bob, "bob")):
            await client.post("/api/auth/login", json={"username": name, "password": "pw-123456"}, headers=O)
        trip = (await alice.post("/api/projects", json={"name": "Trip", "currency": "USD"}, headers=O)).json()
        shed = (await bob.post("/api/projects", json={"name": "Shed"}, headers=O)).json()
        taxi = await alice.post("/api/money/expenses", json={"amount": "30", "project_id": trip["id"]}, headers=O)
        tip = await alice.post("/api/money/expenses", json={"amount": "4", "project": "Trip"}, headers=O)
        euros = await alice.post("/api/money/expenses", json={"amount": "8", "project_id": trip["id"],
                                                               "currency": "EUR"}, headers=O)
        foreign = await alice.post("/api/money/expenses", json={"amount": "1", "project_id": shed["id"]}, headers=O)
        twice = await alice.post("/api/money/expenses", json={"amount": "1", "project": "Trip",
                                                               "project_id": trip["id"]}, headers=O)
        await alice.patch(f"/api/projects/{trip['id']}", json={"status": "archived"}, headers=O)
        archived = await alice.post("/api/money/expenses", json={"amount": "2", "project_id": trip["id"]}, headers=O)
        listed = (await alice.get("/api/money/expenses")).json()
        page = (await alice.get(f"/api/projects/{trip['id']}")).json()
    assert (taxi.status_code, taxi.json()["project"], taxi.json()["project_id"], taxi.json()["currency"]) == (
        201, "Trip", trip["id"], "USD")
    assert (tip.status_code, tip.json()["project_id"], tip.json()["currency"]) == (201, trip["id"], "USD")
    assert euros.json()["currency"] == "EUR"
    assert (foreign.status_code, foreign.json()["detail"]) == (422, "No such project.")
    assert twice.status_code == 422
    assert (archived.status_code, archived.json()["detail"]) == (422, ARCHIVED_TEXT.format(name="Trip"))
    assert sorted(e["amount"] for e in listed) == ["30.00", "4.00", "8.00"]
    assert (page["total"]["spent"], page["other_currencies"]) == ("34.00", {"EUR": "8.00"})


async def test_another_users_expense_cannot_be_starred_or_voided():
    import httpx

    from roost.db.connection import init_db
    from roost.gateway.auth import register_user

    app = create_app()
    cfg = load_config()
    await init_db(cfg)
    for name in ("alice", "bob"):
        await register_user(cfg, name, "pw-123456")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://roost.test") as alice, \
            httpx.AsyncClient(transport=transport, base_url="http://roost.test") as bob:
        for client, name in ((alice, "alice"), (bob, "bob")):
            await client.post("/api/auth/login", json={"username": name, "password": "pw-123456"}, headers=O)
        lunch = (await alice.post("/api/money/expenses", json={"amount": "12"}, headers=O)).json()
        for path, body in ((f"/api/money/expenses/{lunch['id']}/star", {"starred": True}),
                           (f"/api/money/expenses/{lunch['id']}/void", {"void": True})):
            assert (await bob.put(path, json=body, headers=O)).status_code == 404, path
            assert (await alice.put(path, json=body, headers={"Origin": "http://evil.example"})).status_code == 403
        [row] = (await alice.get("/api/money/expenses")).json()
    assert (row["status"], row["is_favorite"]) == ("posted", False)
```

**2c.** Append to the end of `tests/test_tasks_api.py`. Its imports (`httpx`, `TestClient`, `load_config`, `init_db`, `create_app` and `register_user`) and its helpers `O`, `_client` and `_frames` are already at the top of the file:

```python


def test_fail_closes_an_open_task_and_the_failed_filter_finds_it():
    """Hub H11: POST …/fail closes an open task as failed, with completed_at
    set. The failed filter lists it, while done and open leave it out. Only an
    open task can fail."""
    c = _client()
    tap = c.post("/api/tasks", json={"title": "Fix the tap"}, headers=O).json()
    paint = c.post("/api/tasks", json={"title": "Paint"}, headers=O).json()
    c.post(f"/api/tasks/{paint['id']}/complete", headers=O)

    failed = c.post(f"/api/tasks/{tap['id']}/fail", headers=O)

    assert (failed.status_code, failed.json()["status"]) == (200, "failed")
    assert failed.json()["completed_at"] is not None
    assert [t["title"] for t in c.get("/api/tasks", params={"status": "failed"}).json()] == ["Fix the tap"]
    assert [t["title"] for t in c.get("/api/tasks", params={"status": "done"}).json()] == ["Paint"]
    assert c.get("/api/tasks").json() == []
    again = c.post(f"/api/tasks/{tap['id']}/fail", headers=O)
    assert (again.status_code, again.json()["detail"]) == (404, "No open task with that id")
    assert c.post(f"/api/tasks/{paint['id']}/fail", headers={"Origin": "http://evil.example"}).status_code == 403
    assert _frames()[-1] == "tasks_changed"


async def test_tasks_join_a_project_with_a_budget_slice_and_filter_by_it():
    """Hub H11: a task joins one of the user's projects, on create or by
    PATCH, and may carry a budget slice, which needs a project. ?project_id=
    lists that project's tasks. A project that isn't the user's is a 422."""
    app = create_app()
    cfg = load_config()
    await init_db(cfg)
    alice_id = (await register_user(cfg, "alice", "pw-123456")).id
    await register_user(cfg, "bob", "pw-123456")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://roost.test") as alice, \
            httpx.AsyncClient(transport=transport, base_url="http://roost.test") as bob:
        for client, name in ((alice, "alice"), (bob, "bob")):
            await client.post("/api/auth/login", json={"username": name, "password": "pw-123456"}, headers=O)
        house = (await alice.post("/api/projects", json={"name": "House"}, headers=O)).json()
        shed = (await bob.post("/api/projects", json={"name": "Shed"}, headers=O)).json()
        paint = await alice.post("/api/tasks", json={"title": "Paint", "project_id": house["id"],
                                                     "allocated_budget": "250"}, headers=O)
        await alice.post("/api/tasks", json={"title": "Loose"}, headers=O)
        listed = (await alice.get("/api/tasks", params={"project_id": house["id"]})).json()
        every = (await alice.get("/api/tasks", params={"project_id": ""})).json()
        task_id = paint.json()["id"]
        resliced = await alice.patch(f"/api/tasks/{task_id}", json={"allocated_budget": "12,5"}, headers=O)
        cleared = await alice.patch(f"/api/tasks/{task_id}", json={"allocated_budget": None}, headers=O)
        no_project = await alice.post("/api/tasks", json={"title": "x", "allocated_budget": "10"}, headers=O)
        foreign = await alice.post("/api/tasks", json={"title": "x", "project_id": shed["id"]}, headers=O)
        moved = await alice.patch(f"/api/tasks/{task_id}", json={"project_id": shed["id"]}, headers=O)
        zero = await alice.post("/api/tasks", json={"title": "x", "project_id": house["id"], "allocated_budget": "0"},
                                headers=O)
        unlinked = await alice.patch(f"/api/tasks/{task_id}", json={"project_id": None}, headers=O)
        failed = await alice.post(f"/api/tasks/{task_id}/fail", headers=O)
        frames = await app.state.events.since(alice_id, 0)
    assert paint.status_code == 201
    assert (paint.json()["project_id"], paint.json()["allocated_budget"]) == (house["id"], "250.00")
    assert [t["title"] for t in listed] == ["Paint"]
    assert sorted(t["title"] for t in every) == ["Loose", "Paint"]
    assert (resliced.json()["allocated_budget"], cleared.json()["allocated_budget"]) == ("12.50", None)
    assert (no_project.status_code, no_project.json()["detail"]) == (422, "A budget slice needs a project.")
    assert [(r.status_code, r.json()["detail"]) for r in (foreign, moved)] == [(422, "No such project.")] * 2
    assert zero.status_code == 422
    assert (unlinked.json()["project_id"], failed.json()["status"]) == (None, "failed")
    assert [f["change"] for f in frames if f["type"] == "tasks_changed"][-1] == "failed"


async def test_another_users_task_cannot_be_failed_or_listed_by_project():
    app = create_app()
    cfg = load_config()
    await init_db(cfg)
    for name in ("alice", "bob"):
        await register_user(cfg, name, "pw-123456")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://roost.test") as alice, \
            httpx.AsyncClient(transport=transport, base_url="http://roost.test") as bob:
        for client, name in ((alice, "alice"), (bob, "bob")):
            await client.post("/api/auth/login", json={"username": name, "password": "pw-123456"}, headers=O)
        house = (await alice.post("/api/projects", json={"name": "House"}, headers=O)).json()
        task = (await alice.post("/api/tasks", json={"title": "mine", "project_id": house["id"]}, headers=O)).json()
        assert (await bob.post(f"/api/tasks/{task['id']}/fail", headers=O)).status_code == 404
        assert (await bob.patch(f"/api/tasks/{task['id']}", json={"project_id": None}, headers=O)).status_code == 404
        assert (await bob.get("/api/tasks", params={"status": "all", "project_id": house["id"]})).json() == []
        assert [(t["id"], t["status"], t["project_id"]) for t in (await alice.get("/api/tasks")).json()] == [
            (task["id"], "todo", house["id"])]
```

**2d.** Append to the end of `tests/test_notes_api.py`. Its imports (`httpx`, `TestClient`, `load_config`, `init_db`, `create_app` and `register_user`) and `O` and `_client` are at the top of the file:

```python


async def test_a_note_links_to_a_project_without_a_new_revision():
    """Hub H12: a note joins a project when it is created, or later through
    PUT …/project. The link keeps the revision, so an open editor's next save
    still lands, and null unlinks. ?project_id= lists only that project's
    notes. Each link publishes notes_changed "updated"."""
    app = create_app()
    cfg = load_config()
    await init_db(cfg)
    alice_id = (await register_user(cfg, "alice", "pw-123456")).id
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test") as alice:
        await alice.post("/api/auth/login", json={"username": "alice", "password": "pw-123456"}, headers=O)
        house = (await alice.post("/api/projects", json={"name": "House"}, headers=O)).json()
        ideas = await alice.post("/api/notes", json={"title": "Ideas", "content": "green tiles",
                                                     "project_id": house["id"]}, headers=O)
        loose = (await alice.post("/api/notes", json={"title": "Loose", "content": "eggs"}, headers=O)).json()
        filtered = (await alice.get("/api/notes", params={"project_id": house["id"]})).json()
        linked = await alice.put(f"/api/notes/{loose['id']}/project", json={"project_id": house["id"]}, headers=O)
        saved = await alice.put(f"/api/notes/{loose['id']}", json={"base_revision": 1, "content": "eggs, milk"},
                                headers=O)
        unlinked = await alice.put(f"/api/notes/{ideas.json()['id']}/project", json={"project_id": None}, headers=O)
        after = (await alice.get("/api/notes", params={"project_id": house["id"]})).json()
        unknown = await alice.put(f"/api/notes/{loose['id']}/project", json={"project_id": "no-such-project"},
                                  headers=O)
        empty = await alice.put(f"/api/notes/{loose['id']}/project", json={}, headers=O)
        frames = await app.state.events.since(alice_id, 0)
    assert (ideas.status_code, ideas.json()["project_id"], loose["project_id"]) == (201, house["id"], None)
    assert [(n["id"], n["project_id"]) for n in filtered] == [(ideas.json()["id"], house["id"])]
    assert (linked.status_code, linked.json()["project_id"], linked.json()["revision"]) == (200, house["id"], 1)
    assert (saved.status_code, saved.json()["revision"], saved.json()["project_id"]) == (200, 2, house["id"])
    assert (unlinked.json()["project_id"], [n["id"] for n in after]) == (None, [loose["id"]])
    assert (unknown.status_code, unknown.json()["detail"]) == (422, "No such project.")
    assert empty.status_code == 422
    updates = [f["note_id"] for f in frames if f["type"] == "notes_changed" and f["change"] == "updated"]
    assert updates == [loose["id"], loose["id"], ideas.json()["id"]]


async def test_a_note_cannot_link_to_another_users_project_or_be_linked_by_them():
    app = create_app()
    cfg = load_config()
    await init_db(cfg)
    for name in ("alice", "bob"):
        await register_user(cfg, name, "pw-123456")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://roost.test") as alice, \
            httpx.AsyncClient(transport=transport, base_url="http://roost.test") as bob:
        for client, name in ((alice, "alice"), (bob, "bob")):
            await client.post("/api/auth/login", json={"username": name, "password": "pw-123456"}, headers=O)
        house = (await alice.post("/api/projects", json={"name": "House"}, headers=O)).json()
        shed = (await bob.post("/api/projects", json={"name": "Shed"}, headers=O)).json()
        note = (await alice.post("/api/notes", json={"content": "mine"}, headers=O)).json()
        link = f"/api/notes/{note['id']}/project"
        created = await alice.post("/api/notes", json={"content": "x", "project_id": shed["id"]}, headers=O)
        assert (created.status_code, created.json()["detail"]) == (422, "No such project.")
        assert (await alice.put(link, json={"project_id": shed["id"]}, headers=O)).status_code == 422
        assert (await bob.put(link, json={"project_id": shed["id"]}, headers=O)).status_code == 404
        assert (await bob.get("/api/notes", params={"project_id": house["id"]})).json() == []
        evil = {"Origin": "http://evil.example"}
        assert (await alice.put(link, json={"project_id": house["id"]}, headers=evil)).status_code == 403
        assert (await alice.get(f"/api/notes/{note['id']}")).json()["project_id"] is None


def test_a_link_that_meets_two_saves_is_409_with_the_current_note(monkeypatch):
    """Task 5: NoteStore.set_project raises RevisionConflict only when two saves
    land during one link. The route answers like a stale save: 409 with the
    current note."""
    from roost.gateway.routes.notes import NOTE_CONFLICT_TEXT
    from roost.records.revision import RevisionConflict

    app = create_app()
    c = TestClient(app)
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O).status_code == 201
    house = c.post("/api/projects", json={"name": "House"}, headers=O).json()
    note = c.post("/api/notes", json={"title": "List", "content": "eggs"}, headers=O).json()
    notes = app.state.notes

    async def two_saves(user_id: str, note_id: str, project_id: str | None):
        raise RevisionConflict(await notes.get(user_id, note_id))

    monkeypatch.setattr(notes, "set_project", two_saves)
    clash = c.put(f"/api/notes/{note['id']}/project", json={"project_id": house["id"]}, headers=O)
    assert (clash.status_code, clash.json()["detail"]) == (409, NOTE_CONFLICT_TEXT)
    assert (clash.json()["current"]["id"], clash.json()["current"]["revision"]) == (note["id"], 1)
```

**2e.** Append to the end of `tests/test_documents_api.py`. Its imports (`httpx`, `load_config`, `init_db`, `create_app` and `register_user`) and `O` are at the top of the file:

```python


async def test_a_document_links_to_a_project_without_a_new_revision():
    """Hub H12: a doc or sheet joins a project when it is created, or later
    through PUT …/project. The link keeps the revision, so an open editor's
    next autosave still lands, and null unlinks. ?project_id= filters, with or
    without ?kind=. Each link publishes documents_changed "updated"."""
    app = create_app()
    cfg = load_config()
    await init_db(cfg)
    alice_id = (await register_user(cfg, "alice", "pw-123456")).id
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test") as alice:
        await alice.post("/api/auth/login", json={"username": "alice", "password": "pw-123456"}, headers=O)
        house = (await alice.post("/api/projects", json={"name": "House"}, headers=O)).json()
        link = {"project_id": house["id"]}
        plan = await alice.post("/api/documents", json={"kind": "doc", "title": "Plan", **link}, headers=O)
        costs = (await alice.post("/api/documents", json={"kind": "sheet", "title": "Costs",
                                                          "rows": [["Tiles", 40]], **link}, headers=O)).json()
        loose = (await alice.post("/api/documents", json={"kind": "doc", "title": "Loose"}, headers=O)).json()
        listed = (await alice.get("/api/documents", params=link)).json()
        sheets = (await alice.get("/api/documents", params={"kind": "sheet", **link})).json()
        linked = await alice.put(f"/api/documents/{loose['id']}/project", json=link, headers=O)
        saved = await alice.put(f"/api/documents/{loose['id']}", json={"base_revision": 1, "title": "Loose plan"},
                                headers=O)
        unlinked = await alice.put(f"/api/documents/{plan.json()['id']}/project", json={"project_id": None},
                                   headers=O)
        unknown = await alice.put(f"/api/documents/{loose['id']}/project", json={"project_id": "no-such-project"},
                                  headers=O)
        frames = await app.state.events.since(alice_id, 0)
    assert (plan.status_code, plan.json()["project_id"], loose["project_id"]) == (201, house["id"], None)
    assert {d["id"] for d in listed} == {plan.json()["id"], costs["id"]}
    assert [d["id"] for d in sheets] == [costs["id"]]
    assert (linked.status_code, linked.json()["project_id"], linked.json()["revision"]) == (200, house["id"], 1)
    assert (saved.status_code, saved.json()["revision"]) == (200, 2)
    assert unlinked.json()["project_id"] is None
    assert (unknown.status_code, unknown.json()["detail"]) == (422, "No such project.")
    updates = [f["document_id"] for f in frames if f["type"] == "documents_changed" and f["change"] == "updated"]
    assert updates == [loose["id"], loose["id"], plan.json()["id"]]


async def test_a_document_cannot_link_to_another_users_project_or_be_linked_by_them():
    app = create_app()
    cfg = load_config()
    await init_db(cfg)
    for name in ("alice", "bob"):
        await register_user(cfg, name, "pw-123456")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://roost.test") as alice, \
            httpx.AsyncClient(transport=transport, base_url="http://roost.test") as bob:
        for client, name in ((alice, "alice"), (bob, "bob")):
            await client.post("/api/auth/login", json={"username": name, "password": "pw-123456"}, headers=O)
        house = (await alice.post("/api/projects", json={"name": "House"}, headers=O)).json()
        shed = (await bob.post("/api/projects", json={"name": "Shed"}, headers=O)).json()
        doc = (await alice.post("/api/documents", json={"kind": "doc", "title": "mine"}, headers=O)).json()
        link = f"/api/documents/{doc['id']}/project"
        created = await alice.post("/api/documents", json={"kind": "doc", "title": "x", "project_id": shed["id"]},
                                   headers=O)
        assert (created.status_code, created.json()["detail"]) == (422, "No such project.")
        assert (await alice.put(link, json={"project_id": shed["id"]}, headers=O)).status_code == 422
        assert (await bob.put(link, json={"project_id": shed["id"]}, headers=O)).status_code == 404
        assert (await bob.get("/api/documents", params={"project_id": house["id"]})).json() == []
        evil = {"Origin": "http://evil.example"}
        assert (await alice.put(link, json={"project_id": house["id"]}, headers=evil)).status_code == 403
        assert (await alice.get(f"/api/documents/{doc['id']}")).json()["project_id"] is None
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_projects_api.py tests/test_money_api.py tests/test_tasks_api.py tests/test_notes_api.py tests/test_documents_api.py -q`

Expected: FAIL. Every file collects, because the tests import only names Tasks 1–7 already made, and every existing test still passes. The 25 new tests fail:
- `tests/test_projects_api.py`: all 14 fail. There is no `/api/projects` route yet, so a POST answers 404, or 405 when `web/dist` is built. `_project` fails on `assert 405 == 201` (or 404), and the login test on `assert 404 == 401`.
- `tests/test_money_api.py`: the 3 new tests fail.
  - `PUT …/star` answers 404 or 405.
  - `/api/projects` is missing, so `trip["id"]` raises `KeyError: 'id'`.
- `tests/test_tasks_api.py`: the 3 new tests fail.
  - `POST …/fail` answers 404 or 405 where 200 is expected.
  - The project tests fail at `KeyError: 'id'` (no `/api/projects`).
- `tests/test_notes_api.py` and `tests/test_documents_api.py`: the 5 new tests fail at `KeyError: 'id'` (no `/api/projects`).

- [ ] **Step 4: Implement `/api/projects`**

Create `roost/gateway/routes/projects.py`:

```python
"""Projects over HTTP — the Board's Projects tab and a project's page (projects
hub P7, H2, H4, H5, H8–H10, H14, H15). Same ``ProjectService`` as the bots'
tools, so every change is published on ``money_changed`` and every open tab
refreshes.

- General (H2) is hidden from the list and can be neither changed nor deleted
  (422).
- Every amount goes out as a string, and each budget carries its bar's
  ``used_percent`` and ``tone`` (H8): the web never adds amounts.
- The total budget (P3, H5) is set, or cleared with ``null``, only by
  ``PUT /api/projects/{id}/budget`` and top-ups. PATCH never takes ``budget``,
  so every change to the total leaves its row in the history.
- A rename onto a name in use is 409. Any other broken rule is 422 with the
  rule's plain sentence. A top-up already undone stays undone: changing or
  undoing it again is 409 (``TopUpUndone``). A cleared total budget, or one
  that would go below 0, is a broken rule: 422.
- Another user's project or top-up is a 404, never the object.

``ProjectLinkIn`` is also the body of ``PUT /api/notes/{id}/project`` and
``PUT /api/documents/{id}/project`` (H12)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints, model_validator

from roost.constants import (
    CURRENCY_PATTERN, DEFAULT_CURRENCY, DEFAULT_PROJECT_COLOR, MAX_CATEGORY_NAME_LENGTH, MAX_RECORD_ID_LENGTH,
    PROJECT_COLORS, PROJECT_STATUSES, TOPUP_SOURCE_MAX_CHARS,
)
from roost.documents.format import document_out
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.money.amounts import amount_text, parse_amount
from roost.money.models import COLOR_TEXT, DATE_TEXT, Project, ProjectDraft, TopUp
from roost.money.project_store import NAME_TAKEN_TEXT
from roost.money.summary import amounts_out, budget_line_out, expense_row
from roost.money.topup_store import TopUpUndone
from roost.notes.format import note_summary_out
from roost.projects.numbers import Progress, ProjectNumbers, TaskMoney
from roost.projects.service import STATUS_TEXT, ProjectDetail, ProjectService
from roost.tasks.format import task_out

projects_router = APIRouter(tags=["projects"])

PROJECT_NOT_FOUND_TEXT = "Project not found"
TOPUP_NOT_FOUND_TEXT = "Top-up not found"
# ProjectStore's refusal of a name one of the user's other projects has (Task 2): the one 409 of PATCH.
NAME_IN_USE_TEXT = NAME_TAKEN_TEXT
NOTHING_TO_CHANGE_TEXT = "Send at least one change."
NOT_CLEARABLE_TEXT = "A project's name, colour, status and currency can't be cleared."
_NOT_CLEARABLE = frozenset({"name", "color", "status", "currency"})


def _day(value: str | None) -> str | None:
    """A plain ``YYYY-MM-DD`` day, as ``ProjectDraft`` keeps it (Task 2's ``DATE_TEXT``)."""
    if value is None:
        return None
    try:
        day = date.fromisoformat(value)
    except ValueError:
        raise ValueError(DATE_TEXT) from None
    if day.isoformat() != value:   # Python also reads "20261231" or week dates; only the plain form is kept
        raise ValueError(DATE_TEXT)
    return value


def _color(value: str) -> str:
    """One of ``PROJECT_COLORS``, case ignored, as ``ProjectDraft`` tidies it."""
    color = value.strip().lower()
    if color not in PROJECT_COLORS:
        raise ValueError(COLOR_TEXT)
    return color


def _status(value: str) -> str:
    if value not in PROJECT_STATUSES:
        raise ValueError(STATUS_TEXT)
    return value


def _amount(value: str | int | float | None) -> Decimal | None:
    """``parse_amount``'s rules (more than 0, at most 2 decimals); ``None`` stays ``None``."""
    return None if value is None else parse_amount(value)


ProjectName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_CATEGORY_NAME_LENGTH),
]
Amount = str | int | float
Day = Annotated[str | None, AfterValidator(_day)]
Color = Annotated[str, AfterValidator(_color)]
Status = Annotated[str, AfterValidator(_status)]
Currency = Annotated[str, Field(pattern=CURRENCY_PATTERN)]
RecordId = Annotated[str, Field(max_length=MAX_RECORD_ID_LENGTH)]


class ProjectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: ProjectName
    currency: Currency = DEFAULT_CURRENCY
    budget: Amount | None = None              # the total budget; top-ups add to it (H4)
    monthly_budget: Amount | None = None      # the monthly limit
    color: Color = DEFAULT_PROJECT_COLOR
    start_date: Day = None
    due_date: Day = None
    lead_bot_id: RecordId | None = None

    def draft(self) -> ProjectDraft:
        """Raises ``ValueError`` (plain text) for an amount ``parse_amount`` refuses."""
        return ProjectDraft(name=self.name, currency=self.currency, budget=_amount(self.budget),
                            monthly_budget=_amount(self.monthly_budget), color=self.color,
                            start_date=self.start_date, due_date=self.due_date, lead_bot_id=self.lead_bot_id)


class ProjectPatchIn(BaseModel):
    """Only the fields sent change. ``null`` clears a date, the monthly limit
    or the lead bot (H5). The total budget moves only through
    ``PUT …/budget`` (``BudgetIn``) and top-ups."""

    model_config = ConfigDict(extra="forbid")
    name: ProjectName | None = None
    color: Color | None = None
    status: Status | None = None
    currency: Currency | None = None
    start_date: Day = None
    due_date: Day = None
    monthly_budget: Amount | None = None
    lead_bot_id: RecordId | None = None

    @model_validator(mode="after")
    def _a_change_that_clears_only_what_can_be(self) -> "ProjectPatchIn":
        if not self.model_fields_set:
            raise ValueError(NOTHING_TO_CHANGE_TEXT)
        if any(getattr(self, field) is None for field in self.model_fields_set & _NOT_CLEARABLE):
            raise ValueError(NOT_CLEARABLE_TEXT)
        return self

    def changes(self) -> dict[str, Any]:
        """Raises ``ValueError`` (plain text) for a monthly limit ``parse_amount`` refuses."""
        fields = self.model_dump(include=self.model_fields_set)
        if "monthly_budget" in fields:
            return {**fields, "monthly_budget": _amount(fields["monthly_budget"])}
        return fields


class BudgetIn(BaseModel):
    """The total budget (P3): an amount string, or ``null`` to clear it (H5).
    ``amount`` is required, so ``{}`` is a 422, never a silent clear."""

    model_config = ConfigDict(extra="forbid")
    amount: str | None


class TopupIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: Amount
    source: str | None = Field(default=None, max_length=TOPUP_SOURCE_MAX_CHARS)


class TopupEditIn(BaseModel):
    """The top-up's new amount. The store records the difference (H4)."""

    model_config = ConfigDict(extra="forbid")
    amount: Amount


class ProjectLinkIn(BaseModel):
    """One of the user's projects, or ``null`` to unlink (H12)."""

    model_config = ConfigDict(extra="forbid")
    project_id: RecordId | None


def progress_out(progress: Progress) -> dict[str, int]:
    return {"done": progress.done, "failed": progress.failed, "total": progress.total}


def _optional_amount(amount: Decimal | None) -> str | None:
    return None if amount is None else amount_text(amount)


def task_money_out(money: TaskMoney) -> dict[str, str | None]:
    """``TaskMoneyOut``: a task's slice, what is spent on it, and what is left (negative when over)."""
    return {"planned": _optional_amount(money.planned), "spent": amount_text(money.spent),
            "left": _optional_amount(money.left)}


def project_out(project: Project, numbers: ProjectNumbers, progress: Progress) -> dict[str, Any]:
    """``ProjectOut``: a row on the Projects tab, and the head of a project's page."""
    return {
        "id": project.id, "name": project.name, "color": project.color, "currency": project.currency,
        "status": project.status, "start_date": project.start_date, "due_date": project.due_date,
        "lead_bot_id": project.lead_bot_id, "total": budget_line_out(numbers.total),
        "month": budget_line_out(numbers.month), "other_currencies": amounts_out(numbers.other_currencies),
        "starred_total": amount_text(numbers.starred_total), "progress": progress_out(progress),
        "tainted": project.tainted,
    }


def topup_out(topup: TopUp) -> dict[str, Any]:
    """``TopupOut``: one history row. An "edit" with a ``topup_id`` changed that
    top-up; one with none is a budget set by hand (H4)."""
    return {
        "id": topup.id, "amount": amount_text(topup.amount), "currency": topup.currency, "source": topup.source,
        "kind": topup.kind, "topup_id": topup.topup_id, "undone": topup.undone, "created_at": topup.created_at,
    }


def project_detail_out(detail: ProjectDetail) -> dict[str, Any]:
    """``ProjectDetailOut``: the page. Its ``tainted`` covers everything it shows."""
    project = detail.project
    return {
        **project_out(project, detail.numbers, detail.progress),
        "tasks": [task_out(task) for task in detail.tasks],
        "expenses": [expense_row(expense, project) for expense in detail.expenses],
        "notes": [note_summary_out(note) for note in detail.notes],
        "documents": [document_out(meta) for meta in detail.documents],
        "topups": [topup_out(topup) for topup in detail.topups],
        "lead_bot_name": detail.lead_bot_name, "tainted": detail.tainted,
        "task_money": {task_id: task_money_out(money) for task_id, money in detail.task_money.items()},
    }


def _service(request: Request) -> ProjectService:
    return request.app.state.projects


def _unreadable(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


def _refused(exc: ValueError) -> HTTPException:
    """A rename onto a name in use is a conflict (409). Any other broken rule is 422."""
    return HTTPException(status_code=409 if str(exc) == NAME_IN_USE_TEXT else 422, detail=str(exc))


def _undone(exc: TopUpUndone) -> HTTPException:
    """H4: an undone top-up stays undone, so changing or undoing it again is a conflict."""
    return HTTPException(status_code=409, detail=str(exc))


def _found_topup(topup: TopUp | None) -> dict[str, Any]:
    if topup is None:
        raise HTTPException(status_code=404, detail=TOPUP_NOT_FOUND_TEXT)
    return topup_out(topup)


async def _project_answer(service: ProjectService, user_id: str, project_id: str) -> dict[str, Any]:
    """``ProjectOut`` for a project just created or changed, with its numbers."""
    detail = await service.detail(user_id, project_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=PROJECT_NOT_FOUND_TEXT)
    return project_out(detail.project, detail.numbers, detail.progress)


@projects_router.get("/api/projects")
async def list_projects(request: Request, user: CurrentUser, include_archived: bool = False):
    """The Projects tab: General hidden, archived projects only when asked for."""
    rows = await _service(request).list(user.id, include_archived=include_archived)
    return [project_out(project, numbers, progress) for project, numbers, progress in rows]


@projects_router.post("/api/projects", status_code=201, dependencies=[RequireOrigin])
async def create_project(body: ProjectIn, request: Request, user: CurrentUser):
    service = _service(request)
    try:
        project = await service.create(user.id, body.draft())
    except ValueError as exc:
        raise _unreadable(exc) from exc
    return await _project_answer(service, user.id, project.id)


@projects_router.get("/api/projects/{project_id}")
async def get_project(project_id: str, request: Request, user: CurrentUser):
    detail = await _service(request).detail(user.id, project_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=PROJECT_NOT_FOUND_TEXT)
    return project_detail_out(detail)


@projects_router.patch("/api/projects/{project_id}", dependencies=[RequireOrigin])
async def update_project(project_id: str, body: ProjectPatchIn, request: Request, user: CurrentUser):
    service = _service(request)
    try:
        project = await service.update(user.id, project_id, body.changes())
    except ValueError as exc:
        raise _refused(exc) from exc
    if project is None:
        raise HTTPException(status_code=404, detail=PROJECT_NOT_FOUND_TEXT)
    return await _project_answer(service, user.id, project.id)


@projects_router.delete("/api/projects/{project_id}", status_code=204, dependencies=[RequireOrigin])
async def delete_project(project_id: str, request: Request, user: CurrentUser) -> None:
    """H9: the expenses move to General; the tasks, notes and documents stay, unlinked."""
    try:
        deleted = await _service(request).delete(user.id, project_id)
    except ValueError as exc:   # General (H2)
        raise _unreadable(exc) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail=PROJECT_NOT_FOUND_TEXT)


@projects_router.put("/api/projects/{project_id}/budget", dependencies=[RequireOrigin])
async def set_project_budget(project_id: str, body: BudgetIn, request: Request, user: CurrentUser):
    """Set the total budget, or clear it with ``null`` (P3, H5). The history
    gets a "Budget set" row, and ``money_changed`` carries ``budget_set``."""
    service = _service(request)
    try:
        project = await service.set_budget(user.id, project_id, _amount(body.amount))
    except ValueError as exc:   # the amount, or General (H2)
        raise _unreadable(exc) from exc
    if project is None:
        raise HTTPException(status_code=404, detail=PROJECT_NOT_FOUND_TEXT)
    return await _project_answer(service, user.id, project.id)


@projects_router.get("/api/projects/{project_id}/topups")
async def list_topups(project_id: str, request: Request, user: CurrentUser):
    """The top-up history, newest first, undone rows included."""
    topups = await _service(request).topups(user.id, project_id)
    if topups is None:
        raise HTTPException(status_code=404, detail=PROJECT_NOT_FOUND_TEXT)
    return [topup_out(topup) for topup in topups]


@projects_router.post("/api/projects/{project_id}/topups", status_code=201, dependencies=[RequireOrigin])
async def add_topup(project_id: str, body: TopupIn, request: Request, user: CurrentUser):
    try:
        topup = await _service(request).add_topup(user.id, project_id, parse_amount(body.amount), body.source)
    except ValueError as exc:   # the amount, or a source too long once trimmed
        raise _unreadable(exc) from exc
    if topup is None:
        raise HTTPException(status_code=404, detail=PROJECT_NOT_FOUND_TEXT)
    return topup_out(topup)


@projects_router.patch("/api/topups/{topup_id}", dependencies=[RequireOrigin])
async def edit_topup(topup_id: str, body: TopupEditIn, request: Request, user: CurrentUser):
    """``amount`` is the top-up's new amount; the store records the difference (H4)."""
    try:
        topup = await _service(request).edit_topup(user.id, topup_id, parse_amount(body.amount))
    except TopUpUndone as exc:   # a ValueError too, so it is caught first
        raise _undone(exc) from exc
    except ValueError as exc:    # the amount, or a total budget that is cleared or would go below 0
        raise _unreadable(exc) from exc
    return _found_topup(topup)


@projects_router.post("/api/topups/{topup_id}/undo", dependencies=[RequireOrigin])
async def undo_topup(topup_id: str, request: Request, user: CurrentUser):
    """The top-up and its edits leave the budget together (H4)."""
    try:
        topup = await _service(request).undo_topup(user.id, topup_id)
    except TopUpUndone as exc:   # a ValueError too, so it is caught first
        raise _undone(exc) from exc
    except ValueError as exc:    # a total budget that is cleared or would go below 0
        raise _unreadable(exc) from exc
    return _found_topup(topup)
```

- [ ] **Step 5: Wire the gateway (`roost/gateway/app.py`, after the stuck flow)**

These four anchors are lines the stuck flow does not edit. Task 1 changed only the `category_store` import and the `app.state.money` line.

Find:

```python
from roost.gateway.routes.profile import profile_router
from roost.gateway.routes.rooms import rooms_router
```

Replace with:

```python
from roost.gateway.routes.profile import profile_router
from roost.gateway.routes.projects import projects_router
from roost.gateway.routes.rooms import rooms_router
```

Find:

```python
from roost.notes.store import NoteStore
from roost.rooms.service import RoomService
```

Replace with:

```python
from roost.notes.store import NoteStore
from roost.projects.service import ProjectService
from roost.rooms.service import RoomService
```

Find:

```python
    app.state.documents = DocumentService(DocumentStore(resolved_config), app.state.events)
    app.state.rooms = RoomStore(resolved_config)
```

Replace with:

```python
    app.state.documents = DocumentService(DocumentStore(resolved_config), app.state.events)
    # Projects hub (P1, H10): the Projects tab and a project's page. Stores hold no state, so these
    # instances share the database with the money, task, note and document services above.
    app.state.projects = ProjectService(
        ProjectStore(resolved_config), ExpenseStore(resolved_config), TaskStore(resolved_config),
        NoteStore(resolved_config), DocumentStore(resolved_config), app.state.bots, app.state.events,
    )
    app.state.rooms = RoomStore(resolved_config)
```

Find:

```python
    app.include_router(money_router)
    app.include_router(notes_router)
```

Replace with:

```python
    app.include_router(money_router)
    app.include_router(projects_router)
    app.include_router(notes_router)
```

`ProjectStore`, `ExpenseStore`, `TaskStore`, `NoteStore`, `DocumentStore` and `BotStore` (`app.state.bots`) are already imported, `ProjectStore` since Task 1. `mount_static_if_built(app)` stays last, so the static mount never shadows `/api/projects` or `/api/topups`.

- [ ] **Step 6: Star, void, and an expense named by project id (`roost/gateway/routes/money.py`, after Task 1; it calls Task 7's `log_expense`)**

Find (Task 1's imports, router and `ExpenseIn`):

```python
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from roost.constants import CURRENCY_PATTERN, DEFAULT_CURRENCY, MAX_CATEGORY_NAME_LENGTH, MAX_DUE_TEXT_LENGTH, MAX_EXPENSE_NOTE_LENGTH
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.money.amounts import parse_amount
from roost.money.months import current_month, month_bounds, parse_spent_at
from roost.money.service import ExpenseEntry, MoneyService
from roost.money.summary import expense_row, summary_out

money_router = APIRouter(prefix="/api/money", tags=["money"])


class ExpenseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: str | int | float
    project: str | None = Field(default=None, max_length=MAX_CATEGORY_NAME_LENGTH)   # a name; none: General
    note: str | None = Field(default=None, max_length=MAX_EXPENSE_NOTE_LENGTH)
    currency: str = Field(default=DEFAULT_CURRENCY, pattern=CURRENCY_PATTERN)
    spent_at: str | None = Field(default=None, max_length=MAX_DUE_TEXT_LENGTH)
```

Replace with:

```python
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from roost.constants import (
    CURRENCY_PATTERN, MAX_CATEGORY_NAME_LENGTH, MAX_DUE_TEXT_LENGTH, MAX_EXPENSE_NOTE_LENGTH, MAX_RECORD_ID_LENGTH,
)
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.money.amounts import parse_amount
from roost.money.models import EXPENSE_POSTED, EXPENSE_VOID, ExpensePatch, Project
from roost.money.months import current_month, month_bounds, parse_spent_at
from roost.money.service import ExpenseEntry, MoneyService
from roost.money.summary import expense_row, summary_out
from roost.records.project_link import NO_SUCH_PROJECT_TEXT

money_router = APIRouter(prefix="/api/money", tags=["money"])
EXPENSE_NOT_FOUND_TEXT = "Expense not found"
ONE_PROJECT_TEXT = "Name the project or send its id, not both."


class ExpenseIn(BaseModel):
    """``project`` names a project (none: General). A project's page may send
    ``project_id`` instead. With no currency, the expense takes its project's
    currency, however the project was named (H7, Task 7's ``ExpenseEntry``)."""

    model_config = ConfigDict(extra="forbid")
    amount: str | int | float
    project: str | None = Field(default=None, max_length=MAX_CATEGORY_NAME_LENGTH)
    project_id: str | None = Field(default=None, max_length=MAX_RECORD_ID_LENGTH)
    note: str | None = Field(default=None, max_length=MAX_EXPENSE_NOTE_LENGTH)
    currency: str | None = Field(default=None, pattern=CURRENCY_PATTERN)
    spent_at: str | None = Field(default=None, max_length=MAX_DUE_TEXT_LENGTH)

    @model_validator(mode="after")
    def _one_way_to_name_the_project(self) -> "ExpenseIn":
        if self.project is not None and self.project_id is not None:
            raise ValueError(ONE_PROJECT_TEXT)
        return self


class StarIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    starred: StrictBool


class VoidIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    void: StrictBool
```

Find (Task 1's `add_expense`, the last route in the file):

```python
@money_router.post("/expenses", status_code=201, dependencies=[RequireOrigin])
async def add_expense(body: ExpenseIn, request: Request, user: CurrentUser):
    try:
        entry = ExpenseEntry(amount=parse_amount(body.amount), spent_at=parse_spent_at(body.spent_at),
                             project=body.project, note=body.note, currency=body.currency)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    expense, project = await _service(request).log_expense(user.id, entry)
    return expense_row(expense, project)
```

Replace with:

```python
async def _project_by_id(service: MoneyService, user_id: str, project_id: str) -> Project:
    """One of the user's projects, archived ones included. ``ValueError``: not one of theirs."""
    found = {project.id: project for project in await service.projects(user_id)}
    if project_id not in found:
        raise ValueError(NO_SUCH_PROJECT_TEXT)
    return found[project_id]


@money_router.post("/expenses", status_code=201, dependencies=[RequireOrigin])
async def add_expense(body: ExpenseIn, request: Request, user: CurrentUser):
    """A project named by id gets exactly that project (Task 7's ``project=``);
    one named by name is found or made, as before. An archived project
    refuses (H3, ``ARCHIVED_TEXT``), so ``log_expense`` runs inside the ``try``."""
    service = _service(request)
    try:
        entry = ExpenseEntry(amount=parse_amount(body.amount), spent_at=parse_spent_at(body.spent_at),
                             project=body.project, note=body.note, currency=body.currency)
        project = await _project_by_id(service, user.id, body.project_id) if body.project_id else None
        expense, target = await service.log_expense(user.id, entry, project=project)
    except ValueError as exc:   # an amount, a day, or a project it can't use
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return expense_row(expense, target)


async def _changed_row(request: Request, user_id: str, expense_id: str, changes: dict[str, Any]) -> dict[str, Any]:
    """Apply one change from the Board and answer with the expense's row."""
    service = _service(request)
    try:
        expense = await service.update_expense(user_id, expense_id, ExpensePatch(changes))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if expense is None:
        raise HTTPException(status_code=404, detail=EXPENSE_NOT_FOUND_TEXT)
    projects = {project.id: project for project in await service.projects(user_id)}
    return expense_row(expense, projects.get(expense.project_id))


@money_router.put("/expenses/{expense_id}/star", dependencies=[RequireOrigin])
async def star_expense(expense_id: str, body: StarIn, request: Request, user: CurrentUser):
    """Star or unstar (P6). A starred expense counts in its project's starred total."""
    return await _changed_row(request, user.id, expense_id, {"is_favorite": body.starred})


@money_router.put("/expenses/{expense_id}/void", dependencies=[RequireOrigin])
async def void_expense(expense_id: str, body: VoidIn, request: Request, user: CurrentUser):
    """Void, or post again (H6). A void expense stays listed and leaves every sum."""
    status = EXPENSE_VOID if body.void else EXPENSE_POSTED
    return await _changed_row(request, user.id, expense_id, {"status": status})
```

- [ ] **Step 7: Failed tasks, the project link and the budget slice (`roost/gateway/routes/tasks.py`)**

Replace the whole of `roost/gateway/routes/tasks.py`. Step 1 showed it unchanged since `4aecbc3`. The `complete`, `keep` and `delete` routes are carried over as they were:

```python
"""Tasks over HTTP — the Board's data (M1 D8). Same ``TaskService`` as the
tools, so every change publishes ``tasks_changed``.

Projects hub (H11): a task may join one of the user's projects and carry a
budget slice in that project's currency. A project that isn't the user's is
refused (422, "No such project."), ``?project_id=`` lists one project's tasks,
and ``POST /{id}/fail`` closes an open task as failed."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from roost.constants import (
    MAX_DUE_TEXT_LENGTH, MAX_PRE_REMINDERS, MAX_RECORD_ID_LENGTH, MAX_TASK_CATEGORY_LENGTH, MAX_TASK_NOTES_LENGTH,
    MAX_TASK_TITLE_LENGTH,
)
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.money.amounts import parse_amount
from roost.tasks.due import build_schedule, patch_from_fields
from roost.tasks.format import task_out
from roost.tasks.models import Priority, TaskDraft, TaskFilter
from roost.tasks.service import TaskService

tasks_router = APIRouter(prefix="/api/tasks", tags=["tasks"])
NO_OPEN_TASK_TEXT = "No open task with that id"
Amount = str | int | float


class TaskIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=MAX_TASK_TITLE_LENGTH)
    description: str | None = Field(default=None, max_length=MAX_TASK_NOTES_LENGTH)
    category: str | None = Field(default=None, max_length=MAX_TASK_CATEGORY_LENGTH)
    priority: Priority = "medium"
    due_date: str | None = Field(default=None, max_length=MAX_DUE_TEXT_LENGTH)
    pre_reminders: list[str] | None = Field(default=None, max_length=MAX_PRE_REMINDERS)
    project_id: str | None = Field(default=None, max_length=MAX_RECORD_ID_LENGTH)
    allocated_budget: Amount | None = None      # the budget slice, in the project's currency; needs a project


class TaskPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, max_length=MAX_TASK_TITLE_LENGTH)
    description: str | None = Field(default=None, max_length=MAX_TASK_NOTES_LENGTH)
    category: str | None = Field(default=None, max_length=MAX_TASK_CATEGORY_LENGTH)
    priority: Priority | None = None
    status: Literal["todo", "in_progress", "cancelled"] | None = None
    due_date: str | None = Field(default=None, max_length=MAX_DUE_TEXT_LENGTH)
    project_id: str | None = Field(default=None, max_length=MAX_RECORD_ID_LENGTH)   # null unlinks
    allocated_budget: Amount | None = None                                           # null clears the slice


def _service(request: Request) -> TaskService:
    return request.app.state.tasks


def _unreadable(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


def _slice(amount: Amount | None) -> Decimal | None:
    """A budget slice follows ``parse_amount``'s rules; ``None`` is no slice."""
    return None if amount is None else parse_amount(amount)


def _draft(body: TaskIn) -> TaskDraft:
    """Raises ``ValueError`` (plain text) for a due date or a slice it can't read."""
    schedule = build_schedule(body.due_date, None, body.pre_reminders)
    return TaskDraft(title=body.title.strip(), description=body.description, category=body.category,
                     priority=body.priority, due_date=schedule.due_date, reminder_at=schedule.reminder_at,
                     pre_reminders=schedule.pre_reminders, project_id=body.project_id,
                     allocated_budget=_slice(body.allocated_budget))


def _patch_fields(body: TaskPatchIn) -> dict[str, Any]:
    fields = body.model_dump(include=body.model_fields_set)
    if "allocated_budget" in fields:
        return {**fields, "allocated_budget": _slice(fields["allocated_budget"])}
    return fields


@tasks_router.get("")
async def list_tasks(request: Request, user: CurrentUser, status: TaskFilter = "open",
                     project_id: str | None = Query(default=None, max_length=MAX_RECORD_ID_LENGTH)):
    """``project_id`` keeps one project's tasks; an empty one is no filter."""
    tasks = await _service(request).list(user.id, status=status, project_id=project_id or None)
    return [task_out(task) for task in tasks]


@tasks_router.post("", status_code=201, dependencies=[RequireOrigin])
async def create_task(body: TaskIn, request: Request, user: CurrentUser):
    try:
        return task_out(await _service(request).add(user.id, _draft(body)))
    except ValueError as exc:   # a due date or slice it can't read, or not one of the user's projects
        raise _unreadable(exc) from exc


@tasks_router.patch("/{task_id}", dependencies=[RequireOrigin])
async def update_task(task_id: str, body: TaskPatchIn, request: Request, user: CurrentUser):
    try:
        task = await _service(request).update(user.id, task_id, patch_from_fields(_patch_fields(body)))
    except ValueError as exc:   # also the store's "No such project." and "A budget slice needs a project."
        raise _unreadable(exc) from exc
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task_out(task)


@tasks_router.post("/{task_id}/complete", dependencies=[RequireOrigin])
async def complete_task(task_id: str, request: Request, user: CurrentUser):
    completion = await _service(request).complete(user.id, task_id)
    if completion is None:
        raise HTTPException(status_code=404, detail=NO_OPEN_TASK_TEXT)
    return task_out(completion.done)


@tasks_router.post("/{task_id}/fail", dependencies=[RequireOrigin])
async def fail_task(task_id: str, request: Request, user: CurrentUser):
    """Close an open task as failed (H11). As with complete, a recurring task
    comes back for its next time; the answer is the failed task."""
    failure = await _service(request).fail(user.id, task_id)
    if failure is None:
        raise HTTPException(status_code=404, detail=NO_OPEN_TASK_TEXT)
    return task_out(failure.done)


@tasks_router.post("/{task_id}/keep", dependencies=[RequireOrigin])
async def keep_task(task_id: str, request: Request, user: CurrentUser):
    """Keep: the user vouches for a task marked "from web content" — they
    are trusted here, so its taint bit is cleared (no tool can do this)."""
    task = await _service(request).keep(user.id, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task_out(task)


@tasks_router.delete("/{task_id}", status_code=204, dependencies=[RequireOrigin])
async def delete_task(task_id: str, request: Request, user: CurrentUser) -> None:
    if not await _service(request).delete(user.id, task_id):
        raise HTTPException(status_code=404, detail="Task not found")
```

- [ ] **Step 8: Notes join projects (`roost/gateway/routes/notes.py`, `roost/notes/format.py`)**

Replace the whole of `roost/gateway/routes/notes.py`. Step 1 showed it unchanged since `4aecbc3`. `NoteSaveIn`, `get`, `keep` and `delete` are carried over as they were, and the 409 body moves into `_conflict`:

```python
"""Notes over HTTP — the Board's Notes tab (M2 D4). Same ``NoteService`` as the
tools, so every change publishes ``notes_changed``. A save carries the revision
it edited; a stale one is a 409 carrying the current note (never an overwrite).

Projects hub (H12): a note may belong to one of the user's projects.
``PUT /{id}/project`` links or unlinks it without a new revision, so an open
editor's next save still lands, and ``?project_id=`` lists one project's
notes. A project that isn't the user's is refused (422, "No such project.")."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from roost.constants import (
    MAX_NOTE_CONTENT_LENGTH, MAX_NOTE_QUERY_LENGTH, MAX_NOTE_TAG_LENGTH, MAX_NOTE_TAGS, MAX_NOTE_TITLE_LENGTH,
    MAX_RECORD_ID_LENGTH,
)
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.gateway.routes.projects import ProjectLinkIn
from roost.notes.format import note_out, note_summary_out
from roost.notes.models import Note
from roost.notes.service import NoteService, new_note_draft
from roost.records.revision import RevisionConflict

notes_router = APIRouter(prefix="/api/notes", tags=["notes"])
NOTE_CONFLICT_TEXT = "This note changed since you opened it."
NOTE_NOT_FOUND_TEXT = "Note not found"
Tag = Annotated[str, Field(min_length=1, max_length=MAX_NOTE_TAG_LENGTH)]


class NoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, max_length=MAX_NOTE_TITLE_LENGTH)
    content: str = Field(default="", max_length=MAX_NOTE_CONTENT_LENGTH)
    tags: list[Tag] = Field(default_factory=list, max_length=MAX_NOTE_TAGS)
    project_id: str | None = Field(default=None, max_length=MAX_RECORD_ID_LENGTH)

    @model_validator(mode="after")
    def _title_or_text(self) -> "NoteIn":
        if not (self.title or "").strip() and not self.content.strip():
            raise ValueError("A note needs a title or some text.")
        return self


class NoteSaveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_revision: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=MAX_NOTE_TITLE_LENGTH)
    content: str | None = Field(default=None, max_length=MAX_NOTE_CONTENT_LENGTH)
    tags: list[Tag] | None = Field(default=None, max_length=MAX_NOTE_TAGS)
    pinned: bool | None = None

    def changes(self) -> dict[str, Any]:
        fields = self.model_dump(exclude={"base_revision"}, exclude_none=True)
        if "tags" in fields:
            fields = {**fields, "tags": tuple(fields["tags"])}
        if "title" in fields:
            fields = {**fields, "title": fields["title"].strip()}
        return fields


def _service(request: Request) -> NoteService:
    return request.app.state.notes


async def _detail(service: NoteService, user_id: str, note: Note) -> dict:
    return note_out(note, await service.links(user_id, note))


async def _conflict(service: NoteService, user_id: str, exc: RevisionConflict) -> JSONResponse:
    """A stale write never overwrites: 409 with the note as it is now."""
    return JSONResponse(status_code=409, content={"detail": NOTE_CONFLICT_TEXT,
                                                  "current": await _detail(service, user_id, exc.current)})


def _missing() -> HTTPException:
    return HTTPException(status_code=404, detail=NOTE_NOT_FOUND_TEXT)


@notes_router.get("")
async def list_notes(request: Request, user: CurrentUser,
                     q: str = Query(default="", max_length=MAX_NOTE_QUERY_LENGTH),
                     tag: str | None = Query(default=None, max_length=MAX_NOTE_TAG_LENGTH),
                     project_id: str | None = Query(default=None, max_length=MAX_RECORD_ID_LENGTH)):
    """``project_id`` keeps one project's notes; an empty one is no filter, like ``tag``."""
    notes = await _service(request).search(user.id, q, tag=tag, project_id=project_id or None)
    return [note_summary_out(note, q) for note in notes]


@notes_router.get("/{note_id}")
async def get_note(note_id: str, request: Request, user: CurrentUser):
    note = await _service(request).get(user.id, note_id)
    if note is None:
        raise _missing()
    return await _detail(_service(request), user.id, note)


@notes_router.post("", status_code=201, dependencies=[RequireOrigin])
async def create_note(body: NoteIn, request: Request, user: CurrentUser):
    service = _service(request)
    draft = new_note_draft(body.title, body.content, body.tags, project_id=body.project_id)
    try:
        note = await service.add(user.id, draft)
    except ValueError as exc:   # not one of the user's projects
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return await _detail(service, user.id, note)


@notes_router.put("/{note_id}", dependencies=[RequireOrigin])
async def save_note(note_id: str, body: NoteSaveIn, request: Request, user: CurrentUser):
    service = _service(request)
    try:
        note = await service.save(user.id, note_id, body.changes(), base_revision=body.base_revision)
    except RevisionConflict as exc:
        return await _conflict(service, user.id, exc)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if note is None:
        raise _missing()
    return await _detail(service, user.id, note)


@notes_router.put("/{note_id}/project", dependencies=[RequireOrigin])
async def set_note_project(note_id: str, body: ProjectLinkIn, request: Request, user: CurrentUser):
    """Link the note to one of the user's projects, or unlink it (``null``).
    The revision stays, so an open editor's next save still lands (H12)."""
    service = _service(request)
    try:
        note = await service.set_project(user.id, note_id, body.project_id)
    except RevisionConflict as exc:   # two saves landed during the link (rare)
        return await _conflict(service, user.id, exc)
    except ValueError as exc:         # not one of the user's projects
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if note is None:
        raise _missing()
    return await _detail(service, user.id, note)


@notes_router.post("/{note_id}/keep", dependencies=[RequireOrigin])
async def keep_note(note_id: str, request: Request, user: CurrentUser):
    """Keep: the user vouches for a note marked "from web content" (no tool can)."""
    note = await _service(request).keep(user.id, note_id)
    if note is None:
        raise _missing()
    return await _detail(_service(request), user.id, note)


@notes_router.delete("/{note_id}", status_code=204, dependencies=[RequireOrigin])
async def delete_note(note_id: str, request: Request, user: CurrentUser) -> None:
    if not await _service(request).delete(user.id, note_id):
        raise _missing()
```

In `roost/notes/format.py` (Tasks 5 and 7 leave this function alone), find:

```python
        "pinned": note.pinned, "revision": note.revision, "created_at": note.created_at,
        "updated_at": note.updated_at, "created_by_bot": note.created_by_bot, "tainted": note.tainted,
    }
```

Replace with:

```python
        "pinned": note.pinned, "revision": note.revision, "created_at": note.created_at,
        "updated_at": note.updated_at, "created_by_bot": note.created_by_bot, "tainted": note.tainted,
        "project_id": note.project_id,
    }
```

`note_out` spreads `note_summary_out`, so every note route, and the Profile's made-by list, now carry `project_id`.

- [ ] **Step 9: Documents join projects (`roost/gateway/routes/documents.py`, `roost/documents/format.py`)**

In `roost/gateway/routes/documents.py`, find:

```python
from roost.constants import (
    MAX_DOC_MARKDOWN_LENGTH, MAX_DOCUMENT_PAYLOAD_CHARS, MAX_DOCUMENT_TITLE_LENGTH, MAX_PDF_BYTES,
)
```

Replace with:

```python
from roost.constants import (
    MAX_DOC_MARKDOWN_LENGTH, MAX_DOCUMENT_PAYLOAD_CHARS, MAX_DOCUMENT_TITLE_LENGTH, MAX_PDF_BYTES,
    MAX_RECORD_ID_LENGTH,
)
```

Find:

```python
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.records.revision import RevisionConflict
```

Replace with:

```python
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.gateway.routes.projects import ProjectLinkIn
from roost.records.revision import RevisionConflict
```

Find:

```python
    markdown: str = Field(default="", max_length=MAX_DOC_MARKDOWN_LENGTH)
    rows: SheetRows | None = None
```

Replace with:

```python
    markdown: str = Field(default="", max_length=MAX_DOC_MARKDOWN_LENGTH)
    rows: SheetRows | None = None
    project_id: str | None = Field(default=None, max_length=MAX_RECORD_ID_LENGTH)   # one of the user's (H12)
```

Find:

```python
@documents_router.get("")
async def list_documents(request: Request, user: CurrentUser, kind: DocumentKind | None = None):
    return [document_out(meta) for meta in await _service(request).list(user.id, kind)]
```

Replace with:

```python
@documents_router.get("")
async def list_documents(request: Request, user: CurrentUser, kind: DocumentKind | None = None,
                         project_id: str | None = Query(default=None, max_length=MAX_RECORD_ID_LENGTH)):
    """``project_id`` keeps one project's documents (H12); an empty one is no filter."""
    metas = await _service(request).list(user.id, kind, project_id=project_id or None)
    return [document_out(meta) for meta in metas]
```

Find:

```python
@documents_router.post("", status_code=201, dependencies=[RequireOrigin])
async def create_document(body: DocumentCreateIn, request: Request, user: CurrentUser):
    service = _service(request)
    if body.kind == "doc":
        return document_out(await service.create_doc(user.id, body.title.strip(), body.markdown))
    return document_out(await service.create_sheet(user.id, body.title.strip(), body.rows or []))
```

Replace with:

```python
@documents_router.post("", status_code=201, dependencies=[RequireOrigin])
async def create_document(body: DocumentCreateIn, request: Request, user: CurrentUser):
    service, title = _service(request), body.title.strip()
    try:
        if body.kind == "doc":
            meta = await service.create_doc(user.id, title, body.markdown, project_id=body.project_id)
        else:
            meta = await service.create_sheet(user.id, title, body.rows or [], project_id=body.project_id)
    except ValueError as exc:   # not one of the user's projects
        raise _unreadable(exc) from exc
    return document_out(meta)
```

Find:

```python
@documents_router.post("/{document_id}/keep", dependencies=[RequireOrigin])
```

Replace with:

```python
@documents_router.put("/{document_id}/project", dependencies=[RequireOrigin])
async def set_document_project(document_id: str, body: ProjectLinkIn, request: Request, user: CurrentUser):
    """Link the document to one of the user's projects, or unlink it
    (``null``). The revision stays, so an open editor's next autosave still
    lands (H12)."""
    try:
        meta = await _service(request).set_project(user.id, document_id, body.project_id)
    except ValueError as exc:   # not one of the user's projects
        raise _unreadable(exc) from exc
    if meta is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document_out(meta)


@documents_router.post("/{document_id}/keep", dependencies=[RequireOrigin])
```

In `roost/documents/format.py` (Tasks 5 and 7 leave this function alone), find:

```python
        "created_at": meta.created_at, "updated_at": meta.updated_at, "created_by_bot": meta.created_by_bot,
        "tainted": meta.tainted,
    }
```

Replace with:

```python
        "created_at": meta.created_at, "updated_at": meta.updated_at, "created_by_bot": meta.created_by_bot,
        "tainted": meta.tainted, "project_id": meta.project_id,
    }
```

`document_detail_out` spreads `document_out`, so `GET /api/documents/{id}` carries `project_id` too.

- [ ] **Step 10: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_projects_api.py tests/test_money_api.py tests/test_tasks_api.py tests/test_notes_api.py tests/test_documents_api.py -q`

Expected: PASS, `61 passed`:
- `test_projects_api.py`: 14;
- `test_money_api.py`: 9;
- `test_tasks_api.py`: 9;
- `test_notes_api.py`: 11;
- `test_documents_api.py`: 18.

Check the coverage of the new and changed routes:

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_projects_api.py tests/test_money_api.py tests/test_tasks_api.py tests/test_notes_api.py tests/test_documents_api.py --cov=roost.gateway.routes.projects --cov=roost.gateway.routes.money --cov=roost.gateway.routes.tasks --cov=roost.gateway.routes.notes --cov=roost.gateway.routes.documents --cov-report=term-missing -q`

Expected: PASS, with each module at 80% or more. `roost/gateway/routes/projects.py` should be at or near 100%. Two lines may stay uncovered:
- `_project_answer`'s 404, a project deleted between its write and its read-back;
- `_changed_row`'s 422, which only a later rule in `MoneyService.update_expense` could raise.

The related existing tests must stay green. These read the same services, the reshaped wire (`project_id` on notes and documents) or the gateway wiring:

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_project_service.py tests/test_task_projects.py tests/test_notes_docs_projects.py tests/test_profile_api.py tests/test_money_store.py tests/test_money_summary.py tests/test_task_store.py tests/test_note_store.py tests/test_document_store.py tests/test_stuck_api.py tests/test_static.py tests/test_deps.py tests/test_vocabulary.py -q`

Expected: PASS.

Run the full suite with the coverage gate:

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest --cov=roost --cov-fail-under=80 -q`

Expected: PASS.

- [ ] **Step 11: Commit**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost
git add roost/gateway/routes/projects.py roost/gateway/app.py roost/gateway/routes/money.py \
  roost/gateway/routes/tasks.py roost/gateway/routes/notes.py roost/gateway/routes/documents.py \
  roost/notes/format.py roost/documents/format.py \
  tests/test_projects_api.py tests/test_money_api.py tests/test_tasks_api.py tests/test_notes_api.py \
  tests/test_documents_api.py
git status --short   # nothing from this task may still be listed as modified or untracked
git commit -m "feat: projects over HTTP: the project list and page, the total budget, top-ups, star and void, failed tasks and project links"
```

The message has no Co-Authored-By line and no AI attribution.

---

### Task 9: The web: Projects tab, project page, bars, top-ups, star, void and failed

This task is the web side of P1–P7, following H14 (which overrides §3), H4 (the history labels), H6 (void rows stay visible), H8 (bars from the server's numbers), H9 (the delete copy), H10 (the `money_changed` values), H11 (failed, the budget slice) and H16 (the palette). In short:
- **Projects is the Board's first and default tab.** `ProjectsBoard` is an eager named export. It lists every project except General, each with its tasks ("3 of 5 done", failed ones apart in red) and a `role="meter"` `BudgetBar` for each budget it has. It has a "New project" form, and "Show archived" lists archived projects too.
- **A project's page** lives at `/board/projects/:projectId`, and `/board/projects` goes to `/board?tab=projects`.
  - The top shows the lead bot, the dates, progress, both budgets, the starred total and other currencies.
  - Its buttons are Edit (`ProjectEditForm`), Archive/Unarchive and Delete. Delete uses `DocumentRow`'s two-step confirmation with the copy "Its expenses move to General; its tasks, notes and documents stay, just unlinked."
  - Edit also has a **Total budget** field (P3, H5), filled with the server's total (top-ups included). Left empty it clears the total. Save sends it through `setProjectBudget` (`PUT /api/projects/{id}/budget`) only when it changed; the other fields keep going through `updateProject`, and only what changed is sent there too.
  - Sub-tabs Tasks · Money · Notes · Docs sit on `?tab=`. Notes and Docs stay lazy chunks through the extracted `board/lazyPanel.tsx`.
- **Money tab:** `TopupForm` and `TopupHistory` (Top-up / Top-up changed / Budget set, with Change and Undo on a live top-up), then `MoneyBoard` narrowed to the project: its month's expenses, its own spent, and an add form fixed to the project. That form sends the project's id, so the expense lands in the project's currency (H7).
- **Expenses:** the list moves to `board/ExpenseList.tsx`. It has a star toggle and Void/Restore whenever `onStar`/`onVoid` are given, which the Money tab and the project page both do. A void row stays in the list, marked "void", with its amount struck through.
- **Tasks:**
  - On a project page, `TasksBoard` lists **every** task of the project, open ones first. A finished task carries a `done`, `failed` (red `board-chip--failed`) or `cancelled` chip.
  - The edit form gets **Mark failed** (any open task) and, for a task in a project, a **Budget slice** field.
  - On a project page each task also shows what is spent on it and what is left (`ProjectDetailOut.task_money`, design §2's planned / spent / left), formatted from the server's strings.
  - The Board's own Tasks tab still lists open tasks only.
- **Live:** `money_changed` with `project_deleted` also bumps `boardVersion.tasks`, `.notes` and `.documents` (Review Focus 4), so open tabs reload the items it unlinked.
- **The web never adds amounts.** Every number is the server's string, only formatted here (`formatMoney`, `signedMoney`). The one exception is the bar width, which clamps the server's `used_percent` to 0–100.

Snippets marked **(after Task 1)** are written against Task 1's Category → Project rename. Snippets marked **(after the stuck flow)** are written against the stuck-flow plan's Task 8, which edits `web/src/api/types.ts` (`MessageKind`, after `CreatedCardData`, after `DocumentsChangedFrame`, `ServerFrame`), `web/src/store/live.ts` (the header comment, the import, `LiveState`/`initialLiveState`, the `documents_changed` case) and the end of `web/tests/live.test.ts`. None of the anchors below are those lines. `web/e2e/records.spec.ts` still expects Tasks to be the Board's default tab. Task 10 updates it, so `make e2e` is not run here.

**Files:**
- Create:
  - `web/src/api/projects.ts`: `ProjectIn`, `ProjectPatchIn`, `TopupIn`, `listProjects`, `getProject`, `createProject`, `updateProject`, `setProjectBudget`, `deleteProject`, `listTopups`, `addTopup`, `editTopup` and `undoTopup`
  - `web/src/components/board/ExpenseList.tsx` (extracted from `MoneyBoard.tsx`, plus star and void)
  - `web/src/components/board/lazyPanel.tsx` (`lazyPanel`, `PanelProps`; extracted from `Board.tsx`, now passes props)
  - `web/src/components/projects/projects.ts` (the limits and palette mirrored from `roost/constants.py`, plus the label helpers)
  - `web/src/components/projects/BudgetBar.tsx`, `ProjectRow.tsx` (`ProjectRow`, `ProgressLine`), `ProjectsBoard.tsx`, `ProjectEditForm.tsx`, `TopupForm.tsx`, `TopupHistory.tsx`, `ProjectSummary.tsx`, `ProjectActions.tsx` and `ProjectMoney.tsx`
  - `web/src/pages/Project.tsx` (`Project`, `ToProjectsTab`, `TABS`, `ProjectTab`)
  - `web/src/styles/projects.css`
- Modify:
  - `web/src/api/types.ts`:
    - `BoardTab` gains `"projects"` (first);
    - `TaskOut` gains `failed`, `project_id` and `allocated_budget`;
    - `ExpenseOut` gains `task_id`, `step_id`, `status: "posted" | "void"` and `is_favorite`;
    - `ProjectTotalOut` takes Task 3's wire;
    - new `BudgetTone`, `BudgetLineOut`, `ProjectProgressOut`, `ProjectOut`, `TaskMoneyOut`, `ProjectDetailOut` (with `task_money`) and `TopupOut`;
    - `NoteSummaryOut` and `DocumentOut` gain `project_id`;
    - `TasksChangedFrame.change` gains `failed`;
    - `MoneyChangedFrame.change` gains the H10 values.
  - `web/src/api/money.ts`: `ExpenseIn.project_id`, `starExpense` and `voidExpense`.
  - `web/src/api/tasks.ts` (whole file):
    - `TaskIn.project_id` and `TaskPatchIn.allocated_budget`;
    - `listTasks(status, filter?)` with `"failed"` and `"all"`;
    - `failTask`.
  - `web/src/api/notes.ts` (whole file): `NoteIn.project_id` and `listNotes(query, filter?)`.
  - `web/src/api/documents.ts` (whole file): `listDocuments(kind?, filter?)`, `createDocument` with `project_id`, and `setDocumentProject`.
  - `web/src/store/live.ts`: `bumpMoney`, and the `money_changed` case.
  - `web/src/components/board/money.ts`: `AMOUNT_HELP` and `readAmount`.
  - `web/src/components/board/ExpenseAddForm.tsx`: `fixedProjectId` (a project's page sends the project's id, so the expense takes that project's currency, H7), `ProjectField` and `AMOUNT_HELP`.
  - `web/src/components/board/MoneyBoard.tsx` (whole file):
    - `project?` narrows it to one project;
    - each row is shown in its own currency against its monthly limit;
    - star and void.
  - `web/src/components/board/TasksBoard.tsx`, `TaskRow.tsx`, `TaskAddForm.tsx` and `TaskEditForm.tsx` (whole files):
    - `projectId`, `currency`;
    - the ended chips, the budget slice, Mark failed.
  - `web/src/components/notes/NotesBoard.tsx` and `web/src/components/documents/DocumentsBoard.tsx` (whole files): `projectId`.
  - `web/src/pages/Board.tsx` (whole file): Projects first and the default, plus `lazyPanel`.
  - `web/src/App.tsx`: the two project routes.
  - `web/src/styles.css`: imports `styles/projects.css`.
- Test:
  - `web/tests/projectFixtures.ts` (new; shared factories)
  - New: `web/tests/BudgetBar.test.tsx`, `ProjectsBoard.test.tsx`, `Project.test.tsx`, `TopupForm.test.tsx`, `TopupHistory.test.tsx` and `ExpenseList.test.tsx`
  - `web/tests/Board.test.tsx` (whole file)
  - `web/tests/live.test.ts`: the Review Focus test
  - `web/tests/TasksBoard.test.tsx`, `NotesBoard.test.tsx`, `DocumentsBoard.test.tsx` and `MoneyBoard.test.tsx` (mocks, factories, appended tests)

**Interfaces:**
- Consumes:
  - **Task 1 (web):**
    - `ExpenseOut.project` / `.project_id`, `ProjectTotalOut { project, spent, budget, remaining }` and `MoneySummaryOut.by_project`;
    - `ExpenseIn.project`;
    - `ExpenseAddForm({ projects, onAdded })` with the datalist `expense-projects`, and the class `expense-row__project`;
    - Task 1's `web/tests/MoneyBoard.test.tsx`;
    - `tests/test_vocabulary.py::test_the_web_face_says_project_not_category`: no "Category", "By category" or "categories" anywhere in `web/src`.
  - **Task 3 (wire):**
    - `ExpenseOut` keys: `id, project, project_id, task_id, step_id, amount, currency, description, vendor, spent_at, status, is_favorite, created_at, created_by_bot, tainted`;
    - a `by_project` row: `project, project_id, currency, spent, budget, remaining, month: BudgetLineOut, other_currencies`;
    - `BudgetLineOut`: `budget, spent, remaining, used_percent, tone`.
  - **Task 4 (wire):**
    - `task_out` carries `project_id` and `allocated_budget` (`"250.00"` or null);
    - `status` can be `failed`;
    - `TaskFilter` has `failed` and `all`;
    - `tasks_changed` can carry `"failed"`.
  - **Task 6:** the H10 `change` values on `money_changed`.
  - **Task 8 (HTTP)**, the contract's route table, with these request bodies:
    - `GET /api/projects?include_archived=true`, and `GET /api/projects/{id}` → `ProjectDetailOut`, with Task 8's *extra* `task_money` (task id → `{planned, spent, left}`, design §2's planned / spent / left);
    - `POST /api/projects` with `{name, currency, budget, monthly_budget, color, start_date, due_date, lead_bot_id}` (amounts as strings, null for none) → 201 `ProjectOut`;
    - `PATCH /api/projects/{id}` with any subset of `{name, color, start_date, due_date, monthly_budget, lead_bot_id, status, currency}` (null clears) → `ProjectOut`, or 409 / 422 with a plain `detail`;
    - `DELETE /api/projects/{id}` → 204;
    - `PUT /api/projects/{id}/budget` with `{amount}` (a string, or null to clear the total budget, H5) → `ProjectOut`, or 404 / 422 with a plain `detail`. `PATCH` refuses `budget`, so this is the only way the web changes the total after creation;
    - `POST /api/projects/{id}/topups` with `{amount, source?}`;
    - `PATCH /api/topups/{id}` with `{amount}` (the top-up's **new** amount), and `POST /api/topups/{id}/undo` (409 when already undone);
    - `PUT /api/money/expenses/{id}/star` with `{starred}`, and `/void` with `{void}`;
    - `POST /api/money/expenses` with `{amount, project_id, note?}` (Task 8 Step 6's `ExpenseIn.project_id`): an expense named by project id lands in exactly that project and, with no currency sent, takes that project's currency (H7). A name is found or made instead (`log_expense`), so a near name could land elsewhere;
    - `POST /api/tasks/{id}/fail`;
    - `GET /api/tasks?status=all&project_id=`;
    - `GET /api/notes?q=&project_id=` and `GET /api/documents?kind=&project_id=`;
    - `PUT /api/documents/{id}/project` with `{project_id}`;
    - **not in the contract's table:** `POST /api/tasks`, `POST /api/notes` and `POST /api/documents` accept an optional `project_id`, and `PATCH /api/tasks/{id}` accepts `allocated_budget` (a string, or null to clear). Step 1 checks these.
  - **Stuck flow Task 8:** `LiveState.stuckCards` and `initialLiveState()` with it. The `money_changed` case and `applyFrame`'s signature are unchanged.
  - **Existing:** `apiRequest`, `ApiError` and `describeError`; `ErrorNotice`; `MadeByChip` and `WebContentChip`; `formatMoney`, `parseAmountInput`, `dayLabel`, `madridMonth`, `monthLabel`, `shiftMonth` and `MAX_AMOUNT_TEXT` (`board/money.ts`); `BackIcon`; `useLiveState`; `makeBot` (`tests/fixtures.ts`).
- Produces (Task 10's E2E relies on these exact names and texts):
  - **Routes:** `/board?tab=projects` (the Board's default tab); `/board/projects/{id}`, the project page, with `?tab=tasks|money|notes|docs`; `/board/projects` redirects to `/board?tab=projects`.
  - **Projects tab:**
    - the button `New project`, which opens the form `New project`. Its fields are `Name`, `Currency`, `Total budget`, `Monthly limit`, the `Color` radios (`Slate` … `Pink`), `Starts`, `Due` and `Lead bot`, and its button is `Create project`;
    - the checkbox `Show archived`;
    - the list `Your projects`, whose rows link to `/board/projects/{id}`;
    - meters named `Total budget` and `This month`;
    - the texts `{done} of {total} done`, `{n} failed`, `No tasks yet` and `€… spent`.
  - **Project page:**
    - the heading is the project's name, and the link `Back to projects` goes to `/board?tab=projects`;
    - the summary line is `Led by {bot} · Starts {d Mon yyyy} · Due {…}`, with `Starred {money}` and `Also {money} (not in the budgets)`;
    - the buttons are `Edit` (which opens the form `Edit {name}`, with `Save`), `Archive` / `Unarchive`, `Delete {name}` and then `Delete {name} for good`, with the delete copy above;
    - the form `Edit {name}` has the field `Total budget`, filled with the total as the server sends it (`1000.00`); empty clears it;
    - the tabs are `Tasks`, `Money`, `Notes` and `Docs`.
  - **Money tab:**
    - the region `Top-ups`, with the inputs `Top-up amount` and `Where from` and the button `Add top-up`;
    - the list `Top-up history`, whose rows are labelled `Top-up`, `Top-up changed` or `Budget set`, plus the chip `undone`;
    - the buttons `Change the top-up of {money}` (which opens the input `New amount` and `Save`) and `Undo the top-up of {money}`;
    - the text `No top-ups yet.`
  - **Expenses:**
    - the buttons `Star the {project} expense` (with `aria-pressed`), `Void the {project} expense` and `Restore the {project} expense`;
    - the chip `void`, and the image `Starred` when the list cannot change stars.
  - **Tasks:**
    - the chips `done`, `failed` and `cancelled`, and on a project's page `budget {money}` and `{spent} spent, {left} left` / `{spent} spent, over by {money}`;
    - the edit form's button `Mark failed` and its field `Budget slice`.
  - **Code:**
    - `setProjectBudget(projectId, amount: string | null): Promise<ProjectOut>` (`api/projects.ts`);
    - `ExpenseList({ expenses, currency, showProject?, onKeep, onStar?, onVoid? })`;
    - `MoneyBoard({ initialMonth?, project?: { id, name, currency } })`;
    - `TasksBoard({ projectId?, currency?, money? })` and `TaskRow`'s `money?: TaskMoneyOut`;
    - `NotesBoard({ projectId? })` and `DocumentsBoard({ projectId? })`;
    - `lazyPanel(Panel)` and `PanelProps`;
    - `BudgetBar({ label, line, currency })` and `budgetText`;
    - `readAmount` and `AMOUNT_HELP` (`board/money.ts`);
    - `bumpMoney` (`store/live.ts`).

- [ ] **Step 1: Path guard**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

The stuck flow's web task and hub Tasks 1–8 must be in place, and this task must not have run yet.
Run: `cd /Users/blckit/Desktop/Code_Projects/roost && test -f web/src/api/stuck.ts && grep -c "stuckCards" web/src/store/live.ts && grep -n "export interface ProjectTotalOut" web/src/api/types.ts && test -f roost/gateway/routes/projects.py && grep -q '"/api/projects/{project_id}/budget"' roost/gateway/routes/projects.py && test ! -e web/src/api/projects.ts && echo "ready for Task 9"`
Expected: a count of at least 1, then one line for `ProjectTotalOut`, then `ready for Task 9` (the last greps also confirm Task 8's `PUT /api/projects/{id}/budget`). If anything else prints, stop.

The web sends `project_id` when it creates a task, note, document or expense on a project's page, and `allocated_budget` when it changes a task's slice. Check that Task 8's request models accept them.
Run: `cd /Users/blckit/Desktop/Code_Projects/roost && grep -n "project_id\|allocated_budget" roost/gateway/routes/tasks.py roost/gateway/routes/notes.py roost/gateway/routes/documents.py roost/gateway/routes/money.py`
Expected: `TaskIn`, `TaskPatchIn` (with `allocated_budget`), `NoteIn`, `DocumentCreateIn` and the money router's `ExpenseIn` each show a `project_id` field. If one is missing, stop and report it: Task 8 must add it, because all five models are `extra="forbid"` and would answer 422.

- [ ] **Step 2: Write the failing tests**

**2a.** Create `web/tests/projectFixtures.ts`:

```ts
import type { BudgetLineOut, ExpenseOut, ProjectDetailOut, ProjectOut, TopupOut } from "../src/api/types";

// The projects hub's wire shapes (Task 8's routes), shared by the projects tests. Every number
// is already a string from the server: the web only shows them.

export const NO_LIMIT: Pick<BudgetLineOut, "budget" | "remaining" | "used_percent" | "tone"> = {
  budget: null, remaining: null, used_percent: null, tone: null,
};

export function budgetLine(overrides: Partial<BudgetLineOut> = {}): BudgetLineOut {
  return { budget: "1000.00", spent: "920.00", remaining: "80.00", used_percent: 92, tone: "warn", ...overrides };
}

export function makeProject(overrides: Partial<ProjectOut> = {}): ProjectOut {
  return {
    id: "p1", name: "Garden", color: "#22c55e", currency: "EUR", status: "active",
    start_date: "2026-10-01", due_date: "2026-12-20", lead_bot_id: "bot-1",
    total: budgetLine(),
    month: budgetLine({ budget: "200.00", spent: "50.00", remaining: "150.00", used_percent: 25, tone: "ok" }),
    other_currencies: {}, starred_total: "0.00", progress: { done: 3, failed: 1, total: 5 }, tainted: false,
    ...overrides,
  };
}

export function makeTopup(overrides: Partial<TopupOut> = {}): TopupOut {
  return {
    id: "tu1", amount: "200.00", currency: "EUR", source: "birthday", kind: "credit", topup_id: null, undone: false,
    created_at: "2026-10-10T09:00:00Z", ...overrides,
  };
}

export function makeProjectDetail(overrides: Partial<ProjectDetailOut> = {}): ProjectDetailOut {
  return {
    ...makeProject(), tasks: [], expenses: [], notes: [], documents: [], topups: [makeTopup()], lead_bot_name: "Helper",
    task_money: {}, ...overrides,
  };
}

export function makeExpense(overrides: Partial<ExpenseOut> = {}): ExpenseOut {
  return {
    id: "e1", project: "food", project_id: "p-food", task_id: null, step_id: null, amount: "12.50", currency: "EUR",
    description: "lunch", vendor: null, spent_at: "2026-10-13", status: "posted", is_favorite: false,
    created_at: "x", created_by_bot: null, tainted: false, ...overrides,
  };
}
```

**2b.** Create `web/tests/BudgetBar.test.tsx`:

```tsx
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { BudgetBar } from "../src/components/projects/BudgetBar";
import { budgetLine, NO_LIMIT } from "./projectFixtures";

afterEach(() => cleanup());

const THIS_MONTH = budgetLine({ budget: "300.00", spent: "120.00", remaining: "180.00", used_percent: 40, tone: "ok" });

describe("BudgetBar", () => {
  it("is a meter at the share used, saying what is left", () => {
    const { container } = render(<BudgetBar label="This month" line={THIS_MONTH} currency="EUR" />);
    const meter = screen.getByRole("meter", { name: "This month" });
    expect(meter).toHaveAttribute("aria-valuenow", "40");
    expect(meter).toHaveAttribute("aria-valuemin", "0");
    expect(meter).toHaveAttribute("aria-valuemax", "100");
    expect(meter).toHaveAttribute("aria-valuetext", "€180.00 left of €300.00");
    expect(screen.getByText("€180.00 left of €300.00")).toBeInTheDocument();
    expect(container.querySelector(".budget-bar__fill")).toHaveClass("budget-bar__fill--ok");
  });

  it("takes its colour from the server's tone: amber from 80 %", () => {
    const line = budgetLine({ budget: "300.00", spent: "255.00", remaining: "45.00", used_percent: 85, tone: "warn" });
    const { container } = render(<BudgetBar label="Total budget" line={line} currency="EUR" />);
    expect(screen.getByRole("meter", { name: "Total budget" })).toHaveAttribute("aria-valuenow", "85");
    expect(container.querySelector(".budget-bar__fill")).toHaveClass("budget-bar__fill--warn");
  });

  it("is full and red when over, and says by how much", () => {
    const line = budgetLine({ budget: "300.00", spent: "345.00", remaining: "-45.00", used_percent: 115, tone: "over" });
    const { container } = render(<BudgetBar label="Total budget" line={line} currency="EUR" />);
    const meter = screen.getByRole("meter", { name: "Total budget" });
    expect(meter).toHaveAttribute("aria-valuenow", "100");
    expect(meter).toHaveAttribute("aria-valuetext", "Over by €45.00");
    expect(screen.getByText("Over by €45.00")).toBeInTheDocument();
    const fill = container.querySelector(".budget-bar__fill") as HTMLElement;
    expect(fill).toHaveClass("budget-bar__fill--over");
    expect(fill.style.width).toBe("100%");
  });

  it("with no limit it shows only what was spent, and no meter", () => {
    render(<BudgetBar label="This month" line={budgetLine({ ...NO_LIMIT, spent: "12.50" })} currency="EUR" />);
    expect(screen.queryByRole("meter")).not.toBeInTheDocument();
    expect(screen.getByText("€12.50 spent, no limit")).toBeInTheDocument();
  });

  it("speaks the project's own currency", () => {
    render(<BudgetBar label="This month" line={THIS_MONTH} currency="USD" />);
    expect(screen.getByText("US$180.00 left of US$300.00")).toBeInTheDocument();
  });
});
```

**2c.** Create `web/tests/ExpenseList.test.tsx`:

```tsx
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ExpenseList } from "../src/components/board/ExpenseList";
import { makeExpense } from "./projectFixtures";

vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => ({ bots: {}, boardVersion: { tasks: 0, money: 0 } }) }));
afterEach(() => cleanup());

const EXPENSES = [
  makeExpense(),
  makeExpense({ id: "e2", project: "travel", description: "taxi", is_favorite: true }),
  makeExpense({ id: "e3", project: "garden", description: "seeds", status: "void" }),
  makeExpense({ id: "e4", project: "trip", description: "museum", currency: "USD" }),
];

const rowOf = (note: string) => screen.getByText(note).closest("li") as HTMLElement;

describe("ExpenseList", () => {
  it("stars an expense, and unstars a starred one", async () => {
    const onStar = vi.fn();
    const user = userEvent.setup();
    render(<ExpenseList expenses={EXPENSES} currency="EUR" onKeep={vi.fn()} onStar={onStar} onVoid={vi.fn()} />);
    const star = screen.getByRole("button", { name: "Star the food expense" });
    expect(star).toHaveAttribute("aria-pressed", "false");
    await user.click(star);
    expect(onStar).toHaveBeenLastCalledWith("e1", true);
    const starred = screen.getByRole("button", { name: "Star the travel expense" });
    expect(starred).toHaveAttribute("aria-pressed", "true");
    await user.click(starred);
    expect(onStar).toHaveBeenLastCalledWith("e2", false);
  });

  it("voids an expense; a void one stays in the list, marked, and can come back", async () => {
    const onVoid = vi.fn();
    const user = userEvent.setup();
    render(<ExpenseList expenses={EXPENSES} currency="EUR" onKeep={vi.fn()} onStar={vi.fn()} onVoid={onVoid} />);
    await user.click(screen.getByRole("button", { name: "Void the food expense" }));
    expect(onVoid).toHaveBeenLastCalledWith("e1", true);
    const seeds = rowOf("seeds");
    expect(seeds).toHaveClass("expense-row--void");
    expect(within(seeds).getByText("void")).toBeInTheDocument();
    await user.click(within(seeds).getByRole("button", { name: "Restore the garden expense" }));
    expect(onVoid).toHaveBeenLastCalledWith("e3", false);
  });

  it("without onStar and onVoid it offers neither, and only marks the starred one", () => {
    render(<ExpenseList expenses={EXPENSES} currency="EUR" onKeep={vi.fn()} />);
    expect(screen.queryByRole("button", { name: /^(Star|Void|Restore) / })).not.toBeInTheDocument();
    expect(within(rowOf("taxi")).getByRole("img", { name: "Starred" })).toBeInTheDocument();
  });

  it("marks an amount in another currency, and can leave out the project's name", () => {
    render(<ExpenseList expenses={EXPENSES} currency="EUR" showProject={false} onKeep={vi.fn()} />);
    expect(rowOf("museum")).toHaveClass("expense-row--other");
    expect(screen.queryByText("food")).not.toBeInTheDocument();
  });
});
```

**2d.** Create `web/tests/TopupForm.test.tsx`:

```tsx
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TopupForm } from "../src/components/projects/TopupForm";

const addTopupMock = vi.fn();
vi.mock("../src/api/projects", () => ({ addTopup: (...a: unknown[]) => addTopupMock(...a) }));

beforeEach(() => addTopupMock.mockReset());
afterEach(() => cleanup());

describe("TopupForm", () => {
  it("adds 50,00 from a gift, tells the page and clears", async () => {
    addTopupMock.mockResolvedValue({ id: "tu9" });
    const onAdded = vi.fn();
    const user = userEvent.setup();
    render(<TopupForm projectId="p1" onAdded={onAdded} />);
    await user.type(screen.getByLabelText("Top-up amount"), "50,00");
    await user.type(screen.getByLabelText("Where from"), "birthday gift");
    await user.click(screen.getByRole("button", { name: "Add top-up" }));
    expect(addTopupMock).toHaveBeenCalledWith("p1", { amount: "50.00", source: "birthday gift" });
    await waitFor(() => expect(onAdded).toHaveBeenCalledTimes(1));
    expect(screen.getByLabelText("Top-up amount")).toHaveValue("");
  });

  it("sends no source when none is given", async () => {
    addTopupMock.mockResolvedValue({ id: "tu9" });
    const user = userEvent.setup();
    render(<TopupForm projectId="p1" onAdded={vi.fn()} />);
    await user.type(screen.getByLabelText("Top-up amount"), "20");
    await user.click(screen.getByRole("button", { name: "Add top-up" }));
    expect(addTopupMock).toHaveBeenCalledWith("p1", { amount: "20.00" });
  });

  it("refuses an amount it can't read without calling the gateway", async () => {
    const user = userEvent.setup();
    render(<TopupForm projectId="p1" onAdded={vi.fn()} />);
    await user.type(screen.getByLabelText("Top-up amount"), "1.234,56");
    await user.click(screen.getByRole("button", { name: "Add top-up" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Enter an amount like 12,50.");
    expect(addTopupMock).not.toHaveBeenCalled();
  });

  it("shows the gateway's refusal", async () => {
    const { ApiError } = await import("../src/api/client");
    addTopupMock.mockRejectedValue(new ApiError(422, "An amount must be more than 0 and at most 1,000,000."));
    const user = userEvent.setup();
    render(<TopupForm projectId="p1" onAdded={vi.fn()} />);
    await user.type(screen.getByLabelText("Top-up amount"), "2000000");
    await user.click(screen.getByRole("button", { name: "Add top-up" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("at most 1,000,000");
  });
});
```

**2e.** Create `web/tests/TopupHistory.test.tsx`:

```tsx
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TopupHistory } from "../src/components/projects/TopupHistory";
import { makeTopup } from "./projectFixtures";

const editTopupMock = vi.fn();
const undoTopupMock = vi.fn();
vi.mock("../src/api/projects", () => ({
  editTopup: (...a: unknown[]) => editTopupMock(...a),
  undoTopup: (...a: unknown[]) => undoTopupMock(...a),
}));

beforeEach(() => { editTopupMock.mockReset(); undoTopupMock.mockReset(); });
afterEach(() => cleanup());

// Newest first, as the server sends it: a change to the birthday top-up, the top-up itself,
// an undone refund, and the budget set by hand when the project was made.
const HISTORY = [
  makeTopup({ id: "tu3", kind: "edit", topup_id: "tu1", amount: "-50.00", source: null, created_at: "2026-10-12T09:00:00Z" }),
  makeTopup(),
  makeTopup({ id: "tu2", amount: "30.00", source: "refund", undone: true, created_at: "2026-10-05T09:00:00Z" }),
  makeTopup({ id: "tu0", kind: "edit", topup_id: null, amount: "500.00", source: null, created_at: "2026-10-01T09:00:00Z" }),
];

const rowOf = (text: string) => screen.getByText(text).closest("li") as HTMLElement;

describe("TopupHistory", () => {
  it("names each row: a top-up, a change to one, and a budget set by hand", () => {
    render(<TopupHistory topups={HISTORY} onChanged={vi.fn()} />);
    expect(within(screen.getByRole("list", { name: "Top-up history" })).getAllByRole("listitem")).toHaveLength(4);
    expect(within(rowOf("Top-up changed")).getByText("-€50.00")).toBeInTheDocument();
    expect(within(rowOf("Budget set")).getByText("+€500.00")).toBeInTheDocument();
    const birthday = rowOf("birthday");
    expect(within(birthday).getByText("Top-up")).toBeInTheDocument();
    expect(within(birthday).getByText("€200.00")).toBeInTheDocument();
    expect(within(birthday).getByText("10 Oct 2026")).toBeInTheDocument();
  });

  it("an undone top-up says so, and only a live top-up can be changed or undone", () => {
    render(<TopupHistory topups={HISTORY} onChanged={vi.fn()} />);
    const refund = rowOf("refund");
    expect(within(refund).getByText("undone")).toBeInTheDocument();
    expect(within(refund).queryByRole("button")).not.toBeInTheDocument();
    expect(within(rowOf("Budget set")).queryByRole("button")).not.toBeInTheDocument();
    expect(within(rowOf("Top-up changed")).queryByRole("button")).not.toBeInTheDocument();
  });

  it("undoes a top-up and tells the page", async () => {
    undoTopupMock.mockResolvedValue(makeTopup({ undone: true }));
    const onChanged = vi.fn();
    const user = userEvent.setup();
    render(<TopupHistory topups={HISTORY} onChanged={onChanged} />);
    await user.click(screen.getByRole("button", { name: "Undo the top-up of €200.00" }));
    expect(undoTopupMock).toHaveBeenCalledWith("tu1");
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
  });

  it("changes a top-up to a new amount", async () => {
    editTopupMock.mockResolvedValue(makeTopup({ id: "tu4", kind: "edit", topup_id: "tu1", amount: "-20.00" }));
    const onChanged = vi.fn();
    const user = userEvent.setup();
    render(<TopupHistory topups={HISTORY} onChanged={onChanged} />);
    await user.click(screen.getByRole("button", { name: "Change the top-up of €200.00" }));
    await user.type(screen.getByLabelText("New amount"), "180");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(editTopupMock).toHaveBeenCalledWith("tu1", "180.00");
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
  });

  it("shows why an undo was refused and changes nothing", async () => {
    const { ApiError } = await import("../src/api/client");
    undoTopupMock.mockRejectedValue(new ApiError(409, "That top-up is already undone."));
    const onChanged = vi.fn();
    const user = userEvent.setup();
    render(<TopupHistory topups={HISTORY} onChanged={onChanged} />);
    await user.click(screen.getByRole("button", { name: "Undo the top-up of €200.00" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("already undone");
    expect(onChanged).not.toHaveBeenCalled();
  });

  it("says when there are no top-ups yet", () => {
    render(<TopupHistory topups={[]} onChanged={vi.fn()} />);
    expect(screen.getByText("No top-ups yet.")).toBeInTheDocument();
  });
});
```

**2f.** Create `web/tests/ProjectsBoard.test.tsx`:

```tsx
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { ProjectsBoard } from "../src/components/projects/ProjectsBoard";
import type { BotOut } from "../src/api/types";
import { makeBot } from "./fixtures";
import { budgetLine, makeProject, NO_LIMIT } from "./projectFixtures";

const listProjectsMock = vi.fn();
const createProjectMock = vi.fn();
vi.mock("../src/api/projects", () => ({
  listProjects: (...a: unknown[]) => listProjectsMock(...a),
  createProject: (...a: unknown[]) => createProjectMock(...a),
}));
const BOTS: Record<string, BotOut> = { "bot-1": makeBot({ id: "bot-1", name: "Helper" }) };
let live = { bots: BOTS, boardVersion: { tasks: 0, money: 0 } };
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => live }));

const GARDEN = makeProject();
const READING = makeProject({
  id: "p2", name: "Reading", total: budgetLine({ ...NO_LIMIT, spent: "12.50" }),
  month: budgetLine({ ...NO_LIMIT, spent: "12.50" }), progress: { done: 0, failed: 0, total: 0 },
});

beforeEach(() => {
  live = { bots: BOTS, boardVersion: { tasks: 0, money: 0 } };
  for (const mock of [listProjectsMock, createProjectMock]) mock.mockReset();
  listProjectsMock.mockResolvedValue([GARDEN, READING]);
});
afterEach(() => cleanup());

const board = () => <MemoryRouter><ProjectsBoard /></MemoryRouter>;
const rowOf = async (name: string) => (await screen.findByRole("link", { name })).closest("li") as HTMLElement;

async function openNewProject(user: ReturnType<typeof userEvent.setup>) {
  await rowOf("Garden");
  await user.click(screen.getByRole("button", { name: "New project" }));
  return screen.getByRole("form", { name: "New project" });
}

describe("ProjectsBoard", () => {
  it("lists each project with its tasks and its budget bars, linking to its page", async () => {
    render(board());
    const garden = await rowOf("Garden");
    expect(within(garden).getByRole("link", { name: "Garden" })).toHaveAttribute("href", "/board/projects/p1");
    expect(within(garden).getByText("3 of 5 done")).toBeInTheDocument();
    expect(within(garden).getByText("1 failed")).toBeInTheDocument();
    expect(within(garden).getByRole("meter", { name: "Total budget" })).toHaveAttribute("aria-valuenow", "92");
    expect(within(garden).getByRole("meter", { name: "This month" })).toHaveAttribute("aria-valuenow", "25");
    expect(listProjectsMock).toHaveBeenCalledWith(false);
  });

  it("a project with no budget shows what it spent and no bar", async () => {
    render(board());
    const reading = await rowOf("Reading");
    expect(within(reading).getByText("€12.50 spent")).toBeInTheDocument();
    expect(within(reading).getByText("No tasks yet")).toBeInTheDocument();
    expect(within(reading).queryByRole("meter")).not.toBeInTheDocument();
  });

  it("makes a project from the form and reloads the list", async () => {
    createProjectMock.mockResolvedValue(makeProject({ id: "p3", name: "Kitchen" }));
    const user = userEvent.setup();
    render(board());
    const form = await openNewProject(user);
    await user.type(within(form).getByLabelText("Name"), "Kitchen");
    await user.type(within(form).getByLabelText("Total budget"), "1200");
    await user.type(within(form).getByLabelText("Monthly limit"), "300,50");
    await user.click(within(form).getByRole("radio", { name: "Blue" }));
    await user.selectOptions(within(form).getByLabelText("Lead bot"), "Helper");
    await user.click(within(form).getByRole("button", { name: "Create project" }));
    expect(createProjectMock).toHaveBeenCalledWith({
      name: "Kitchen", currency: "EUR", budget: "1200.00", monthly_budget: "300.50", color: "#3b82f6",
      start_date: null, due_date: null, lead_bot_id: "bot-1",
    });
    await waitFor(() => expect(listProjectsMock).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole("form", { name: "New project" })).not.toBeInTheDocument();
  });

  it("refuses an amount or a currency it can't read before calling the gateway", async () => {
    const user = userEvent.setup();
    render(board());
    const form = await openNewProject(user);
    await user.type(within(form).getByLabelText("Name"), "Kitchen");
    await user.type(within(form).getByLabelText("Total budget"), "1.234,56");
    await user.click(within(form).getByRole("button", { name: "Create project" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent("Enter an amount like 12,50.");
    await user.clear(within(form).getByLabelText("Total budget"));
    await user.clear(within(form).getByLabelText("Currency"));
    await user.type(within(form).getByLabelText("Currency"), "E1");
    await user.click(within(form).getByRole("button", { name: "Create project" }));
    expect(await within(form).findByText("A currency is three letters, like EUR.")).toBeInTheDocument();
    expect(createProjectMock).not.toHaveBeenCalled();
  });

  it("shows the gateway's refusal", async () => {
    const { ApiError } = await import("../src/api/client");
    createProjectMock.mockRejectedValue(new ApiError(409, "A project with that name exists."));
    const user = userEvent.setup();
    render(board());
    const form = await openNewProject(user);
    await user.type(within(form).getByLabelText("Name"), "Garden");
    await user.click(within(form).getByRole("button", { name: "Create project" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent("A project with that name exists.");
  });

  it("shows archived projects when asked", async () => {
    const user = userEvent.setup();
    render(board());
    await rowOf("Garden");
    listProjectsMock.mockResolvedValue([makeProject({ status: "archived" })]);
    await user.click(screen.getByRole("checkbox", { name: "Show archived" }));
    await waitFor(() => expect(listProjectsMock).toHaveBeenLastCalledWith(true));
    expect(await screen.findByText("archived")).toBeInTheDocument();
  });

  it("reloads when a money_changed or a tasks_changed frame arrives", async () => {
    const { rerender } = render(board());
    await rowOf("Garden");
    live = { bots: BOTS, boardVersion: { tasks: 0, money: 1 } };
    rerender(board());
    await waitFor(() => expect(listProjectsMock).toHaveBeenCalledTimes(2));
    live = { bots: BOTS, boardVersion: { tasks: 1, money: 1 } };
    rerender(board());
    await waitFor(() => expect(listProjectsMock).toHaveBeenCalledTimes(3));
  });

  it("says there are none yet, in the shared words", async () => {
    listProjectsMock.mockResolvedValue([]);
    render(board());
    expect(await screen.findByText("No projects yet. Make one here, or ask any bot to start one.")).toBeInTheDocument();
  });

  it("says what went wrong when the list can't load", async () => {
    listProjectsMock.mockRejectedValue(new Error("down"));
    render(board());
    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong");
  });
});
```

**2g.** Create `web/tests/Project.test.tsx` (the `MemoryRouter` + `Routes` pattern of `Profile.test.tsx`):

```tsx
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useSearchParams } from "react-router-dom";
import { Project, ToProjectsTab } from "../src/pages/Project";
import { makeBot } from "./fixtures";
import { makeProjectDetail } from "./projectFixtures";

const getProjectMock = vi.fn();
const updateProjectMock = vi.fn();
const setProjectBudgetMock = vi.fn();
const deleteProjectMock = vi.fn();
const addTopupMock = vi.fn();
vi.mock("../src/api/projects", () => ({
  getProject: (...a: unknown[]) => getProjectMock(...a),
  updateProject: (...a: unknown[]) => updateProjectMock(...a),
  setProjectBudget: (...a: unknown[]) => setProjectBudgetMock(...a),
  deleteProject: (...a: unknown[]) => deleteProjectMock(...a),
  addTopup: (...a: unknown[]) => addTopupMock(...a),
}));
vi.mock("../src/components/board/TasksBoard", () => ({
  TasksBoard: ({ projectId, currency }: { projectId: string; currency: string }) => <p>Tasks of {projectId} in {currency}</p>,
}));
vi.mock("../src/components/board/MoneyBoard", () => ({
  MoneyBoard: ({ project }: { project: { name: string } }) => <p>Months of {project.name}</p>,
}));
vi.mock("../src/components/notes/NotesBoard", () => ({
  default: ({ projectId }: { projectId: string }) => <p>Notes of {projectId}</p>,
}));
vi.mock("../src/components/documents/DocumentsBoard", () => ({
  default: ({ projectId }: { projectId: string }) => <p>Docs of {projectId}</p>,
}));
vi.mock("../src/hooks/useLiveStore", () => ({
  useLiveState: () => ({
    bots: { "bot-1": makeBot({ id: "bot-1", name: "Helper" }) },
    boardVersion: { tasks: 0, money: 0, notes: 0, documents: 0 },
  }),
}));

function BoardSpy() {
  const [params] = useSearchParams();
  return <p>Board on {params.get("tab")}</p>;
}

function renderAt(entry: string) {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route path="/board/projects/:projectId" element={<Project />} />
        <Route path="/board/projects" element={<ToProjectsTab />} />
        <Route path="/board" element={<BoardSpy />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  for (const mock of [getProjectMock, updateProjectMock, setProjectBudgetMock, deleteProjectMock, addTopupMock]) {
    mock.mockReset();
  }
  getProjectMock.mockResolvedValue(makeProjectDetail({ other_currencies: { USD: "20.00" }, starred_total: "45.00" }));
});
afterEach(() => cleanup());

describe("Project", () => {
  it("shows the lead bot, the dates, progress and both budgets, then the project's tasks", async () => {
    renderAt("/board/projects/p1");
    expect(await screen.findByRole("heading", { name: "Garden" })).toBeInTheDocument();
    expect(getProjectMock).toHaveBeenCalledWith("p1");
    expect(screen.getByText("Led by Helper · Starts 1 Oct 2026 · Due 20 Dec 2026")).toBeInTheDocument();
    expect(screen.getByText("3 of 5 done")).toBeInTheDocument();
    expect(screen.getByText("1 failed")).toBeInTheDocument();
    expect(screen.getByRole("meter", { name: "Total budget" })).toHaveAttribute("aria-valuenow", "92");
    expect(screen.getByRole("meter", { name: "This month" })).toHaveAttribute("aria-valuenow", "25");
    expect(screen.getByText("Starred €45.00")).toBeInTheDocument();
    expect(screen.getByText(/Also .*20\.00.*not in the budgets/)).toBeInTheDocument();
    expect(screen.getAllByRole("tab").map((tab) => tab.textContent)).toEqual(["Tasks", "Money", "Notes", "Docs"]);
    expect(screen.getByRole("tab", { name: "Tasks" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("Tasks of p1 in EUR")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to projects" })).toHaveAttribute("href", "/board?tab=projects");
  });

  it("opens Money with the top-ups and the project's months, and a top-up reloads the page", async () => {
    addTopupMock.mockResolvedValue({ id: "tu2" });
    const user = userEvent.setup();
    renderAt("/board/projects/p1?tab=money");
    expect(await screen.findByText("Months of Garden")).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "Top-up history" })).getByText("birthday")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Top-up amount"), "50");
    await user.type(screen.getByLabelText("Where from"), "gift");
    await user.click(screen.getByRole("button", { name: "Add top-up" }));
    expect(addTopupMock).toHaveBeenCalledWith("p1", { amount: "50.00", source: "gift" });
    await waitFor(() => expect(getProjectMock).toHaveBeenCalledTimes(2));
  });

  it("opens Notes and Docs as their own chunks, narrowed to the project", async () => {
    const user = userEvent.setup();
    renderAt("/board/projects/p1");
    await user.click(await screen.findByRole("tab", { name: "Notes" }));
    expect(await screen.findByText("Notes of p1")).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Docs" }));
    expect(await screen.findByText("Docs of p1")).toBeInTheDocument();
  });

  it("edits the project and sends only what changed", async () => {
    updateProjectMock.mockResolvedValue(makeProjectDetail({ name: "Back garden" }));
    const user = userEvent.setup();
    renderAt("/board/projects/p1");
    await user.click(await screen.findByRole("button", { name: "Edit" }));
    const form = screen.getByRole("form", { name: "Edit Garden" });
    expect(within(form).getByLabelText("Total budget")).toHaveValue("1000.00");
    const name = within(form).getByLabelText("Name");
    await user.clear(name);
    await user.type(name, "Back garden");
    const monthly = within(form).getByLabelText("Monthly limit");
    expect(monthly).toHaveValue("200.00");
    await user.clear(monthly);
    await user.type(monthly, "150");
    await user.click(within(form).getByRole("button", { name: "Save" }));
    expect(updateProjectMock).toHaveBeenCalledWith("p1", { name: "Back garden", monthly_budget: "150.00" });
    expect(setProjectBudgetMock).not.toHaveBeenCalled();
    await waitFor(() => expect(getProjectMock).toHaveBeenCalledTimes(2));
  });

  it("saves a changed total budget on its own route, and an emptied one clears it", async () => {
    setProjectBudgetMock.mockResolvedValue(makeProjectDetail());
    const user = userEvent.setup();
    const editForm = () => screen.getByRole("form", { name: "Edit Garden" });
    renderAt("/board/projects/p1");
    await user.click(await screen.findByRole("button", { name: "Edit" }));
    await user.clear(within(editForm()).getByLabelText("Total budget"));
    await user.type(within(editForm()).getByLabelText("Total budget"), "1500,50");
    await user.click(within(editForm()).getByRole("button", { name: "Save" }));
    expect(setProjectBudgetMock).toHaveBeenCalledWith("p1", "1500.50");
    await waitFor(() => expect(getProjectMock).toHaveBeenCalledTimes(2));
    await user.click(await screen.findByRole("button", { name: "Edit" }));
    await user.clear(within(editForm()).getByLabelText("Total budget"));
    await user.click(within(editForm()).getByRole("button", { name: "Save" }));
    expect(setProjectBudgetMock).toHaveBeenLastCalledWith("p1", null);
    expect(setProjectBudgetMock).toHaveBeenCalledTimes(2);
    expect(updateProjectMock).not.toHaveBeenCalled();
    await waitFor(() => expect(getProjectMock).toHaveBeenCalledTimes(3));
  });

  it("archives the project", async () => {
    updateProjectMock.mockResolvedValue(makeProjectDetail({ status: "archived" }));
    const user = userEvent.setup();
    renderAt("/board/projects/p1");
    await user.click(await screen.findByRole("button", { name: "Archive" }));
    expect(updateProjectMock).toHaveBeenCalledWith("p1", { status: "archived" });
    await waitFor(() => expect(getProjectMock).toHaveBeenCalledTimes(2));
  });

  it("deletes only after the second click, saying what happens to its records, then goes back to Projects", async () => {
    deleteProjectMock.mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderAt("/board/projects/p1");
    await user.click(await screen.findByRole("button", { name: "Delete Garden" }));
    expect(screen.getByText("Its expenses move to General; its tasks, notes and documents stay, just unlinked."))
      .toBeInTheDocument();
    expect(deleteProjectMock).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Delete Garden for good" }));
    expect(deleteProjectMock).toHaveBeenCalledWith("p1");
    expect(await screen.findByText("Board on projects")).toBeInTheDocument();
  });

  it("says so when the project is gone, with the way back", async () => {
    const { ApiError } = await import("../src/api/client");
    getProjectMock.mockRejectedValue(new ApiError(404, "Project not found"));
    renderAt("/board/projects/gone");
    expect(await screen.findByRole("alert")).toHaveTextContent("Project not found");
    expect(screen.getByRole("link", { name: "Back to projects" })).toHaveAttribute("href", "/board?tab=projects");
  });

  it("/board/projects opens the Board on its Projects tab", async () => {
    renderAt("/board/projects");
    expect(await screen.findByText("Board on projects")).toBeInTheDocument();
  });
});
```

**2h.** Replace the whole of `web/tests/Board.test.tsx` with:

```tsx
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { Board } from "../src/pages/Board";

vi.mock("../src/components/projects/ProjectsBoard", () => ({ ProjectsBoard: () => <p>Projects panel</p> }));
vi.mock("../src/components/board/TasksBoard", () => ({ TasksBoard: () => <p>Tasks panel</p> }));
vi.mock("../src/components/board/MoneyBoard", () => ({ MoneyBoard: () => <p>Money panel</p> }));
vi.mock("../src/components/notes/NotesBoard", () => ({ default: () => <p>Notes panel</p> }));
vi.mock("../src/components/documents/DocumentsBoard", () => ({ default: () => <p>Documents panel</p> }));

afterEach(cleanup);

describe("the shared Board", () => {
  it("opens on Projects, then has Tasks, Money, Notes and Documents, whatever bot you came from", async () => {
    render(<MemoryRouter initialEntries={["/board"]}><Board /></MemoryRouter>);
    expect(screen.getAllByRole("tab").map((tab) => tab.textContent)).toEqual(["Projects", "Tasks", "Money", "Notes", "Documents"]);
    expect(screen.getByRole("tab", { name: "Projects" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("Projects panel")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Documents" }));
    expect(await screen.findByText("Documents panel")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to chats" })).toHaveAttribute("href", "/");
  });

  it("opens on the tab in the address", () => {
    render(<MemoryRouter initialEntries={["/board?tab=money"]}><Board /></MemoryRouter>);
    expect(screen.getByRole("tab", { name: "Money" })).toHaveAttribute("aria-selected", "true");
  });

  it("still loads Notes as its own chunk", async () => {
    render(<MemoryRouter initialEntries={["/board?tab=notes"]}><Board /></MemoryRouter>);
    expect(await screen.findByText("Notes panel")).toBeInTheDocument();
  });
});
```

**2i.** `web/tests/live.test.ts` (after the stuck flow; its additions are an import and a block at the end of the file, not the "board frames" block). Find:

```ts
  it("counts documents_changed frames so the Documents tab can reload", () => {
    const next = applyFrame(initialLiveState(), {
      type: "documents_changed", seq: 8, change: "created", document_id: "d1", kind: "doc",
    });
    expect(next.boardVersion.documents).toBe(1);
  });
```

Replace with:

```ts
  it("counts documents_changed frames so the Documents tab can reload", () => {
    const next = applyFrame(initialLiveState(), {
      type: "documents_changed", seq: 8, change: "created", document_id: "d1", kind: "doc",
    });
    expect(next.boardVersion.documents).toBe(1);
  });

  // Review Focus 4: deleting a project unlinks its tasks, notes and documents with no frame of their own.
  it("refreshes tasks, notes and documents when a project is deleted", () => {
    const before = initialLiveState();
    const deleted = applyFrame(before, { type: "money_changed", seq: 9, change: "project_deleted", id: "p1" });
    expect(deleted.boardVersion).toEqual({ tasks: 1, money: 1, notes: 1, documents: 1 });
    expect(deleted.cursor).toBe(9);
    const toppedUp = applyFrame(deleted, { type: "money_changed", seq: 10, change: "topup_added", id: "tu1" });
    expect(toppedUp.boardVersion).toEqual({ tasks: 1, money: 2, notes: 1, documents: 1 });
    // The reducer never mutates its input (immutability rule).
    expect(before.boardVersion).toEqual({ tasks: 0, money: 0, notes: 0, documents: 0 });
  });
```

**2j.** `web/tests/TasksBoard.test.tsx`. Find:

```tsx
const keepTaskMock = vi.fn();
vi.mock("../src/api/tasks", () => ({
  keepTask: (...a: unknown[]) => keepTaskMock(...a),
```

Replace with:

```tsx
const keepTaskMock = vi.fn();
const failTaskMock = vi.fn();
vi.mock("../src/api/tasks", () => ({
  failTask: (...a: unknown[]) => failTaskMock(...a),
  keepTask: (...a: unknown[]) => keepTaskMock(...a),
```

Find:

```tsx
    created_at: "x", updated_at: "x", completed_at: null, created_by_bot: "bot-1", tainted: false, ...overrides,
```

Replace with:

```tsx
    created_at: "x", updated_at: "x", completed_at: null, created_by_bot: "bot-1", tainted: false,
    project_id: null, allocated_budget: null, ...overrides,
```

Find:

```tsx
  for (const mock of [listTasksMock, createTaskMock, updateTaskMock, completeTaskMock, keepTaskMock]) mock.mockReset();
```

Replace with:

```tsx
  for (const mock of [listTasksMock, createTaskMock, updateTaskMock, completeTaskMock, keepTaskMock, failTaskMock]) {
    mock.mockReset();
  }
```

Append at the end of the file:

```tsx

describe("TasksBoard failed tasks and one project's tasks", () => {
  it("marks a task failed from its edit form, and reloads", async () => {
    failTaskMock.mockResolvedValue(task({ status: "failed" }));
    const user = userEvent.setup();
    render(<TasksBoard />);
    await user.click(within(await rowOf("Call the dentist")).getByRole("button", { name: "Edit" }));
    await user.click(screen.getByRole("button", { name: "Mark failed" }));
    expect(failTaskMock).toHaveBeenCalledWith("t1");
    await waitFor(() => expect(listTasksMock).toHaveBeenCalledTimes(2));
  });

  it("lists every task of a project, open first, with a red chip on a failed one", async () => {
    listTasksMock.mockResolvedValue([
      task({ id: "t3", title: "Fix the fence", status: "failed", project_id: "p1", completed_at: "2026-10-14T18:00:00+00:00" }),
      task({ project_id: "p1" }),
    ]);
    render(<TasksBoard projectId="p1" currency="EUR" />);
    const fence = await rowOf("Fix the fence");
    expect(within(fence).getByText("failed")).toHaveClass("board-chip--failed");
    expect(within(fence).getByRole("checkbox", { name: "Complete Fix the fence" })).toBeDisabled();
    const titles = screen.getAllByRole("listitem").map((item) => item.querySelector(".task-row__title")?.textContent);
    expect(titles).toEqual(["Call the dentist", "Fix the fence"]);
    expect(listTasksMock).toHaveBeenCalledWith("all", { projectId: "p1" });
  });

  it("adds a task into the project", async () => {
    createTaskMock.mockResolvedValue(task({ id: "t4", title: "Buy seeds", project_id: "p1" }));
    const user = userEvent.setup();
    render(<TasksBoard projectId="p1" currency="EUR" />);
    await user.type(await screen.findByLabelText("New task"), "Buy seeds");
    await user.click(screen.getByRole("button", { name: "Add" }));
    expect(createTaskMock).toHaveBeenCalledWith({ title: "Buy seeds", due_date: null, project_id: "p1" });
  });

  it("shows a task's budget slice in the project's currency and changes it", async () => {
    listTasksMock.mockResolvedValue([task({ project_id: "p1", allocated_budget: "50.00" })]);
    updateTaskMock.mockResolvedValue(task({ project_id: "p1", allocated_budget: "60.00" }));
    const user = userEvent.setup();
    render(<TasksBoard projectId="p1" currency="EUR" />);
    const row = await rowOf("Call the dentist");
    expect(within(row).getByText("budget €50.00")).toBeInTheDocument();
    await user.click(within(row).getByRole("button", { name: "Edit" }));
    const slice = screen.getByLabelText("Budget slice");
    expect(slice).toHaveValue("50.00");
    await user.clear(slice);
    await user.type(slice, "60");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(updateTaskMock).toHaveBeenCalledWith("t1", { title: "Call the dentist", priority: "medium", allocated_budget: "60.00" });
  });

  it("refuses a slice it can't read without calling the gateway", async () => {
    listTasksMock.mockResolvedValue([task({ project_id: "p1" })]);
    const user = userEvent.setup();
    render(<TasksBoard projectId="p1" currency="EUR" />);
    await user.click(within(await rowOf("Call the dentist")).getByRole("button", { name: "Edit" }));
    await user.type(screen.getByLabelText("Budget slice"), "lots");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Enter an amount like 12,50.");
    expect(updateTaskMock).not.toHaveBeenCalled();
  });

  it("says a project has no tasks yet", async () => {
    listTasksMock.mockResolvedValue([]);
    render(<TasksBoard projectId="p1" />);
    expect(await screen.findByText("No tasks in this project yet. Add one, or ask any bot.")).toBeInTheDocument();
  });

  it("shows what is spent on a task's slice and what is left, as the server reckons it", async () => {
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
    render(<TasksBoard projectId="p1" currency="EUR" money={money} />);
    expect(within(await rowOf("Call the dentist")).getByText("€80.00 spent, €20.00 left")).toBeInTheDocument();
    expect(within(await rowOf("Fix the fence")).getByText("€130.00 spent, over by €30.00")).toBeInTheDocument();
    expect(within(await rowOf("Buy seeds")).queryByText(/spent/)).toBeNull();
  });
});
```

**2k.** `web/tests/NotesBoard.test.tsx`. Find:

```tsx
    created_at: "2026-10-14T08:00:00Z", updated_at: "2026-10-14T08:00:00Z", created_by_bot: "b1", tainted: false,
    ...overrides,
```

Replace with:

```tsx
    created_at: "2026-10-14T08:00:00Z", updated_at: "2026-10-14T08:00:00Z", created_by_bot: "b1", tainted: false,
    project_id: null, ...overrides,
```

Append at the end of the file:

```tsx

describe("NotesBoard in a project", () => {
  it("lists and writes only that project's notes", async () => {
    createNoteMock.mockResolvedValue({ id: "n9" });
    const user = userEvent.setup();
    render(<NotesBoard projectId="p1" />);
    await screen.findByText("Ana");
    expect(listNotesMock).toHaveBeenCalledWith("", { projectId: "p1" });
    await user.click(screen.getByRole("button", { name: "New note" }));
    expect(createNoteMock).toHaveBeenCalledWith({ title: "Untitled note", content: "", project_id: "p1" });
    expect(await screen.findByText("editing n9")).toBeInTheDocument();
  });

  it("searches within the project", async () => {
    const user = userEvent.setup();
    render(<NotesBoard projectId="p1" />);
    await screen.findByText("Ana");
    await user.type(screen.getByRole("searchbox", { name: "Search notes" }), "orchids{Enter}");
    await waitFor(() => expect(listNotesMock).toHaveBeenLastCalledWith("orchids", { projectId: "p1" }));
  });
});
```

**2l.** `web/tests/DocumentsBoard.test.tsx`. Find:

```tsx
const deleteDocumentMock = vi.fn();
```

Replace with:

```tsx
const deleteDocumentMock = vi.fn();
const setDocumentProjectMock = vi.fn();
```

Find:

```tsx
  deleteDocument: (...a: unknown[]) => deleteDocumentMock(...a),
```

Replace with:

```tsx
  deleteDocument: (...a: unknown[]) => deleteDocumentMock(...a),
  setDocumentProject: (...a: unknown[]) => setDocumentProjectMock(...a),
```

Find:

```tsx
    updated_at: "2026-10-14T08:00:00Z", created_by_bot: "b1", tainted: false, ...overrides,
```

Replace with:

```tsx
    updated_at: "2026-10-14T08:00:00Z", created_by_bot: "b1", tainted: false, project_id: null, ...overrides,
```

Find:

```tsx
  for (const mock of [listDocumentsMock, getDocumentMock, createDocumentMock, uploadPdfMock, keepDocumentMock,
    deleteDocumentMock]) mock.mockReset();
```

Replace with:

```tsx
  for (const mock of [listDocumentsMock, getDocumentMock, createDocumentMock, uploadPdfMock, keepDocumentMock,
    deleteDocumentMock, setDocumentProjectMock]) mock.mockReset();
```

Append at the end of the file:

```tsx

describe("DocumentsBoard in a project", () => {
  it("lists and makes only that project's documents", async () => {
    const created = meta({ id: "d2", title: "Untitled doc", project_id: "p1" });
    createDocumentMock.mockResolvedValue(created);
    getDocumentMock.mockResolvedValue({ ...created, payload: {} });
    const user = userEvent.setup();
    render(<DocumentsBoard projectId="p1" />);
    await user.click(await screen.findByRole("button", { name: "New doc" }));
    expect(listDocumentsMock).toHaveBeenCalledWith(undefined, { projectId: "p1" });
    expect(createDocumentMock).toHaveBeenCalledWith({ kind: "doc", title: "Untitled doc", project_id: "p1" });
    expect(await screen.findByText("doc editor for Untitled doc")).toBeInTheDocument();
  });

  it("puts an uploaded PDF in the project, then opens it", async () => {
    const uploaded = meta({ id: "p2", kind: "pdf", title: "Scan", tainted: true });
    uploadPdfMock.mockResolvedValue(uploaded);
    setDocumentProjectMock.mockResolvedValue({ ...uploaded, project_id: "p1" });
    getDocumentMock.mockResolvedValue({ ...uploaded, payload: null });
    render(<DocumentsBoard projectId="p1" />);
    await screen.findByRole("button", { name: "Lease" });
    const file = new File(["%PDF-1.4"], "Scan.pdf", { type: "application/pdf" });
    fireEvent.change(screen.getByLabelText("PDF file"), { target: { files: [file] } });
    await waitFor(() => expect(setDocumentProjectMock).toHaveBeenCalledWith("p2", "p1"));
    expect(await screen.findByText("pdf viewer /api/documents/p2/pdf")).toBeInTheDocument();
  });
});
```

**2m.** `web/tests/MoneyBoard.test.tsx` **(after Task 1)**. Find:

```tsx
const keepExpenseMock = vi.fn();
vi.mock("../src/api/money", () => ({
  keepExpense: (...a: unknown[]) => keepExpenseMock(...a),
```

Replace with:

```tsx
const keepExpenseMock = vi.fn();
const starExpenseMock = vi.fn();
const voidExpenseMock = vi.fn();
vi.mock("../src/api/money", () => ({
  starExpense: (...a: unknown[]) => starExpenseMock(...a),
  voidExpense: (...a: unknown[]) => voidExpenseMock(...a),
  keepExpense: (...a: unknown[]) => keepExpenseMock(...a),
```

Find:

```tsx
const SUMMARY: MoneySummaryOut = {
  month: "2026-10", currency: "EUR", total: "12.50", expense_count: 2,
  by_project: [{ project: "food", spent: "12.50", budget: "300.00", remaining: "287.50" }],
  other_currencies: { USD: "20.00" },
};
const EXPENSES: ExpenseOut[] = [
  { id: "e1", project: "food", project_id: "p-food", amount: "12.50", currency: "EUR", description: "lunch", vendor: null,
    spent_at: "2026-10-13", status: "posted", created_at: "x", created_by_bot: "bot-1", tainted: false },
  { id: "e2", project: "travel", project_id: "p-travel", amount: "20.00", currency: "USD", description: "taxi", vendor: null,
    spent_at: "2026-10-12", status: "posted", created_at: "x", created_by_bot: null, tainted: true },
];
```

Replace with (Task 3's wire: each row has its own currency and its month line, and each expense has its links, star and status):

```tsx
const SUMMARY: MoneySummaryOut = {
  month: "2026-10", currency: "EUR", total: "12.50", expense_count: 2,
  by_project: [{
    project: "food", project_id: "p-food", currency: "EUR", spent: "12.50", budget: "300.00", remaining: "287.50",
    month: { budget: "300.00", spent: "12.50", remaining: "287.50", used_percent: 4, tone: "ok" }, other_currencies: {},
  }],
  other_currencies: { USD: "20.00" },
};
const EXPENSES: ExpenseOut[] = [
  { id: "e1", project: "food", project_id: "p-food", task_id: null, step_id: null, amount: "12.50", currency: "EUR",
    description: "lunch", vendor: null, spent_at: "2026-10-13", status: "posted", is_favorite: false, created_at: "x",
    created_by_bot: "bot-1", tainted: false },
  { id: "e2", project: "travel", project_id: "p-travel", task_id: null, step_id: null, amount: "20.00", currency: "USD",
    description: "taxi", vendor: null, spent_at: "2026-10-12", status: "posted", is_favorite: false, created_at: "x",
    created_by_bot: null, tainted: true },
];
```

Find:

```tsx
  for (const mock of [getSummaryMock, listExpensesMock, createExpenseMock, keepExpenseMock]) mock.mockReset();
```

Replace with:

```tsx
  for (const mock of [getSummaryMock, listExpensesMock, createExpenseMock, keepExpenseMock, starExpenseMock,
    voidExpenseMock]) mock.mockReset();
```

Append at the end of the file:

```tsx

describe("MoneyBoard stars, voids and one project's month", () => {
  it("stars and voids from the month list, and reloads after each", async () => {
    starExpenseMock.mockResolvedValue({ ...EXPENSES[0], is_favorite: true });
    voidExpenseMock.mockResolvedValue({ ...EXPENSES[0], status: "void" });
    const user = userEvent.setup();
    render(<MoneyBoard />);
    const list = await screen.findByRole("list", { name: "Expenses" });
    await user.click(within(list).getByRole("button", { name: "Star the food expense" }));
    expect(starExpenseMock).toHaveBeenCalledWith("e1", true);
    await waitFor(() => expect(getSummaryMock).toHaveBeenCalledTimes(2));
    await user.click(within(list).getByRole("button", { name: "Void the food expense" }));
    expect(voidExpenseMock).toHaveBeenCalledWith("e1", true);
    await waitFor(() => expect(getSummaryMock).toHaveBeenCalledTimes(3));
  });

  it("a project's month shows only its expenses and what it spent, and adds to it", async () => {
    createExpenseMock.mockResolvedValue(EXPENSES[0]);
    const user = userEvent.setup();
    render(<MoneyBoard project={{ id: "p-food", name: "food", currency: "EUR" }} />);
    const list = await screen.findByRole("list", { name: "Expenses" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(1);
    expect(within(list).getByText("lunch")).toBeInTheDocument();
    expect(screen.getByText(/12\.50/, { selector: ".money-board__total strong" })).toBeInTheDocument();
    expect(screen.queryByRole("table", { name: "By project" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Project")).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("Amount"), "5");
    await user.click(screen.getByRole("button", { name: "Add expense" }));
    // By id, so the gateway files it in this project and in its currency (H7), never by a name.
    expect(createExpenseMock).toHaveBeenCalledWith({ amount: "5.00", project_id: "p-food" });
  });

  it("says when a project spent nothing that month", async () => {
    render(<MoneyBoard initialMonth="2026-09" project={{ id: "p-garden", name: "Garden", currency: "EUR" }} />);
    expect(await screen.findByText("Nothing spent on this project in September 2026.")).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npx vitest run tests/BudgetBar.test.tsx tests/ExpenseList.test.tsx tests/TopupForm.test.tsx tests/TopupHistory.test.tsx tests/ProjectsBoard.test.tsx tests/Project.test.tsx tests/Board.test.tsx tests/live.test.ts tests/TasksBoard.test.tsx tests/NotesBoard.test.tsx tests/DocumentsBoard.test.tsx tests/MoneyBoard.test.tsx`

Expected: FAIL.
- Six files do not load, with `Failed to resolve import`:
  - `BudgetBar.test.tsx`, `ExpenseList.test.tsx`, `TopupForm.test.tsx`, `TopupHistory.test.tsx` and `ProjectsBoard.test.tsx` (`../src/components/projects/…` and `../src/components/board/ExpenseList`);
  - `Project.test.tsx` (`../src/pages/Project`).
- `Board.test.tsx`: "opens on Projects…" fails, because the tabs are `["Tasks", "Money", "Notes", "Documents"]`. The other two tests pass.
- `live.test.ts`: "refreshes tasks, notes and documents when a project is deleted" fails, because the boardVersion is `{ tasks: 0, money: 1, notes: 0, documents: 0 }`.
- `TasksBoard.test.tsx`: the seven new tests fail. They find no `Mark failed` or `Budget slice`, no `failed` chip, no `budget €50.00` chip, no spent / left chip and no project wording. `listTasks` was called with `"open"` and `createTask` without `project_id`.
- `NotesBoard.test.tsx` and `DocumentsBoard.test.tsx`: the four new tests fail, because the lists were called without the project filter and `setDocumentProject` was never called.
- `MoneyBoard.test.tsx`: the three new tests fail. There is no `Star the food expense` button, and the project's month still lists both expenses and the `Project` field.
- Every test that was already in these files still passes.

- [ ] **Step 4: Implement the types and the API**

**4a.** `web/src/api/types.ts` **(after Task 1 and the stuck flow; none of these lines are the stuck flow's)**. Find:

```ts
export type BoardTab = "tasks" | "money" | "notes" | "documents";
```

Replace with:

```ts
// Projects is first, and so the tab the Board opens on (projects hub H14).
export type BoardTab = "projects" | "tasks" | "money" | "notes" | "documents";
```

Find:

```ts
  status: "todo" | "in_progress" | "done" | "cancelled";
```

Replace with:

```ts
  status: "todo" | "in_progress" | "done" | "cancelled" | "failed";
```

Find:

```ts
  completed_at: string | null;
  created_by_bot: string | null;
  tainted: boolean; // written by a run that had read web content
}

// The user's expense (M1 D3): shared by every bot holding the finance role.
```

Replace with:

```ts
  completed_at: string | null; // when it was done, or failed
  created_by_bot: string | null;
  tainted: boolean; // written by a run that had read web content
  project_id: string | null; // the project it belongs to (projects hub P1)
  allocated_budget: string | null; // its budget slice, "250.00", in the project's currency (H11)
}

// The user's expense (M1 D3): shared by every bot holding the finance role.
```

Find:

```ts
  project_id: string;
  amount: string; // "12.50" — a decimal string, never a float
  currency: string;
  description: string | null;
  vendor: string | null;
  spent_at: string; // YYYY-MM-DD (Madrid day)
  status: string;
```

Replace with:

```ts
  project_id: string;
  task_id: string | null; // the task it was spent on, if any (H11)
  step_id: string | null; // one step of that task, if any
  amount: string; // "12.50" — a decimal string, never a float
  currency: string;
  description: string | null;
  vendor: string | null;
  spent_at: string; // YYYY-MM-DD (Madrid day)
  status: "posted" | "void"; // a void expense stays in the list and leaves every total (H6)
  is_favorite: boolean; // starred
```

Find:

```ts
export interface ProjectTotalOut {
  project: string; // the project's name
  spent: string;
  budget: string | null;
  remaining: string | null;
}
```

Replace with:

```ts
// One project's row of the month (Task 3's wire, H7): in the project's own currency, against
// its monthly limit. `spent`, `budget` and `remaining` repeat `month`'s.
export interface ProjectTotalOut {
  project: string; // the project's name
  project_id: string;
  currency: string;
  spent: string;
  budget: string | null; // the monthly limit
  remaining: string | null;
  month: BudgetLineOut;
  other_currencies: Record<string, string>;
}
```

Find:

```ts
  by_project: ProjectTotalOut[];
  other_currencies: Record<string, string>;
}
```

Replace with:

```ts
  by_project: ProjectTotalOut[];
  other_currencies: Record<string, string>;
}

// A budget as the server reckons it (H8): the web never adds amounts, it only shows them.
// `used_percent` and `tone` are null when there is no budget; `remaining` is negative when over.
export type BudgetTone = "ok" | "warn" | "over";

export interface BudgetLineOut {
  budget: string | null;
  spent: string;
  remaining: string | null;
  used_percent: number | null;
  tone: BudgetTone | null;
}

// A project's tasks: how many are done and how many failed, out of all but the cancelled ones (H11).
export interface ProjectProgressOut {
  done: number;
  failed: number;
  total: number;
}

// One project (GET /api/projects): every number in its own currency, General never among them (H2).
export interface ProjectOut {
  id: string;
  name: string;
  color: string; // one of the nine palette colours (H16)
  currency: string;
  status: "active" | "archived";
  start_date: string | null; // "YYYY-MM-DD"
  due_date: string | null;
  lead_bot_id: string | null;
  total: BudgetLineOut; // the total budget, top-ups included, against all spending
  month: BudgetLineOut; // the monthly limit, against this Madrid month
  other_currencies: Record<string, string>; // spent in other currencies, never converted (P4)
  starred_total: string;
  progress: ProjectProgressOut;
  tainted: boolean;
}

// A task's money on its project's page (design §2): its slice, what is spent on it, and what is
// left (negative when over). The server reckons all three.
export interface TaskMoneyOut {
  planned: string | null;
  spent: string;
  left: string | null;
}

// A project's page (GET /api/projects/{id}).
export interface ProjectDetailOut extends ProjectOut {
  tasks: TaskOut[];
  expenses: ExpenseOut[]; // the latest ones, void ones included
  notes: NoteSummaryOut[];
  documents: DocumentOut[];
  topups: TopupOut[]; // the whole history, newest first
  lead_bot_name: string | null;
  task_money: Record<string, TaskMoneyOut>; // by task id, over every expense of the project
}

// One row of a project's top-up history (H4): a credit, or an edit of one (`topup_id` set) or of
// the budget by hand (`topup_id` null). An edit's amount is the signed difference.
export interface TopupOut {
  id: string;
  amount: string;
  currency: string;
  source: string | null;
  kind: "credit" | "edit";
  topup_id: string | null;
  undone: boolean;
  created_at: string;
}
```

Find:

```ts
  pinned: boolean;
  revision: number;
  created_at: string;
  updated_at: string;
  created_by_bot: string | null;
  tainted: boolean;
}
```

Replace with:

```ts
  pinned: boolean;
  revision: number;
  created_at: string;
  updated_at: string;
  created_by_bot: string | null;
  tainted: boolean;
  project_id: string | null;
}
```

Find:

```ts
  pages: number | null;
  revision: number;
  created_at: string;
  updated_at: string;
  created_by_bot: string | null;
  tainted: boolean;
}
```

Replace with:

```ts
  pages: number | null;
  revision: number;
  created_at: string;
  updated_at: string;
  created_by_bot: string | null;
  tainted: boolean;
  project_id: string | null;
}
```

Find:

```ts
  change: "created" | "updated" | "completed" | "deleted";
```

Replace with:

```ts
  change: "created" | "updated" | "completed" | "deleted" | "failed";
```

Find:

```ts
  change: "expense_created" | "expense_updated" | "expense_deleted" | "budget_set";
```

Replace with:

```ts
  change:
    | "expense_created" | "expense_updated" | "expense_deleted" | "budget_set"
    // Projects and their top-ups ride on money_changed too (H10); `id` is the project's or the top-up's.
    | "project_created" | "project_updated" | "project_deleted" | "topup_added" | "topup_edited" | "topup_undone";
```

**4b.** Create `web/src/api/projects.ts`:

```ts
import { apiRequest } from "./client";
import type { ProjectDetailOut, ProjectOut, TopupOut } from "./types";

// The user's projects (projects hub): the same records every bot works on with its project tools.
// Amounts go as decimal strings ("1200.00"), already read by parseAmountInput.

export interface ProjectIn {
  name: string;
  currency: string;
  budget: string | null; // the total budget; top-ups raise it later
  monthly_budget: string | null;
  color: string;
  start_date: string | null; // "YYYY-MM-DD"
  due_date: string | null;
  lead_bot_id: string | null;
}

// Only the fields that change; null clears a date, the monthly limit or the lead bot.
// The total budget is not here: it has its own call, setProjectBudget.
export type ProjectPatchIn = Partial<{
  name: string;
  color: string;
  start_date: string | null;
  due_date: string | null;
  monthly_budget: string | null;
  lead_bot_id: string | null;
  status: ProjectOut["status"];
  currency: string;
}>;

export interface TopupIn {
  amount: string;
  source?: string; // where the money came from
}

const path = (projectId: string) => `/api/projects/${encodeURIComponent(projectId)}`;
const topupPath = (topupId: string) => `/api/topups/${encodeURIComponent(topupId)}`;

// General is never listed (H2); archived projects only when asked.
export function listProjects(includeArchived = false): Promise<ProjectOut[]> {
  return apiRequest<ProjectOut[]>("GET", includeArchived ? "/api/projects?include_archived=true" : "/api/projects");
}

export function getProject(projectId: string): Promise<ProjectDetailOut> {
  return apiRequest<ProjectDetailOut>("GET", path(projectId));
}

export function createProject(input: ProjectIn): Promise<ProjectOut> {
  return apiRequest<ProjectOut>("POST", "/api/projects", input);
}

export function updateProject(projectId: string, patch: ProjectPatchIn): Promise<ProjectOut> {
  return apiRequest<ProjectOut>("PATCH", path(projectId), patch);
}

// The total budget (P3): set it, or clear it with null (H5). The history gets a "Budget set" row.
export function setProjectBudget(projectId: string, amount: string | null): Promise<ProjectOut> {
  return apiRequest<ProjectOut>("PUT", `${path(projectId)}/budget`, { amount });
}

// Its expenses move to General; its tasks, notes and documents stay, unlinked (H9).
export function deleteProject(projectId: string): Promise<void> {
  return apiRequest<void>("DELETE", path(projectId));
}

export function listTopups(projectId: string): Promise<TopupOut[]> {
  return apiRequest<TopupOut[]>("GET", `${path(projectId)}/topups`);
}

export function addTopup(projectId: string, input: TopupIn): Promise<TopupOut> {
  return apiRequest<TopupOut>("POST", `${path(projectId)}/topups`, input);
}

// `amount` is the top-up's new amount; the server writes the difference as a "Top-up changed" row (H4).
export function editTopup(topupId: string, amount: string): Promise<TopupOut> {
  return apiRequest<TopupOut>("PATCH", topupPath(topupId), { amount });
}

// Undo takes the top-up and its changes out of the budget together; 409 when it is already undone.
export function undoTopup(topupId: string): Promise<TopupOut> {
  return apiRequest<TopupOut>("POST", `${topupPath(topupId)}/undo`);
}
```

**4c.** `web/src/api/money.ts` **(after Task 1)**. Find:

```ts
export interface ExpenseIn {
  amount: string; // already read by parseAmountInput: "12.50"
  project?: string; // a project's name; a new name makes a new project, none means General
  note?: string;
}
```

Replace with:

```ts
export interface ExpenseIn {
  amount: string; // already read by parseAmountInput: "12.50"
  project?: string; // a project's name; a new name makes a new project, none means General
  // A project's page names its project by id instead (never both): the expense then lands in exactly
  // that project, in its currency (H7). A name is found or made, so a near name could land elsewhere.
  project_id?: string;
  note?: string;
}
```

Find:

```ts
export function keepExpense(expenseId: string): Promise<ExpenseOut> {
  return apiRequest<ExpenseOut>("POST", `/api/money/expenses/${encodeURIComponent(expenseId)}/keep`);
}
```

Replace with:

```ts
export function keepExpense(expenseId: string): Promise<ExpenseOut> {
  return apiRequest<ExpenseOut>("POST", `/api/money/expenses/${encodeURIComponent(expenseId)}/keep`);
}

// Star an expense to keep an eye on it; its project shows the starred total (P6).
export function starExpense(expenseId: string, starred: boolean): Promise<ExpenseOut> {
  return apiRequest<ExpenseOut>("PUT", `/api/money/expenses/${encodeURIComponent(expenseId)}/star`, { starred });
}

// A void expense stays in the list and leaves every total; void it with false to restore it (H6).
export function voidExpense(expenseId: string, isVoid: boolean): Promise<ExpenseOut> {
  return apiRequest<ExpenseOut>("PUT", `/api/money/expenses/${encodeURIComponent(expenseId)}/void`, { void: isVoid });
}
```

**4d.** Replace the whole of `web/src/api/tasks.ts` with:

```ts
import { apiRequest } from "./client";
import type { TaskOut } from "./types";

// The user's tasks (M1 D2/D8): the same records every tasks-role bot works on.

export interface TaskIn {
  title: string;
  due_date?: string | null; // words ("tomorrow at 9") or ISO; the gateway reads it on Madrid time
  category?: string | null;
  priority?: TaskOut["priority"];
  project_id?: string; // the project it belongs to (a project page's Tasks tab)
}

// allocated_budget is the task's budget slice ("250.00", or null to clear it); it needs a project (H11).
export type TaskPatchIn = Partial<
  Pick<TaskOut, "title" | "description" | "category" | "priority" | "due_date" | "allocated_budget">
>;

export type TaskListStatus = "open" | "done" | "failed" | "all";

export interface TaskListFilter {
  projectId?: string; // only that project's tasks
}

export function listTasks(status: TaskListStatus = "open", filter: TaskListFilter = {}): Promise<TaskOut[]> {
  const project = filter.projectId ? `&project_id=${encodeURIComponent(filter.projectId)}` : "";
  return apiRequest<TaskOut[]>("GET", `/api/tasks?status=${status}${project}`);
}

export function createTask(input: TaskIn): Promise<TaskOut> {
  return apiRequest<TaskOut>("POST", "/api/tasks", input);
}

export function updateTask(taskId: string, patch: TaskPatchIn): Promise<TaskOut> {
  return apiRequest<TaskOut>("PATCH", `/api/tasks/${encodeURIComponent(taskId)}`, patch);
}

export function completeTask(taskId: string): Promise<TaskOut> {
  return apiRequest<TaskOut>("POST", `/api/tasks/${encodeURIComponent(taskId)}/complete`);
}

// Failed (P6): the task is closed as not done; a repeating one comes back like a done one (H11).
export function failTask(taskId: string): Promise<TaskOut> {
  return apiRequest<TaskOut>("POST", `/api/tasks/${encodeURIComponent(taskId)}/fail`);
}

// Keep: the user vouches for a task marked "from web content" (only here — no bot can).
export function keepTask(taskId: string): Promise<TaskOut> {
  return apiRequest<TaskOut>("POST", `/api/tasks/${encodeURIComponent(taskId)}/keep`);
}

export function deleteTask(taskId: string): Promise<void> {
  return apiRequest<void>("DELETE", `/api/tasks/${encodeURIComponent(taskId)}`);
}
```

**4e.** Replace the whole of `web/src/api/notes.ts` with:

```ts
import { apiRequest } from "./client";
import { withConflict } from "./conflict";
import type { NoteOut, NoteSummaryOut } from "./types";

// The user's notes (M2 D1/D4): the same records every notes-role bot works on.

export interface NoteIn {
  title?: string | null;
  content: string;
  tags?: string[];
  project_id?: string; // the project it belongs to (a project page's Notes tab)
}

export interface NoteSaveIn {
  base_revision: number;
  title?: string;
  content?: string;
  tags?: string[];
  pinned?: boolean;
}

export interface NoteListFilter {
  projectId?: string; // only that project's notes
}

const path = (noteId: string) => `/api/notes/${encodeURIComponent(noteId)}`;

export function listNotes(query = "", filter: NoteListFilter = {}): Promise<NoteSummaryOut[]> {
  const q = query.trim();
  const params = [
    q ? `q=${encodeURIComponent(q)}` : "",
    filter.projectId ? `project_id=${encodeURIComponent(filter.projectId)}` : "",
  ].filter((part) => part !== "");
  return apiRequest<NoteSummaryOut[]>("GET", params.length > 0 ? `/api/notes?${params.join("&")}` : "/api/notes");
}

export function getNote(noteId: string): Promise<NoteOut> {
  return apiRequest<NoteOut>("GET", path(noteId));
}

export function createNote(input: NoteIn): Promise<NoteOut> {
  return apiRequest<NoteOut>("POST", "/api/notes", input);
}

// A stale base_revision throws RevisionConflictError<NoteOut> carrying the stored note.
export function saveNote(noteId: string, input: NoteSaveIn): Promise<NoteOut> {
  return withConflict<NoteOut, NoteOut>(apiRequest<NoteOut>("PUT", path(noteId), input));
}

// Keep: the user vouches for a note marked "from web content" (only here — no bot can).
export function keepNote(noteId: string): Promise<NoteOut> {
  return apiRequest<NoteOut>("POST", `${path(noteId)}/keep`);
}

export function deleteNote(noteId: string): Promise<void> {
  return apiRequest<void>("DELETE", path(noteId));
}
```

**4f.** Replace the whole of `web/src/api/documents.ts` with:

```ts
import { apiRequest, apiUpload } from "./client";
import { withConflict } from "./conflict";
import type { DocumentDetailOut, DocumentKind, DocumentOut } from "./types";

// The user's documents (M2 D2/D4): the same records every docs-role bot works on.

const MAX_DOCUMENT_TITLE_LENGTH = 120; // roost/constants.py

export interface DocumentSaveIn {
  base_revision: number;
  payload?: Record<string, unknown>;
  title?: string;
}

export interface DocumentCreateIn {
  kind: "doc" | "sheet";
  title: string;
  project_id?: string; // the project it belongs to (a project page's Docs tab)
}

export interface DocumentListFilter {
  projectId?: string; // only that project's documents
}

const path = (documentId: string) => `/api/documents/${encodeURIComponent(documentId)}`;

export function listDocuments(kind?: DocumentKind, filter: DocumentListFilter = {}): Promise<DocumentOut[]> {
  const params = [
    kind ? `kind=${kind}` : "",
    filter.projectId ? `project_id=${encodeURIComponent(filter.projectId)}` : "",
  ].filter((part) => part !== "");
  return apiRequest<DocumentOut[]>("GET", params.length > 0 ? `/api/documents?${params.join("&")}` : "/api/documents");
}

export function getDocument(documentId: string): Promise<DocumentDetailOut> {
  return apiRequest<DocumentDetailOut>("GET", path(documentId));
}

export function createDocument(input: DocumentCreateIn): Promise<DocumentOut> {
  return apiRequest<DocumentOut>("POST", "/api/documents", input);
}

// A stale base_revision throws RevisionConflictError<DocumentDetailOut> carrying the stored copy.
export function saveDocument(documentId: string, input: DocumentSaveIn): Promise<DocumentOut> {
  return withConflict<DocumentOut, DocumentDetailOut>(apiRequest<DocumentOut>("PUT", path(documentId), input));
}

// An uploaded PDF is outside content: it arrives marked "from web content" until Kept.
export function uploadPdf(file: File): Promise<DocumentOut> {
  const title = (file.name.replace(/\.pdf$/i, "").trim() || "Untitled PDF").slice(0, MAX_DOCUMENT_TITLE_LENGTH);
  return apiUpload<DocumentOut>(`/api/documents/pdf?title=${encodeURIComponent(title)}`, file, "application/pdf");
}

// Put a document in a project, or with null take it out. The revision stays, so an open editor
// is not disturbed (H12).
export function setDocumentProject(documentId: string, projectId: string | null): Promise<DocumentOut> {
  return apiRequest<DocumentOut>("PUT", `${path(documentId)}/project`, { project_id: projectId });
}

export function pdfUrl(documentId: string): string {
  return `${path(documentId)}/pdf`;
}

// Keep: the user vouches for a web-made or uploaded document (only here — no bot can).
export function keepDocument(documentId: string): Promise<DocumentOut> {
  return apiRequest<DocumentOut>("POST", `${path(documentId)}/keep`);
}

export function deleteDocument(documentId: string): Promise<void> {
  return apiRequest<void>("DELETE", path(documentId));
}
```

**4g.** `web/src/components/board/money.ts`. Find:

```ts
  const amount = Number(value);
  return amount > 0 ? amount.toFixed(2) : null;
}
```

Replace with:

```ts
  const amount = Number(value);
  return amount > 0 ? amount.toFixed(2) : null;
}

export const AMOUNT_HELP = "Enter an amount like 12,50.";

/** A money field that may be left empty: "" → null (none, or clear it); "12,50" → "12.50"; unreadable → undefined. */
export function readAmount(text: string): string | null | undefined {
  if (!text.trim()) return null;
  return parseAmountInput(text) ?? undefined;
}
```

- [ ] **Step 5: Implement the live store**

`web/src/store/live.ts` **(after the stuck flow; it edits the header, the import, `LiveState`/`initialLiveState` and the `documents_changed` case, not these lines)**. Find:

```ts
export function applyFrame(state: LiveState, frame: ServerFrame): LiveState {
```

Replace with:

```ts
type BoardVersion = LiveState["boardVersion"];
type MoneyChange = Extract<ServerFrame, { type: "money_changed" }>["change"];

// money_changed reloads the money (H10). A deleted project also unlinks its tasks, notes and
// documents in one go (H9), with no frame of their own, so those tabs reload too.
export function bumpMoney(version: BoardVersion, change: MoneyChange): BoardVersion {
  const money = { ...version, money: version.money + 1 };
  if (change !== "project_deleted") return money;
  return { ...money, tasks: version.tasks + 1, notes: version.notes + 1, documents: version.documents + 1 };
}

export function applyFrame(state: LiveState, frame: ServerFrame): LiveState {
```

Find:

```ts
    case "money_changed":
      return { ...state, cursor: frame.seq, boardVersion: { ...state.boardVersion, money: state.boardVersion.money + 1 } };
```

Replace with:

```ts
    case "money_changed":
      return { ...state, cursor: frame.seq, boardVersion: bumpMoney(state.boardVersion, frame.change) };
```

- [ ] **Step 6: Implement the expense list, star and void, and one project's month**

**6a.** Create `web/src/components/board/ExpenseList.tsx`:

```tsx
import { MadeByChip } from "./MadeByChip";
import { WebContentChip } from "./WebContentChip";
import { dayLabel, formatMoney } from "./money";
import type { ExpenseOut } from "../../api/types";

export interface ExpenseListProps {
  expenses: readonly ExpenseOut[];
  currency: string; // an amount in another currency is marked apart
  showProject?: boolean; // false on a project's own page, where every row is that project
  onKeep: (expenseId: string) => void;
  onStar?: (expenseId: string, starred: boolean) => void;
  onVoid?: (expenseId: string, isVoid: boolean) => void;
}

const what = (expense: ExpenseOut) => `the ${expense.project} expense`;

function rowClass(expense: ExpenseOut, currency: string): string {
  const other = expense.currency === currency ? "" : " expense-row--other";
  const voided = expense.status === "void" ? " expense-row--void" : "";
  return `expense-row${other}${voided}`;
}

// The star (P6): a toggle when the list may change it, a quiet mark when it may not.
function Star({ expense, onStar }: { expense: ExpenseOut; onStar: ExpenseListProps["onStar"] }) {
  if (!onStar) {
    return expense.is_favorite ? <span className="expense-row__star" role="img" aria-label="Starred">★</span> : null;
  }
  return (
    <button type="button" className={`expense-star${expense.is_favorite ? " expense-star--on" : ""}`}
      aria-pressed={expense.is_favorite} aria-label={`Star ${what(expense)}`}
      onClick={() => onStar(expense.id, !expense.is_favorite)}>
      {expense.is_favorite ? "★" : "☆"}
    </button>
  );
}

// Void keeps the expense in the list but takes it out of every total; Restore brings it back (H6).
function VoidButton({ expense, onVoid }: { expense: ExpenseOut; onVoid: ExpenseListProps["onVoid"] }) {
  if (!onVoid) return null;
  const isVoid = expense.status === "void";
  return (
    <button type="button" className="expense-row__void" aria-label={`${isVoid ? "Restore" : "Void"} ${what(expense)}`}
      onClick={() => onVoid(expense.id, !isVoid)}>
      {isVoid ? "Restore" : "Void"}
    </button>
  );
}

export function ExpenseList({ expenses, currency, showProject = true, onKeep, onStar, onVoid }: ExpenseListProps) {
  return (
    <ul className="expense-list" aria-label="Expenses">
      {expenses.map((e) => (
        <li key={e.id} className={rowClass(e, currency)}>
          <Star expense={e} onStar={onStar} />
          <span className="expense-row__day">{dayLabel(e.spent_at)}</span>
          <span className="expense-row__what">
            {showProject ? <span className="expense-row__project">{e.project}</span> : null}
            {e.description ? <span className="expense-row__note">{e.description}</span> : null}
            {e.status === "void" ? <span className="board-chip board-chip--void">void</span> : null}
            <MadeByChip botId={e.created_by_bot} />
            {e.tainted ? <WebContentChip what={what(e)} onKeep={() => onKeep(e.id)} /> : null}
            <VoidButton expense={e} onVoid={onVoid} />
          </span>
          <span className="expense-row__amount">{formatMoney(e.amount, e.currency)}</span>
        </li>
      ))}
    </ul>
  );
}
```

**6b.** `web/src/components/board/ExpenseAddForm.tsx` **(after Task 1)**. Find:

```tsx
import { MAX_AMOUNT_TEXT, MAX_CATEGORY, MAX_NOTE, parseAmountInput } from "./money";
```

Replace with:

```tsx
import { AMOUNT_HELP, MAX_AMOUNT_TEXT, MAX_CATEGORY, MAX_NOTE, parseAmountInput } from "./money";
```

Find:

```tsx
export interface ExpenseAddFormProps {
  projects: readonly string[]; // offered as suggestions; a new name makes a new project
  onAdded: () => void;
}
```

Replace with:

```tsx
export interface ExpenseAddFormProps {
  projects: readonly string[]; // offered as suggestions; a new name makes a new project
  // A project's page: every expense goes to this project (by id, so it takes the project's
  // currency, H7), and there is no Project field.
  fixedProjectId?: string;
  onAdded: () => void;
}

interface ProjectFieldProps {
  value: string;
  projects: readonly string[];
  onChange: (name: string) => void;
}

function ProjectField({ value, projects, onChange }: ProjectFieldProps) {
  return (
    <>
      <input className="input" aria-label="Project" placeholder="Project" value={value} list="expense-projects"
        maxLength={MAX_CATEGORY} onChange={(e) => onChange(e.target.value)} />
      <datalist id="expense-projects">
        {projects.map((name) => <option key={name} value={name} />)}
      </datalist>
    </>
  );
}
```

Find:

```tsx
export function ExpenseAddForm({ projects, onAdded }: ExpenseAddFormProps) {
```

Replace with:

```tsx
export function ExpenseAddForm({ projects, fixedProjectId, onAdded }: ExpenseAddFormProps) {
```

Find:

```tsx
      setError("Enter an amount like 12,50.");
```

Replace with:

```tsx
      setError(AMOUNT_HELP);
```

Find:

```tsx
      await moneyApi.createExpense({ amount: parsed, project: project.trim() || undefined, note: note.trim() || undefined });
```

Replace with:

```tsx
      const target = fixedProjectId === undefined
        ? { project: project.trim() || undefined }
        : { project_id: fixedProjectId };
      await moneyApi.createExpense({ amount: parsed, ...target, note: note.trim() || undefined });
```

Find:

```tsx
    <form className="expense-add" onSubmit={(event) => { event.preventDefault(); void submit(); }}>
      <input className="input" aria-label="Amount" inputMode="decimal" placeholder="€ 12,50" value={amount}
        maxLength={MAX_AMOUNT_TEXT} onChange={(e) => setAmount(e.target.value)} />
      <input className="input" aria-label="Project" placeholder="Project" value={project} list="expense-projects"
        maxLength={MAX_CATEGORY} onChange={(e) => setProject(e.target.value)} />
      <datalist id="expense-projects">
        {projects.map((name) => <option key={name} value={name} />)}
      </datalist>
```

Replace with:

```tsx
    <form className={fixedProjectId === undefined ? "expense-add" : "expense-add expense-add--fixed"}
      onSubmit={(event) => { event.preventDefault(); void submit(); }}>
      <input className="input" aria-label="Amount" inputMode="decimal" placeholder="€ 12,50" value={amount}
        maxLength={MAX_AMOUNT_TEXT} onChange={(e) => setAmount(e.target.value)} />
      {fixedProjectId === undefined ? <ProjectField value={project} projects={projects} onChange={setProject} /> : null}
```

**6c.** Replace the whole of `web/src/components/board/MoneyBoard.tsx` **(after Task 1)** with:

```tsx
import { useCallback, useEffect, useRef, useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { ExpenseAddForm } from "./ExpenseAddForm";
import { ExpenseList } from "./ExpenseList";
import { formatMoney, madridMonth, monthLabel, shiftMonth } from "./money";
import { useLiveState } from "../../hooks/useLiveStore";
import * as moneyApi from "../../api/money";
import { describeError } from "../../api/client";
import type { ExpenseOut, MoneySummaryOut, ProjectOut, ProjectTotalOut } from "../../api/types";

interface MonthData {
  month: string;
  summary: MoneySummaryOut;
  expenses: ExpenseOut[];
}

// The project a MoneyBoard is narrowed to: a project page's Money tab (H14).
export type MoneyProject = Pick<ProjectOut, "id" | "name" | "currency">;

export interface MoneyBoardProps {
  initialMonth?: string;
  project?: MoneyProject;
}

// Each project in its own currency, against its monthly limit (H7); the server sends every number.
function LimitCell({ row }: { row: ProjectTotalOut }) {
  const money = (amount: string) => formatMoney(amount, row.currency);
  if (row.budget === null || row.remaining === null) return <td className="money-table__none">no limit</td>;
  const over = row.remaining.startsWith("-");
  return (
    <td className={over ? "money-table__over" : undefined}>
      {over ? `${money(row.remaining.slice(1))} over ${money(row.budget)}` : `${money(row.remaining)} left of ${money(row.budget)}`}
    </td>
  );
}

function ProjectTable({ summary }: { summary: MoneySummaryOut }) {
  return (
    <table className="money-table" aria-label="By project">
      <thead><tr><th scope="col">Project</th><th scope="col">Spent</th><th scope="col">Monthly limit</th></tr></thead>
      <tbody>
        {summary.by_project.map((row) => (
          <tr key={row.project_id}>
            <th scope="row">{row.project}</th>
            <td>{formatMoney(row.spent, row.currency)}</td>
            <LimitCell row={row} />
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function MonthTotals({ data, isThisMonth }: { data: MonthData; isThisMonth: boolean }) {
  const { summary, expenses } = data;
  if (summary.expense_count === 0 && expenses.length === 0) {
    return isThisMonth
      ? <p className="board-empty">Nothing spent yet this month. Add an expense, or tell any bot in its chat.</p>
      : <p className="board-empty">Nothing spent in {monthLabel(data.month)}.</p>;
  }
  return (
    <>
      <p className="money-board__total">Spent <strong>{formatMoney(summary.total, summary.currency)}</strong></p>
      {Object.entries(summary.other_currencies).map(([code, total]) => (
        <p key={code} className="money-board__other">Also {formatMoney(total, code)} (not in the total)</p>
      ))}
      {summary.by_project.length > 0 ? <ProjectTable summary={summary} /> : null}
    </>
  );
}

interface ProjectMonthProps {
  data: MonthData;
  project: MoneyProject;
  isThisMonth: boolean;
}

// One project's month: what it spent in its own currency, from its row of the summary.
function ProjectMonthTotals({ data, project, isThisMonth }: ProjectMonthProps) {
  if (data.expenses.length === 0) {
    return isThisMonth
      ? <p className="board-empty">Nothing spent on this project yet this month.</p>
      : <p className="board-empty">Nothing spent on this project in {monthLabel(data.month)}.</p>;
  }
  const row = data.summary.by_project.find((candidate) => candidate.project_id === project.id);
  if (!row) return null;
  return (
    <>
      <p className="money-board__total">Spent <strong>{formatMoney(row.spent, row.currency)}</strong></p>
      {Object.entries(row.other_currencies).map(([code, total]) => (
        <p key={code} className="money-board__other">Also {formatMoney(total, code)} (not in the total)</p>
      ))}
    </>
  );
}

function MonthHead({ month, atThisMonth, onPick }: { month: string; atThisMonth: boolean; onPick: (month: string) => void }) {
  return (
    <header className="money-board__head">
      <button type="button" className="icon-btn" aria-label="Previous month" onClick={() => onPick(shiftMonth(month, -1))}>‹</button>
      <h2 className="money-board__month">{monthLabel(month)}</h2>
      <button type="button" className="icon-btn" aria-label="Next month" disabled={atThisMonth}
        onClick={() => onPick(shiftMonth(month, 1))}>›</button>
    </header>
  );
}

function PastMonth({ month, thisMonth, onBack }: { month: string; thisMonth: string; onBack: () => void }) {
  return (
    <div className="money-board__past">
      <button type="button" className="btn btn--quiet btn--small" onClick={onBack}>Back to {monthLabel(thisMonth)}</button>
      <p className="board-empty">New expenses land on today. For a day in {monthLabel(month)}, tell any bot in its chat.</p>
    </div>
  );
}

// Only the newest request may paint (fast month clicks).
function useMonthData(month: string, version: number) {
  const [data, setData] = useState<MonthData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef(0);
  const load = useCallback(() => {
    const ticket = ++latest.current;
    Promise.all([moneyApi.getSummary(month), moneyApi.listExpenses(month)])
      .then(([summary, expenses]) => {
        if (ticket === latest.current) { setData({ month, summary, expenses }); setError(null); }
      })
      .catch((err: unknown) => { if (ticket === latest.current) setError(describeError(err)); });
  }, [month]);
  useEffect(() => load(), [load, version]);
  const fail = useCallback((err: unknown) => setError(describeError(err)), []);
  return { data: data && data.month === month ? data : null, error, fail, load };
}

function expenseActions(load: () => void, fail: (err: unknown) => void) {
  return {
    keep: (expenseId: string) => { moneyApi.keepExpense(expenseId).then(load).catch(fail); },
    star: (expenseId: string, starred: boolean) => { moneyApi.starExpense(expenseId, starred).then(load).catch(fail); },
    setVoid: (expenseId: string, isVoid: boolean) => { moneyApi.voidExpense(expenseId, isVoid).then(load).catch(fail); },
  };
}

// The month's rows for one project only: a filter, never a sum.
function forProject(data: MonthData, projectId: string): MonthData {
  return { ...data, expenses: data.expenses.filter((expense) => expense.project_id === projectId) };
}

// The user's money for one Madrid month, shared by every bot (D1); with a project, that project's
// month only. Reloads whenever a money_changed frame arrives (a bot or another tab logged one).
export function MoneyBoard({ initialMonth, project }: MoneyBoardProps) {
  const live = useLiveState();
  const [month, setMonth] = useState(() => initialMonth ?? madridMonth(new Date()));
  const { data, error, fail, load } = useMonthData(month, live.boardVersion.money);
  const actions = expenseActions(load, fail);
  const thisMonth = madridMonth(new Date());
  const atThisMonth = month >= thisMonth; // new expenses land today, so the form lives on this month
  const shown = data && project ? forProject(data, project.id) : data;
  return (
    <section className="money-board" aria-label="Money">
      <MonthHead month={month} atThisMonth={atThisMonth} onPick={setMonth} />
      {error ? <ErrorNotice message={error} onRetry={load} /> : null}
      {shown && project ? <ProjectMonthTotals data={shown} project={project} isThisMonth={atThisMonth} /> : null}
      {shown && !project ? <MonthTotals data={shown} isThisMonth={atThisMonth} /> : null}
      {!shown && !error ? <p className="board-loading">Loading&hellip;</p> : null}
      {atThisMonth ? (
        <ExpenseAddForm projects={shown ? shown.summary.by_project.map((row) => row.project) : []}
          fixedProjectId={project?.id} onAdded={load} />
      ) : <PastMonth month={month} thisMonth={thisMonth} onBack={() => setMonth(thisMonth)} />}
      {shown && shown.expenses.length > 0 ? (
        <ExpenseList expenses={shown.expenses} currency={project?.currency ?? shown.summary.currency}
          showProject={!project} onKeep={actions.keep} onStar={actions.star} onVoid={actions.setVoid} />
      ) : null}
    </section>
  );
}
```

- [ ] **Step 7: Implement failed tasks and a project's tasks**

**7a.** Replace the whole of `web/src/components/board/TaskRow.tsx` with:

```tsx
import { MadeByChip } from "./MadeByChip";
import { formatMoney } from "./money";
import { formatDueChip, formatEarly, formatReminder } from "./taskChips";
import { WebContentChip } from "./WebContentChip";
import type { TaskMoneyOut, TaskOut } from "../../api/types";

export interface TaskRowProps {
  task: TaskOut;
  currency?: string; // its project's currency (a project page), to show its budget slice
  money?: TaskMoneyOut; // what is spent on it and what is left (a project page)
  completing: boolean;
  onComplete: (taskId: string) => void;
  onEdit: (task: TaskOut) => void;
  onKeep: (taskId: string) => void;
}

const FLAGGED: ReadonlySet<TaskOut["priority"]> = new Set(["high", "urgent"]);
const OPEN: ReadonlySet<TaskOut["status"]> = new Set(["todo", "in_progress"]);
// How a finished task ended; failed is red (design §2: it counts as finished but is shown red).
const ENDED: Partial<Record<TaskOut["status"], string>> = { done: "done", failed: "failed", cancelled: "cancelled" };
const NOTHING_SPENT = "0.00";

interface ChipsProps {
  task: TaskOut;
  currency?: string;
  money?: TaskMoneyOut;
  onKeep: (taskId: string) => void;
}

// "€80.00 spent, €40.00 left" or "€130.00 spent, over by €30.00" (design §2). The server
// reckons every number; this only formats them.
function spentText(money: TaskMoneyOut, currency: string): string {
  const spent = `${formatMoney(money.spent, currency)} spent`;
  if (money.left === null) return spent;
  return money.left.startsWith("-")
    ? `${spent}, over by ${formatMoney(money.left.slice(1), currency)}`
    : `${spent}, ${formatMoney(money.left, currency)} left`;
}

// The chips under a task's title: how it ended, when, reminders, kind, its budget slice and where
// it came from. A finished task's due and reminders no longer matter, so they are left out.
function TaskChips({ task, currency, money, onKeep }: ChipsProps) {
  const open = OPEN.has(task.status);
  const ended = ENDED[task.status];
  const due = formatDueChip(task.due_date, task.reminder_at);
  const early = formatEarly(task.pre_reminders, task.reminder_at);
  return (
    <div className="task-row__chips">
      {ended ? <span className={`board-chip board-chip--${task.status}`}>{ended}</span> : null}
      {FLAGGED.has(task.priority) ? (
        <span className={`board-chip board-chip--${task.priority}`}>{task.priority}</span>
      ) : null}
      {open && due.label ? <span className={`board-chip board-chip--${due.tone}`}>{due.label}</span> : null}
      {open && task.reminder_at ? (
        <span className="board-chip board-chip--reminder">{formatReminder(task.reminder_at, task.due_date)}</span>
      ) : null}
      {open && early ? <span className="board-chip">{early}</span> : null}
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

export function TaskRow({ task, currency, money, completing, onComplete, onEdit, onKeep }: TaskRowProps) {
  const open = OPEN.has(task.status);
  return (
    <li className={`task-row task-row--${task.priority}${open ? "" : " task-row--closed"}`}>
      <input type="checkbox" className="task-row__check" aria-label={`Complete ${task.title}`}
        checked={completing || task.status === "done"} disabled={completing || !open}
        onChange={() => onComplete(task.id)} />
      <div className="task-row__main">
        <span className="task-row__title">{task.title}</span>
        <TaskChips task={task} currency={currency} money={money} onKeep={onKeep} />
      </div>
      <button type="button" className="btn btn--quiet btn--small" onClick={() => onEdit(task)}>
        Edit
      </button>
    </li>
  );
}
```

**7b.** Replace the whole of `web/src/components/board/TaskAddForm.tsx` with:

```tsx
import { useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
import * as tasksApi from "../../api/tasks";
import { describeError } from "../../api/client";
import { MAX_DUE_TEXT, MAX_TITLE } from "./taskLimits";

export interface TaskAddFormProps {
  onAdded: () => void;
  projectId?: string; // a project page: the new task joins that project
}

// "When" takes words ("tomorrow at 9"): the gateway reads them on Madrid time.
export function TaskAddForm({ onAdded, projectId }: TaskAddFormProps) {
  const [title, setTitle] = useState("");
  const [when, setWhen] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    if (!title.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const input = { title: title.trim(), due_date: when.trim() || null };
      await tasksApi.createTask(projectId ? { ...input, project_id: projectId } : input);
      setTitle("");
      setWhen("");
      onAdded();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="task-add" onSubmit={(event) => { event.preventDefault(); void submit(); }}>
      <input className="input" aria-label="New task" placeholder="Add a task…" value={title}
        maxLength={MAX_TITLE} onChange={(e) => setTitle(e.target.value)} />
      <input className="input" aria-label="When" placeholder="When? e.g. tomorrow at 9" value={when}
        maxLength={MAX_DUE_TEXT} onChange={(e) => setWhen(e.target.value)} />
      <button type="submit" className="btn btn--primary" disabled={busy || !title.trim()}>Add</button>
      {error ? <ErrorNotice message={error} /> : null}
    </form>
  );
}
```

**7c.** Replace the whole of `web/src/components/board/TaskEditForm.tsx` with:

```tsx
import { useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
import * as tasksApi from "../../api/tasks";
import { describeError } from "../../api/client";
import type { TaskOut } from "../../api/types";
import { AMOUNT_HELP, MAX_AMOUNT_TEXT, readAmount } from "./money";
import { MAX_DUE_TEXT, MAX_TITLE } from "./taskLimits";

const PRIORITIES: readonly TaskOut["priority"][] = ["low", "medium", "high", "urgent"];
const OPEN: ReadonlySet<TaskOut["status"]> = new Set(["todo", "in_progress"]);

interface Fields {
  title: string;
  priority: TaskOut["priority"];
  when: string;
  slice: string;
}

// A timed due reads "2026-10-14 09:00" (Madrid time, which the gateway reads back).
function dueText(due: string | null): string {
  if (!due) return "";
  return due.includes("T") ? due.slice(0, 16).replace("T", " ") : due;
}

// Sends only the due and the budget slice when they changed; an emptied field clears it.
// A slice it can't read gives null, and the form says so instead of sending.
function patchFor(task: TaskOut, fields: Fields): tasksApi.TaskPatchIn | null {
  const patch: tasksApi.TaskPatchIn = { title: fields.title.trim(), priority: fields.priority };
  const when = fields.when.trim();
  const withDue = when === dueText(task.due_date) ? patch : { ...patch, due_date: when || null };
  if (!task.project_id) return withDue;
  const slice = readAmount(fields.slice);
  if (slice === undefined) return null;
  return slice === (task.allocated_budget ?? null) ? withDue : { ...withDue, allocated_budget: slice };
}

function useTaskAction(onDone: () => void) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = async (request: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await request();
      onDone();
    } catch (err) {
      setError(describeError(err));
      setBusy(false);
    }
  };
  return { busy, error, setError, run };
}

// A task's share of its project's budget (H11), in the project's currency.
function SliceField({ value, onChange }: { value: string; onChange: (text: string) => void }) {
  return (
    <label className="field"><span className="field__label">Budget slice</span>
      <input className="input" inputMode="decimal" value={value} maxLength={MAX_AMOUNT_TEXT}
        placeholder="part of the project's budget, or empty" onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}

export function TaskEditForm({ task, onDone }: { task: TaskOut; onDone: () => void }) {
  const [fields, setFields] = useState<Fields>(() => ({
    title: task.title, priority: task.priority, when: dueText(task.due_date), slice: task.allocated_budget ?? "",
  }));
  const { busy, error, setError, run } = useTaskAction(onDone);
  const set = <K extends keyof Fields>(key: K, value: Fields[K]) => setFields((current) => ({ ...current, [key]: value }));
  const save = () => {
    const patch = patchFor(task, fields);
    if (patch === null) setError(AMOUNT_HELP);
    else void run(() => tasksApi.updateTask(task.id, patch));
  };

  return (
    <form className="task-edit" aria-label={`Edit ${task.title}`} onSubmit={(e) => { e.preventDefault(); save(); }}>
      <label className="field task-edit__title"><span className="field__label">Title</span>
        <input className="input" value={fields.title} maxLength={MAX_TITLE} onChange={(e) => set("title", e.target.value)} />
      </label>
      <label className="field"><span className="field__label">Due</span>
        <input className="input" value={fields.when} maxLength={MAX_DUE_TEXT} placeholder="tomorrow at 9, 2026-10-20, or empty"
          onChange={(e) => set("when", e.target.value)} />
      </label>
      <label className="field"><span className="field__label">Priority</span>
        <select className="input" value={fields.priority}
          onChange={(e) => set("priority", e.target.value as TaskOut["priority"])}>
          {PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
      </label>
      {task.project_id ? <SliceField value={fields.slice} onChange={(text) => set("slice", text)} /> : null}
      {error ? <ErrorNotice message={error} /> : null}
      <div className="task-edit__actions">
        <button type="submit" className="btn btn--primary btn--small" disabled={busy || !fields.title.trim()}>Save</button>
        <button type="button" className="btn btn--quiet btn--small" onClick={onDone}>Cancel</button>
        {OPEN.has(task.status) ? (
          <button type="button" className="btn btn--danger btn--small task-edit__fail" disabled={busy}
            onClick={() => void run(() => tasksApi.failTask(task.id))}>Mark failed</button>
        ) : null}
      </div>
    </form>
  );
}
```

**7d.** Replace the whole of `web/src/components/board/TasksBoard.tsx` with:

```tsx
import { useCallback, useEffect, useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { TaskAddForm } from "./TaskAddForm";
import { TaskEditForm } from "./TaskEditForm";
import { TaskRow } from "./TaskRow";
import { useLiveState } from "../../hooks/useLiveStore";
import * as tasksApi from "../../api/tasks";
import { describeError } from "../../api/client";
import type { TaskMoneyOut, TaskOut } from "../../api/types";

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

// The user's open tasks, shared by every bot (D1), or one project's tasks. Reloads
// whenever a tasks_changed frame arrives (a bot or another tab changed one).
export function TasksBoard({ projectId, currency, money }: TasksBoardProps) {
  const { tasks, setTasks, error, setError, load } = useTaskList(projectId);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [completing, setCompleting] = useState<ReadonlySet<string>>(NONE);
  const fail = (err: unknown) => setError(describeError(err));

  const complete = (taskId: string) => {
    setCompleting((ids) => new Set([...ids, taskId]));
    tasksApi.completeTask(taskId)
      .then(() => { setTasks((shown) => shown && shown.filter((task) => task.id !== taskId)); load(); })
      .catch(fail)
      .finally(() => setCompleting((ids) => new Set([...ids].filter((id) => id !== taskId))));
  };
  const doneEditing = () => { setEditingId(null); load(); };
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
          {tasks.map((task) => task.id === editingId ? (
            <li key={task.id} className="task-row task-row--editing"><TaskEditForm task={task} onDone={doneEditing} /></li>
          ) : (
            <TaskRow key={task.id} task={task} currency={currency} money={money?.[task.id]}
              completing={completing.has(task.id)} onComplete={complete}
              onEdit={(picked) => setEditingId(picked.id)} onKeep={keep} />
          ))}
        </ul>
      ) : null}
    </section>
  );
}
```

- [ ] **Step 8: Implement notes and documents in a project, and the shared lazy panel**

**8a.** Create `web/src/components/board/lazyPanel.tsx`:

```tsx
import { Suspense, type ComponentType, type LazyExoticComponent } from "react";

// What a lazy Board panel may be told: the project it is narrowed to (a project page), or nothing (the Board).
export interface PanelProps {
  projectId?: string;
}

// Heavier panels are their own chunks (M2 D4), so the main bundle stays small. This shows the Board's
// loading line while a chunk arrives, and passes the panel its props.
export function lazyPanel(Panel: LazyExoticComponent<ComponentType<PanelProps>>) {
  return function LazyPanel(props: PanelProps) {
    return (
      <Suspense fallback={<p className="board-loading">Loading&hellip;</p>}>
        <Panel {...props} />
      </Suspense>
    );
  };
}
```

**8b.** Replace the whole of `web/src/components/notes/NotesBoard.tsx` with:

```tsx
import { useCallback, useEffect, useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { NoteEditor } from "./NoteEditor";
import { NoteList } from "./NoteList";
import { MAX_NOTE_QUERY_LENGTH } from "./noteHelpers";
import { useLiveState } from "../../hooks/useLiveStore";
import * as notesApi from "../../api/notes";
import { describeError } from "../../api/client";
import type { NoteSummaryOut } from "../../api/types";

interface ToolbarProps {
  search: string;
  onSearch: (text: string) => void;
  onSubmit: () => void;
  onNew: () => void;
}

function NotesToolbar({ search, onSearch, onSubmit, onNew }: ToolbarProps) {
  return (
    <form role="search" className="notes-toolbar" onSubmit={(event) => { event.preventDefault(); onSubmit(); }}>
      <input type="search" aria-label="Search notes" placeholder="Search notes" value={search}
        maxLength={MAX_NOTE_QUERY_LENGTH} onChange={(event) => onSearch(event.target.value)} />
      <button type="submit" className="btn btn--quiet">Search</button>
      <button type="button" className="btn btn--primary" onClick={onNew}>New note</button>
    </form>
  );
}

interface ListAreaProps {
  notes: NoteSummaryOut[] | null;
  query: string;
  onOpen: (noteId: string) => void;
  onKeep: (noteId: string) => void;
}

function NotesListArea({ notes, query, onOpen, onKeep }: ListAreaProps) {
  if (notes === null) return <p className="board-loading">Loading&hellip;</p>;
  if (notes.length === 0) {
    return <p className="board-empty">{query ? `No note matches “${query}”.` : "No notes yet. Write one, or tell any bot “note: …”."}</p>;
  }
  return <NoteList notes={notes} onOpen={onOpen} onKeep={onKeep} />;
}

export interface NotesBoardProps {
  projectId?: string; // one project's notes (its page's Notes tab); a new note joins that project
}

// The user's notes, shared by every bot (D1), or one project's. The list reloads on every
// notes_changed frame (a bot or another window changed a note). The project is asked for
// only when there is one, so the Board's own call stays listNotes(query).
export default function NotesBoard({ projectId }: NotesBoardProps) {
  const live = useLiveState();
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [notes, setNotes] = useState<NoteSummaryOut[] | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fail = useCallback((err: unknown) => setError(describeError(err)), []);

  const load = useCallback(() => {
    const request = projectId ? notesApi.listNotes(query, { projectId }) : notesApi.listNotes(query);
    request.then((found) => { setNotes(found); setError(null); }).catch(fail);
  }, [query, fail, projectId]);
  useEffect(() => load(), [load, live.boardVersion.notes]);

  const create = useCallback((title?: string) => {
    const input = { title: title ?? "Untitled note", content: title ? `# ${title}\n\n` : "" };
    notesApi.createNote(projectId ? { ...input, project_id: projectId } : input)
      .then((note) => setOpenId(note.id)).catch(fail);
  }, [fail, projectId]);
  const keep = (noteId: string) => { notesApi.keepNote(noteId).then(load).catch(fail); };
  const close = useCallback(() => { setOpenId(null); load(); }, [load]);
  // An emptied search box (typed away, or its clear button) lists every note again.
  const typeSearch = (text: string) => {
    setSearch(text);
    if (!text.trim()) setQuery("");
  };

  return (
    <section className="notes-board" aria-label="Notes">
      {openId ? null : (
        <NotesToolbar search={search} onSearch={typeSearch} onSubmit={() => setQuery(search.trim())} onNew={() => create()} />
      )}
      {error ? <ErrorNotice message={error} onRetry={load} /> : null}
      {openId
        ? <NoteEditor key={openId} noteId={openId} onClose={close} onOpenNote={setOpenId} onCreateNote={create} />
        : <NotesListArea notes={notes} query={query} onOpen={setOpenId} onKeep={keep} />}
    </section>
  );
}
```

**8c.** Replace the whole of `web/src/components/documents/DocumentsBoard.tsx` with:

```tsx
import { useCallback, useEffect, useRef, useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { DocumentOpen } from "./DocumentOpen";
import { DocumentRow } from "./DocumentRow";
import { useLiveState } from "../../hooks/useLiveStore";
import * as documentsApi from "../../api/documents";
import { describeError } from "../../api/client";
import type { DocumentDetailOut, DocumentOut } from "../../api/types";

type NewKind = "doc" | "sheet";
const NEW_TITLE: Record<NewKind, string> = { doc: "Untitled doc", sheet: "Untitled sheet" };

function DocumentsToolbar({ onNew, onUpload }: { onNew: (kind: NewKind) => void; onUpload: (file: File) => void }) {
  const fileRef = useRef<HTMLInputElement>(null);
  return (
    <div className="documents-toolbar">
      <button type="button" className="btn btn--primary" onClick={() => onNew("doc")}>New doc</button>
      <button type="button" className="btn btn--quiet" onClick={() => onNew("sheet")}>New sheet</button>
      <button type="button" className="btn btn--quiet" onClick={() => fileRef.current?.click()}>Upload PDF</button>
      <input ref={fileRef} type="file" accept="application/pdf" hidden aria-label="PDF file" onChange={(event) => {
        const file = event.target.files?.[0];
        event.target.value = "";
        if (file) onUpload(file);
      }} />
    </div>
  );
}

interface ListAreaProps {
  documents: DocumentOut[] | null;
  onOpen: (id: string) => void;
  onKeep: (id: string) => void;
  onDelete: (id: string) => void;
}

function DocumentsListArea({ documents, onOpen, onKeep, onDelete }: ListAreaProps) {
  if (documents === null) return <p className="board-loading">Loading&hellip;</p>;
  if (documents.length === 0) {
    return <p className="board-empty">No documents yet. Make one here, or ask a bot to “save … in a document”.</p>;
  }
  return (
    <ul className="doc-list" aria-label="Your documents">
      {documents.map((document) => (
        <DocumentRow key={document.id} document={document} onOpen={onOpen} onKeep={onKeep} onDelete={onDelete} />
      ))}
    </ul>
  );
}

// In a project, a new doc or sheet is made in it; an uploaded PDF is put in it right after the upload.
function useDocumentActions(load: () => void, open: (id: string) => void, fail: (err: unknown) => void,
  projectId: string | undefined) {
  const link = (meta: DocumentOut) => (projectId ? documentsApi.setDocumentProject(meta.id, projectId) : Promise.resolve(meta));
  return {
    create: (kind: NewKind) => {
      const input = { kind, title: NEW_TITLE[kind] };
      documentsApi.createDocument(projectId ? { ...input, project_id: projectId } : input)
        .then((meta) => open(meta.id)).catch(fail);
    },
    upload: (file: File) => {
      documentsApi.uploadPdf(file).then(link).then((meta) => { load(); open(meta.id); }).catch(fail);
    },
    keep: (id: string) => { documentsApi.keepDocument(id).then(load).catch(fail); },
    remove: (id: string) => { documentsApi.deleteDocument(id).then(load).catch(fail); },
  };
}

export interface DocumentsBoardProps {
  projectId?: string; // one project's documents (its page's Docs tab); a new one joins that project
}

// The user's documents, shared by every bot (D1), or one project's. The
// list reloads on every documents_changed frame.
export default function DocumentsBoard({ projectId }: DocumentsBoardProps) {
  const live = useLiveState();
  const [documents, setDocuments] = useState<DocumentOut[] | null>(null);
  const [open, setOpen] = useState<DocumentDetailOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fail = useCallback((err: unknown) => setError(describeError(err)), []);
  const load = useCallback(() => {
    const request = projectId ? documentsApi.listDocuments(undefined, { projectId }) : documentsApi.listDocuments();
    request.then((found) => { setDocuments(found); setError(null); }).catch(fail);
  }, [fail, projectId]);
  useEffect(() => load(), [load, live.boardVersion.documents]);
  const openDocument = useCallback((id: string) => { documentsApi.getDocument(id).then(setOpen).catch(fail); }, [fail]);
  const actions = useDocumentActions(load, openDocument, fail, projectId);

  if (open) return <DocumentOpen key={open.id} document={open} onBack={() => { setOpen(null); load(); }} />;
  return (
    <section className="documents-board" aria-label="Documents">
      <DocumentsToolbar onNew={actions.create} onUpload={actions.upload} />
      {error ? <ErrorNotice message={error} onRetry={load} /> : null}
      <DocumentsListArea documents={documents} onOpen={openDocument} onKeep={actions.keep} onDelete={actions.remove} />
    </section>
  );
}
```

- [ ] **Step 9: Implement the projects components**

**9a.** Create `web/src/components/projects/projects.ts`:

```ts
// The gateway's project limits and palette (roost/constants.py PROJECT_COLORS,
// DEFAULT_PROJECT_COLOR, MAX_CATEGORY_NAME_LENGTH, TOPUP_SOURCE_MAX_CHARS,
// CURRENCY_PATTERN): the inputs stop there, and the gateway checks again.
// Like board/money.ts, nothing here adds amounts: the server sends every number.
import { formatMoney } from "../board/money";
import type { ProjectProgressOut, TopupOut } from "../../api/types";

// The nine colours of H16, in the server's order (the first is the default), with the names a screen reader says.
export const PROJECT_COLORS: ReadonlyArray<readonly [string, string]> = [
  ["#64748b", "Slate"], ["#ef4444", "Red"], ["#f97316", "Orange"], ["#eab308", "Yellow"], ["#22c55e", "Green"],
  ["#14b8a6", "Teal"], ["#3b82f6", "Blue"], ["#8b5cf6", "Violet"], ["#ec4899", "Pink"],
];
export const DEFAULT_PROJECT_COLOR = PROJECT_COLORS[0][0];
export const DEFAULT_CURRENCY = "EUR";
export const MAX_PROJECT_NAME = 40;
export const MAX_TOPUP_SOURCE = 120;
export const CURRENCY_LENGTH = 3;
export const FULL_PERCENT = 100;
export const CURRENCY_HELP = "A currency is three letters, like EUR.";

const CURRENCY_CODE = /^[A-Z]{3}$/;
const MADRID = "Europe/Madrid";
const MOMENT_DAY = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: MADRID });

/** "eur " → "EUR"; anything that is not three letters → null. */
export function readCurrency(text: string): string | null {
  const code = text.trim().toUpperCase();
  return CURRENCY_CODE.test(code) ? code : null;
}

/** A history row's name (H4): a top-up, a change to one, or the budget set by hand. */
export function topupLabel(topup: TopupOut): string {
  if (topup.kind === "credit") return "Top-up";
  return topup.topup_id ? "Top-up changed" : "Budget set";
}

/** A change to a budget with its sign, as the server wrote it: "+€20.00", "-€20.00". */
export function signedMoney(amount: string, currency: string): string {
  return amount.startsWith("-") ? formatMoney(amount, currency) : `+${formatMoney(amount, currency)}`;
}

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

/** "3 of 5 done" (the server leaves cancelled tasks out of the total), or "No tasks yet". */
export function progressText(progress: ProjectProgressOut): string {
  return progress.total === 0 ? "No tasks yet" : `${progress.done} of ${progress.total} done`;
}
```

**9b.** Create `web/src/components/projects/BudgetBar.tsx`:

```tsx
import { formatMoney } from "../board/money";
import { FULL_PERCENT } from "./projects";
import type { BudgetLineOut } from "../../api/types";

export interface BudgetBarProps {
  label: string; // "Total budget" or "This month": the meter's name
  line: BudgetLineOut;
  currency: string; // the project's own
}

// "€180.00 left of €300.00", "Over by €45.00", or with no limit "€12.50 spent, no limit".
// The server sends every number (H8); this only formats them.
export function budgetText(line: BudgetLineOut, currency: string): string {
  const money = (amount: string) => formatMoney(amount, currency);
  if (line.budget === null || line.remaining === null) return `${money(line.spent)} spent, no limit`;
  return line.remaining.startsWith("-")
    ? `Over by ${money(line.remaining.slice(1))}`
    : `${money(line.remaining)} left of ${money(line.budget)}`;
}

// One budget as a bar (H8, H14): green below 80 %, amber from 80 %, red from 100 %, the tone
// being the server's. Over 100 % the bar is full; the text says by how much.
export function BudgetBar({ label, line, currency }: BudgetBarProps) {
  const text = budgetText(line, currency);
  if (line.budget === null || line.used_percent === null) {
    return (
      <p className="budget-bar budget-bar--none">
        <span className="budget-bar__label">{label}</span>
        <span className="budget-bar__text">{text}</span>
      </p>
    );
  }
  const filled = Math.min(Math.max(line.used_percent, 0), FULL_PERCENT);
  const tone = line.tone ?? "ok";
  return (
    <div className="budget-bar">
      <div className="budget-bar__head">
        <span className="budget-bar__label">{label}</span>
        <span className={`budget-bar__text${tone === "over" ? " budget-bar__text--over" : ""}`}>{text}</span>
      </div>
      <div className="budget-bar__track" role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={FULL_PERCENT}
        aria-valuenow={filled} aria-valuetext={text}>
        <div className={`budget-bar__fill budget-bar__fill--${tone}`} style={{ width: `${filled}%` }} />
      </div>
    </div>
  );
}
```

**9c.** Create `web/src/components/projects/ProjectRow.tsx`:

```tsx
import { Link } from "react-router-dom";
import { BudgetBar } from "./BudgetBar";
import { progressText } from "./projects";
import { formatMoney } from "../board/money";
import type { ProjectOut, ProjectProgressOut } from "../../api/types";

// "3 of 5 done", with the failed ones apart, in red (design §2: failed counts as finished).
export function ProgressLine({ progress }: { progress: ProjectProgressOut }) {
  return (
    <p className="project-progress">
      <span>{progressText(progress)}</span>
      {progress.failed > 0 ? <span className="project-progress__failed">{progress.failed} failed</span> : null}
    </p>
  );
}

// One project on the Projects tab: its name (a link to its page), its tasks, and a bar for each budget it has.
export function ProjectRow({ project }: { project: ProjectOut }) {
  const { total, month, currency } = project;
  return (
    <li className="project-row">
      <span className="project-dot" style={{ background: project.color }} aria-hidden="true" />
      <div className="project-row__main">
        <div className="project-row__head">
          <Link to={`/board/projects/${encodeURIComponent(project.id)}`} className="project-row__name">{project.name}</Link>
          {project.status === "archived" ? <span className="board-chip">archived</span> : null}
          {project.tainted ? <span className="board-chip board-chip--web">from web content</span> : null}
        </div>
        <ProgressLine progress={project.progress} />
        {total.budget !== null ? <BudgetBar label="Total budget" line={total} currency={currency} /> : null}
        {month.budget !== null ? <BudgetBar label="This month" line={month} currency={currency} /> : null}
        {total.budget === null && month.budget === null
          ? <p className="project-row__spent">{formatMoney(total.spent, currency)} spent</p> : null}
      </div>
    </li>
  );
}
```

**9d.** Create `web/src/components/projects/ProjectEditForm.tsx`:

```tsx
import { useId, useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
import {
  CURRENCY_HELP, CURRENCY_LENGTH, DEFAULT_CURRENCY, DEFAULT_PROJECT_COLOR, MAX_PROJECT_NAME, PROJECT_COLORS, readCurrency,
} from "./projects";
import { AMOUNT_HELP, MAX_AMOUNT_TEXT, readAmount } from "../board/money";
import { useLiveState } from "../../hooks/useLiveStore";
import * as projectsApi from "../../api/projects";
import { describeError } from "../../api/client";
import type { ProjectOut } from "../../api/types";

interface Fields {
  name: string;
  currency: string;
  budget: string; // the total budget, top-ups included; "" is none (or, on a saved project, clears it, H5)
  monthly: string;
  color: string;
  start: string;
  due: string;
  lead: string; // "" for no lead bot
}
type Setter = (key: keyof Fields, value: string) => void;

interface Read {
  currency: string;
  budget: string | null;
  monthly: string | null;
}

function fieldsOf(project: ProjectOut | undefined): Fields {
  return {
    name: project?.name ?? "", currency: project?.currency ?? DEFAULT_CURRENCY, budget: project?.total.budget ?? "",
    monthly: project?.month.budget ?? "", color: project?.color ?? DEFAULT_PROJECT_COLOR,
    start: project?.start_date ?? "", due: project?.due_date ?? "", lead: project?.lead_bot_id ?? "",
  };
}

// The fields as the gateway takes them, or the sentence that says what to fix. A total budget left as
// shown keeps the server's string unread: it can be "0.00" once every top-up is undone, which readAmount refuses.
function readFields(fields: Fields, shownBudget: string | null): Read | string {
  const currency = readCurrency(fields.currency);
  if (currency === null) return CURRENCY_HELP;
  const budget = fields.budget === (shownBudget ?? "") ? shownBudget : readAmount(fields.budget);
  const monthly = readAmount(fields.monthly);
  if (budget === undefined || monthly === undefined) return AMOUNT_HELP;
  return { currency, budget, monthly };
}

function draftFor(fields: Fields, read: Read): projectsApi.ProjectIn {
  return {
    name: fields.name.trim(), currency: read.currency, budget: read.budget, monthly_budget: read.monthly,
    color: fields.color, start_date: fields.start || null, due_date: fields.due || null, lead_bot_id: fields.lead || null,
  };
}

// Only what changed is sent. The total budget is not part of it: PATCH never takes it.
function patchFor(project: ProjectOut, fields: Fields, read: Read): projectsApi.ProjectPatchIn {
  const next: projectsApi.ProjectPatchIn = {
    name: fields.name.trim(), color: fields.color, start_date: fields.start || null, due_date: fields.due || null,
    monthly_budget: read.monthly, lead_bot_id: fields.lead || null, currency: read.currency,
  };
  const before: projectsApi.ProjectPatchIn = {
    name: project.name, color: project.color, start_date: project.start_date, due_date: project.due_date,
    monthly_budget: project.month.budget, lead_bot_id: project.lead_bot_id, currency: project.currency,
  };
  const changed = Object.entries(next).filter(([key, value]) => before[key as keyof projectsApi.ProjectPatchIn] !== value);
  return Object.fromEntries(changed) as projectsApi.ProjectPatchIn;
}

// Save on a saved project: what changed goes through updateProject, then the total budget through
// setProjectBudget, only when it changed ("1000" typed over the server's "1000.00" is no change).
function editRequest(project: ProjectOut, fields: Fields, read: Read): () => Promise<unknown> {
  const patch = patchFor(project, fields, read);
  const budgetChanged = read.budget !== project.total.budget;
  return async () => {
    if (Object.keys(patch).length > 0) await projectsApi.updateProject(project.id, patch);
    if (budgetChanged) await projectsApi.setProjectBudget(project.id, read.budget);
  };
}

// What Save sends, or the sentence that says why it can't yet.
function requestFor(project: ProjectOut | undefined, fields: Fields): (() => Promise<unknown>) | string {
  const read = readFields(fields, project?.total.budget ?? null);
  if (typeof read === "string") return read;
  return project ? editRequest(project, fields, read) : () => projectsApi.createProject(draftFor(fields, read));
}

function NameFields({ fields, set }: { fields: Fields; set: Setter }) {
  return (
    <>
      <label className="field project-edit__name"><span className="field__label">Name</span>
        <input className="input" value={fields.name} maxLength={MAX_PROJECT_NAME} onChange={(e) => set("name", e.target.value)} />
      </label>
      <label className="field"><span className="field__label">Currency</span>
        <input className="input" value={fields.currency} maxLength={CURRENCY_LENGTH} autoCapitalize="characters"
          onChange={(e) => set("currency", e.target.value)} />
      </label>
      <label className="field"><span className="field__label">Total budget</span>
        <input className="input" inputMode="decimal" placeholder="none" value={fields.budget} maxLength={MAX_AMOUNT_TEXT}
          onChange={(e) => set("budget", e.target.value)} />
      </label>
      <label className="field"><span className="field__label">Monthly limit</span>
        <input className="input" inputMode="decimal" placeholder="none" value={fields.monthly} maxLength={MAX_AMOUNT_TEXT}
          onChange={(e) => set("monthly", e.target.value)} />
      </label>
    </>
  );
}

function ColorPicker({ value, onChange }: { value: string; onChange: (color: string) => void }) {
  const group = useId();
  return (
    <fieldset className="field project-edit__colors">
      <legend className="field__label">Color</legend>
      <div className="project-swatches">
        {PROJECT_COLORS.map(([color, label]) => (
          <label key={color} className="project-swatch" style={{ background: color }} title={label}>
            <input type="radio" name={`${group}-color`} className="sr-only" aria-label={label}
              checked={value === color} onChange={() => onChange(color)} />
          </label>
        ))}
      </div>
    </fieldset>
  );
}

// The dates and the lead bot (H15: one of the user's own bots, which the gateway checks).
function WhenFields({ fields, set }: { fields: Fields; set: Setter }) {
  const live = useLiveState();
  const bots = [...Object.values(live.bots)].sort((a, b) => a.name.localeCompare(b.name));
  return (
    <>
      <label className="field"><span className="field__label">Starts</span>
        <input className="input" type="date" value={fields.start} onChange={(e) => set("start", e.target.value)} />
      </label>
      <label className="field"><span className="field__label">Due</span>
        <input className="input" type="date" value={fields.due} onChange={(e) => set("due", e.target.value)} />
      </label>
      <label className="field project-edit__lead"><span className="field__label">Lead bot</span>
        <select className="input" value={fields.lead} onChange={(e) => set("lead", e.target.value)}>
          <option value="">No lead bot</option>
          {bots.map((bot) => <option key={bot.id} value={bot.id}>{bot.name}</option>)}
        </select>
      </label>
    </>
  );
}

export interface ProjectEditFormProps {
  project?: ProjectOut; // none: a new project
  onDone: () => void; // saved, or cancelled
}

// Make a project, or change one (P6): its name, currency, budgets, color, dates and lead bot.
export function ProjectEditForm({ project, onDone }: ProjectEditFormProps) {
  const [fields, setFields] = useState<Fields>(() => fieldsOf(project));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set: Setter = (key, value) => setFields((current) => ({ ...current, [key]: value }));

  const save = async () => {
    const request = requestFor(project, fields);
    if (typeof request === "string") {
      setError(request);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await request();
      onDone();
    } catch (err) {
      setError(describeError(err));
      setBusy(false);
    }
  };

  return (
    <form className="project-edit" aria-label={project ? `Edit ${project.name}` : "New project"}
      onSubmit={(event) => { event.preventDefault(); void save(); }}>
      <NameFields fields={fields} set={set} />
      <ColorPicker value={fields.color} onChange={(color) => set("color", color)} />
      <WhenFields fields={fields} set={set} />
      {error ? <ErrorNotice message={error} /> : null}
      <div className="project-edit__actions">
        <button type="submit" className="btn btn--primary btn--small" disabled={busy || !fields.name.trim()}>
          {project ? "Save" : "Create project"}
        </button>
        <button type="button" className="btn btn--quiet btn--small" onClick={onDone}>Cancel</button>
      </div>
    </form>
  );
}
```

**9e.** Create `web/src/components/projects/ProjectsBoard.tsx`:

```tsx
import { useCallback, useEffect, useRef, useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { ProjectEditForm } from "./ProjectEditForm";
import { ProjectRow } from "./ProjectRow";
import { useLiveState } from "../../hooks/useLiveStore";
import * as projectsApi from "../../api/projects";
import { describeError } from "../../api/client";
import type { ProjectOut } from "../../api/types";

function ProjectList({ projects }: { projects: ProjectOut[] }) {
  if (projects.length === 0) {
    return <p className="board-empty">No projects yet. Make one here, or ask any bot to start one.</p>;
  }
  return (
    <ul className="project-list" aria-label="Your projects">
      {projects.map((project) => <ProjectRow key={project.id} project={project} />)}
    </ul>
  );
}

// Only the newest request may paint (a fast "Show archived" toggle).
function useProjectList(archived: boolean) {
  const live = useLiveState();
  const [projects, setProjects] = useState<ProjectOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef(0);
  const load = useCallback(() => {
    const ticket = ++latest.current;
    projectsApi.listProjects(archived)
      .then((found) => { if (ticket === latest.current) { setProjects(found); setError(null); } })
      .catch((err: unknown) => { if (ticket === latest.current) setError(describeError(err)); });
  }, [archived]);
  useEffect(() => load(), [load, live.boardVersion.money, live.boardVersion.tasks]);
  return { projects, error, load };
}

// The Board's first tab (P7, H14): every project but General, shared by every bot. It reloads on
// money_changed (project, budget and top-up changes ride on it, H10) and on tasks_changed (progress).
export function ProjectsBoard() {
  const [archived, setArchived] = useState(false);
  const [creating, setCreating] = useState(false);
  const { projects, error, load } = useProjectList(archived);
  const doneCreating = () => { setCreating(false); load(); };

  return (
    <section className="projects-board" aria-label="Projects">
      <div className="projects-toolbar">
        {creating ? null : (
          <button type="button" className="btn btn--primary" onClick={() => setCreating(true)}>New project</button>
        )}
        <label className="projects-toolbar__archived">
          <input type="checkbox" checked={archived} onChange={(event) => setArchived(event.target.checked)} />
          Show archived
        </label>
      </div>
      {creating ? <ProjectEditForm onDone={doneCreating} /> : null}
      {error ? <ErrorNotice message={error} onRetry={load} /> : null}
      {projects === null && !error ? <p className="board-loading">Loading&hellip;</p> : null}
      {projects !== null ? <ProjectList projects={projects} /> : null}
    </section>
  );
}
```

**9f.** Create `web/src/components/projects/TopupForm.tsx`:

```tsx
import { useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { AMOUNT_HELP, MAX_AMOUNT_TEXT, parseAmountInput } from "../board/money";
import { MAX_TOPUP_SOURCE } from "./projects";
import * as projectsApi from "../../api/projects";
import { describeError } from "../../api/client";

export interface TopupFormProps {
  projectId: string;
  onAdded: () => void;
}

// A top-up raises the project's total budget (H4); where it came from is optional.
export function TopupForm({ projectId, onAdded }: TopupFormProps) {
  const [amount, setAmount] = useState("");
  const [source, setSource] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    const parsed = parseAmountInput(amount);
    if (parsed === null) {
      setError(AMOUNT_HELP);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await projectsApi.addTopup(projectId, source.trim() ? { amount: parsed, source: source.trim() } : { amount: parsed });
      setAmount("");
      setSource("");
      onAdded();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="topup-add" onSubmit={(event) => { event.preventDefault(); void submit(); }}>
      <input className="input" aria-label="Top-up amount" inputMode="decimal" placeholder="50,00" value={amount}
        maxLength={MAX_AMOUNT_TEXT} onChange={(e) => setAmount(e.target.value)} />
      <input className="input" aria-label="Where from" placeholder="Where from? e.g. a gift" value={source}
        maxLength={MAX_TOPUP_SOURCE} onChange={(e) => setSource(e.target.value)} />
      <button type="submit" className="btn btn--primary" disabled={busy}>Add top-up</button>
      {error ? <ErrorNotice message={error} /> : null}
    </form>
  );
}
```

**9g.** Create `web/src/components/projects/TopupHistory.tsx`:

```tsx
import { useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { AMOUNT_HELP, MAX_AMOUNT_TEXT, formatMoney, parseAmountInput } from "../board/money";
import { momentDay, signedMoney, topupLabel } from "./projects";
import * as projectsApi from "../../api/projects";
import { describeError } from "../../api/client";
import type { TopupOut } from "../../api/types";

export interface TopupHistoryProps {
  topups: readonly TopupOut[]; // newest first, undone ones included (H4)
  onChanged: () => void;
}

// A credit shows its amount; an edit shows the change it made, with its sign.
function shownAmount(topup: TopupOut): string {
  return topup.kind === "credit" ? formatMoney(topup.amount, topup.currency) : signedMoney(topup.amount, topup.currency);
}

interface TopupRowProps {
  topup: TopupOut;
  onChange: () => void;
  onUndo: () => void;
}

function TopupRow({ topup, onChange, onUndo }: TopupRowProps) {
  const amount = shownAmount(topup);
  const live = topup.kind === "credit" && !topup.undone;
  return (
    <li className={`topup-row${topup.undone ? " topup-row--undone" : ""}`}>
      <span className="topup-row__day">{momentDay(topup.created_at)}</span>
      <span className="topup-row__what">
        <span className="topup-row__label">{topupLabel(topup)}</span>
        {topup.source ? <span className="topup-row__source">{topup.source}</span> : null}
        {topup.undone ? <span className="board-chip">undone</span> : null}
      </span>
      <span className="topup-row__amount">{amount}</span>
      {live ? (
        <span className="topup-row__actions">
          <button type="button" className="btn btn--quiet btn--small" aria-label={`Change the top-up of ${amount}`}
            onClick={onChange}>Change</button>
          <button type="button" className="btn btn--quiet btn--small" aria-label={`Undo the top-up of ${amount}`}
            onClick={onUndo}>Undo</button>
        </span>
      ) : null}
    </li>
  );
}

interface ChangeFormProps {
  topup: TopupOut;
  onDone: () => void;
  onCancel: () => void;
}

// The top-up's new amount; the server writes the difference as a "Top-up changed" row (H4).
function TopupChangeForm({ topup, onDone, onCancel }: ChangeFormProps) {
  const [amount, setAmount] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const save = async () => {
    const parsed = parseAmountInput(amount);
    if (parsed === null) {
      setError(AMOUNT_HELP);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await projectsApi.editTopup(topup.id, parsed);
      onDone();
    } catch (err) {
      setError(describeError(err));
      setBusy(false);
    }
  };
  return (
    <li className="topup-row topup-row--editing">
      <form className="topup-change" aria-label={`Change the top-up of ${shownAmount(topup)}`}
        onSubmit={(event) => { event.preventDefault(); void save(); }}>
        <input className="input" aria-label="New amount" inputMode="decimal" placeholder="New amount" value={amount}
          maxLength={MAX_AMOUNT_TEXT} onChange={(e) => setAmount(e.target.value)} />
        <button type="submit" className="btn btn--primary btn--small" disabled={busy}>Save</button>
        <button type="button" className="btn btn--quiet btn--small" onClick={onCancel}>Cancel</button>
        {error ? <ErrorNotice message={error} /> : null}
      </form>
    </li>
  );
}

export function TopupHistory({ topups, onChanged }: TopupHistoryProps) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const undo = (topupId: string) => {
    setError(null);
    projectsApi.undoTopup(topupId).then(onChanged).catch((err: unknown) => setError(describeError(err)));
  };
  const doneEditing = () => { setEditingId(null); onChanged(); };
  if (topups.length === 0) return <p className="board-empty">No top-ups yet.</p>;
  return (
    <>
      {error ? <ErrorNotice message={error} /> : null}
      <ul className="topup-list" aria-label="Top-up history">
        {topups.map((topup) => (topup.id === editingId
          ? <TopupChangeForm key={topup.id} topup={topup} onDone={doneEditing} onCancel={() => setEditingId(null)} />
          : <TopupRow key={topup.id} topup={topup} onChange={() => setEditingId(topup.id)} onUndo={() => undo(topup.id)} />))}
      </ul>
    </>
  );
}
```

**9h.** Create `web/src/components/projects/ProjectSummary.tsx`:

```tsx
import { BudgetBar } from "./BudgetBar";
import { ProgressLine } from "./ProjectRow";
import { dateLabel } from "./projects";
import { formatMoney } from "../board/money";
import type { ProjectDetailOut } from "../../api/types";

function factsOf(project: ProjectDetailOut): string[] {
  const facts = [
    project.lead_bot_name ? `Led by ${project.lead_bot_name}` : "",
    project.start_date ? `Starts ${dateLabel(project.start_date)}` : "",
    project.due_date ? `Due ${dateLabel(project.due_date)}` : "",
  ];
  return facts.filter((fact) => fact !== "");
}

// The top of a project's page (design §3): the lead bot, the dates, progress, both budgets,
// the starred total and any other currencies, all as the server sent them.
export function ProjectSummary({ project }: { project: ProjectDetailOut }) {
  const facts = factsOf(project);
  return (
    <section className="project-summary" aria-label="Summary">
      {facts.length > 0 ? <p className="project-summary__facts">{facts.join(" · ")}</p> : null}
      <ProgressLine progress={project.progress} />
      <BudgetBar label="Total budget" line={project.total} currency={project.currency} />
      <BudgetBar label="This month" line={project.month} currency={project.currency} />
      {Number(project.starred_total) > 0 ? (
        <p className="project-summary__starred">Starred {formatMoney(project.starred_total, project.currency)}</p>
      ) : null}
      {Object.entries(project.other_currencies).map(([code, total]) => (
        <p key={code} className="project-summary__other">Also {formatMoney(total, code)} (not in the budgets)</p>
      ))}
    </section>
  );
}
```

**9i.** Create `web/src/components/projects/ProjectActions.tsx`:

```tsx
import { useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
import * as projectsApi from "../../api/projects";
import { describeError } from "../../api/client";
import type { ProjectOut } from "../../api/types";

// H9: deleting keeps everything the project held; the copy says where it goes.
const DELETE_NOTE = "Its expenses move to General; its tasks, notes and documents stay, just unlinked.";

export interface ProjectActionsProps {
  project: ProjectOut;
  onEdit: () => void;
  onChanged: () => void;
  onDeleted: () => void;
}

// Edit, Archive / Unarchive, and Delete with DocumentRow's two-step confirmation (H14).
export function ProjectActions({ project, onEdit, onChanged, onDeleted }: ProjectActionsProps) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const archived = project.status === "archived";
  const act = (request: () => Promise<unknown>, then: () => void) => {
    setBusy(true);
    setError(null);
    request().then(then).catch((err: unknown) => setError(describeError(err))).finally(() => setBusy(false));
  };
  const toggleArchive = () => act(
    () => projectsApi.updateProject(project.id, { status: archived ? "active" : "archived" }), onChanged,
  );

  return (
    <div className="project-actions">
      <button type="button" className="btn btn--quiet btn--small" onClick={onEdit}>Edit</button>
      <button type="button" className="btn btn--quiet btn--small" disabled={busy} onClick={toggleArchive}>
        {archived ? "Unarchive" : "Archive"}
      </button>
      {confirming ? (
        <div className="project-actions__confirm" role="group" aria-label={`Delete ${project.name}?`}>
          <p>{DELETE_NOTE}</p>
          <button type="button" className="btn btn--danger btn--small" aria-label={`Delete ${project.name} for good`}
            disabled={busy} onClick={() => act(() => projectsApi.deleteProject(project.id), onDeleted)}>Delete</button>
          <button type="button" className="btn btn--quiet btn--small" onClick={() => setConfirming(false)}>Cancel</button>
        </div>
      ) : (
        <button type="button" className="btn btn--quiet btn--small" aria-label={`Delete ${project.name}`}
          onClick={() => setConfirming(true)}>Delete</button>
      )}
      {error ? <ErrorNotice message={error} /> : null}
    </div>
  );
}
```

**9j.** Create `web/src/components/projects/ProjectMoney.tsx`:

```tsx
import { MoneyBoard } from "../board/MoneyBoard";
import { TopupForm } from "./TopupForm";
import { TopupHistory } from "./TopupHistory";
import type { ProjectDetailOut } from "../../api/types";

export interface ProjectMoneyProps {
  project: ProjectDetailOut;
  onChanged: () => void; // a top-up changed the budget: the page reloads its numbers
}

// A project's Money tab: its top-ups (which move the total budget), then its expenses month by month.
export function ProjectMoney({ project, onChanged }: ProjectMoneyProps) {
  return (
    <div className="project-money">
      <section className="project-money__topups" aria-label="Top-ups">
        <h2 className="project-money__title">Top-ups</h2>
        <TopupForm projectId={project.id} onAdded={onChanged} />
        <TopupHistory topups={project.topups} onChanged={onChanged} />
      </section>
      <MoneyBoard project={{ id: project.id, name: project.name, currency: project.currency }} />
    </div>
  );
}
```

- [ ] **Step 10: Implement the project page, the Board's first tab and the routes**

**10a.** Create `web/src/pages/Project.tsx`:

```tsx
import { lazy, useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Link, Navigate, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ErrorNotice } from "../components/ErrorNotice";
import { BackIcon } from "../components/icons";
import { lazyPanel } from "../components/board/lazyPanel";
import { TasksBoard } from "../components/board/TasksBoard";
import { ProjectActions } from "../components/projects/ProjectActions";
import { ProjectEditForm } from "../components/projects/ProjectEditForm";
import { ProjectMoney } from "../components/projects/ProjectMoney";
import { ProjectSummary } from "../components/projects/ProjectSummary";
import { useLiveState } from "../hooks/useLiveStore";
import * as projectsApi from "../api/projects";
import { ApiError, describeError } from "../api/client";
import type { ProjectDetailOut } from "../api/types";

export type ProjectTab = "tasks" | "money" | "notes" | "docs";
export const TABS: ReadonlyArray<{ id: ProjectTab; label: string }> = [
  { id: "tasks", label: "Tasks" }, { id: "money", label: "Money" }, { id: "notes", label: "Notes" }, { id: "docs", label: "Docs" },
];
const PROJECTS_TAB = "/board?tab=projects";

// Notes and Docs stay their own chunks here too (M2 D4).
const NotesPanel = lazyPanel(lazy(() => import("../components/notes/NotesBoard")));
const DocumentsPanel = lazyPanel(lazy(() => import("../components/documents/DocumentsBoard")));

interface PanelArgs {
  project: ProjectDetailOut;
  reload: () => void;
}
const PANELS: Record<ProjectTab, (args: PanelArgs) => ReactNode> = {
  tasks: ({ project }) => <TasksBoard projectId={project.id} currency={project.currency} money={project.task_money} />,
  money: ({ project, reload }) => <ProjectMoney project={project} onChanged={reload} />,
  notes: ({ project }) => <NotesPanel projectId={project.id} />,
  docs: ({ project }) => <DocumentsPanel projectId={project.id} />,
};

// /board/projects opens the Board on its Projects tab: the list has one address.
export function ToProjectsTab() {
  return <Navigate to={PROJECTS_TAB} replace />;
}

// The project and its numbers. It reloads when its tasks, money, notes or documents change anywhere;
// once the project is gone (deleted in another tab) it shows why, with the way back.
function useProjectDetail(projectId: string | undefined) {
  const { tasks, money, notes, documents } = useLiveState().boardVersion;
  const [project, setProject] = useState<ProjectDetailOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef(0);
  const load = useCallback(() => {
    if (!projectId) return;
    const ticket = ++latest.current;
    projectsApi.getProject(projectId)
      .then((found) => { if (ticket === latest.current) { setProject(found); setError(null); } })
      .catch((err: unknown) => {
        if (ticket !== latest.current) return;
        if (err instanceof ApiError && err.status === 404) setProject(null);
        setError(describeError(err));
      });
  }, [projectId]);
  useEffect(() => load(), [load, tasks, money, notes, documents]);
  return { project, error, load };
}

function ProjectHead({ project }: { project: ProjectDetailOut | null }) {
  return (
    <header className="board-page__head">
      <Link to={PROJECTS_TAB} className="icon-btn" aria-label="Back to projects"><BackIcon /></Link>
      {project ? (
        <>
          <span className="project-dot" style={{ background: project.color }} aria-hidden="true" />
          <h1 className="board-page__title">{project.name}</h1>
          {project.status === "archived" ? <span className="board-chip">archived</span> : null}
          {project.tainted ? <span className="board-chip board-chip--web">from web content</span> : null}
        </>
      ) : null}
    </header>
  );
}

function ProjectTabs({ current, onPick }: { current: ProjectTab; onPick: (tab: ProjectTab) => void }) {
  return (
    <div className="board-tabs" role="tablist" aria-label="In this project">
      {TABS.map((tab) => (
        <button key={tab.id} id={`project-tab-${tab.id}`} type="button" role="tab" aria-selected={tab.id === current}
          aria-controls="project-panel" className={`board-tab${tab.id === current ? " board-tab--active" : ""}`}
          onClick={() => onPick(tab.id)}>
          {tab.label}
        </button>
      ))}
    </div>
  );
}

interface BodyProps {
  project: ProjectDetailOut;
  reload: () => void;
  onDeleted: () => void;
}

function ProjectBody({ project, reload, onDeleted }: BodyProps) {
  const [params, setParams] = useSearchParams();
  const [editing, setEditing] = useState(false);
  const current = TABS.find((tab) => tab.id === params.get("tab"))?.id ?? TABS[0].id;
  const doneEditing = () => { setEditing(false); reload(); };
  return (
    <>
      {editing ? <ProjectEditForm project={project} onDone={doneEditing} /> : <ProjectSummary project={project} />}
      {editing ? null : (
        <ProjectActions project={project} onEdit={() => setEditing(true)} onChanged={reload} onDeleted={onDeleted} />
      )}
      <ProjectTabs current={current} onPick={(tab) => setParams({ tab }, { replace: true })} />
      <div id="project-panel" role="tabpanel" aria-labelledby={`project-tab-${current}`} className="board-panel">
        {PANELS[current]({ project, reload })}
      </div>
    </>
  );
}

// A project's page (H14): what it holds, its budgets and its top-ups, with Tasks · Money · Notes · Docs.
export function Project() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const { project, error, load } = useProjectDetail(projectId);
  const shown = project && project.id === projectId ? project : null;
  return (
    <div className="board-page">
      <ProjectHead project={shown} />
      <div className="board-page__body">
        {error ? <ErrorNotice message={error} onRetry={load} /> : null}
        {!shown && !error ? <p className="board-loading">Loading&hellip;</p> : null}
        {shown ? <ProjectBody project={shown} reload={load} onDeleted={() => navigate(PROJECTS_TAB, { replace: true })} /> : null}
      </div>
    </div>
  );
}
```

**10b.** Replace the whole of `web/src/pages/Board.tsx` with:

```tsx
import { lazy, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { BackIcon } from "../components/icons";
import { lazyPanel } from "../components/board/lazyPanel";
import { MoneyBoard } from "../components/board/MoneyBoard";
import { TasksBoard } from "../components/board/TasksBoard";
import { ProjectsBoard } from "../components/projects/ProjectsBoard";
import type { BoardTab } from "../api/types";

// Heavier panels are their own chunks (M2 D4): the main bundle stays small.
const NotesPanel = lazyPanel(lazy(() => import("../components/notes/NotesBoard")));
const DocumentsPanel = lazyPanel(lazy(() => import("../components/documents/DocumentsBoard")));

// Projects is first, and so where the Board opens (H14).
const TABS: ReadonlyArray<{ id: BoardTab; label: string }> = [
  { id: "projects", label: "Projects" }, { id: "tasks", label: "Tasks" }, { id: "money", label: "Money" },
  { id: "notes", label: "Notes" }, { id: "documents", label: "Documents" },
];
const PANELS: Record<BoardTab, () => ReactNode> = {
  projects: () => <ProjectsBoard />, tasks: () => <TasksBoard />, money: () => <MoneyBoard />,
  notes: () => <NotesPanel />, documents: () => <DocumentsPanel />,
};

// The user's records, one Board for every bot (D1), opened from Home.
export function Board() {
  const [params, setParams] = useSearchParams();
  const current = TABS.find((tab) => tab.id === params.get("tab")) ?? TABS[0];
  return (
    <div className="board-page">
      <header className="board-page__head">
        <Link to="/" className="icon-btn" aria-label="Back to chats"><BackIcon /></Link>
        <h1 className="board-page__title">Board</h1>
      </header>
      <div className="board-page__body">
        <p className="board-page__lede">Your projects, tasks, money, notes and documents. Every bot uses the same ones.</p>
        <div className="board-tabs" role="tablist" aria-label="Board">
          {TABS.map((tab) => (
            <button key={tab.id} id={`board-tab-${tab.id}`} type="button" role="tab" aria-selected={tab.id === current.id}
              aria-controls="board-panel" className={`board-tab${tab.id === current.id ? " board-tab--active" : ""}`}
              onClick={() => setParams({ tab: tab.id }, { replace: true })}>
              {tab.label}
            </button>
          ))}
        </div>
        <div id="board-panel" className="board-panel" role="tabpanel" aria-labelledby={`board-tab-${current.id}`}>
          {PANELS[current.id]()}
        </div>
      </div>
    </div>
  );
}
```

**10c.** `web/src/App.tsx`. Find:

```tsx
import { Board } from "./pages/Board";
```

Replace with:

```tsx
import { Board } from "./pages/Board";
import { Project, ToProjectsTab } from "./pages/Project";
```

Find:

```tsx
        <Route path="/board" element={<Board />} />
```

Replace with:

```tsx
        <Route path="/board" element={<Board />} />
        <Route path="/board/projects" element={<ToProjectsTab />} />
        <Route path="/board/projects/:projectId" element={<Project />} />
```

- [ ] **Step 11: Add the styles**

**11a.** `web/src/styles.css`. Find:

```css
@import "./styles/board.css";
```

Replace with:

```css
@import "./styles/board.css";
@import "./styles/projects.css";
```

**11b.** Create `web/src/styles/projects.css`:

```css
/* ---------------------------------------------------------------------
   Projects (projects hub): the Board's first tab, a page per project,
   budget bars, top-ups, and the starred / void / failed marks. Loaded
   after board.css, so its modifiers win at equal specificity.
   --------------------------------------------------------------------- */

.projects-board,
.project-money,
.project-money__topups {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.project-money {
  gap: 24px;
}

.projects-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 16px;
  align-items: center;
}

.projects-toolbar__archived {
  display: inline-flex;
  gap: 8px;
  align-items: center;
  color: var(--muted);
  font-size: var(--fs-sm);
  cursor: pointer;
}

.projects-toolbar__archived input {
  accent-color: var(--emerald);
}

.project-list,
.topup-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.project-row {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
  background: var(--surface);
}

.project-dot {
  flex: none;
  width: 12px;
  height: 12px;
  margin-top: 5px;
  border-radius: 50%;
  box-shadow: inset 0 0 0 1px var(--avatar-outline);
}

.board-page__head .project-dot {
  margin: 0 2px 0 4px;
}

.project-row__main {
  display: flex;
  flex: 1 1 0;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}

.project-row__head {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 8px;
  align-items: center;
}

.project-row__name {
  color: var(--text);
  font-weight: 600;
  text-decoration: none;
  overflow-wrap: anywhere;
}

.project-row__name:hover {
  color: var(--emerald-soft);
  text-decoration: underline;
}

.project-row__spent {
  margin: 0;
  color: var(--muted);
  font: var(--fs-xs) var(--font-mono);
}

.project-progress {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 10px;
  margin: 0;
  color: var(--muted);
  font-size: var(--fs-sm);
}

.project-progress__failed {
  color: var(--coral);
}

/* ---- Budget bars: the server's numbers and tone (H8), never a sum made here ---- */

.budget-bar {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 0;
}

.budget-bar__head,
.budget-bar--none {
  display: flex;
  flex-direction: row;
  flex-wrap: wrap;
  gap: 4px 12px;
  justify-content: space-between;
  font-size: var(--fs-sm);
}

.budget-bar__label {
  color: var(--muted);
}

.budget-bar__text {
  color: var(--text);
  font: var(--fs-xs) var(--font-mono);
  font-variant-numeric: tabular-nums;
}

.budget-bar__text--over {
  color: var(--coral);
}

.budget-bar__track {
  height: 8px;
  overflow: hidden;
  border-radius: var(--pill);
  background: var(--raised);
  box-shadow: inset 0 0 0 1px var(--line);
}

.budget-bar__fill {
  height: 100%;
  border-radius: inherit;
  background: var(--emerald);
  transition: width var(--slow) var(--ease);
}

.budget-bar__fill--warn {
  background: var(--amber);
}

.budget-bar__fill--over {
  background: var(--coral);
}

@media (prefers-reduced-motion: reduce) {
  .budget-bar__fill {
    transition: none;
  }
}

/* ---- The project page ------------------------------------------------- */

.project-summary {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.project-summary__facts {
  margin: 0;
  color: var(--muted);
  font-size: var(--fs-sm);
}

.project-summary__starred {
  margin: 0;
  color: var(--text);
  font: var(--fs-xs) var(--font-mono);
}

.project-summary__other {
  margin: 0;
  color: var(--amber);
  font: var(--fs-xs) var(--font-mono);
}

.project-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.project-actions__confirm {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  width: 100%;
  padding: 12px 14px;
  border: 1px solid var(--coral-edge);
  border-radius: var(--radius-md);
  background: var(--coral-tint);
}

.project-actions__confirm p {
  flex: 1 1 100%;
  margin: 0;
  color: var(--text);
  font-size: var(--fs-sm);
}

.project-edit {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.project-edit__name,
.project-edit__colors,
.project-edit__lead,
.project-edit .error-notice,
.project-edit__actions {
  grid-column: 1 / -1;
}

.project-edit__actions {
  display: flex;
  gap: 8px;
}

.project-swatches {
  display: grid;
  grid-template-columns: repeat(9, minmax(0, 32px));
  gap: 10px;
}

.project-swatch {
  position: relative;
  width: 100%;
  aspect-ratio: 1;
  border-radius: 50%;
  box-shadow: inset 0 0 0 1px var(--avatar-outline);
  cursor: pointer;
  transition: box-shadow var(--fast) var(--ease);
}

/* The radio is the swatch's only child: centre its hit box on the circle (see profile.css). */
.project-swatch input.sr-only {
  inset: 0;
  margin: auto;
}

.project-swatch:has(input:checked) {
  box-shadow:
    inset 0 0 0 1px var(--avatar-outline),
    0 0 0 3px var(--surface),
    0 0 0 5px var(--text);
}

.project-swatch:has(input:focus-visible) {
  outline: 2px solid var(--emerald);
  outline-offset: 3px;
}

/* ---- Top-ups ------------------------------------------------------------ */

.project-money__title {
  margin: 0;
  font: 600 var(--fs-md) / 1.2 var(--font-display);
}

.topup-add {
  display: grid;
  grid-template-columns: minmax(0, 0.8fr) minmax(0, 1.6fr) auto;
  gap: 8px;
  align-items: center;
}

.topup-add .btn {
  height: 44px;
}

.topup-add .error-notice,
.topup-change .error-notice {
  grid-column: 1 / -1;
}

.topup-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  align-items: center;
  padding: 10px 14px;
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
  background: var(--surface);
}

.topup-row__day {
  flex: none;
  min-width: 7em;
  color: var(--faint);
  font: var(--fs-xs) var(--font-mono);
}

.topup-row__what {
  display: flex;
  flex: 1 1 0;
  flex-wrap: wrap;
  gap: 4px 8px;
  align-items: baseline;
  min-width: 0;
}

.topup-row__label {
  color: var(--text);
  font-weight: 500;
}

.topup-row__source {
  color: var(--muted);
  font-size: var(--fs-sm);
  overflow-wrap: anywhere;
}

.topup-row__amount {
  flex: none;
  color: var(--text);
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.topup-row__actions {
  display: flex;
  gap: 6px;
}

.topup-row--undone .topup-row__label,
.topup-row--undone .topup-row__amount {
  color: var(--faint);
  text-decoration: line-through;
}

.topup-change {
  display: grid;
  flex: 1;
  grid-template-columns: minmax(0, 1fr) auto auto;
  gap: 8px;
  align-items: center;
}

/* ---- Starred and void expenses; finished tasks ------------------------- */

.expense-star {
  flex: none;
  width: 28px;
  height: 28px;
  padding: 0;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: var(--faint);
  font-size: 1rem;
  line-height: 1;
  cursor: pointer;
}

.expense-star:hover {
  background: var(--raised);
  color: var(--text);
}

.expense-star--on,
.expense-row__star {
  color: var(--text);
}

.expense-row__star {
  flex: none;
  width: 28px;
  text-align: center;
}

.expense-row__void {
  padding: 4px 10px;
  border: 1px solid var(--line);
  border-radius: var(--pill);
  background: transparent;
  color: var(--muted);
  font: 600 var(--fs-xs) / 1 var(--font-mono);
  white-space: nowrap;
  cursor: pointer;
}

.expense-row__void:hover {
  border-color: var(--line-strong);
  color: var(--text);
}

.expense-row--void .expense-row__amount {
  color: var(--faint);
  text-decoration: line-through;
}

.board-chip--void {
  border-style: dashed;
  color: var(--faint);
}

.board-chip--failed {
  border-color: var(--coral-edge);
  color: var(--coral);
}

.board-chip--done {
  border-color: var(--emerald-edge);
  color: var(--emerald-soft);
}

.task-row--closed .task-row__title {
  color: var(--muted);
}

.task-edit__fail {
  margin-left: auto;
}

/* A project's page has no Project field: Amount, Note, Add. */
.expense-add.expense-add--fixed {
  grid-template-columns: minmax(0, 0.8fr) minmax(0, 1.6fr) auto;
}

@media (max-width: 768px) {
  .project-edit {
    grid-template-columns: minmax(0, 1fr);
  }

  .project-swatches {
    grid-template-columns: repeat(9, minmax(0, 1fr));
  }

  .topup-add,
  .expense-add.expense-add--fixed {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  }

  .topup-add .btn,
  .expense-add.expense-add--fixed .btn {
    grid-column: 1 / -1;
  }
}
```

- [ ] **Step 12: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npx vitest run tests/BudgetBar.test.tsx tests/ExpenseList.test.tsx tests/TopupForm.test.tsx tests/TopupHistory.test.tsx tests/ProjectsBoard.test.tsx tests/Project.test.tsx tests/Board.test.tsx tests/live.test.ts tests/TasksBoard.test.tsx tests/NotesBoard.test.tsx tests/DocumentsBoard.test.tsx tests/MoneyBoard.test.tsx`
Expected: PASS. Per file:

| File | Tests |
|---|---|
| BudgetBar | 5 |
| ExpenseList | 4 |
| TopupForm | 4 |
| TopupHistory | 6 |
| ProjectsBoard | 9 |
| Project | 9 |
| Board | 3 |
| live | 24 (the stuck flow's 23 and the Review Focus test) |
| TasksBoard | 16 |
| NotesBoard | 10 |
| DocumentsBoard | 9 |
| MoneyBoard | 14 |

Run the whole web suite. It includes `DocumentsTab.test.tsx`, `Profile.test.tsx`, `Home.test.tsx`, `NoteEditor.test.tsx`, `UniverEditor.test.tsx`, `useLiveStore.test.ts` and the stuck-flow tests, which must stay green:
`cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npm test`
Expected: PASS.

Run the type check, the build and the bundle budget:
`cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npm run build && npm run size`
Expected:
- `tsc -b` reports no errors (no `CategoryTotalOut`, no `status: string` on `ExpenseOut`).
- `vite build` still emits the Notes and Documents boards as their own chunks.
- `npm run size` prints `entry assets/index-….js: … B gzip (budget 257400 B)`, with no "Over the main-bundle budget" line.

Run the vocabulary checks. The new copy says project, Board and bot, and uses no "Category", "By category", "categories", ">Desk<" or " in Talk":
`cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_vocabulary.py -q`
Expected: PASS.

`web/e2e/records.spec.ts` still expects the Board to open on Tasks. Task 10 updates it and runs `make e2e`.

- [ ] **Step 13: Commit**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && git add web/src/api/types.ts web/src/api/projects.ts web/src/api/money.ts web/src/api/tasks.ts web/src/api/notes.ts \
  web/src/api/documents.ts web/src/store/live.ts \
  web/src/components/board/money.ts web/src/components/board/ExpenseList.tsx web/src/components/board/ExpenseAddForm.tsx \
  web/src/components/board/MoneyBoard.tsx web/src/components/board/lazyPanel.tsx web/src/components/board/TaskRow.tsx \
  web/src/components/board/TaskAddForm.tsx web/src/components/board/TaskEditForm.tsx web/src/components/board/TasksBoard.tsx \
  web/src/components/notes/NotesBoard.tsx web/src/components/documents/DocumentsBoard.tsx \
  web/src/components/projects/projects.ts web/src/components/projects/BudgetBar.tsx \
  web/src/components/projects/ProjectRow.tsx web/src/components/projects/ProjectEditForm.tsx \
  web/src/components/projects/ProjectsBoard.tsx web/src/components/projects/TopupForm.tsx \
  web/src/components/projects/TopupHistory.tsx web/src/components/projects/ProjectSummary.tsx \
  web/src/components/projects/ProjectActions.tsx web/src/components/projects/ProjectMoney.tsx \
  web/src/pages/Project.tsx web/src/pages/Board.tsx web/src/App.tsx web/src/styles.css web/src/styles/projects.css \
  web/tests/projectFixtures.ts web/tests/BudgetBar.test.tsx web/tests/ExpenseList.test.tsx web/tests/TopupForm.test.tsx \
  web/tests/TopupHistory.test.tsx web/tests/ProjectsBoard.test.tsx web/tests/Project.test.tsx web/tests/Board.test.tsx \
  web/tests/live.test.ts web/tests/TasksBoard.test.tsx web/tests/NotesBoard.test.tsx web/tests/DocumentsBoard.test.tsx \
  web/tests/MoneyBoard.test.tsx
cd /Users/blckit/Desktop/Code_Projects/roost && git status --short
cd /Users/blckit/Desktop/Code_Projects/roost && git commit -m "feat: the Board's Projects tab and project page, budget bars, top-ups, starred and void expenses, failed tasks"
```

Expected from `git status --short` before the commit: the 33 source files and 13 test files above are staged (`A` or `M`). Anything else it lists is unstaged (` M` or `??`) and belongs to another change, such as the stuck flow's files still in progress; never stage it here.

---

### Task 10: E2E and the docs

This task covers design §4 (E2E: create a project, add an expense and a top-up, then see both bars and the history) and the web decisions P2, P3, P4, P6 (starred and void expenses, top-ups with their history) and P7. It also covers §5 H4 (top-ups and their undo, with the history), H6 (void expenses stay listed but are not counted, plus starred ones), H8 (the server sends the bars' numbers), H9 (deleting a project moves its expenses to General) and H14 (Projects is the first **and default** Board tab, with a page per project and the documents' two-step delete). Tasks 1–9 built all of this. This task proves it end to end in a real browser and updates the docs.
- **Through the UI only.** `web/e2e/projects.spec.ts` drives only the Board and the project page. No bot is involved, so `web/e2e/fixtures/team-script.json` stays as it is.
  - The flow: sign in and open the Board, which lands on Projects. Create "Renovation" (total budget 3000, monthly limit 1000, EUR) and open it. On its Money sub-tab, add a 2500 expense and a 500 top-up, and see the total bar and the history change. Undo the top-up and see the bar go back. Star the expense and see the starred total, then void it, and see it marked and left out of both bars and the starred total. Delete the project with the two-step confirmation, then find the expense under General on the Board's Money tab.
- **Expected texts come from the web's own formatter.** The spec imports `formatMoney` from `web/src/components/board/money.ts`, so `formatMoney("2500", "EUR")` gives `€2,500.00` (en-IE), exactly what the bars show. A bar's line is Task 9's `budgetText`: `{remaining} left of {budget}`, or `Over by {-remaining}` past the budget. The spec does no sums: the remaining amounts are written down as constants. The percentages are the server's `used_percent`, which Task 3 rounds down, and the tone is the server's (H8):
  - 2500 / 3000 gives `83`, tone `warn` (amber), and `€500.00 left of €3,000.00`;
  - 2500 / 3500 gives `71`, tone `ok`, and `€1,000.00 left of €3,500.00`;
  - 2500 against the 1000 monthly limit gives `250`, tone `over`, and `Over by €1,500.00`. `BudgetBar` clamps its `aria-valuenow` to 0–100, so this meter reads `100`;
  - a void expense counts nowhere, which gives `0` and `ok` on both bars, and takes it out of the starred total.
- **The older specs.** `records.spec.ts` and `every-bot.spec.ts` assumed that the Board opens on Tasks. Each one now clicks the Tasks tab first, and `records.spec.ts` checks that Projects is the default.
- **Spec order.** Playwright runs the spec files alphabetically on one worker: `computer`, `every-bot`, `main-bot`, `profile`, `projects`, `records`, `stuck`, `team`.
  - `projects.spec.ts` needs no bot and no earlier spec. By the time it runs, `every-bot` has made a "food" project, which the Projects tab lists next to Renovation.
  - It leaves one void 2500 EUR "Kitchen tiles" expense in General for the current month. No later spec counts the month's expenses or the General row: `records.spec.ts` picks Life admin's own row.
- **Docs.**
  - The CLAUDE.md Documentation Map gains the hub design and plan. The Architecture section gains one short paragraph about projects.
  - `README.md` drops its last use of "category". Task 1 left this to this task (Task 1, Step 8).
  - A small pytest file, `tests/test_docs.py`, keeps the map honest: the hub entries are there, and every file the map names exists.

**Files:**
- Create:
  - `web/e2e/projects.spec.ts`
  - `tests/test_docs.py`
- Modify:
  - `web/e2e/records.spec.ts` (Projects is the default tab; click Tasks first)
  - `web/e2e/every-bot.spec.ts` (click Tasks before looking for the task row)
  - `CLAUDE.md` (two Documentation Map lines and one Architecture paragraph)
  - `README.md` ("category name" becomes "project name")
- Test: `web/e2e/projects.spec.ts`, `web/e2e/records.spec.ts`, `web/e2e/every-bot.spec.ts` and `tests/test_docs.py`

**Interfaces:**
- Consumes:
  - **Task 9: the accessible names this spec relies on** (Task 9's "Produces", checked against its code). Step 1 greps for each one. Task 9's vitest tests pin the same names.
    - **Board** (`pages/Board.tsx`):
      - The first tab is `Projects` (role `tab`), and it is selected on `/board`.
      - The `Tasks` and `Money` tabs are still there.
    - **`ProjectsBoard`** (`<section aria-label="Projects">`):
      - A button `New project` opens `ProjectEditForm` as a `<form aria-label="New project">`. Its fields are labelled `Name`, `Currency` (its value starts as `EUR`, the default currency), `Total budget` and `Monthly limit` (a `<label>` around each input). Its submit button is `Create project`, and the form closes after a save.
      - The list `<ul aria-label="Your projects">` shows a `ProjectRow` per project but General. Its link to `/board/projects/{id}` has the project's name as its whole text.
      - With no project at all, it reads `No projects yet. …` instead of the list.
    - **`pages/Project.tsx`**, at `/board/projects/:projectId`:
      - an `<h1>` with the project's name;
      - `ProjectSummary` above the tabs, on every sub-tab: a `BudgetBar` named `Total budget`, one named `This month`, and `Starred {formatMoney(starred_total)}` while the starred total is above zero;
      - a tablist with the tabs `Tasks`, `Money`, `Notes` and `Docs`;
      - a button named `Delete {name}`, which opens a group named `Delete {name}?` with the copy "Its expenses move to General; its tasks, notes and documents stay, just unlinked." and the button `Delete {name} for good` (with `Cancel`), as in `DocumentRow`'s two-step delete;
      - after the delete, the page goes to `/board?tab=projects`;
      - the page reloads its detail on `boardVersion.money`, so the bars follow every expense change.
    - **`BudgetBar`:**
      - The bar is a `role="meter"` named by its label. Its `aria-valuenow` is the server's `used_percent` clamped to 0–100, Task 9's one exception to "no maths".
      - Inside the meter, the fill has the class `budget-bar__fill--{tone}` (`ok`, `warn` or `over`, the server's tone).
      - Its visible line is `budgetText`: `{formatMoney(remaining)} left of {formatMoney(budget)}`, or `Over by {formatMoney(-remaining)}` past the budget (design §2's "Over by …").
    - **The Money sub-tab** (`ProjectMoney`):
      - `MoneyBoard` narrowed to the project. Its expense form (`Amount`, `Note` and `Add expense`, no Project field) files the expense into this project.
      - `ExpenseList` (`<ul aria-label="Expenses">`). A row's buttons are `Star the {project} expense` (with `aria-pressed`) and `Void the {project} expense`, which reads `Restore the {project} expense` once the row is void.
      - A void row has the class `expense-row--void` and the chip `void`.
    - **`TopupForm`:** a field `Top-up amount` and a button `Add top-up`, inside the region `Top-ups`.
    - **`TopupHistory`:**
      - A `<ul aria-label="Top-up history">`. Each row shows its H4 label (`Top-up`, `Top-up changed` or `Budget set`) and its amount. An edit row's amount is signed, so "Budget set" reads `+€3,000.00`.
      - A live credit row has the buttons `Change the top-up of {money}` and `Undo the top-up of {money}`.
      - An undone row keeps its place with the chip `undone` (lower case), and has neither button.
  - **Task 8:** the routes behind those screens: `GET /api/projects`, `POST /api/projects`, `GET /api/projects/{id}`, `POST /api/projects/{id}/topups`, `POST /api/topups/{id}/undo`, `PUT /api/money/expenses/{id}/star`, `PUT /api/money/expenses/{id}/void`, `DELETE /api/projects/{id}` and `POST /api/money/expenses`.
  - **Task 6:**
    - `ProjectService.delete` moves the expenses to General (H9).
    - Every change is published on `money_changed`, so open pages reload.
  - **Task 3:**
    - `budget_line` rounds `used_percent` down; its tone is `warn` from 80 and `over` from 100.
    - Voids are left out of every sum, the starred total included.
    - `list_month` still returns void rows.
  - **Task 2:** creating a project with a budget writes the first history row, a `set_budget` edit with no `topup_id`, shown as "Budget set". Undo keeps the credit in the history with `undone=True`.
  - **Task 1:**
    - An expense row shows its project's name (`ExpenseOut.project`, `expense-row__project`).
    - The `records.spec.ts` comment now reads "By project". This task's find there avoids that line.
  - **The stuck flow, Task 9:** its CLAUDE.md map lines, which are this task's anchor (after the stuck flow).
  - **Existing code:**
    - `web/e2e/helpers.ts`: `signIn`, `openBoard` and `detailPane`;
    - `formatMoney(amount, currency)` from `web/src/components/board/money.ts`.
- Produces:
  - E2E names taken from now on: the project "Renovation" and the expense note "Kitchen tiles".
  - `tests/test_docs.py`: every later docs task must keep the CLAUDE.md map pointing at files that exist.
  - No code interface.

- [ ] **Step 1: Path guard**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

Then confirm three things: Task 9 and the stuck flow's docs have landed, and this task has not.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && test -f web/src/pages/Project.tsx && test -f web/src/components/projects/ProjectsBoard.tsx && test -f web/src/components/board/ExpenseList.tsx && test ! -f web/e2e/projects.spec.ts && grep -c "roost-stuck-flow" CLAUDE.md`
Expected: `3`. If a test fails or the count differs, stop. Either Task 9 or the stuck flow's Task 9 has not landed, or this task already ran.

Then check that Task 9 uses the names this spec relies on:

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && for text in '"New project"' 'Create project' '>Name<' '>Currency<' '>Total budget<' '>Monthly limit<' 'Your projects' 'No projects yet' '"This month"' 'role="meter"' 'budget-bar__fill--' 'left of' 'Over by' 'Starred ' 'Top-up amount' 'Add top-up' 'Top-up history' 'Budget set' 'undone</span>' 'Undo the top-up of' 'aria-pressed' 'the ${expense.project} expense' '"Restore" : "Void"' 'expense-row--void' 'Its expenses move to General' 'for good' 'tab=projects' '"Docs"'; do grep -rqF -- "$text" web/src/components/projects web/src/components/board/ExpenseList.tsx web/src/pages/Project.tsx || echo "missing: $text"; done; grep -qF '"Projects"' web/src/pages/Board.tsx || echo 'missing: the "Projects" tab'`
Expected: no output. (The single quotes keep `${expense.project}` literal: it is `ExpenseList`'s `what` helper, which names the Star, Void and Restore buttons.) If something is listed, stop and report it: Task 9 has diverged from the names in this task's Interfaces. Reconcile the plan before you write the spec. Never loosen the spec to fit.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_docs.py`:

```python
"""CLAUDE.md loads on every turn, and the README is what a user reads first (projects hub, Task 10).
The Documentation Map names the plans that shaped the code, and only files that exist. The
Architecture section says where projects live. The README calls an expense's group its project (H1)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLAUDE_MD = ROOT / "CLAUDE.md"
README = ROOT / "README.md"
HUB_DOCS = (
    "docs/plans/2026-10-14-roost-projects-hub-design.md",
    "docs/plans/2026-10-14-roost-projects-hub.md",
)
MAP_HEADING = "## Documentation Map"
ARCHITECTURE_HEADING = "## Architecture"
OLD_MONEY_WORD = "categor"            # "category" / "categories": money is grouped by project now (H1)
_MAP_ENTRY = re.compile(r"^- `([^`]+\.md)`", re.MULTILINE)


def _section(text: str, heading: str) -> str:
    """The text under ``heading``, up to the next ``## `` heading."""
    return text.split(heading, 1)[1].split("\n## ", 1)[0]


def _map_paths() -> list[str]:
    return _MAP_ENTRY.findall(_section(CLAUDE_MD.read_text(encoding="utf-8"), MAP_HEADING))


def test_the_documentation_map_names_the_projects_hub_design_and_plan():
    assert [path for path in HUB_DOCS if path not in _map_paths()] == []


def test_every_file_on_the_documentation_map_exists():
    paths = _map_paths()
    assert paths, "the Documentation Map lists no files"
    assert [path for path in paths if not (ROOT / path).is_file()] == []


def test_the_architecture_section_says_where_projects_live():
    architecture = _section(CLAUDE_MD.read_text(encoding="utf-8"), ARCHITECTURE_HEADING)
    assert "roost/projects/" in architecture
    assert "/board/projects/:projectId" in architecture


def test_the_readme_calls_an_expenses_group_its_project():
    assert OLD_MONEY_WORD not in README.read_text(encoding="utf-8").casefold()
```

Create `web/e2e/projects.spec.ts`:

```ts
import { expect, test, type Locator, type Page } from "@playwright/test";
import { formatMoney } from "../src/components/board/money";
import { detailPane, openBoard, signIn } from "./helpers";

// Projects hub (design P2–P4, P6, P7 and §5 H4, H6, H8, H9, H14), through the Board only. No bot is
// involved, so fixtures/team-script.json is untouched. Amounts are what the web shows, formatted by
// its own formatMoney (en-IE): "€2,500.00". The server does every sum (H8); this spec only reads them,
// so the amounts left are written down here, never computed.
const PROJECT = "Renovation";
const NOTE = "Kitchen tiles";
const CURRENCY = "EUR";               // the New project form's default
const TOTAL = "3000";
const MONTHLY = "1000";
const SPENT = "2500";
const TOP_UP = "500";
const TOTAL_WITH_TOP_UP = "3500";
const LEFT = "500";                   // 3000 − 2500
const LEFT_WITH_TOP_UP = "1000";      // 3500 − 2500
const MONTH_OVER = "1500";            // 2500 spent this month against the 1000 monthly limit
const eur = (amount: string): string => formatMoney(amount, CURRENCY);
const STARRED = `Starred ${eur(SPENT)}`;

// A BudgetBar (Task 9): its line (budgetText), its aria-valuenow (the server's used_percent, rounded
// down and clamped to 0–100) and the server's tone, which names the fill's class.
type Tone = "ok" | "warn" | "over";
type Bar = readonly [text: string, percent: string, tone: Tone];
const left = (remaining: string, budget: string): string => `${eur(remaining)} left of ${eur(budget)}`;
const FRESH_TOTAL: Bar = [left(TOTAL, TOTAL), "0", "ok"];
const FRESH_MONTH: Bar = [left(MONTHLY, MONTHLY), "0", "ok"];
const SPENT_TOTAL: Bar = [left(LEFT, TOTAL), "83", "warn"];                                  // amber from 80 %
const TOPPED_UP_TOTAL: Bar = [left(LEFT_WITH_TOP_UP, TOTAL_WITH_TOP_UP), "71", "ok"];
const OVER_MONTH: Bar = [`Over by ${eur(MONTH_OVER)}`, "100", "over"];                       // the server says 250

const history = (detail: Locator): Locator => detail.getByRole("list", { name: "Top-up history" });
const expenseRow = (detail: Locator): Locator =>
  detail.getByRole("list", { name: "Expenses" }).getByRole("listitem").filter({ hasText: NOTE });

async function expectBar(detail: Locator, name: string, [text, percent, tone]: Bar): Promise<void> {
  const meter = detail.getByRole("meter", { name, exact: true });
  await expect(meter).toHaveAttribute("aria-valuenow", percent);
  await expect(meter.locator(`.budget-bar__fill--${tone}`)).toHaveCount(1);
  await expect(detail.getByText(text, { exact: true })).toBeVisible();
}

async function expectBars(detail: Locator, total: Bar, month: Bar): Promise<void> {
  await expectBar(detail, "Total budget", total);
  await expectBar(detail, "This month", month);
}

async function createProject(detail: Locator): Promise<void> {
  await detail.getByRole("button", { name: "New project", exact: true }).click();
  const form = detail.getByRole("form", { name: "New project", exact: true });
  await form.getByLabel("Name", { exact: true }).fill(PROJECT);
  await expect(form.getByLabel("Currency", { exact: true })).toHaveValue(CURRENCY);
  await form.getByLabel("Total budget", { exact: true }).fill(TOTAL);
  await form.getByLabel("Monthly limit", { exact: true }).fill(MONTHLY);
  await form.getByRole("button", { name: "Create project", exact: true }).click();
  await expect(form).toHaveCount(0);
}

async function openProjectMoney(page: Page, detail: Locator): Promise<void> {
  await detail.getByRole("list", { name: "Your projects" }).getByRole("link", { name: PROJECT, exact: true }).click();
  await page.waitForURL(/\/board\/projects\/[^/?]+/);
  await expect(detail.getByRole("heading", { name: PROJECT, exact: true })).toBeVisible();
  await detail.getByRole("tab", { name: "Money", exact: true }).click();
  await expectBars(detail, FRESH_TOTAL, FRESH_MONTH);
  // H4: the budget given at creation is the history's first row ("+€3,000.00").
  await expect(history(detail).getByRole("listitem").filter({ hasText: "Budget set" })).toContainText(eur(TOTAL));
}

async function addExpense(detail: Locator): Promise<Locator> {
  await detail.getByRole("textbox", { name: "Amount", exact: true }).fill(SPENT);
  await detail.getByRole("textbox", { name: "Note", exact: true }).fill(NOTE);
  await detail.getByRole("button", { name: "Add expense", exact: true }).click();
  const expense = expenseRow(detail);
  await expect(expense).toContainText(eur(SPENT));
  await expectBars(detail, SPENT_TOTAL, OVER_MONTH);                         // the month is over its limit
  return expense;
}

async function topUpThenUndo(detail: Locator): Promise<void> {
  await detail.getByRole("textbox", { name: "Top-up amount", exact: true }).fill(TOP_UP);
  await detail.getByRole("button", { name: "Add top-up", exact: true }).click();
  await expectBars(detail, TOPPED_UP_TOTAL, OVER_MONTH);                     // the top-up raises the total budget
  const topUp = history(detail).getByRole("listitem").filter({ hasText: "Top-up" }).filter({ hasText: eur(TOP_UP) });
  const undo = topUp.getByRole("button", { name: `Undo the top-up of ${eur(TOP_UP)}`, exact: true });
  await undo.click();
  await expectBars(detail, SPENT_TOTAL, OVER_MONTH);                         // and its undo takes it back off
  await expect(topUp).toContainText("undone");                               // still in the history, marked
  await expect(undo).toHaveCount(0);
}

async function starThenVoid(detail: Locator, expense: Locator): Promise<void> {
  const star = expense.getByRole("button", { name: `Star the ${PROJECT} expense`, exact: true });
  await star.click();
  await expect(star).toHaveAttribute("aria-pressed", "true");
  await expect(detail.getByText(STARRED, { exact: true })).toBeVisible();          // P6: the starred total
  await expense.getByRole("button", { name: `Void the ${PROJECT} expense`, exact: true }).click();
  await expect(expense.getByRole("button", { name: `Restore the ${PROJECT} expense`, exact: true })).toBeVisible();
  await expect(expense).toHaveClass(/expense-row--void/);                          // H6: still listed, marked
  await expectBars(detail, FRESH_TOTAL, FRESH_MONTH);                              // and counted in neither bar
  await expect(detail.getByText(STARRED, { exact: true })).toHaveCount(0);         // nor in the starred total
}

async function deleteProject(page: Page, detail: Locator): Promise<void> {
  await detail.getByRole("button", { name: `Delete ${PROJECT}`, exact: true }).click();
  await expect(detail.getByRole("group", { name: `Delete ${PROJECT}?`, exact: true }))
    .toContainText("Its expenses move to General");
  await detail.getByRole("button", { name: `Delete ${PROJECT} for good`, exact: true }).click();
  await page.waitForURL(/\/board\?tab=projects$/);
  await expect(detail.getByRole("tab", { name: "Projects", exact: true })).toHaveAttribute("aria-selected", "true");
  // Wait for the list (or its empty line) before checking that the project left it.
  await expect(detail.getByRole("list", { name: "Your projects" }).or(detail.getByText(/^No projects yet/))).toBeVisible();
  await expect(detail.getByRole("link", { name: PROJECT, exact: true })).toHaveCount(0);
}

test("a project with a total budget and a monthly limit: an expense, a top-up and its undo, star and void, then delete it", async ({ page }) => {
  test.setTimeout(60_000);
  await signIn(page);
  await openBoard(page);
  const detail = detailPane(page);
  await expect(detail.getByRole("tab", { name: "Projects", exact: true })).toHaveAttribute("aria-selected", "true");   // H14
  await createProject(detail);
  await openProjectMoney(page, detail);
  const expense = await addExpense(detail);
  await topUpThenUndo(detail);
  await starThenVoid(detail, expense);
  await deleteProject(page, detail);

  // H9: the project is gone but its expense is not. It moved to General, void as it was, and the Money tab lists it there.
  await detail.getByRole("tab", { name: "Money", exact: true }).click();
  const moved = expenseRow(detail);
  await expect(moved.locator(".expense-row__project")).toHaveText("General");
  await expect(moved).toContainText(eur(SPENT));
  await expect(moved).toHaveClass(/expense-row--void/);
});
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_docs.py -q`
Expected: FAIL, 3 failed and 1 passed:
- `test_the_documentation_map_names_the_projects_hub_design_and_plan`: both hub paths are still missing from the map.
- `test_the_architecture_section_says_where_projects_live`: `assert "roost/projects/" in architecture`.
- `test_the_readme_calls_an_expenses_group_its_project`: README line 103 still says "category name the row shows".
- `test_every_file_on_the_documentation_map_exists` passes. This test is a guard, not new behaviour.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && df -g /System/Volumes/Data | awk 'NR==2{print $4}'`
Expected: at least 8. Otherwise stop and report.

Run this as one shell call. It uses `make e2e`'s port rule: 5173 while the live gateway holds 18800. The Chromium build that `make e2e` installed earlier is reused. If Playwright reports that the browser executable is missing, run `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npx playwright install chromium` (the disk guard above has passed), then run this again.

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && cd web && \
port=18800 && if curl -fsS -o /dev/null --max-time 2 http://127.0.0.1:18800/api/health; then port=5173; fi && \
npm run build && ROOST_E2E_PORT=$port npx playwright test e2e/every-bot.spec.ts e2e/projects.spec.ts e2e/records.spec.ts
```

Expected: 2 failed and 2 passed.
- `every-bot.spec.ts` fails at `toContainText("by Helper")` on the "Call the dentist" row. The element is not found because the Board now opens on Projects.
- `records.spec.ts`, "a new bot keeps the user's tasks and money on the shared Board", fails at the Tasks tab's `aria-selected`, with `Expected: "true"` and `Received: "false"`.
- The first test in `records.spec.ts` passes, because it clicks its own tabs.
- `projects.spec.ts` passes already. It adds no code of its own: it is new coverage of Task 9's finished screens. If it fails, read Step 6's triage before going on.

- [ ] **Step 4: The older specs open the Tasks tab**

`web/e2e/records.spec.ts` (after Task 1, which changed only the "By project" comment six lines further down). Find:

```ts
  await expect(detail.getByRole("tab", { name: "Tasks" })).toHaveAttribute("aria-selected", "true");
```

Replace with:

```ts
  // Projects is the Board's first and default tab (projects hub H14); the tasks are one click away.
  await expect(detail.getByRole("tab", { name: "Projects" })).toHaveAttribute("aria-selected", "true");
  await detail.getByRole("tab", { name: "Tasks" }).click();
  await expect(detail.getByRole("tab", { name: "Tasks" })).toHaveAttribute("aria-selected", "true");
```

`web/e2e/every-bot.spec.ts`. Find:

```ts
  await openBoard(page);
  await expect(detail.getByRole("listitem").filter({ hasText: "Call the dentist" })).toContainText("by Helper");
```

Replace with:

```ts
  await openBoard(page);
  await detail.getByRole("tab", { name: "Tasks" }).click();   // Projects is the default tab (projects hub H14)
  await expect(detail.getByRole("listitem").filter({ hasText: "Call the dentist" })).toContainText("by Helper");
```

- [ ] **Step 5: The docs**

`CLAUDE.md`, the Documentation Map (after the stuck flow: its Task 9 added this line). Find:

```markdown
- `docs/plans/2026-10-14-roost-stuck-flow.md` — the stuck flow plan: schema v12 (`stuck_cards`), `roost/desk/stuck.py`, `roost/stuck/`, `ask_for_help`, the `/api/stuck` routes, the keeper's `main-browser/open`, and My turn on Home.
```

Replace with:

```markdown
- `docs/plans/2026-10-14-roost-stuck-flow.md` — the stuck flow plan: schema v12 (`stuck_cards`), `roost/desk/stuck.py`, `roost/stuck/`, `ask_for_help`, the `/api/stuck` routes, the keeper's `main-browser/open`, and My turn on Home.
- `docs/plans/2026-10-14-roost-projects-hub-design.md` — the projects hub design (migration part 1): one project holds its tasks, money (a total budget and/or a monthly limit, expenses, top-ups), notes and documents. Its §5 (H1–H16) overrides the earlier sections.
- `docs/plans/2026-10-14-roost-projects-hub.md` — the projects hub plan: Category becomes Project, schema v13, `roost/projects/` (`numbers.py`, `ProjectService`, the project tools), the `/api/projects` and top-up routes, and the Board's Projects tab with a page per project.
```

`CLAUDE.md`, the Architecture section, after its last paragraph (after the stuck flow: its Task 9 puts its own paragraph just above this one and leaves this one as it is). Find:

```markdown
Notes and documents are the **user's** too (`roost/notes/`, `roost/documents/`): one encrypted blob per document (AAD `docs:payload` / `sheets:payload` / `pdf:payload`), a `revision` compare-and-swap on every save (409 + the current copy), and the web editors are lazy chunks built from Univer's open-source presets only (`web/tests/licenseGate.test.ts`).
```

Replace with:

```markdown
Notes and documents are the **user's** too (`roost/notes/`, `roost/documents/`): one encrypted blob per document (AAD `docs:payload` / `sheets:payload` / `pdf:payload`), a `revision` compare-and-swap on every save (409 + the current copy), and the web editors are lazy chunks built from Univer's open-source presets only (`web/tests/licenseGate.test.ts`).

A project (the `money_projects` table, schema v13) holds its tasks, money, notes and documents. `roost/projects/numbers.py` is the one place for the sums: the total and monthly budgets, bar tones, other currencies, and each task's planned / spent / left. `ProjectService` (`roost/projects/service.py`) owns create, update, archive, top-ups and delete; a deleted project's expenses move to the hidden General project, and its tasks, notes and documents are unlinked. Every bot has the project tools. The Board's first tab, Projects, opens a page per project at `/board/projects/:projectId`.
```

`README.md`. Find:

```markdown
from then on (a repeating task's next one too, and on an expense, the
category name the row shows), so listing it marks nothing. Then start a
```

Replace with:

```markdown
from then on (a repeating task's next one too, and on an expense, the
project name the row shows), so listing it marks nothing. Then start a
```

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && grep -c "roost-projects-hub" CLAUDE.md`
Expected: `2`. That is the two map lines. The Architecture paragraph names no plan file.

- [ ] **Step 6: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_docs.py tests/test_vocabulary.py -q`
Expected: PASS. `test_docs.py` has 4 tests. `test_vocabulary.py` still passes, because the new lines contain no "Take the wheel" and no "| Desk |".

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && df -g /System/Volumes/Data | awk 'NR==2{print $4}'`
Expected: at least 8. Otherwise stop and report.

Run this as one shell call:

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && cd web && \
port=18800 && if curl -fsS -o /dev/null --max-time 2 http://127.0.0.1:18800/api/health; then port=5173; fi && \
ROOST_E2E_PORT=$port npx playwright test e2e/every-bot.spec.ts e2e/projects.spec.ts e2e/records.spec.ts
```

Expected: 4 passed. The build from Step 3 is still current, because only spec files changed.

If it fails:
- **"resolved to 2 elements" (strict mode).** A query escaped its scope. Scope it to `detail`, the expense row or the `Top-up history` list. Never loosen it with `.first()`.
- **A name is not found** (the `New project` button or form, a field, `Create project`, the `Total budget` or `This month` meter, `Top-up history`, `Undo the top-up of €500.00`, `Star the Renovation expense`, `Void …` / `Restore …`, or `Delete Renovation for good`). Check it against the Task 9 names under Interfaces, which Step 1 grepped. Fix the component, never the expected text. Task 9's vitest tests pin the same names.
- **A bar line, a percentage or a tone is wrong.**
  - The web must format the server's strings with `formatMoney` (`budgetText`) and do no sums (H8). Only `aria-valuenow` is clamped to 0–100.
  - `used_percent` and `tone` come from Task 3's `budget_line`, which rounds down.
  - If the bars or the `Starred …` line do not change after an action, the page did not reload. Its load must run after each action, or on `boardVersion.money`.
- **After the delete, the expense shows a project other than General, or does not show at all.**
  - `ProjectStore.delete` (Task 2) must move every expense, void ones included, to General in its one transaction.
  - `list_month` (Task 3) must still list void rows.
- **The expense lands in General before the delete.** The project page's expense form must send this project (Task 9).

- [ ] **Step 7: Full verification**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest -q`
Expected: PASS, the whole suite.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest --cov=roost --cov-fail-under=80`
Expected: PASS, with `Required test coverage of 80% reached`.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npm test && npm run build && npm run size`
Expected:
- Every vitest file passes, including Task 9's `Board`, `ProjectsBoard`, `Project`, `BudgetBar` and `TopupForm` tests.
- The build succeeds.
- The size check reports the entry chunk within `bundle-budget.json`.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && df -g /System/Volumes/Data | awk 'NR==2{print $4}'`
Expected: at least 8. Otherwise stop and report.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && make e2e`
Expected: every spec passes: `computer`, `every-bot`, `main-bot`, `profile`, `projects`, `records`, `stuck` and `team`.
- `make e2e` picks port 5173 when the live gateway holds 18800.
- It never touches `~/Roost/data`, because the throwaway gateway uses `ROOST_DATA_DIR=$(mktemp -d)`.

- [ ] **Step 8: Commit**

The hub plan is untracked until now, and the design is already committed, so both are listed: the new map lines must never point at an uncommitted file. `git add` of an unchanged tracked file does nothing.

Run:

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && \
git add web/e2e/projects.spec.ts web/e2e/records.spec.ts web/e2e/every-bot.spec.ts tests/test_docs.py \
  CLAUDE.md README.md docs/plans/2026-10-14-roost-projects-hub-design.md docs/plans/2026-10-14-roost-projects-hub.md && \
git commit -m "test: E2E for projects on the Board; docs: the projects hub in CLAUDE.md and the README"
```

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git status --short`
Expected: none of the eight files above is still listed as modified or untracked.

