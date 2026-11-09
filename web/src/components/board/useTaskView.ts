import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { INBOX_VIEW, TASK_VIEW_KEYS, type BoardView } from "./constants";
import { KANBAN_GROUPS, KANBAN_SORTS, type KanbanGroup } from "./kanban/kanbanGroups";
import { describeError } from "../../api/client";
import { listTasks, type TaskRowOut, type TaskSort, type TaskView } from "../../api/tasks";
import type { TaskStepOut } from "../../api/types";
import { useLiveState } from "../../hooks/useLiveStore";
import { useShowFinished } from "../../hooks/useShowFinished";
import { ALL_TASKS, parseScope, scopeParam, type TaskScope } from "./taskScope";
import { askTasks } from "./scopedTasks";
import { isFinished } from "../../lib/finished";

const DEFAULT_VIEW: BoardView = "today";
const DEFAULT_SORT: TaskSort = "due";
const DEFAULT_GROUP: KanbanGroup = "status";
export type TaskLayout = "list" | "kanban" | "calendar";
const isGroup = (value: string | null): value is KanbanGroup => KANBAN_GROUPS.some((group) => group.value === value);
const isKanbanSort = (value: string | null): value is TaskSort => KANBAN_SORTS.some((sort) => sort.value === value);
const isView = (value: string | null): value is BoardView =>
  value === INBOX_VIEW || (TASK_VIEW_KEYS as readonly string[]).includes(value ?? "");

export interface TaskViewState {
  view: BoardView; // the server's view, or the Inbox
  q: string;
  sort: TaskSort;
  setView: (view: BoardView) => void;
  setQ: (q: string) => void;
  setSort: (sort: TaskSort) => void;
  layout: TaskLayout; // ?layout=kanban or calendar; the list is the default
  setLayout: (layout: TaskLayout) => void;
  group: KanbanGroup; // ?group= (Kanban)
  setGroup: (group: KanbanGroup) => void;
  ksort: TaskSort; // ?ksort= (how Kanban cards are sorted)
  setKsort: (sort: TaskSort) => void;
  split: boolean; // ?split=1 (Kanban: one row per project)
  setSplit: (split: boolean) => void;
  tasks: readonly TaskRowOut[] | null; // null until the first answer
  error: string | null;
  setError: (message: string | null) => void;
  load: () => void;
  setSteps: (taskId: string, steps: readonly TaskStepOut[]) => void;
  stepsOpen: ReadonlySet<string>;
  toggleSteps: (taskId: string) => void;
  expandAll: (taskIds: readonly string[]) => void;
  collapseAll: () => void;
}

const INBOX_SCOPE: TaskScope = { kind: "inbox" }; // the Inbox view: every open task with no project, any chip
const WITH_FINISHED: ReadonlySet<BoardView> = new Set(["today", "upcoming", "someday"]);

// The open rows first, then the finished ones, each in the server's order.
const openFirst = (rows: readonly TaskRowOut[]) => [...rows.filter((row) => !isFinished(row)), ...rows.filter(isFinished)];

// Today is what is late and what is due today, so it asks for both and puts the late ones first. With Show finished,
// a view that holds days asks the server for its done tasks too (include_finished; failed and cancelled ones never
// come), shown after the open ones. Overdue never holds a finished task.
// `scope` (the Tasks rail) narrows every request: see scopedTasks.ts.
function fetchView(view: BoardView, q: string, sort: TaskSort, finished: boolean, scope: TaskScope): Promise<TaskRowOut[]> {
  if (view === INBOX_VIEW) return askTasks(INBOX_SCOPE, { status: "open", sort, ...(q ? { q } : {}) });
  const withDone = finished && WITH_FINISHED.has(view);
  const ask = (which: TaskView, done = false) =>
    askTasks(scope, { view: which, sort, ...(q ? { q } : {}), ...(done ? { includeFinished: true } : {}) });
  const rows = view === "today"
    ? Promise.all([ask("overdue"), ask("today", withDone)]).then(([late, now]) => [...late, ...now]) : ask(view, withDone);
  return withDone ? rows.then(openFirst) : rows;
}

type Address = Pick<TaskViewState, "view" | "q" | "sort" | "layout" | "group" | "ksort" | "split" | "setView" | "setQ"
  | "setSort" | "setLayout" | "setGroup" | "setKsort" | "setSplit">;

