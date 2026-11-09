// What a reminder card's buttons do (2026-10-26, owner: "should be card Done failed reschedule Skip"), pure where it
// can be: the new due a Reschedule pick means, and the words of each outcome. The answer itself is kept on the
// server (`answerReminder`), so every screen shows it.
import { ApiError, describeError } from "../../api/client";
import type { TaskRowOut } from "../../api/tasks";
import { dayText, dueParts } from "../../ui/date/dates";
import type { DuePick } from "../board/ReschedulePopover";
import { REMINDER_DONE, REMINDER_FAILED, REMINDER_MOVED, REMINDER_NO_DATE, REMINDER_SKIPPED, TASK_GONE } from "./constants";

// Before the answer was kept on the server (2026-10-26), a Skip lived in this browser's storage; it still folds.
const LEGACY_SKIP_KEY = "roost.reminderSkipped.";

/** The due a pick sets: its day with its time, or the task's own time when the pick has none; null clears it. */
export function pickedDue(task: TaskRowOut, pick: DuePick): string | null {
  if (pick.day === null) return null;
  const time = pick.time ?? (task.due_date ? dueParts(task.due_date)?.time ?? null : null);
  return time ? `${pick.day}T${time}` : pick.day;
}

/** "Moved to Thu 29 Oct 10:00", or "Now has no date". */
export function movedWords(task: TaskRowOut, pick: DuePick): string {
  return dueMovedWords(pickedDue(task, pick));
}

/** A new due in words: "Moved to Thu 29 Oct 10:00", or "Now has no date" for null. */
export function dueMovedWords(due: string | null): string {
  if (due === null) return REMINDER_NO_DATE;
  const parts = dueParts(due);
  const when = parts ? `${dayText(parts.day, { weekday: true })}${parts.time ? ` ${parts.time}` : ""}` : due;
  return REMINDER_MOVED.replace("{when}", when);
}

/** A failed action in words: a deleted task is "This task is gone.", anything else the server's reason. */
export function actionProblem(err: unknown): string {
  return err instanceof ApiError && err.status === 404 ? TASK_GONE : describeError(err);
}

/** The card's line for an answer the server kept, or null when it has none. */
export function answerWords(answer: string | null, due: string | null): string | null {
  switch (answer) {
    case "done": return REMINDER_DONE;
    case "failed": return REMINDER_FAILED;
    case "skipped": return REMINDER_SKIPPED;
    case "rescheduled": return dueMovedWords(due);
    default: return null;
  }
}

/** A Skip this browser kept before the server did (read only, so those cards stay folded). */
export function wasSkippedHere(messageId: string): boolean {
  try {
    return window.localStorage.getItem(LEGACY_SKIP_KEY + messageId) === "1";
  } catch {
    return false;
  }
}
