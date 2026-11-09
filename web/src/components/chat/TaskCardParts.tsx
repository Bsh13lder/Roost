import { FolderIcon } from "../icons";
import { PriorityMark } from "../board/PriorityMark";
import { dueTone, dueWords } from "../board/taskChips";
import type { TaskRowOut } from "../../api/tasks";
import { cx } from "../../ui/cx";
import { dueParts, todayIn } from "../../ui/date/dates";
import { useChatShared } from "./chatContext";
import { WebMark } from "./WebMark";

const FINISHED: ReadonlySet<TaskRowOut["status"]> = new Set(["done", "failed", "cancelled"]);

export const isFinished = (task: TaskRowOut) => FINISHED.has(task.status);

// "Today 09:30", "3d overdue", "Fri": the due in the account's words (the Board's own reading), its time when it has one.
export function dueLabel(task: TaskRowOut, today = todayIn()): string {
  const words = dueWords(task.due_date, today, isFinished(task));
  const time = task.due_date ? dueParts(task.due_date)?.time : null;
  return words && time ? `${words} ${time}` : words;
}

// A task's quiet facts on a chat card: its due (late in red, today in green), priority, project and web mark.
export function TaskFacts({ task }: { task: TaskRowOut }) {
  const { projects } = useChatShared();
  const project = task.project_id ? projects.find((p) => p.id === task.project_id) : undefined;
  const due = dueLabel(task);
  return (
    <span className="task-card__facts">
      {due ? <span className={cx("task-card__due", `task-card__due--${dueTone(task.due_date, todayIn())}`)}>{due}</span> : null}
      <PriorityMark priority={task.priority} />
      {project ? <span className="task-card__project"><FolderIcon />{project.name}</span> : null}
      {task.tainted ? <WebMark /> : null}
    </span>
  );
}

// The round tick of a task card: ticks an open task done, or opens a done one again.
export function TaskTick({ task, busy, onToggle }: { task: TaskRowOut; busy: boolean; onToggle: () => void }) {
  const done = task.status === "done";
  return (
    <button type="button" className={cx("task-card__tick", done && "task-card__tick--done")} disabled={busy}
      aria-pressed={done} aria-label={done ? `Open “${task.title}” again` : `Mark “${task.title}” done`}
      onClick={onToggle}>
      <svg viewBox="0 0 20 20" width={14} height={14} aria-hidden="true" focusable="false">
        <path d="M5 10.5l3 3 7-7" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </button>
  );
}
