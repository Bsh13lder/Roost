// web/src/components/board/taskScope.ts: which tasks the Tasks area shows (lead task 15): All of them, the Inbox
// (the tasks with no project; a task has no parent, its steps are not tasks) or one project's. It lives in the
// address (?project=<id>|inbox; none is All) and this browser remembers the last one, for a visit whose address
// names none.

export type TaskScope = { kind: "all" } | { kind: "inbox" } | { kind: "project"; id: string };

export const ALL_TASKS: TaskScope = { kind: "all" };
export const TASK_SCOPE_PARAM = "project";
export const TASK_SCOPE_STORAGE_KEY = "roost.tasks-scope.v1";
const ALL_WORD = "all"; // ?project=all: All, said out loud (the old Projects tab's address goes there)
const INBOX_WORD = "inbox";

/** The address's ?project= value as a selection: none, empty or "all" is All. */
export function parseScope(value: string | null): TaskScope {
  if (!value || value === ALL_WORD) return ALL_TASKS;
  if (value === INBOX_WORD) return { kind: "inbox" };
  return { kind: "project", id: value };
}

/** The ?project= value for a selection; All has none. */
export function scopeParam(scope: TaskScope): string | null {
  if (scope.kind === "inbox") return INBOX_WORD;
  return scope.kind === "project" ? scope.id : null;
}

/** Whether a task belongs in the selection (the server narrows the lists; this tells where a new task went). */
export function inScope(task: { project_id: string | null }, scope: TaskScope): boolean {
  if (scope.kind === "inbox") return task.project_id === null;
  return scope.kind === "all" || task.project_id === scope.id;
}

/** The project a new task in the selection goes to, if any (the Inbox's have none). */
export function scopeProjectId(scope: TaskScope): string | undefined {
  return scope.kind === "project" ? scope.id : undefined;
}

export const NO_PROJECT = "none"; // project_id=none: the server's filter for the tasks with no project

/** The project_id a request is narrowed with: the project's id, "none" for the Inbox, nothing for All. */
export function scopeQuery(scope: TaskScope): string | undefined {
  return scope.kind === "inbox" ? NO_PROJECT : scopeProjectId(scope);
}

export const isAllWord = (value: string | null): boolean => value === ALL_WORD;

/** The selection this browser remembers (a ?project= value), or null for All. */
export function readScope(): string | null {
  try {
    return window.localStorage.getItem(TASK_SCOPE_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function rememberScope(scope: TaskScope): void {
  const value = scopeParam(scope);
  try {
    if (value === null) window.localStorage.removeItem(TASK_SCOPE_STORAGE_KEY);
    else window.localStorage.setItem(TASK_SCOPE_STORAGE_KEY, value);
  } catch (error) {
    console.warn("Could not remember the Tasks selection.", error);
  }
}
