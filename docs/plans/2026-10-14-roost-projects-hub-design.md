# Roost Projects Hub (Migration Part 1) — Design

**Status:** design approved in conversation on 2026-10-14, section by section. This file is the
written record for review. The implementation plan comes next.

**Why:** LazyClaw's data (projects, budgets, expenses, top-ups, tasks, notes) will move into
Roost. In LazyClaw a project tied tasks and money together. Roost lost that link and several
features. This part gives every LazyClaw field a home in Roost, so the importer (part 3) can carry
everything over.

**Order of the migration work:**
1. **Projects hub** (this design).
2. **Scheduler** (M3): reminders and nags that fire, recurring expenses, reports, and the 80 % /
   100 % budget warnings.
3. **Importer** (M4): LazyClaw → Roost with ids kept, counts checked and dry runs. Roost's
   current task and money rows are test data and are wiped first; the user confirmed that no real
   data is in Roost yet.

## Decisions (from the user, 2026-10-14)

- **P1.** One project holds its tasks, money (budgets, expenses, top-ups), notes **and documents**.
- **P2.** Linking an item to a project is **optional**. Loose expenses go to the hidden **General**
  project, as today.
- **P3.** A project can have a **total budget**, a **monthly limit**, or both.
- **P4.** Budgets count only spending in the **project's own currency**. Other currencies are
  listed apart and never converted.
- **P5.** Every bot can work on every project. A project may name a **lead bot**.
- **P6.** These lost LazyClaw features come back:
  - project basics: rename, delete, archive, colour, start and due dates;
  - money details: top-ups (add, edit, undo, with history), starred expenses, void expenses;
  - task ↔ money: a budget slice per task, expenses linked to a task or a step, planned vs spent;
  - task extras: the "failed" status and the end-of-day summary. The summary is *sent* by the
    scheduler in part 2; this part provides its content.
- **P7.** Projects live on the Board, as a new first tab, **Projects**, with a page per project.
- **P8.** Approach A: today's `money_projects` table **becomes** the project table. No second
  concept is added.

## 1. Data (schema v13, additive only)

**`money_projects`** (called "Project" in code and on the web; the word "category" goes away). New
columns:

| Column | Type / rule |
|---|---|
| `color` | plaintext, one of a fixed palette (constants) |
| `start_date`, `due_date` | plaintext ISO dates, nullable |
| `monthly_budget` | `enc:v2` decimal string, nullable (AAD `money_projects:monthly_budget`) |
| `lead_bot_id` | `REFERENCES bots(id) ON DELETE SET NULL` |

The other columns change meaning or gain values:
- `budget` is the **total** budget. Following LazyClaw's meaning, it already **includes** top-ups.
- `status` gains `archived` next to `active`.
- `currency` is the project's currency.

**Links:** `tasks.project_id`, `notes.project_id` and `documents.project_id` are new and nullable,
`REFERENCES money_projects(id) ON DELETE SET NULL`. `tasks.category` stays as the task's **list**.

**Tasks:**
- `allocated_budget` is new: an `enc:v2` decimal string, nullable.
- `status` gains `failed`. The column has no CHECK constraint, so no rebuild is needed.

**Expenses (`money_expenses`):**
- `project_id` stays required; loose expenses go to General.
- `task_id` already exists and is now used.
- `step_id` is new: the id of one step in the task's `steps` list.
- `is_favorite` is new, an integer defaulting to 0.
- `status` gains `void`.

**Top-ups (`money_topups`):** each add, edit or undo writes a row. These rows are the history: a
credit, an edit (the difference) or an undo (`deleted_at` set), and they always adjust
`money_projects.budget` in the same transaction.

**Encryption:** names, amounts, budgets, descriptions and notes stay `enc:v2`. Ids, dates, status,
colour and flags stay plaintext. Every query includes `user_id`, and another user's id gives 404.

## 2. Calculations

All amounts are `Decimal`. A **counted expense** is one that is `posted`, not deleted, and in the
project's currency.

