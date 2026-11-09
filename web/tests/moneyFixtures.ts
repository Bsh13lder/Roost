import { vi } from "vitest";
import type {
  BoardProjectTotalOut, ExpenseLineOut, MoneyRangeOut, MoneySummaryBoardOut, RangeExpenseOut, TrendOut,
} from "../src/api/money";
import type { BudgetLineOut, ExpenseOut } from "../src/api/types";

// The Money tab's wire shapes (Board G8), shared by the Money tests. Every number is a string the
// server added: the web only shows them.

export const noLine: BudgetLineOut = { budget: null, spent: "0.00", remaining: null, used_percent: null, tone: null };

export function line(overrides: Partial<BudgetLineOut> = {}): BudgetLineOut {
  return { budget: "1500.00", spent: "1700.20", remaining: "-200.20", used_percent: 113, tone: "over", ...overrides };
}

export function makeExpense(overrides: Partial<ExpenseOut> = {}): ExpenseOut {
  return {
    id: "e1", project: "Casa Nueva", project_id: "p-casa", task_id: null, step_id: null, amount: "84.20",
    currency: "EUR", description: "Paint", vendor: null, spent_at: "2026-10-20", status: "posted",
    is_favorite: false, created_at: "2026-10-20T09:00:00Z", created_by_bot: null, tainted: false, kind: "expense",
    ...overrides,
  };
}

export const CASA: BoardProjectTotalOut = {
  project: "Casa Nueva", project_id: "p-casa", currency: "EUR", spent: "1700.20", budget: "1500.00",
  remaining: "-200.20", month: line(), other_currencies: {}, color: "#22c55e", pinned: true,
  total: line({ budget: "12000.00", spent: "3200.20", remaining: "8799.80", used_percent: 26, tone: "ok" }),
};
export const LISBON: BoardProjectTotalOut = {
  project: "Trip to Lisbon", project_id: "p-lisbon", currency: "EUR", spent: "320.00", budget: null, remaining: null,
  month: { budget: null, spent: "320.00", remaining: null, used_percent: null, tone: null }, other_currencies: {},
  color: "#3b82f6", pinned: false,
  total: line({ budget: "1800.00", spent: "750.00", remaining: "1050.00", used_percent: 41, tone: "ok" }),
};
export const SIDE: BoardProjectTotalOut = {
  project: "Side business", project_id: "p-side", currency: "USD", spent: "153.00", budget: "400.00",
  remaining: "247.00", month: line({ budget: "400.00", spent: "153.00", remaining: "247.00", used_percent: 38, tone: "ok" }),
  other_currencies: {}, color: "#8b5cf6", pinned: false, total: noLine,
};
export const LOOSE: BoardProjectTotalOut = {
  project: "Groceries", project_id: "p-groc", currency: "EUR", spent: "12.00", budget: null, remaining: null,
  month: { budget: null, spent: "12.00", remaining: null, used_percent: null, tone: null }, other_currencies: {},
  color: "#64748b", pinned: false, total: noLine,
};

export function makeSummary(overrides: Partial<MoneySummaryBoardOut> = {}): MoneySummaryBoardOut {
  return {
    month: "2026-10", currency: "EUR", total: "4238.74", expense_count: 25, other_currencies: { USD: "153.00" },
    by_project: [CASA, LISBON, SIDE, LOOSE],
    today: { day: "2026-10-20", count: 3, totals: { EUR: "84.20", USD: "12.00" } },
    previous: { month: "2026-09", total: "3117.00" }, change_percent: 36,
    limits: { over_count: 1, items: [
      { project_id: "p-casa", project: "Casa Nueva", currency: "EUR", amount: "200.20", over: true, tone: "over" },
      { project_id: "p-side", project: "Side business", currency: "USD", amount: "247.00", over: false, tone: "ok" },
    ] },
    top_project: { project_id: "p-casa", project: "Casa Nueva", color: "#22c55e", currency: "EUR", spent: "1234.00",
      share_percent: 29 },
    coming_up: { days: 31, count: 2, totals: { EUR: "9.99", USD: "12.00" },
      next: { note: "Netflix", day: "2026-11-18", amount: "9.99", currency: "EUR" } },
    pinned_projects: [{
      project_id: "p-casa", project: "Casa Nueva", color: "#22c55e", currency: "EUR", spent_month: "1700.20",
      month: line(), total: CASA.total as BudgetLineOut,
    }],
    pinned_expenses: [
      makeExpense({ id: "s1", description: "Sofa", amount: "450.00", is_favorite: true, spent_at: "2026-10-18" }),
      makeExpense({ id: "s2", description: "Flights", amount: "120.00", is_favorite: true, project: "Trip to Lisbon",
        project_id: "p-lisbon", spent_at: "2026-10-12" }),
    ],
    ...overrides,
  };
}

