import { apiRequest } from "./client";
import type { BudgetLineOut, BudgetTone, ExpenseOut, MoneySummaryOut, ProjectTotalOut } from "./types";

// The user's money (M1 D3/D8): the same records every finance-role bot works on.

export interface ExpenseIn {
  amount: string; // already read by parseAmountInput: "12.50"
  currency?: string; // the money sign's: none means the project's own
  vendor?: string;
  starred?: boolean;
  income?: boolean; // money in: kept apart, never counted as spent
  cadence?: "weekly" | "monthly" | "yearly"; // also makes a repeating rule
  project?: string; // a project's name; a new name makes a new project, none means General
  // A project's page names its project by id instead (never both): the expense then lands in exactly
  // that project, in its currency (H7). A name is found or made, so a near name could land elsewhere.
  project_id?: string;
  note?: string;
  spent_at?: string; // "YYYY-MM-DD", a day on the account's calendar; none is today (the gateway refuses a future day)
  task_id?: string; // a task's drawer (redesign P3): filed under the task; no project named → the task's
  step_id?: string; // …or under one of its steps
}

// The Money tab's rows and fields (Board redesign G8). Amounts are strings the server added; the web only shows them.
export interface BoardProjectTotalOut extends ProjectTotalOut {
  total: BudgetLineOut | null; // the total budget against all-time spending
  color: string;
  pinned: boolean;
}

export interface LimitItemOut {
  project_id: string;
  project: string;
  currency: string;
  amount: string; // the overage or what is left: never signed
  over: boolean;
  tone: BudgetTone;
}

export interface PinnedProjectOut {
  project_id: string;
  project: string;
  color: string;
  currency: string;
  spent_month: string;
  month: BudgetLineOut;
  total: BudgetLineOut;
}

export interface MoneySummaryBoardOut extends Omit<MoneySummaryOut, "by_project"> {
  by_project: BoardProjectTotalOut[];
  today: { day: string; count: number; totals: Record<string, string> };
  previous: { month: string; total: string } | null;
  change_percent: number | null; // this month against the previous one, main currency only
  limits: { over_count: number; items: LimitItemOut[] };
  top_project: {
    project_id: string; project: string; color: string; currency: string; spent: string; share_percent: number;
  } | null;
  coming_up: {
    days: number; count: number; totals: Record<string, string>;
    next: { note: string | null; day: string; amount: string; currency: string } | null;
  };
  pinned_projects: PinnedProjectOut[];
  pinned_expenses: ExpenseOut[];
}

export function getSummary(month: string): Promise<MoneySummaryBoardOut> {
  return apiRequest<MoneySummaryBoardOut>("GET", `/api/money/summary?month=${encodeURIComponent(month)}`);
}

// The month's CSV (Task 14): a plain download link, months written YYYY-MM.
export function exportCsvUrl(month: string): string {
  const query = `from=${encodeURIComponent(month)}&to=${encodeURIComponent(month)}`;
  return `/api/money/export.csv?${query}`;
}

export function listExpenses(month: string): Promise<ExpenseOut[]> {
  return apiRequest<ExpenseOut[]>("GET", `/api/money/expenses?month=${encodeURIComponent(month)}`);
}

// How the server reads an expense quick line (POST /api/money/parse, Task 6): the chips come from this, and
// what is added is exactly this reading. Amounts are strings; the web works out nothing.
export type ExpenseKind = "amount" | "project" | "date" | "star" | "vendor" | "repeat";

export interface ExpenseLineOut {
  note: string;
  amount: string | null;
  currency: string;
  income: boolean;
  income_problem: string | null;
  amount_words: string | null;
  amount_math: string | null; // "2×31" when the amount was worked out
  amount_problem: string | null;
  project: { id: string; name: string; currency: string; color: string; is_general: boolean } | null;
  project_words: string | null;
  project_question: string | null; // why the /project can't be used as typed
  spent_at: string; // YYYY-MM-DD
  spent_text: string; // "Wed 21 Oct"
  day_words: string | null;
  day_problem: string | null;
  vendor: string | null;
  starred: boolean;
  cadence: "weekly" | "monthly" | "yearly" | null;
  repeat_words: string | null;
  repeat_problem: string | null;
  text_problem: string | null;
  ready: boolean;
  matches: Record<string, string[]>;
  warnings: string[];
}

export interface ExpenseLineIn {
  text: string;
  project_id?: string; // a project's page
  skip?: ExpenseKind[]; // kinds the user dismissed: their words stay in the note
  default_day?: string; // YYYY-MM-DD: the day of a line that names none (the money calendar's +)
}

export function parseExpenseLine(input: ExpenseLineIn): Promise<ExpenseLineOut> {
  return apiRequest<ExpenseLineOut>("POST", "/api/money/parse", input);
}

export function createExpense(input: ExpenseIn): Promise<ExpenseOut> {
  return apiRequest<ExpenseOut>("POST", "/api/money/expenses", input);
}

// Keep: the user vouches for an expense marked "from web content", and for the
// project name its row shows (only here — no bot can).
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

