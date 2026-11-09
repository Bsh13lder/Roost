import { DayPopover } from "./DayPopover";
import type { DayNotes } from "./useDayNotes";
import type { ProjectLook } from "./calendarProps";
import { TaskPill } from "./TaskPill";
import type { TaskRowOut } from "../../../api/tasks";
import { Button } from "../../../ui/Button";
import { formatMoneyShort } from "../money";
import type { DuePick } from "../ReschedulePopover";
import type { IsoDay } from "../../../ui/date/dates";

export interface TaskDayPopoverProps {
  day: IsoDay;
  today: IsoDay;
  tasks: readonly TaskRowOut[];
  projects: (task: TaskRowOut) => ProjectLook | undefined;
  notes: DayNotes;
  spend: string | null; // the day's spending in the main currency
  currency: string | null;
  onOpen: (taskId: string) => void;
  onReschedule: (task: TaskRowOut, pick: DuePick) => void;
  onAdd: () => void;
  onClose: () => void;
}

// A task calendar day's panel (G11): its tasks as pills that cannot be dragged here (each has →), its Day note, and
// Add task, which turns the same popover into the quick add for that day.
export function TaskDayPopover({ day, today, tasks, projects, notes, spend, currency, onOpen, onReschedule, onAdd, onClose }: TaskDayPopoverProps) {
  return (
    <DayPopover kind="tasks" day={day} count={tasks.length} onClose={onClose} notes={notes.byDay.get(day) ?? []}
      totals={spend && currency ? formatMoneyShort(spend, currency) : null}
      onAddNote={(text) => notes.add(day, text)} onDeleteNote={(note) => void notes.remove(note)}
      footer={<Button variant="ghost" size="sm" onClick={onAdd}>Add task</Button>}>
      {tasks.map((task) => (
        <TaskPill key={task.id} task={task} today={today} project={projects(task)} onOpen={onOpen} onReschedule={onReschedule} />
      ))}
    </DayPopover>
  );
}
