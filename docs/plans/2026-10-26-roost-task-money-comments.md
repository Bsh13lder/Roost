# Task money and comments in the drawer (2026-10-26)

**Owner request (2026-10-26, their words):** "in Tasks I cant add comenta budget expensesn not in Taks not in
subtasks imoosible. that we need". They mostly use the phone app.

## What was missing

| | Server | Web drawer | Phone drawer |
|---|---|---|---|
| Comments on a task | yes | yes | yes |
| Comments on a step | yes (`step_id`) | yes (About picker) | **no** |
| Edit / delete your own comment | yes | yes | yes (the edit dialog disposed its field too early) |
| Budget on a task in a project | yes | yes | **no** (shown, never editable) |
| Budget on a task in no project | **no** (H11: "A budget slice needs a project.") | **no** | **no** |
| Budget on a step | **no** | **no** | **no** |
| Add an expense for the task / a step | yes (`task_id`, `step_id`) | yes | **no** |
| Delete an expense | yes (soft, with restore) | yes (with Undo) | **no** in the drawer |
| Money shown for a task in no project | **no** (`money: null`) | text only | hidden |

## Decisions

- **D1. Any task takes a budget.** A task in no project counts its money in **General's currency** (where its
  expenses already go; `DEFAULT_CURRENCY` before General exists). `TaskStore._checked_slice` no longer needs a
  project. A move keeps the slice when the currency stays the same (General counts as the no-project home)
  and clears it otherwise, with the same `notice`. A respawned repeating task keeps its slice.
  **Bots keep H11**: `add_task` / `update_task` still refuse a slice on a task in no project
  (`_bot_slice_rule` in `roost/tasks/tools.py`). The owner's quick-add line follows D1 too (below).
- **D2. A step's own budget** lives in the sealed steps JSON as `budget` (amount text) and `budget_currency`
  (the task's currency when set). No schema change. A damaged value reads as none. When the task later counts
  in another currency, the step budget reads as none (`step_lines`), so nothing has to be rewritten on a move.
- **D3. The server reckons every number.** `GET /api/tasks/{id}` always answers `money` (project currency or
  General's) and adds `steps_money: {step_id: {planned, spent, left, used_percent, tone}}`
  (`roost/projects/numbers.step_lines`, the same `budget_line` rule as every bar). `steps` (spent per step) stays.

## Routes

- `PATCH /api/tasks/{id}` `allocated_budget`: now also for a task in no project.
- `PATCH /api/tasks/{id}/steps/{step_id}` gains `budget` (string or number by `parse_amount`'s rules; `null`
  clears). 422 with the plain sentence for a bad amount; another user's task or an unknown step is a 404.
- Unchanged and reused: `POST /api/money/expenses` (`task_id`, `step_id`, `note`, `spent_at` words, default
  Madrid's today), `DELETE /api/money/expenses/{id}` + `POST …/restore`, `/api/tasks/{id}/comments`,
  `/api/comments/{id}`.

## Clients

- **Web** (`web/src/components/tasks/`): the Budget property shows for every task; `StepBudget.tsx` puts a
  Budget button and "€25.00 of €20.00 · €5.00 over" on each step; `TaskMoneyPanel` says "In no project, so its
  money counts in General, in EUR." Expense delete with Undo was already there.
- **Phone** (`mobile/lib/board/tasks/`): a Budget row (applies at once), Money for every task with Add
  expense and tap-to-edit/delete (the Money tab's expense sheet, Undo included), a ⋯ menu on each step
  (Budget…, Add expense…, Comment…, Delete step) and its money line, and a step picker beside the comment
  field. Forms are bottom sheets (`drawer_sheets.dart`); `drawer_money_view.dart` only reads the server's
  strings. Tested at 360 dp.

## Follow-ups

- Done: the quick-add line (`roost/tasks/quick_line.py`, `POST /api/tasks/parse` and `parse-many`) reads
  `Buy shoes €30` with no project as a budget in General's currency (`ProjectService.general_currency`) and
  answers `budget_currency`; another sign is refused like a project's ("“General” keeps its money in EUR:
  write the budget in EUR."). Web `taskInputOf` and phone `toTaskIn` send the budget with no project.
- Bots have no tool for a step's budget.
