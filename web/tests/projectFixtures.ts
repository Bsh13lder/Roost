import type { RecurringOut, UpcomingChargeOut } from "../src/api/money";
import type { ProjectDetailBoardOut } from "../src/api/projects";
import type { BudgetLineOut, ExpenseOut, ProjectOut, TopupOut } from "../src/api/types";

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
    other_currencies: {}, starred_total: "0.00", progress: { done: 3, failed: 1, total: 5, open: 1, overdue: 0, steps_done: 0, steps_total: 0, planned_total: "0.00" }, tainted: false,
    ...overrides,
  };
}

export function makeRecurring(overrides: Partial<RecurringOut> = {}): RecurringOut {
  return {
    id: "r1", project_id: "p1", project: "Garden", amount: "42.00", currency: "EUR", note: "Home insurance", vendor: null,
    cadence: "monthly", anchor_day: "2026-09-05", next_due: "2026-11-05", ends_on: null, paused: false,
    created_at: "2026-09-05T09:00:00Z", tainted: false, ...overrides,
  };
}

export function makeCharge(overrides: Partial<UpcomingChargeOut> = {}): UpcomingChargeOut {
  return { recurring_id: "r1", project_id: "p1", day: "2026-11-05", amount: "42.00", currency: "EUR", note: "Home insurance", ...overrides };
}

export function makeTopup(overrides: Partial<TopupOut> = {}): TopupOut {
  return {
    id: "tu1", amount: "200.00", currency: "EUR", source: "birthday", kind: "credit", topup_id: null, undone: false,
    created_at: "2026-10-10T09:00:00Z", can_change: true, ...overrides,
  };
}

export function makeProjectDetail(overrides: Partial<ProjectDetailBoardOut> = {}): ProjectDetailBoardOut {
  const base = makeProject();
  return {
    ...base, progress: { ...base.progress, overdue: 2, steps_done: 5, steps_total: 8, planned_total: "3850.00" },
    tasks: [], expenses: [], notes: [], documents: [], topups: [makeTopup()], lead_bot_name: "Helper",
    task_money: {}, counts: { tasks_open: 2, expenses: 7, notes: 3, documents: 1 }, repeating: [makeRecurring()],
    upcoming_charges: [makeCharge()], ...overrides,
  };
}

export function makeExpense(overrides: Partial<ExpenseOut> = {}): ExpenseOut {
  return {
    id: "e1", project: "food", project_id: "p-food", task_id: null, step_id: null, amount: "12.50", currency: "EUR",
    description: "lunch", vendor: null, spent_at: "2026-10-13", status: "posted", is_favorite: false,
    created_at: "x", created_by_bot: null, tainted: false, ...overrides,
  };
}
