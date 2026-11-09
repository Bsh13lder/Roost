import { monthOfDay } from "../../board/calendar/monthCells";
import type { TaskRowOut } from "../../../api/tasks";
import { cx } from "../../../ui/cx";
import { dayText, type IsoDay } from "../../../ui/date/dates";

export const MAX_DOTS = 3; // a day shows this many dots, then "+N"
const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] as const;
const WEEK = WEEKDAYS.length;
const DEFAULT_DOT = "var(--color-text-faint)"; // a task with no project

export interface DotMonthProps {
  label: string; // "October 2026"
  month: string; // "YYYY-MM"
  days: readonly IsoDay[]; // whole weeks, Monday first
  today: IsoDay;
  picked: IsoDay;
  placed: ReadonlyMap<IsoDay, readonly TaskRowOut[]>;
  colorOf: (task: TaskRowOut) => string | undefined; // its project's colour
  onPick: (day: IsoDay) => void;
  routineCounts?: ReadonlyMap<IsoDay, number>; // how many routines run each day, when Routines is on
}

const plural = (count: number, word = "task") => `${count} ${word}${count === 1 ? "" : "s"}`;

function DayCell({ day, props }: { day: IsoDay; props: DotMonthProps }) {
  const tasks = props.placed.get(day) ?? [];
  const more = tasks.length - MAX_DOTS;
  const runs = props.routineCounts?.get(day) ?? 0;
  const name = `${dayText(day, { weekday: true })}${tasks.length ? `, ${plural(tasks.length)}` : ""}`
    + `${runs ? `, ${plural(runs, "routine")}` : ""}`;
  return (
    <span role="gridcell" className="wcal__cell">
      <button type="button" aria-label={name} aria-pressed={day === props.picked} onClick={() => props.onPick(day)}
        className={cx("wcal__day", day === props.today && "is-today", monthOfDay(day) !== props.month && "is-outside")}>
        <span className="wcal__num">{Number(day.slice(-2))}</span>
        <span className="wcal__dots" aria-hidden="true">
          {tasks.slice(0, MAX_DOTS).map((task) => (
            <i key={task.id} className="wcal__dot" style={{ background: props.colorOf(task) ?? DEFAULT_DOT }} />
          ))}
          {more > 0 ? <span className="wcal__more">+{more}</span> : null}
          {runs ? <i className="wcal__rdot" /> : null}
        </span>
      </button>
    </span>
  );
}

// The Workspace's month (app restructure): a quiet grid of days, up to three dots in the tasks' project colours
// (then +N), a hollow ring on a day a routine runs, today boxed in the accent, the picked day filled. Picking a day lists it below.
export function DotMonth(props: DotMonthProps) {
  const weeks = Array.from({ length: props.days.length / WEEK }, (_, index) => props.days.slice(index * WEEK, (index + 1) * WEEK));
  return (
    <div role="grid" aria-label={props.label} className="wcal__grid">
      <div role="row" className="wcal__row wcal__row--head">
        {WEEKDAYS.map((name) => <span key={name} role="columnheader" className="wcal__weekday">{name}</span>)}
      </div>
      {weeks.map((week) => (
        <div key={week[0]} role="row" className="wcal__row">
          {week.map((day) => <DayCell key={day} day={day} props={props} />)}
        </div>
      ))}
    </div>
  );
}
