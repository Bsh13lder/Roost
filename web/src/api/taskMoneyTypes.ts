// Wire types for the user's tasks, money and projects (M1, the projects hub, redesign P3), split from types.ts
// to keep each file within 800 lines. types.ts re-exports every one, so consumers import from "./types" as before.
import type { DocumentOut, NoteSummaryOut } from "./types";

export interface TaskStepOut {
  id: string;
  title: string;
  done: boolean;
}

// The user's task (M1 D2): shared by every bot holding the tasks role.
export interface TaskOut {
  id: string;
  title: string;
  description: string | null;
  category: string | null;
  priority: "low" | "medium" | "high" | "urgent";
  status: "todo" | "in_progress" | "done" | "cancelled" | "failed";
  owner: string;
  due_date: string | null; // "YYYY-MM-DD" or an account-local ISO datetime
  reminder_at: string | null; // UTC ISO
  pre_reminders: string[];
  recurring: string | null;
  recur_until: string | null;
  tags: string[];
  steps: TaskStepOut[];
  created_at: string;
  updated_at: string;
  completed_at: string | null; // when it was done, or failed
  created_by_bot: string | null;
  tainted: boolean; // written by a run that had read web content
  project_id: string | null; // the project it belongs to (projects hub P1)
  allocated_budget: string | null; // its budget slice, "250.00", in the project's currency (H11)
  imported_from?: "lazyclaw" | null; // a row the LazyClaw import made
  estimate_minutes?: number | null;
  repeat_text?: string | null; // "every Monday 09:00"
}

// The user's expense (M1 D3): shared by every bot holding the finance role.
export interface ExpenseOut {
  id: string;
  project: string; // the project's name ("General" for a loose expense)
  project_id: string;
  task_id: string | null; // the task it was spent on, if any (H11)
  step_id: string | null; // one step of that task, if any
  amount: string; // "12.50" — a decimal string, never a float
  currency: string;
  description: string | null;
  vendor: string | null;
  spent_at: string; // YYYY-MM-DD (the account's day)
  status: "posted" | "void"; // a void expense stays in the list and leaves every total (H6)
  is_favorite: boolean; // starred
  created_at: string;
  created_by_bot: string | null;
  tainted: boolean; // written by a run that had read web content
  imported_from?: "lazyclaw" | null; // a row the LazyClaw import made
  kind?: "expense" | "income"; // income is money in: shown apart, never counted as spent
}

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
  money_in?: Record<string, string>; // that month's income per currency, apart from `spent`
}

// One month on the account's calendar: the euro total, and other currencies kept apart.
export interface MoneySummaryOut {
  month: string; // "YYYY-MM"
  currency: string;
  total: string;
  expense_count: number;
  by_project: ProjectTotalOut[];
  other_currencies: Record<string, string>;
  money_in?: Record<string, string>; // the month's income per currency, never in `total`
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
// A project's progress, the same on the projects list and the project page (lead task 20). The server counts.
export interface ProjectProgressOut {
  done: number;
  failed: number;
  total: number;
  open: number; // todo and in progress (the Tasks rail and the picked project's card)
  overdue: number; // open tasks due before today (the account's)
  steps_done: number;
  steps_total: number;
  planned_total: string; // the open tasks' budget slices, in the project's currency
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
  month: BudgetLineOut; // the monthly limit, against this month on the account's calendar
  other_currencies: Record<string, string>; // spent in other currencies, never converted (P4)
  starred_total: string;
  money_in?: Record<string, string>; // income per currency, all time; never counted as spent
  progress: ProjectProgressOut;
  tainted: boolean;
  pinned?: boolean; // pinned to the Board (G7): the Tasks rail lists it first
  pinned_at?: string | null;
}

// A task's money on its project's page (design §2): its slice, what is spent on it, and what is
// left (negative when over). The server reckons all three.
export interface TaskMoneyOut {
  planned: string | null;
  spent: string;
  left: string | null;
}

// A task's money in its drawer (redesign P3, GET /api/tasks/{id}): the TaskMoneyOut numbers in its
// project's currency, and what is spent on each step, by step id. The server reckons every number.
// One step's own budget (owner, 2026-10-26): planned, spent and left as the server reckons them, with its bar.
export interface StepMoneyOut {
  planned: string | null;
  spent: string;
  left: string | null; // negative when over
  used_percent: number | null;
  tone: BudgetTone | null;
}

export interface TaskDetailMoneyOut extends TaskMoneyOut {
  currency: string; // the task's project's, or General's for a task in no project
  steps: Record<string, string>;
  steps_money?: Record<string, StepMoneyOut>; // by step id, in the steps' order
  other_currencies: Record<string, string>; // posted spending in other currencies, never added in
  steps_other_currencies: Record<string, Record<string, string>>; // the same by step id, only steps that have any
  used_percent: number | null; // the slice used, by the one rule every budget bar follows; null without a slice
  tone: BudgetTone | null;
}

// One task as its drawer shows it: a task in no project counts its money in General's currency; expenses are every
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
  budget: string | null; // the slice, "200.00", in the project's currency (General's with no project)
  budget_words: string | null; // "€200", as typed
  budget_problem: string | null; // why that amount can't be the slice
  ready: boolean;
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
  // Change and Undo still work on it: a top-up that is not undone and that clearing the total budget has
  // not taken back (H5). An edit row never can.
  can_change: boolean;
}
