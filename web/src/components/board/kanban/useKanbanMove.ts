import { useCallback } from "react";
import { columnOf, moveFor, NO_PROJECT_KEY, type KanbanColumn, type KanbanGroup, type KanbanMove } from "./kanbanGroups";
import { describeError } from "../../../api/client";
import { completeTask, deleteTask, reopenTask, updateTask, type TaskRowOut } from "../../../api/tasks";
import { useToast } from "../../../ui/Toast";
import { todayIn } from "../../../ui/date/dates";
import type { DuePick } from "../ReschedulePopover";

export interface KanbanMover {
  // A card was dropped on, or moved to, a column (`lane`: the project row it sits in when the board is split).
  apply: (task: TaskRowOut, key: string, lane?: string) => Promise<void>;
  // The day the picker chose for This week / Later.
  pickDay: (task: TaskRowOut, key: string, pick: DuePick) => Promise<void>;
}

export interface KanbanMoveOptions {
  group: KanbanGroup;
  columns: readonly KanbanColumn[];
  reload: () => void;
  reschedule: (task: TaskRowOut, pick: DuePick, where?: string) => Promise<void>;
  onPickDay: (task: TaskRowOut, key: string) => void; // open the date picker for a This week / Later drop
}

const laneProject = (lane: string): string | null => (lane === NO_PROJECT_KEY ? null : lane);

// Run one move against the server. A lane adds its project to the same write when it can. Returns the id of the
// next copy a repeating task made when it was completed (its Undo removes it).
async function perform(task: TaskRowOut, group: KanbanGroup, key: string | null, lane: string | undefined): Promise<string | null> {
  const project = lane !== undefined && (task.project_id ?? NO_PROJECT_KEY) !== lane ? { project_id: laneProject(lane) } : null;
  if (key === null) { // the same column in another row: only the project changes
    if (project) await updateTask(task.id, project);
    return null;
  }
  const move: KanbanMove = moveFor(group, key, task, todayIn());
  if (move.kind === "patch") {
    await updateTask(task.id, { ...move.patch, ...project });
    return null;
  }
  let nextId: string | null = null;
  if (move.kind === "complete") nextId = (await completeTask(task.id)).next_id ?? null;
  if (move.kind === "reopen") {
    await reopenTask(task.id);
    if (move.then) await updateTask(task.id, move.then);
  }
  if (project && move.kind !== "none") await updateTask(task.id, project);
  return nextId;
}

// What a card does when it changes column (G6): the grouped field is set, a toast says where it went, and Undo
// puts the earlier value back the same way. Day columns go through G2's reschedule (it has its own Undo);
// This week and Later ask for the day first; Overdue and Bot columns do nothing.
export function useKanbanMove({ group, columns, reload, reschedule, onPickDay }: KanbanMoveOptions): KanbanMover {
  const toast = useToast();
  const label = useCallback((key: string) => columns.find((column) => column.key === key)?.label ?? key, [columns]);
  const fail = useCallback((err: unknown) => toast.show(describeError(err), { tone: "danger" }), [toast]);

  const undo = useCallback(async (task: TaskRowOut, key: string, nextId: string | null, lane: string | undefined) => {
    const after: TaskRowOut = { ...task, status: key === "done" && group === "status" ? "done" : task.status };
    const before = columnOf(task, group);
    const back = lane === undefined ? undefined : task.project_id ?? NO_PROJECT_KEY;
    try {
      await perform({ ...after, project_id: lane === undefined ? after.project_id : laneProject(lane) }, group,
        before === key ? null : before, back);
      if (nextId) await deleteTask(nextId);
    } catch (err) {
      fail(err);
    }
    reload();
  }, [fail, group, reload]);

  const apply = useCallback(async (task: TaskRowOut, key: string, lane?: string) => {
    const sameColumn = columnOf(task, group) === key;
    const sameLane = lane === undefined || (task.project_id ?? NO_PROJECT_KEY) === lane;
    if (sameColumn && sameLane) return;
    const move = moveFor(group, key, task, todayIn());
    if (move.kind === "none") return;
    if (move.kind === "pick-day") { onPickDay(task, key); return; }
    if (move.kind === "day") { await reschedule(task, { day: move.day, time: null }, label(key)); return; }
    try {
      const nextId = await perform(task, group, sameColumn ? null : key, lane);
      reload();
      toast.show(`“${task.title}” moved to ${label(key)}`, { action: { label: "Undo", run: () => void undo(task, key, nextId, lane) } });
    } catch (err) {
      fail(err);
    }
  }, [fail, group, label, onPickDay, reload, reschedule, toast, undo]);

  const pickDay = useCallback((task: TaskRowOut, key: string, pick: DuePick) => reschedule(task, pick, label(key)), [label, reschedule]);
  return { apply, pickDay };
}
