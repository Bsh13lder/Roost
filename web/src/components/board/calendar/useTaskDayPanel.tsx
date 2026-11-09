import { useState, type ReactElement } from "react";
import { DayNoteMark } from "./DayNoteMark";
import { TaskDayPopover } from "./TaskDayPopover";
import type { DayNotes } from "./useDayNotes";
import type { ProjectLook } from "./calendarProps";
import type { TaskRowOut } from "../../../api/tasks";
import { QuickAddBody } from "../QuickAddPopover";
import type { DuePick } from "../ReschedulePopover";
import { Popover } from "../../../ui/Popover";
import { dayText, type IsoDay } from "../../../ui/date/dates";

const QUICK_PLACEHOLDER = "Call plumber /Casa Nueva €200 !!";

export interface TaskDayPanelInput {
  today: IsoDay;
  placed: ReadonlyMap<IsoDay, readonly TaskRowOut[]>;
  notes: DayNotes;
  project: (task: TaskRowOut) => ProjectLook | undefined;
  spend: { currency: string; byDay: ReadonlyMap<IsoDay, string> } | null;
  onOpen: (taskId: string) => void;
  onReschedule: (task: TaskRowOut, pick: DuePick) => void;
  onChanged: () => void; // a task was added: load again
}

interface Active {
  day: IsoDay;
  mode: "day" | "add";
}

// The popover a task day opens (G11): its tasks, Day note and Add task, or the quick add for the day. The month
// grid anchors it on a cell, the phone agenda on a day's header; both call `wrap`, `add` and `noteMark`.
export function useTaskDayPanel(input: TaskDayPanelInput) {
  const { today, placed, notes, project, spend, onOpen, onReschedule, onChanged } = input;
  const [active, setActive] = useState<Active | null>(null);
  const close = () => setActive(null);
  const add = (day: IsoDay) => setActive({ day, mode: "add" });
  const openDay = (day: IsoDay) => setActive({ day, mode: "day" });
  const panel = (day: IsoDay) => {
    const name = dayText(day, { weekday: true });
    if (active?.mode === "add") {
      return <QuickAddBody title={`Add task on ${name}`} defaultDue={day} placeholder={QUICK_PLACEHOLDER} dayBadge={`Due ${name}`}
        onAdded={() => { close(); onChanged(); }} />;
    }
    return (
      <TaskDayPopover day={day} today={today} tasks={placed.get(day) ?? []} projects={project} notes={notes}
        spend={spend?.byDay.get(day) ?? null} currency={spend?.currency ?? null} onOpen={onOpen}
        onReschedule={onReschedule} onAdd={() => add(day)} onClose={close} />
    );
  };
  const wrap = (day: IsoDay, anchor: ReactElement) => {
    const name = dayText(day, { weekday: true });
    const open = active?.day === day;
    return (
      <Popover anchor={anchor} open={open} onOpenChange={(next) => { if (!next) close(); }} align="start"
        label={open && active?.mode === "add" ? `Add task on ${name}` : name}>
        {open ? panel(day) : null}
      </Popover>
    );
  };
  const noteMark = (day: IsoDay) => (
    <DayNoteMark day={day} count={notes.byDay.get(day)?.length ?? 0} onOpen={() => openDay(day)} />
  );
  return { wrap, add, openDay, noteMark };
}
