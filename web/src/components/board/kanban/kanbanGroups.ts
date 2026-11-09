import type { DueBucket, TaskPatchIn, TaskRowOut, TaskSort, TaskStatusPatch } from "../../../api/tasks";
import { addDays, todayIn, type IsoDay } from "../../../ui/date/dates";

// The Kanban's classification (Board redesign G6, §7.2 and §7.8). It only sorts server-given fields into
// columns (status, due_bucket, project_id, priority, created_by_bot, category): it never adds anything up.

export type KanbanGroup = "status" | "due" | "project" | "priority" | "bot" | "list";

export const KANBAN_GROUPS: ReadonlyArray<{ value: KanbanGroup; label: string }> = [
  { value: "status", label: "Status" }, { value: "due", label: "Due date" }, { value: "project", label: "Project" },
  { value: "priority", label: "Priority" }, { value: "bot", label: "Bot" }, { value: "list", label: "List" },
];

export const KANBAN_SORTS: ReadonlyArray<{ value: TaskSort; label: string }> = [
  { value: "due", label: "Due date" }, { value: "priority", label: "Priority" }, { value: "created", label: "Newest" },
  { value: "created_asc", label: "Oldest" }, { value: "title", label: "Title A–Z" }, { value: "money_left", label: "Money left" },
];

export const NO_PROJECT_KEY = "none";
export const YOU_KEY = "you";
export const NO_LIST_KEY = "none";

export interface KanbanColumn {
  key: string;
  label: string;
  dropTarget: boolean; // false: Overdue and every Bot column
  canAdd: boolean; // false: Done, Overdue
  color?: string; // a project's colour
  botId?: string; // a bot's column
}

export interface KanbanContext {
  tasks: readonly TaskRowOut[];
  projects: ReadonlyArray<{ id: string; name: string; color: string }>;
  bots: Readonly<Record<string, { name: string }>>;
}

export type KanbanMove =
  | { kind: "patch"; patch: TaskPatchIn & TaskStatusPatch }
  | { kind: "day"; day: IsoDay | null } // Today, Tomorrow, No date: applied at once, keeping the time
  | { kind: "complete" }
  | { kind: "reopen"; then?: TaskStatusPatch }
  | { kind: "pick-day" } // This week, Later: the date picker opens
  | { kind: "none" };

const column = (key: string, label: string, extra: Partial<KanbanColumn> = {}): KanbanColumn =>
  ({ key, label, dropTarget: true, canAdd: true, ...extra });

const STATUS_COLUMNS: readonly KanbanColumn[] = [
  column("todo", "To do"), column("in_progress", "On it"), column("done", "Done", { canAdd: false }),
];
const DUE_COLUMNS: readonly KanbanColumn[] = [
  column("overdue", "Overdue", { dropTarget: false, canAdd: false }), column("today", "Today"),
  column("tomorrow", "Tomorrow"), column("week", "This week"), column("later", "Later"), column("none", "No date"),
];
const PRIORITY_COLUMNS: readonly KanbanColumn[] = [
  column("urgent", "Urgent"), column("high", "High"), column("medium", "Medium"), column("low", "Low"),
];

const byName = (a: string, b: string) => a.localeCompare(b, undefined, { sensitivity: "base" });

function projectColumns({ tasks, projects }: KanbanContext): KanbanColumn[] {
  const used = new Set(tasks.map((task) => task.project_id));
  const found = projects.filter((project) => used.has(project.id))
    .map((project) => column(project.id, project.name, { color: project.color }));
  return [...found, column(NO_PROJECT_KEY, "No project")];
}

function botColumns({ tasks, bots }: KanbanContext): KanbanColumn[] {
  const made = [...new Set(tasks.map((task) => task.created_by_bot).filter((id): id is string => id !== null && id in bots))];
  const named = made.map((id) => ({ id, name: bots[id].name })).sort((a, b) => byName(a.name, b.name));
  return [column(YOU_KEY, "You", { dropTarget: false, botId: undefined }),
    ...named.map((bot) => column(bot.id, bot.name, { dropTarget: false, botId: bot.id }))];
}

function listColumns({ tasks }: KanbanContext): KanbanColumn[] {
  const lists = [...new Set(tasks.map((task) => task.category).filter((name): name is string => !!name))].sort(byName);
  return [...lists.map((name) => column(name, name)), column(NO_LIST_KEY, "No list")];
}

export function columnsFor(group: KanbanGroup, ctx: KanbanContext): readonly KanbanColumn[] {
  switch (group) {
    case "status": return STATUS_COLUMNS;
    case "due": return DUE_COLUMNS;
    case "priority": return PRIORITY_COLUMNS;
    case "project": return projectColumns(ctx);
    case "bot": return botColumns(ctx);
    default: return listColumns(ctx);
  }
}

export function columnOf(task: TaskRowOut, group: KanbanGroup): string {
  switch (group) {
    case "status": return task.status === "done" ? "done" : task.status === "in_progress" ? "in_progress" : "todo";
    case "due": return task.due_bucket satisfies DueBucket;
    case "priority": return task.priority;
    case "project": return task.project_id ?? NO_PROJECT_KEY;
    case "bot": return task.created_by_bot ?? YOU_KEY;
    default: return task.category || NO_LIST_KEY;
  }
}

// A finished task whose day has passed would only crowd Overdue: under Due date it is left out.
export function visibleTasks(tasks: readonly TaskRowOut[], group: KanbanGroup): readonly TaskRowOut[] {
  return group === "due" ? tasks.filter((task) => !(task.status === "done" && task.due_bucket === "overdue")) : tasks;
}

function statusMove(key: string, from?: TaskRowOut): KanbanMove {
  if (key === "done") return { kind: "complete" };
  const status = key === "in_progress" ? "in_progress" : "todo";
  if (from?.status === "done") return status === "todo" ? { kind: "reopen" } : { kind: "reopen", then: { status } };
  return { kind: "patch", patch: { status } };
}

function dueMove(key: string, today: IsoDay): KanbanMove {
  switch (key) {
    case "today": return { kind: "day", day: today };
    case "tomorrow": return { kind: "day", day: addDays(today, 1) };
    case "none": return { kind: "day", day: null };
    case "week": case "later": return { kind: "pick-day" };
    default: return { kind: "none" }; // Overdue is where late tasks are, never where one is sent
  }
}

// What dropping a card on column `key` does to the grouped field. `from` is the card (a done card is reopened
// before it can be On it); `today` is the account's.
export function moveFor(group: KanbanGroup, key: string, from?: TaskRowOut, today: IsoDay = todayIn()): KanbanMove {
  switch (group) {
    case "status": return statusMove(key, from);
    case "due": return dueMove(key, today);
    case "project": return { kind: "patch", patch: { project_id: key === NO_PROJECT_KEY ? null : key } };
    case "priority": return { kind: "patch", patch: { priority: key as TaskRowOut["priority"] } };
    case "list": return { kind: "patch", patch: { category: key === NO_LIST_KEY ? null : key } };
    default: return { kind: "none" }; // who made a task is its history
  }
}

// The first day a column's "+" gives a new task; This week and Later leave it for the user to type.
export function defaultDueFor(group: KanbanGroup, key: string, today: IsoDay = todayIn()): IsoDay | undefined {
  if (group !== "due") return undefined;
  return key === "today" ? today : key === "tomorrow" ? addDays(today, 1) : undefined;
}