// The list's choices, kept in the address (?view=&q=&sort=&layout=&group=&ksort=&split=); a default drops out. A
// project's page is always the list.
function useTaskAddress(projectId: string | undefined): Address {
  const [params, setParams] = useSearchParams();
  const patch = useCallback((changes: Record<string, string | null>, replace = false) => {
    setParams((current) => {
      const next = new URLSearchParams(current);
      for (const [key, value] of Object.entries(changes)) {
        if (value === null) next.delete(key); else next.set(key, value);
      }
      return next;
    }, { replace });
  }, [setParams]);
  const layoutParam = params.get("layout");
  return {
    view: isView(params.get("view")) ? (params.get("view") as BoardView) : DEFAULT_VIEW,
    layout: projectId ? "list" : layoutParam === "kanban" || layoutParam === "calendar" ? layoutParam : "list",
    group: isGroup(params.get("group")) ? (params.get("group") as KanbanGroup) : DEFAULT_GROUP,
    ksort: isKanbanSort(params.get("ksort")) ? (params.get("ksort") as TaskSort) : DEFAULT_SORT,
    split: params.get("split") === "1",
    q: params.get("q") ?? "",
    sort: params.get("sort") === "priority" ? "priority" : DEFAULT_SORT,
    setView: (next) => patch({ view: next === DEFAULT_VIEW ? null : next }),
    setQ: useCallback((next: string) => patch({ q: next || null }, true), [patch]),
    setSort: (next) => patch({ sort: next === DEFAULT_SORT ? null : next }),
    setLayout: (next) => patch({ layout: next === "list" ? null : next }),
    setGroup: (next) => patch({ group: next === DEFAULT_GROUP ? null : next }),
    setKsort: (next) => patch({ ksort: next === DEFAULT_SORT ? null : next }),
    setSplit: (next) => patch({ split: next ? "1" : null }),
  };
}

type Rows = Pick<TaskViewState, "tasks" | "error" | "setError" | "load" | "setSteps">;

// The rows for the address's choices, newest answer only: a project's every task, the Kanban's board view, or the
// list's view (fetchView). Again on every tasks_changed; another layout or list shows nothing stale meanwhile.
function useTaskRows(address: Address, projectId: string | undefined, scope: TaskScope): Rows {
  const { layout, ksort, view, q, sort } = address;
  const live = useLiveState();
  const [finished] = useShowFinished();
  const [tasks, setTasks] = useState<readonly TaskRowOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef(0);
  const load = useCallback(() => {
    const ticket = ++latest.current;
    if (layout === "calendar") return; // the calendar asks for its own span of tasks (G11)
    const request = projectId ? listTasks("all", { projectId })
      : layout === "kanban" ? askTasks(scope, { view: "board", sort: ksort }) : fetchView(view, q, sort, finished, scope);
    request.then((found) => { if (ticket === latest.current) { setTasks(found); setError(null); } })
      .catch((err: unknown) => { if (ticket === latest.current) setError(describeError(err)); });
  }, [projectId, layout, ksort, view, q, sort, finished, scope]);
  useEffect(() => setTasks(null), [layout, projectId, scope]); // another layout or list: show nothing stale
  useEffect(() => load(), [load, live.boardVersion.tasks]);
  const setSteps = useCallback((taskId: string, steps: readonly TaskStepOut[]) => setTasks((shown) =>
    shown && shown.map((task) => (task.id === taskId ? { ...task, steps: [...steps] } : task))), []);
  return { tasks, error, setError, load, setSteps };
}

type StepsOpen = Pick<TaskViewState, "stepsOpen" | "toggleSteps" | "expandAll" | "collapseAll">;

// Each task's steps open on their own: new Sets, never mutated.
function useStepsOpen(): StepsOpen {
  const [stepsOpen, setStepsOpen] = useState<ReadonlySet<string>>(new Set());
  const toggleSteps = useCallback((taskId: string) => setStepsOpen((open) =>
    new Set(open.has(taskId) ? [...open].filter((id) => id !== taskId) : [...open, taskId])), []);
  return {
    stepsOpen, toggleSteps,
    expandAll: (taskIds) => setStepsOpen((open) => new Set([...open, ...taskIds])),
    collapseAll: () => setStepsOpen(new Set()),
  };
}

// The Tasks list's state (G4). The view, search and sort live in the address (?view=&q=&sort=, Today and Due by
// default); a project's page (`projectId`) lists that project's tasks of every status and ignores them. The Board's
// `scope` (the Tasks rail, lead task 15) narrows its views, Kanban included, to one project or the Inbox. The list
// reloads when a task changes anywhere (tasks_changed).
export function useTaskView(projectId?: string, given: TaskScope = ALL_TASKS): TaskViewState {
  const scopeKey = scopeParam(given);
  const scope = useMemo(() => parseScope(scopeKey), [scopeKey]); // one object per selection: loads follow its value
  const address = useTaskAddress(projectId);
  const rows = useTaskRows(address, projectId, scope);
  return { ...address, ...rows, ...useStepsOpen() };
}
