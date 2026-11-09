import { Fragment, type MouseEvent, type ReactElement, type ReactNode } from "react";
import { isWeekend } from "./monthCells";
import type { DayDrop } from "./useCalendarDrag";
import { PlusIcon } from "../../icons";
import { IconButton } from "../../../ui/IconButton";
import { cx } from "../../../ui/cx";
import { dayText, type IsoDay } from "../../../ui/date/dates";
import "../../../styles/board-calendar.css";

export const WEEKDAY_HEADS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] as const;
const DAYS_PER_WEEK = 7;
const INTERACTIVE = "button, a, input, [role='button'], [draggable='true']";

export interface CalendarGridProps {
  label: string; // "October 2026"
  days: readonly IsoDay[]; // whole weeks, Monday first
  month: string | null; // days of other months fade; null: none do
  today: IsoDay;
  selected?: IsoDay | null;
  noteMark: (day: IsoDay) => ReactNode; // the day-note icon, when the day has notes
  corner: (day: IsoDay, inMonth: boolean) => ReactNode; // the summary at the right of a cell's head
  body: (day: IsoDay, inMonth: boolean) => ReactNode;
  onAdd: (day: IsoDay) => void; // the "+"
  onCell?: (day: IsoDay) => void; // a click on an empty spot
  drop?: (day: IsoDay) => DayDrop;
  wrap?: (day: IsoDay, cell: ReactElement) => ReactElement; // a popover anchored on the cell
  addLabel?: string; // "Add on" (default)
  caption?: string;
}

// The month grid both calendars share (G11, G12): weekday heads Mon…Sun, then one rounded card per day with its
// date (today's filled, with the word Today), a note mark, a corner summary and a "+" on hover or focus. What sits in
// the card is the caller's.
export function CalendarGrid({
  label, days, month, today, selected = null, noteMark, corner, body, onAdd, onCell, drop, wrap, addLabel = "Add on", caption,
}: CalendarGridProps) {
  const weeks = Array.from({ length: days.length / DAYS_PER_WEEK }, (_, index) => days.slice(index * DAYS_PER_WEEK, (index + 1) * DAYS_PER_WEEK));
  const cell = (day: IsoDay) => {
    const inMonth = month === null || day.startsWith(month);
    const dropping = drop?.(day);
    const name = dayText(day, { weekday: true });
    const click = (event: MouseEvent<HTMLElement>) => {
      if (onCell && !(event.target as HTMLElement).closest(INTERACTIVE)) onCell(day);
    };
    const element = (
      <div role="gridcell" aria-label={name} aria-current={day === today ? "date" : undefined} data-day={day} onClick={click}
        className={cx("ccell", day === today && "is-today", isWeekend(day) && "is-wknd", !inMonth && "is-out",
          selected === day && "is-sel", dropping?.isOver && "is-over")}
        onDragOver={dropping?.onDragOver} onDragLeave={dropping?.onDragLeave} onDrop={dropping?.onDrop}>
        <div className="ccell__head">
          <span className="ccell__n">{Number(day.slice(-2))}</span>
          {day === today ? <span className="ccell__today">Today</span> : null}
          {noteMark(day)}
          <span className="ccell__sp" />
          {corner(day, inMonth)}
          <IconButton className="ccell__add" size="sm" tooltip={false} label={`${addLabel} ${name}`}
            icon={<PlusIcon />} onClick={(event) => { event.stopPropagation(); onAdd(day); }} />
        </div>
        {body(day, inMonth)}
      </div>
    );
    return <Fragment key={day}>{wrap ? wrap(day, element) : element}</Fragment>;
  };
  return (
    <div className="calwrap">
      <div className="calhead" aria-hidden="true">{WEEKDAY_HEADS.map((name) => <span key={name}>{name}</span>)}</div>
      <div className="calgrid" role="grid" aria-label={label}>
        {weeks.map((week) => <div key={week[0]} role="row" className="calrow">{week.map(cell)}</div>)}
      </div>
      {caption ? <p className="calcap">{caption}</p> : null}
    </div>
  );
}