| Number | Rule |
|---|---|
| Total budget | `budget` (includes top-ups) |
| Spent (total) | sum of counted expenses, all time |
| Remaining (total) | total budget − spent; negative shows "Over by …" |
| This month | counted expenses whose `spent_at` falls in the current Madrid month |
| Remaining this month | monthly limit − this month |
| Other currencies | sum per currency of posted, non-deleted expenses in other currencies; shown apart, never added |
| Bar colour (each budget) | green below 80 %, amber from 80 %, red from 100 % |
| Starred total | sum of the project's counted starred expenses |
| Task progress | done / all; failed counts as finished but is shown red |
| Task planned / spent / left | `allocated_budget` / counted expenses linked to the task or any of its steps / planned − spent |
| Step removed | its expenses' `step_id` is cleared, so they stay on the task (LazyClaw's rule) |

The Board's Money tab keeps its month view, with each project in its own currency. Archived
projects are hidden by default, but their numbers stay correct.

## 3. Bot tools and the web

**Tools** (every bot; the gate kinds and the tainted-write rule are unchanged):

| Kind | Tools |
|---|---|
| read | `list_projects` (with numbers), `get_project` (budgets, tasks, latest expenses, notes, documents) |
| write_create | `create_project` (name, currency, total and/or monthly budget, colour, dates, lead bot), `add_topup` |
| write_change | `update_project` (rename, colour, dates, lead bot, monthly limit, archive/unarchive; currency only while the project has no expenses), `set_budget`, `edit_topup`, `undo_topup` |

The existing tools learn projects:
- `add_task` and `update_task` get `project`, a budget slice, and the status `failed`.
- `add_expense` and `update_expense` get `project`, `task`, `step`, starred, and void.
- `add_note` and the document tools get `project`.
- Projects are named the way categories are today: the name is matched with case ignored.

**Deleting a project is not a bot tool.** It happens only on the Board, after a confirmation: its
expenses move to General, and its tasks, notes and documents stay but lose the link.

**Web: the Board gets a new first tab, Projects.**
- The list shows each project's name, its total and monthly bars, and its number of tasks.
- A project page shows the lead bot, the dates, both budgets, and Tasks · Money · Notes · Docs
  for that project.
- On the page you can edit the project, add, edit or undo top-ups (with the history), star or void
  expenses, and set a task's budget slice.

## 4. Testing

- **Calculations:** fixed-number unit tests covering mixed currencies, void expenses, undoing a
  top-up, the Madrid month boundary, going over budget, and planned vs spent per task (including a
  removed step).
- **Store and API:** ciphertext on disk, 404 for another user's project, unlinking items on
  delete, and expenses moving to General.
- **Web:** unit tests for the Projects tab and the project page.
- **E2E:** create a project, add an expense and a top-up, then see both bars and the history.

## 5. Refinements after reading the code (2026-10-14)

These replace the matching lines above where they differ. The decisions the user made (P1–P8) are
unchanged.

- **H1. Names.** One mechanical rename runs first:
  - in code, `Category`/`CategoryStore` become `Project`/`ProjectStore`, and `category_store.py`
    becomes `project_store.py`;
  - on the wire, `by_category`/`CategoryTotalOut` become `by_project`/`ProjectTotalOut`, and the
    expense's `category` becomes `project` (+ `project_id`);
  - in the UI, "Category" becomes "Project";
  - `GENERAL_CATEGORY_NAME` becomes `GENERAL_PROJECT_NAME`.
  - The money tools' argument becomes `project`, and still accepts `category` as an alias, so a
    model using the old name never lands in General by accident.
  - `tasks.category` stays: it is the task's **list**.
  - The expense tool keeps its real name, `log_expense`; the design text's `add_expense` means it.
- **H2. General.** General is the project whose `name_key` is the key of `GENERAL_PROJECT_NAME`.
  It is hidden on the Projects tab, and it can't be renamed, archived or deleted.
- **H3. Finding a project by name.**
  - Only `log_expense` keeps find-or-create, which is today's behaviour.
  - Every other tool that takes `project` is exact-or-ask. A fuzzy hit may be read but never
    changed, and an unknown name is refused: "No project is called “X”. Use create_project first."
  - An expense aimed at an archived project is refused: "“X” is archived; unarchive it first."
