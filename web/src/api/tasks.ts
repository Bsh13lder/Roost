import { apiRequest, apiSendOnLeave } from "./client";
import type { QuickKind, QuickLineOut, StepRemovalOut, TaskDetailOut, TaskOut } from "./types";

// The user's tasks (M1 D2/D8): the same records every tasks-role bot works on.

export interface TaskIn {
  title: string;
  due_date?: string | null; // words ("tomorrow at 9") or ISO; the gateway reads it on the account's time
  category?: string | null;
  priority?: TaskOut["priority"];
  project_id?: string; // the project it belongs to (a project page's Tasks tab)
  allocated_budget?: string; // its budget slice ("200.00"), in that project's currency (H11)
  reminder_at?: string | null; // words or ISO (a quick line sends the UTC time the server read)
  recurring?: string | null; // a cron on the account's time, or a repeat rule (JSON) the server wrote
  recur_until?: string | null; // the series' last day ("ending <date>")
  starred?: boolean;
  estimate_minutes?: number | null;
  tags?: string[]; // #tags
  steps?: string[]; // checklist titles (a pasted list's indented lines)
  assign_bot_id?: string; // hand the task to this bot...
  assign_confirmed?: boolean; // ...once the user confirmed (the server refuses without it)
}

// allocated_budget is the task's budget slice ("250.00", or null to clear it); a task in no project counts it in General's currency.
// reminder_at takes words or ISO on the account's time (null clears it), pre_reminders goes with it ([]: none);
// recurring is a cron (null: no repeat).
export type TaskPatchIn = Partial<
  Pick<TaskOut, "title" | "description" | "category" | "priority" | "due_date" | "allocated_budget"
    | "project_id" | "reminder_at" | "pre_reminders" | "recurring" | "estimate_minutes">
>;

// The status a drag can set (the server also takes "cancelled"; done and failed go through their own routes).
export interface TaskStatusPatch {
  status?: "todo" | "in_progress";
}

// A step change (redesign P3): a new title, a tick or an untick.
export interface StepPatchIn {
  title?: string;
  done?: boolean;
  budget?: string | null; // the step's own budget in the task's currency, as typed; null clears it
}

// The kinds a removed chip can skip: redesign P3's four, and the rich line's five (Tasks & Money polish).
export type QuickKindRich = QuickKind | "star" | "estimate" | "reminder" | "repeat" | "assignee" | "tag";

// What the rich quick line adds to the server's reading (POST /api/tasks/parse); all keys are always sent.
export type QuickLineRichOut = QuickLineOut & {
  matches?: Record<string, string[]>; // kind -> the words its chip came from (to keep them when it is removed)
  tags: string[]; // #shopping: the task's tags, as typed
  due_text: string | null; // the resolved due in the account's time, "Wed 21 Oct 09:00" (a live preview)
  reminder_text: string | null; // the resolved reminder, the same way
  budget_math: string | null; // "3×45": the sum the budget was worked out from
  budget_currency?: string | null; // the budget's currency: the project's, or General's for a task in no project
  starred: boolean;
  estimate_minutes: number | null;
  reminder_at: string | null; // UTC ISO, against the due
  reminder_words: string | null; // "^30m before", as typed
  recurring: string | null; // an account-zone cron, or a repeat rule (JSON)
  recur_until: string | null; // "ending <date>": the series' last day
  repeat_text: string | null; // "every Monday 09:00"
  repeat_words: string | null; // "every Monday", as typed
  repeat_problem: string | null; // why those words can't be a repeat
  assignee: { id: string; name: string } | null;
  assignee_words: string | null; // "@Scout", as typed
  assignee_question: string | null; // why that @bot can't be used as typed
  warnings: string[]; // never block: "Two priorities: kept !low."
};

// A quick-add line to read (redesign P3). A project page sends its project; `skip` holds removed chips.
export interface QuickLineIn {
  text: string;
  project_id?: string;
  skip?: QuickKindRich[];
  keep?: string[]; // words whose chips were removed: they stay plain title text
  default_due?: string; // "YYYY-MM-DD": a Kanban column's day, used only when the line names none
}

// A pasted list (POST /api/tasks/parse-many): each line read as a quick line, its indented lines as steps.
export interface PastedListOut {
  count: number;
  tasks: Array<QuickLineRichOut & { steps: string[] }>;
  ready: boolean; // false while any line has a problem
  problem: string | null; // the first, with its line number
}

export function parsePastedList(input: { text: string; project_id?: string }): Promise<PastedListOut> {
  return apiRequest<PastedListOut>("POST", "/api/tasks/parse-many", input);
}

const taskPath = (taskId: string) => `/api/tasks/${encodeURIComponent(taskId)}`;
const stepPath = (taskId: string, stepId: string) => `${taskPath(taskId)}/steps/${encodeURIComponent(stepId)}`;

export type TaskListStatus = "open" | "done" | "failed" | "all";
export type TaskView = "today" | "upcoming" | "overdue" | "someday" | "done" | "board";
export type TaskSort = "due" | "priority" | "created" | "created_asc" | "title" | "money_left";

