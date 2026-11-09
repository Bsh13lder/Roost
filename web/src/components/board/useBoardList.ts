import { useEffect, useMemo, useRef, useState, type RefObject } from "react";
import { groupsFor, projectGroups } from "./groupTasks";
import { useTaskKeys } from "./useTaskKeys";
import type { useTaskActions } from "./useTaskActions";
import type { TaskViewState } from "./useTaskView";
import { useShowFinished } from "../../hooks/useShowFinished";
import { useScreenToggle } from "../../hooks/useScreenToggle";
import { finishedCount, keepShown } from "../../lib/finished";
import { botMadeCount, keepMade } from "../../lib/madeBy";
import { SCREEN_BOARD_CALENDAR, SCREEN_BOARD_KANBAN, SCREEN_BOARD_LIST, SCREEN_PROJECT } from "./constants";
import type { TaskRowOut } from "../../api/tasks";
import type { BoardView as TaskView } from "./constants";
import { addDays, todayIn } from "../../ui/date/dates";

// The Workspace's "Add or find anything" pill: / and q go there when the list has no box of its own.
const PILL_SELECTOR = "input[aria-label='Add or find anything']";

/** Whose show / hide choices a Tasks board uses: a project's page, or the Workspace's List, Kanban or Calendar. */
export function boardScreen(projectId: string | undefined, layout: TaskViewState["layout"]): string {
  if (projectId) return SCREEN_PROJECT;
  return layout === "kanban" ? SCREEN_BOARD_KANBAN : layout === "calendar" ? SCREEN_BOARD_CALENDAR : SCREEN_BOARD_LIST;
}

// Show finished and Made by bots: the tasks to draw, and how many each switch is keeping out.
function useShownTasks(tasks: readonly TaskRowOut[] | null, allFinished: boolean, screen: string) {
  const [show] = useShowFinished();
  const [made] = useScreenToggle(screen, "botMade");
  const keepAll = show || allFinished;
  const shownTasks = useMemo(() => (tasks ? keepMade(keepAll ? tasks : keepShown(tasks, false), made) : tasks),
    [tasks, keepAll, made]);
  return {
    shownTasks, hidden: tasks && !keepAll ? finishedCount(tasks) : 0,
    botMadeHidden: tasks && !made ? botMadeCount(keepAll ? tasks : keepShown(tasks, false)) : 0,
  };
}

export interface BoardListInput {
  state: TaskViewState;
  projectId?: string; // a project's page: its own groups, no views
  actions: ReturnType<typeof useTaskActions>;
  onOpen: (taskId: string) => void;
  boardRef: RefObject<HTMLElement | null>;
}

// What the Tasks board draws (G4): the tasks Show finished keeps, grouped for the list (or the project's page),
// the keyboard's cursor over them (j/k, x, t, Enter, /, q, 1 to 5) and the layout flags.
export function useBoardList({ state, projectId, actions, onOpen, boardRef }: BoardListInput) {
  const { view, layout } = state;
  const [cursor, setCursor] = useState(0);
  const searchRef = useRef<HTMLInputElement>(null);
  const today = todayIn();
  const grouped = layout === "list"; // the list's rows
  const allFinished = projectId === undefined && view === "done" && grouped; // the Done view: finished is the point
  const screen = boardScreen(projectId, layout);
  const { shownTasks, hidden, botMadeHidden } = useShownTasks(state.tasks, allFinished, screen);
  const groups = useMemo(() => {
    if (shownTasks === null || !grouped) return [];
    return projectId ? projectGroups(shownTasks, today) : groupsFor(view, shownTasks, today);
  }, [shownTasks, projectId, grouped, view, today]);
  const flat = useMemo(() => groups.flatMap((group) => group.rows), [groups]);
  useEffect(() => setCursor((now) => Math.min(now, Math.max(flat.length - 1, 0))), [flat.length]);
  const toView = (next: TaskView) => { setCursor(0); state.setView(next); };
  useTaskKeys({
    enabled: grouped, rows: flat, cursor, setCursor, onDone: actions.complete, onOpen,
    onTomorrow: (task) => void actions.one(task, { day: addDays(today, 1), time: null }),
    onView: projectId ? undefined : toView,
    focusSearch: () => (searchRef.current ?? document.querySelector<HTMLInputElement>(PILL_SELECTOR))?.focus(),
    focusQuick: () => (boardRef.current?.querySelector<HTMLInputElement>("input[aria-label='New task']")
      ?? document.querySelector<HTMLInputElement>(PILL_SELECTOR))?.focus(),
  });
  return { today, grouped, allFinished, shownTasks, hidden, botMadeHidden, screen, groups, flat, cursor, toView, searchRef };
}

export type BoardList = ReturnType<typeof useBoardList>;
