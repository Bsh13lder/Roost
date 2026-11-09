import type { CSSProperties, DragEvent, KeyboardEvent } from "react";
import { daysLate, dueTime, isLate } from "./taskPlacement";
import type { TaskRowOut } from "../../../api/tasks";
import { PriorityMark } from "../PriorityMark";
import { ReschedulePopover, type DuePick } from "../ReschedulePopover";
import { IconButton } from "../../../ui/IconButton";
import { cx } from "../../../ui/cx";
import type { IsoDay } from "../../../ui/date/dates";
import type { ProjectLook } from "./calendarProps";
import { CheckIcon } from "../../icons";
import { useLiveState } from "../../../hooks/useLiveStore";

export interface PillDrag {
  draggable: true;
  onDragStart: (event: DragEvent<HTMLElement>) => void;
  onDragEnd: () => void;
}

export interface TaskPillProps {
  task: TaskRowOut;
  today: IsoDay;
  project?: ProjectLook; // its project: the colour edge and wash, and the name in its words
  onOpen: (taskId: string) => void;
  drag?: PillDrag; // a pill in a grid drags; one in the day popover does not
  onReschedule?: (task: TaskRowOut, pick: DuePick) => void; // given: the → button opens the reschedule popover
}

const CLOSED_WORDS: Partial<Record<TaskRowOut["status"], string>> = { done: "done", failed: "failed", cancelled: "cancelled" };

// "Fix the sink · 09:30 · Casa Nueva · by Gela (4d overdue)", or "… · done": what the pill says to a screen reader
// and on hover.
function pillWords(task: TaskRowOut, today: IsoDay, time: string | null, project: ProjectLook | undefined,
  maker: string | undefined): string {
  const late = isLate(task, today);
  const closed = CLOSED_WORDS[task.status];
  return `${task.title}${time ? ` · ${time}` : ""}${project ? ` · ${project.name}` : ""}${maker ? ` · by ${maker}` : ""}`
    + `${late ? ` (${daysLate(task, today)}d overdue)` : ""}${closed ? ` · ${closed}` : ""}`;
}

// One task as a pill (G11): a 3px edge and a soft wash in its project's colour, the time, the title, the urgent flag.
// A closed task is quiet (no wash, faint, after the open ones), a done one struck through with a tick; a late open
// task wears a red tint and "4d". A task a bot made ends with that bot's name (a retired bot's: none). A click
// opens the drawer.
export function TaskPill({ task, today, project, onOpen, drag, onReschedule }: TaskPillProps) {
  const bots = useLiveState().bots;
  const maker = task.created_by_bot ? bots[task.created_by_bot]?.name : undefined;
  const late = isLate(task, today);
  const time = late ? null : dueTime(task);
  const words = pillWords(task, today, time, project, maker);
  const closed = CLOSED_WORDS[task.status] !== undefined;
  const body = (
    <>
      {task.status === "done" ? <span className="tchip__tick" aria-hidden="true"><CheckIcon /></span>
        : closed ? null : <PriorityMark priority={task.priority} size="icon" />}
      {time ? <span className="tchip__time">{time}</span> : null}
      <span className="tchip__title">{task.title}</span>
      {late ? <span className="tchip__late">{daysLate(task, today)}d</span> : null}
      {maker ? <span className="tchip__by">{maker}</span> : null}
    </>
  );
  const classes = cx("tchip", late && "is-over", closed && "is-closed", task.status === "done" && "is-done", project && "has-project");
  const style = project ? ({ "--pc": project.color } as CSSProperties) : undefined;
  if (onReschedule) {
    return (
      <div className={classes} style={style} title={words}>
        <button type="button" className="tchip__open" onClick={() => onOpen(task.id)}>{body}</button>
        <ReschedulePopover title={`Reschedule “${task.title}”`} current={null}
          onPick={(pick) => onReschedule(task, pick)}
          trigger={<IconButton className="tchip__go" size="sm" label={`Reschedule ${task.title}`} icon={<span aria-hidden="true">→</span>} />} />
      </div>
    );
  }
  const onKey = (event: KeyboardEvent) => {
    if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onOpen(task.id); }
  };
  return (
    <div className={classes} style={style} title={words} role="button" tabIndex={0} aria-label={words}
      onClick={() => onOpen(task.id)} onKeyDown={onKey} {...drag}>
      {body}
    </div>
  );
}