export interface TaskListFilter {
  projectId?: string; // only that project's tasks
  status?: TaskListStatus;
  view?: TaskView; // one Board view (the server picks, searches and sorts)
  q?: string; // search in the title and notes
  sort?: TaskSort;
  from?: string; // YYYY-MM-DD: with `to`, the tasks the calendar shows (G11), at most 62 days
  to?: string;
  includeFinished?: boolean; // Today, Upcoming, Someday: their done tasks too (never failed or cancelled)
  ids?: readonly string[]; // these tasks only, any status, in this order (the chat's task cards)
}

// A list row (G3): the task, plus what the server works out for it. The web adds nothing up.
export type DueBucket = "overdue" | "today" | "tomorrow" | "week" | "later" | "none";

export interface RowMoneyOut {
  planned: string;
  spent: string;
  left: string; // negative when over
  currency: string;
  over: boolean;
}

export type TaskRowOut = TaskOut & {
  money: RowMoneyOut | null; // null: no project, or no budget slice
  due_bucket: DueBucket; // by the account's today
  starred?: boolean;
  estimate_minutes?: number | null;
  repeat_text?: string | null; // "every Monday 09:00"
};

// Two shapes: listTasks("all", { projectId }) as before, or listTasks({ view, q, sort }).
export function listTasks(status: TaskListStatus | TaskListFilter = "open", filter: TaskListFilter = {}): Promise<TaskRowOut[]> {
  const options: TaskListFilter = typeof status === "string" ? { ...filter, status } : status;
  const query = new URLSearchParams();
  if (options.status) query.set("status", options.status);
  if (options.projectId) query.set("project_id", options.projectId);
  if (options.view) query.set("view", options.view);
  if (options.q) query.set("q", options.q);
  if (options.sort) query.set("sort", options.sort);
  if (options.from) query.set("from", options.from);
  if (options.to) query.set("to", options.to);
  if (options.includeFinished) query.set("include_finished", "1");
  if (options.ids) query.set("ids", options.ids.join(","));
  const text = query.toString();
  return apiRequest<TaskRowOut[]>("GET", text ? `/api/tasks?${text}` : "/api/tasks");
}

// What each Board tab counts (GET /api/tasks/counts); the server counts, the web only shows. `open` is the
// todo and in-progress tasks. A project id narrows every count to that project, "none" to the tasks with none.
export interface TaskCountsOut {
  overdue: number;
  today: number;
  upcoming_14: number;
  someday: number;
  done_week: number;
  open: number;
}

export function getTaskCounts(projectId?: string): Promise<TaskCountsOut> {
  const query = projectId ? `?${new URLSearchParams({ project_id: projectId })}` : "";
  return apiRequest<TaskCountsOut>("GET", `/api/tasks/counts${query}`);
}

// A task's schedule: what move-overdue answers (the values before) and restore-dues writes back.
export interface MovedDue {
  id: string;
  due_date: string | null;
  reminder_at: string | null;
  pre_reminders: string[];
}

export interface MoveOverdueOut {
  moved: MovedDue[];
}

// `to` is words, an ISO day, an account-local ISO moment, or null for no date. A task that had a time keeps it
// when `to` is a day.
export function moveOverdue(to: string | null): Promise<MoveOverdueOut> {
  return apiRequest<MoveOverdueOut>("POST", "/api/tasks/move-overdue", { to });
}

export function restoreDues(items: readonly MovedDue[]): Promise<{ restored: number }> {
  return apiRequest<{ restored: number }>("POST", "/api/tasks/restore-dues", { items });
}

// Open a done task again (the Undo of a complete).
export function reopenTask(taskId: string): Promise<TaskOut> {
  return apiRequest<TaskOut>("POST", `${taskPath(taskId)}/reopen`);
}

export function createTask(input: TaskIn): Promise<TaskOut> {
  return apiRequest<TaskOut>("POST", "/api/tasks", input);
}

export function updateTask(taskId: string, patch: TaskPatchIn & TaskStatusPatch): Promise<TaskOut> {
  return apiRequest<TaskOut>("PATCH", `/api/tasks/${encodeURIComponent(taskId)}`, patch);
}

// The same PATCH, sent as the page goes away (pagehide): it outlives the page, and nobody reads the answer.
export function updateTaskOnLeave(taskId: string, patch: TaskPatchIn): void {
  apiSendOnLeave("PATCH", `/api/tasks/${encodeURIComponent(taskId)}`, patch);
}

// A repeating task answers `next_id`, the copy it made for its next time (the Undo of a complete removes it).
export function completeTask(taskId: string): Promise<TaskOut & { next_id?: string | null }> {
  return apiRequest<TaskOut & { next_id?: string | null }>("POST", `/api/tasks/${encodeURIComponent(taskId)}/complete`);
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

// Delete is soft: this brings the same task back (its id, steps and comments), Delete's exact Undo.
export function restoreTask(taskId: string): Promise<TaskOut> {
  return apiRequest<TaskOut>("POST", `${taskPath(taskId)}/restore`);
}

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
export function parseQuickLine(input: QuickLineIn): Promise<QuickLineRichOut> {
  return apiRequest<QuickLineRichOut>("POST", "/api/tasks/parse", input);
}
