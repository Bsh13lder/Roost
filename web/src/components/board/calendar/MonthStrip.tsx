import { useEffect, useMemo, useRef } from "react";
import { monthDays, weekdayIndex } from "./monthCells";
import { WEEKDAY_HEADS } from "./CalendarGrid";
import { cx } from "../../../ui/cx";
import { dayText, type IsoDay } from "../../../ui/date/dates";
import "../../../styles/board-calendar.css";

export interface MonthStripProps {
  month: string; // "YYYY-MM"
  today: IsoDay;
  marks: ReadonlySet<IsoDay>; // days with something in them: they get a dot
  picked: IsoDay | null;
  onPick: (day: IsoDay | null) => void;
}

// A phone's month at a glance (G14): one chip per day of the month, scrolling sideways, with the weekday's
// letter, the date and a dot when the day has items. Today has an accent edge. A picked day shows alone
// under it; Clear gives the whole agenda back.
export function MonthStrip({ month, today, marks, picked, onPick }: MonthStripProps) {
  const days = useMemo(() => monthDays(month).filter((day) => day.startsWith(month)), [month]);
  const todayChip = useRef<HTMLButtonElement>(null);
  useEffect(() => { todayChip.current?.scrollIntoView?.({ inline: "center", block: "nearest" }); }, [month]);
  return (
    <div className="mstrip" role="group" aria-label="Days of the month">
      {days.map((day) => (
        <button key={day} type="button" ref={day === today ? todayChip : undefined} aria-pressed={picked === day}
          aria-label={dayText(day, { weekday: true })}
          className={cx("mstrip__day", day === today && "is-today", picked === day && "is-picked", marks.has(day) && "has-items")}
          onClick={() => onPick(picked === day ? null : day)}>
          <span className="mstrip__wd" aria-hidden="true">{WEEKDAY_HEADS[weekdayIndex(day)][0]}</span>
          <span className="mstrip__n" aria-hidden="true">{Number(day.slice(-2))}</span>
          <i className="mstrip__dot" aria-hidden="true" />
        </button>
      ))}
      {picked ? <button type="button" className="mstrip__clear" onClick={() => onPick(null)}>Clear</button> : null}
    </div>
  );
}