// A row of the range route (Board redesign G9): the expense, its project's colour for the dot, and the
// cadence of the repeating rule that made it.
export type Repeat = "weekly" | "monthly" | "yearly";
export type RangeExpenseOut = ExpenseOut & { repeat?: Repeat | null; project_color?: string | null };

export interface DayTotalOut {
  day: string; // YYYY-MM-DD, a day on the account's calendar
  count: number;
  totals: Record<string, string>; // per currency, the server's
  bar_percent: number; // the main currency's total against the biggest day's
}

export interface MoneyRangeOut {
  from: string;
  to: string;
  currency: string; // the main currency
  general_project_id: string | null;
  expenses: RangeExpenseOut[];
  days: DayTotalOut[]; // only days with expenses, newest first
  summary: { count: number; totals: Record<string, string> };
}

// The expenses of a span of days on the account's calendar, with the server's totals per day and for the span. A future last day
// is clamped to today; a project's page narrows it with `projectId`.
export function getRange(from: string, to: string, projectId?: string): Promise<MoneyRangeOut> {
  const project = projectId ? `&project_id=${encodeURIComponent(projectId)}` : "";
  return apiRequest<MoneyRangeOut>("GET", `/api/money/range?from=${from}&to=${to}${project}`);
}

// Only what changes. A note or vendor sent blank is cleared; the day may be words ("yesterday").
export interface ExpensePatchIn {
  amount?: string;
  note?: string;
  vendor?: string;
  spent_at?: string;
  project_id?: string;
}

const expensePath = (expenseId: string) => `/api/money/expenses/${encodeURIComponent(expenseId)}`;

export function updateExpense(expenseId: string, patch: ExpensePatchIn): Promise<RangeExpenseOut> {
  return apiRequest<RangeExpenseOut>("PATCH", expensePath(expenseId), patch);
}

export function deleteExpense(expenseId: string): Promise<void> {
  return apiRequest<void>("DELETE", expensePath(expenseId));
}

// Undo a delete. A 422 says its project is gone: move it into another one first.
export function restoreExpense(expenseId: string): Promise<RangeExpenseOut> {
  return apiRequest<RangeExpenseOut>("POST", `${expensePath(expenseId)}/restore`);
}

// File up to 100 expenses under one open project, all or none; each answer names where it came from.
export function moveExpenses(expenseIds: readonly string[], projectId: string):
  Promise<{ moved: Array<{ id: string; from_project_id: string }> }> {
  return apiRequest("POST", "/api/money/expenses/move", { expense_ids: expenseIds, project_id: projectId });
}

// Each of the last months' spending, per currency (never mixed), ending this month (Task 14).
export interface TrendMonthOut {
  month: string; // YYYY-MM
  totals: Record<string, string>;
}

export interface TrendOut {
  months: TrendMonthOut[];
}

export function getTrend(months = 6, projectId?: string): Promise<TrendOut> {
  const project = projectId ? `&project_id=${encodeURIComponent(projectId)}` : "";
  return apiRequest<TrendOut>("GET", `/api/money/trend?months=${months}${project}`);
}

// The expenses sitting in General, newest first, a page at a time; `next` is the cursor for the page after.
export interface GeneralInboxOut {
  expenses: RangeExpenseOut[];
  next: string | null;
}

export function getGeneralInbox(before?: string): Promise<GeneralInboxOut> {
  return apiRequest<GeneralInboxOut>("GET", `/api/money/general${before ? `?before=${encodeURIComponent(before)}` : ""}`);
}

// Repeating charges (Task 12): a rule makes one expense on each of its days. The server reckons every day.
export interface RecurringOut {
  id: string;
  project_id: string;
  project: string;
  amount: string;
  currency: string;
  note: string | null;
  vendor: string | null;
  cadence: Repeat;
  anchor_day: string; // YYYY-MM-DD: carries the weekday, the day of the month, or month and day
  next_due: string;
  ends_on: string | null;
  paused: boolean; // its project is archived
  created_at: string;
  tainted: boolean;
}

export interface UpcomingChargeOut {
  recurring_id: string;
  project_id: string;
  day: string;
  amount: string;
  currency: string;
  note: string | null;
}

export interface RecurringPatchIn {
  amount?: string;
  note?: string | null;
  vendor?: string | null;
  ends_on?: string | null;
}

export function listRecurring(projectId?: string): Promise<RecurringOut[]> {
  return apiRequest<RecurringOut[]>("GET", `/api/money/recurring${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ""}`);
}

export function updateRecurring(ruleId: string, patch: RecurringPatchIn): Promise<RecurringOut> {
  return apiRequest<RecurringOut>("PATCH", `/api/money/recurring/${encodeURIComponent(ruleId)}`, patch);
}

// Stop: no more charges; the ones already made stay.
export function stopRecurring(ruleId: string): Promise<void> {
  return apiRequest<void>("DELETE", `/api/money/recurring/${encodeURIComponent(ruleId)}`);
}
