import { Fragment, type DragEvent, type MouseEvent, type ReactElement, type ReactNode } from "react";
import { isWeekend } from "./monthCells";
import { isTimed, dueTime, slotShare, slotTop } from "./taskPlacement";
import { WEEKDAY_HEADS } from "./CalendarGrid";
import type { DayDrop } from "./useCalendarDrag";
import type { TaskRowOut } from "../../../api/tasks";
import { CAL_FIRST_HOUR, CAL_HOUR_PX, CAL_HOURS } from "../constants";
import { PlusIcon } from "../../icons";
import { IconButton } from "../../../ui/IconButton";
import { cx } from "../../../ui/cx";
import { dayText, type IsoDay } from "../../../ui/date/dates";

const INTERACTIVE = "button, a, input, [role='button'], [draggable='true']";

export interface WeekGridProps {
  label: string; // "Week 19–25 Oct"
  days: readonly IsoDay[]; // Monday to Sunday
  today: IsoDay;
  tasksByDay: ReadonlyMap<IsoDay, readonly TaskRowOut[]>;
  pill: (task: TaskRowOut) => ReactNode;
  noteMark: (day: IsoDay) => ReactNode;
  onAdd: (day: IsoDay) => void;
  drop: (day: IsoDay, hourAt?: (event: DragEvent<HTMLElement>) => number) => DayDrop;
  wrap: (day: IsoDay, head: ReactElement) => ReactElement; // the day's popover sits on its head
  caption?: string;
  extras?: (day: IsoDay) => ReactNode; // quiet lines under the day's all-day tasks: its routines
}

// The hour a drop landed on, from how far down the time grid it fell.
function hourAt(event: DragEvent<HTMLElement>): number {
  const box = event.currentTarget.getBoundingClientRect();
  const hour = CAL_FIRST_HOUR + Math.floor((event.clientY - box.top) / CAL_HOUR_PX);
  return Math.min(Math.max(hour, CAL_FIRST_HOUR), CAL_FIRST_HOUR + CAL_HOURS - 1);
}

// Tasks sharing a time share the width of their block.
function slots(tasks: readonly TaskRowOut[], pill: WeekGridProps["pill"]): ReactNode {
  const groups = new Map<string, TaskRowOut[]>();
  for (const task of tasks) groups.set(dueTime(task) ?? "", [...(groups.get(dueTime(task) ?? "") ?? []), task]);
  return [...groups].flatMap(([time, group]) => group.map((task, index) => {
    const share = slotShare(index, group.length);
    return (
      <div key={task.id} className="slot" style={{ top: `${slotTop(time)}px`, left: `${share.left}%`, width: `${share.width}%` }}>
        {pill(task)}
      </div>
    );
  }));
}

// The week (G11): a 52px hour column and seven day columns, a head row (weekday, date, note mark, "+"), an All day row
// for untimed and overdue tasks, and a 07–22 time grid where a timed task sits at its hour.
export function WeekGrid({ label, days, today, tasksByDay, pill, noteMark, onAdd, drop, wrap, caption, extras }: WeekGridProps) {
  const column = (day: IsoDay, inner: ReactNode, extra?: string, slotsColumn = false) => {
    const dropping = drop(day, slotsColumn ? hourAt : undefined);
    return (
      <div key={day} role="gridcell" aria-label={`${dayText(day, { weekday: true })}${slotsColumn ? " time grid" : " all day"}`}
        className={cx("wk__col", extra, day === today && "is-today", isWeekend(day) && "is-wknd", dropping.isOver && "is-over")}
        onClick={(event: MouseEvent<HTMLElement>) => { if (!(event.target as HTMLElement).closest(INTERACTIVE)) onAdd(day); }}
        onDragOver={dropping.onDragOver} onDragLeave={dropping.onDragLeave} onDrop={dropping.onDrop}>
        {inner}
      </div>
    );
  };
  const tasksOf = (day: IsoDay) => tasksByDay.get(day) ?? [];
  const head = (day: IsoDay, index: number) => <Fragment key={day}>{wrap(day, (
    <div role="columnheader" aria-label={dayText(day, { weekday: true })} aria-current={day === today ? "date" : undefined}
      className={cx("wk__day", day === today && "is-today")}>
      {WEEKDAY_HEADS[index]}
      <span className="ccell__n">{Number(day.slice(-2))}</span>
      {noteMark(day)}
      <IconButton className="ccell__add" size="sm" tooltip={false} label={`Add on ${dayText(day, { weekday: true })}`}
        icon={<PlusIcon />} onClick={() => onAdd(day)} />
    </div>
  ))}</Fragment>;
  return (
    <div className="calwrap">
      <div className="wk" role="grid" aria-label={label}>
        <div className="wk__row" role="row"><span />{days.map(head)}</div>
        <div className="wk__row wk__allday" role="row" aria-label="All day">
          <span className="wk__lbl">All day</span>
          {days.map((day) => column(day, <>
            {tasksOf(day).filter((task) => !isTimed(task, today)).map((task) => <div key={task.id} className="wk__item">{pill(task)}</div>)}
            {extras?.(day)}
          </>))}
        </div>
        <div className="wk__row" role="row" aria-label="Hours">
          <div className="wk__hours" aria-hidden="true">
            {Array.from({ length: CAL_HOURS }, (_, index) => <span key={index}>{String(CAL_FIRST_HOUR + index).padStart(2, "0")}</span>)}
          </div>
          {days.map((day) => column(day, slots(tasksOf(day).filter((task) => isTimed(task, today)), pill), "wk__slots", true))}
        </div>
      </div>
      {caption ? <p className="calcap">{caption}</p> : null}
    </div>
  );
}