export function makeExpenseLine(overrides: Partial<ExpenseLineOut> = {}): ExpenseLineOut {
  return {
    note: "", amount: null, currency: "EUR", income: false, income_problem: null, amount_words: null,
    amount_math: null, amount_problem: null, project: null, project_words: null, project_question: null,
    spent_at: "2026-10-21", spent_text: "Wed 21 Oct", day_words: null, day_problem: null, vendor: null,
    starred: false, cadence: null, repeat_words: null, repeat_problem: null, text_problem: null, ready: false,
    matches: {}, warnings: [], ...overrides,
  };
}

// "€12 lunch /Trip yesterday vendor:Mercadona *", as the server reads it.
export const FULL_EXPENSE_LINE = makeExpenseLine({
  note: "lunch", amount: "12.00", amount_words: "€12",
  project: { id: "p-trip", name: "Trip", currency: "EUR", color: "#3b82f6", is_general: false },
  project_words: "/Trip", spent_at: "2026-10-20", spent_text: "Tue 20 Oct", day_words: "yesterday",
  vendor: "Mercadona", starred: true, ready: true,
  matches: { amount: ["€12"], project: ["/Trip"], date: ["yesterday"], vendor: ["vendor:Mercadona"], star: ["*"] },
});

// ---- The range route (G9) ----


export function makeRangeExpense(overrides: Partial<RangeExpenseOut> = {}): RangeExpenseOut {
  return { ...makeExpense(), project_color: "#22c55e", repeat: null, ...overrides };
}

// Three days (the 20th is "today" in the tests), with the server's totals and bars.
export function makeRange(overrides: Partial<MoneyRangeOut> = {}): MoneyRangeOut {
  return {
    from: "2026-10-01", to: "2026-10-20", currency: "EUR", general_project_id: "p-gen",
    expenses: [
      makeRangeExpense({ id: "e1", description: "Paint", amount: "84.20", spent_at: "2026-10-20" }),
      makeRangeExpense({ id: "e2", description: "Taxi", amount: "12.00", currency: "USD", project: "Trip to Lisbon",
        project_id: "p-lisbon", project_color: "#3b82f6", spent_at: "2026-10-20", vendor: "Cabify" }),
      makeRangeExpense({ id: "e3", description: "Netflix", amount: "9.99", spent_at: "2026-10-19", repeat: "monthly",
        project: "Home", project_id: "p-home" }),
      makeRangeExpense({ id: "e4", description: "Old lamp", amount: "30.00", spent_at: "2026-10-18", status: "void" }),
    ],
    days: [
      { day: "2026-10-20", count: 2, totals: { EUR: "84.20", USD: "12.00" }, bar_percent: 100 },
      { day: "2026-10-19", count: 1, totals: { EUR: "9.99" }, bar_percent: 12 },
      { day: "2026-10-18", count: 0, totals: {}, bar_percent: 0 },
    ],
    summary: { count: 3, totals: { EUR: "94.19", USD: "12.00" } },
    ...overrides,
  };
}

// The row's writes, all spies (G9).
export function makeActions() {
  return {
    keep: vi.fn(), star: vi.fn(), setVoid: vi.fn(), remove: vi.fn(), edit: vi.fn().mockResolvedValue(undefined),
  };
}

// ---- Reports and the General inbox (Task 15) ----


// Six months, two currencies: May to Oct.
export function makeTrend(overrides: Partial<TrendOut> = {}): TrendOut {
  const eur = ["1820.00", "2410.00", "1960.00", "2730.00", "3105.00", "4238.74"];
  const usd = ["80.00", "95.00", "120.00", "110.00", "140.00", "153.00"];
  const names = ["2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"];
  return { months: names.map((month, i) => ({ month, totals: { EUR: eur[i], USD: usd[i] } })), ...overrides };
}
