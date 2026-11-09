import type { TaskRowOut } from "../src/api/tasks";
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

// A list row (G3): a task with the money and due bucket the server works out for it.
export function makeRow(overrides: Partial<TaskRowOut> = {}): TaskRowOut {
  return { ...makeTask(), money: null, due_bucket: "later", ...overrides } as TaskRowOut;
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