- **H4. Top-ups.**
  - `money_topups` gains `topup_id`: an `edit` row's link to the `credit` row it edits. A NULL
    `topup_id` means a `set_budget` edit.
  - Edit writes an `edit` row holding the difference. Undo sets `deleted_at` on the credit and its
    edits, and lowers `budget` by their sum. Both happen in one transaction that reads inside the
    write session.
  - Invariant: `budget == Σ amount of live top-up rows` while a budget is set.
  - History labels: "Top-up", "Top-up changed", "Budget set".
  - **`add_topup` is `write_change`**, not `write_create`: it changes an existing project's
    budget, so a run that read a web page must not do it.
- **H5. Clearing budgets.** Both budgets can be cleared. Clearing the total writes an `edit` row
  of −budget and then sets `budget` to NULL.
- **H6. Void and starred.** Expense reads show void rows (`deleted_at IS NULL`). The counting rule
  ("posted + the project's currency") is applied in Python, because amounts are encrypted.
- **H7. Currency.** An expense with no currency takes its project's currency.
  - Each project row in the summary carries its own `currency` and `other_currencies`.
  - The month summary's top-level EUR total stays, for compatibility.
  - A project's currency can change only while it has no expenses **and** no top-ups.
- **H8. Bars.** The web does no sums. The server sends each budget's `used_percent` and `tone`
  (`ok` / `warn` / `over`), with thresholds `BUDGET_WARN_PERCENT = 80` and
  `BUDGET_OVER_PERCENT = 100` (constants).
- **H9. Deleting a project.** It is a soft delete in one transaction:
  1. move the project's expenses to General (creating General if needed);
  2. set `project_id` to NULL on its tasks, notes and documents;
  3. set the project's `deleted_at`.

  The `ON DELETE SET NULL` clauses are only a safety net, because every delete here is soft.
- **H10. Events.** Project and top-up changes ride on `money_changed`, with new `change` values
  `project_created | project_updated | project_deleted | topup_added | topup_edited | topup_undone`.
  On `project_deleted` the web also refreshes Tasks, Notes and Documents.
- **H11. Tasks.**
  - `failed` goes through `TaskStore.fail` / `TaskService.fail`, which set `completed_at`. A failed
    recurring task comes back like a done one.
  - The `done` filter excludes failed, and a new `failed` filter exists.
  - A budget slice needs a project and is in that project's currency.
  - An expense's `task` resolves among tasks of every status. A `step` requires a `task` and must
    be one of its steps.
  - A task's spent is every counted expense with its `task_id`. An unknown `step_id` counts at task
    level, which gives the "removed step" rule at read time.
  - Progress is done / (all − cancelled).
- **H12. Notes and documents.**
  - Linking goes through `set_project`, which does **not** bump the revision, so an open editor is
    not disturbed.
  - The store refuses a project that isn't the user's.
  - Tool changes:
    - `add_note`, `find_notes` and `update_note` take `project` (`""` unlinks);
    - `create_doc` and `create_sheet` take `project`;
    - `make_pdf_from_doc` inherits its source's project;
    - `list_documents` filters by project;
    - a new write_change tool, `set_document_project`.
  - Routes: `PUT /api/notes/{id}/project`, `PUT /api/documents/{id}/project`, and
    `?project_id=` on the lists.
- **H13. End-of-day summary content.** `roost/tasks/day_summary.py` builds `DaySummary(day, done,
  failed, overdue, spent)` for a Madrid day: tasks closed that day, open overdue tasks, and that
  day's counted expenses per currency. No tool or route uses it yet; the scheduler (part 2) will
  send it.
- **H14. Web.**
  - Projects is the first **and default** Board tab.
  - A project page lives at `/board/projects/:projectId`, with sub-tabs Tasks · Money · Notes ·
    Docs.
  - `BudgetBar` is a `role="meter"` element.
  - The expense list moves to its own component, with star and void buttons.
  - Deleting a project uses the two-step confirmation the documents already use.
- **H15. Lead bot.** `lead_bot_id` must be one of the user's own bots. `get_project` names the lead.
- **H16. Colours.** `PROJECT_COLORS` is a fixed palette of nine hex colours in constants; the first
  is the default.

## Out of scope (later parts)

The 80 % / 100 % warning messages, recurring expenses, reports, reminders that fire, and the
end-of-day summary sending belong to part 2 (the scheduler). The LazyClaw importer is part 3.
