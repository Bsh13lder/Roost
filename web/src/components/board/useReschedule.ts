import { useCallback } from "react";
import { describeError } from "../../api/client";
import { moveOverdue, restoreDues, updateTask, type MovedDue } from "../../api/tasks";
import type { TaskOut } from "../../api/types";
import { useToast } from "../../ui/Toast";
import { dayText } from "../../ui/date/dates";
import type { DuePick } from "./ReschedulePopover";

const DAY_LENGTH = "YYYY-MM-DD".length;
const CLOCK_START = "YYYY-MM-DDT".length;
const CLOCK_END = "YYYY-MM-DDTHH:MM".length;

export interface Reschedule {
  one: (task: TaskOut, pick: DuePick, where?: string) => Promise<void>; // `where` names the place for the toast (a Kanban column)
  overdue: (pick: DuePick) => Promise<void>;
}

// "Wed 21 Oct, 09:30": the words a moved toast uses.
function whenText(pick: DuePick, time: string | null): string {
  return `${dayText(pick.day ?? "", { weekday: true })}${time ? `, ${time}` : ""}`;
}

// The task's own time of day, from its stored due ("2026-10-18T09:30:00+02:00"); null for a plain day.
function ownTime(due: string | null): string | null {
  return due && due.length > DAY_LENGTH ? due.slice(CLOCK_START, CLOCK_END) : null;
}

const plural = (count: number) => `${count} task${count === 1 ? "" : "s"}`;

// Change a due date and offer Undo (G2). `one` keeps the task's time when the pick has none; Undo writes the
// earlier due, reminder and advance reminders back (restore-dues). `overdue` moves every overdue task, and
// the server keeps each one's own time. `onChanged` runs after every write, the Undo included.
export function useReschedule(onChanged: () => void): Reschedule {
  const toast = useToast();
  const undoer = useCallback((before: readonly MovedDue[]) => ({
    label: "Undo",
    run: () => {
      restoreDues(before).then(onChanged).catch((err: unknown) => toast.show(describeError(err), { tone: "danger" }));
    },
  }), [onChanged, toast]);

  const one = useCallback(async (task: TaskOut, pick: DuePick, where?: string) => {
    const before: MovedDue = { id: task.id, due_date: task.due_date, reminder_at: task.reminder_at, pre_reminders: task.pre_reminders };
    const time = pick.day === null ? null : pick.time ?? ownTime(task.due_date);
    const due = pick.day === null ? null : time ? `${pick.day}T${time}` : pick.day;
    try {
      await updateTask(task.id, { due_date: due });
    } catch (err) {
      toast.show(describeError(err), { tone: "danger" });
      return;
    }
    onChanged();
    const message = where ? `“${task.title}” moved to ${where}`
      : pick.day === null ? `“${task.title}” now has no date` : `“${task.title}” moved to ${whenText(pick, time)}`;
    toast.show(message, { action: undoer([before]) });
  }, [onChanged, toast, undoer]);

  const overdue = useCallback(async (pick: DuePick) => {
    const to = pick.day === null ? null : pick.time ? `${pick.day}T${pick.time}` : pick.day;
    try {
      const { moved } = await moveOverdue(to);
      onChanged();
      if (moved.length === 0) { toast.show("Nothing was overdue."); return; }
      const where = pick.day === null ? "now have no date" : `moved to ${whenText(pick, pick.time)}`;
      toast.show(`${plural(moved.length)} ${where}`, { action: undoer(moved) });
    } catch (err) {
      toast.show(describeError(err), { tone: "danger" });
    }
  }, [onChanged, toast, undoer]);

  return { one, overdue };
}
