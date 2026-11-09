import type { CSSProperties } from "react";
import { WEEKDAY_HEADS } from "./CalendarGrid";
import { CELL_MAX_DOTS, cellWords, dotTone, type DayMark } from "./dayMarks";
import type { ProjectLook } from "./calendarProps";
import type { TaskRowOut } from "../../../api/tasks";
import type { BotOut } from "../../../api/types";
import { BellIcon, CheckIcon, RepeatIcon } from "../../icons";
import { cx } from "../../../ui/cx";
import type { IsoDay } from "../../../ui/date/dates";
import "../../../styles/calendar-marks.css";

export interface MarksMonthGridProps {
  days: readonly IsoDay[]; // whole weeks, Monday first
  month: string; // "YYYY-MM"
  today: IsoDay;
  picked: IsoDay;
  marks: ReadonlyMap<IsoDay, DayMark>;
  bots: Readonly<Record<string, BotOut>>;
  project: (task: TaskRowOut) => ProjectLook | undefined;
  onPick: (day: IsoDay) => void;
}

function Dot({ task, today, project }: { task: TaskRowOut; today: IsoDay; project: ProjectLook | undefined }) {
  const tone = dotTone(task, today, project);
  const style = tone.kind === "project" ? ({ "--pc": tone.color } as CSSProperties) : undefined;
  return <i className={cx("mcell__dot", `is-${tone.kind}`)} style={style} aria-hidden="true" />;
}

function BotMark({ bot }: { bot: BotOut | undefined }) {
  if (!bot) return null;
  return (
    <span className="mcell__bot" style={{ "--bot": bot.avatar.color } as CSSProperties} aria-hidden="true">
      {bot.name.slice(0, 1).toUpperCase()}
    </span>
  );
}

function Cell({ day, inMonth, props }: { day: IsoDay; inMonth: boolean; props: MarksMonthGridProps }) {
  const mark = props.marks.get(day);
  const tasks = mark?.tasks ?? [];
  const more = tasks.length - CELL_MAX_DOTS;
  return (
    <button type="button" aria-pressed={props.picked === day} aria-label={cellWords(day, mark)}
      className={cx("mcell", day === props.today && "is-today", props.picked === day && "is-picked", !inMonth && "is-out")}
      onClick={() => props.onPick(day)}>
      <span className="mcell__n" aria-hidden="true">{Number(day.slice(-2))}</span>
      <span className="mcell__dots" aria-hidden="true">
        {tasks.slice(0, CELL_MAX_DOTS).map((task) => <Dot key={task.id} task={task} today={props.today} project={props.project(task)} />)}
        {more > 0 ? <span className="mcell__more">+{more}</span> : null}
      </span>
      <span className="mcell__icons" aria-hidden="true">
        {mark?.reminders ? <span className="mcell__bell"><BellIcon /></span> : null}
        {mark?.routines ? <span className="mcell__repeat"><RepeatIcon /></span> : null}
        {(mark?.botIds ?? []).map((id) => <BotMark key={id} bot={props.bots[id]} />)}
      </span>
    </button>
  );
}

/** One line under the grid that says what each mark means. */
export function MarksLegend() {
  return (
    <p className="mlegend" role="note" aria-label="What the marks mean">
      <span><i className="mcell__dot is-plain" aria-hidden="true" /> task</span>
      <span><i className="mcell__dot is-done" aria-hidden="true"><CheckIcon /></i> done</span>
      <span className="mcell__bell"><BellIcon /></span><span>reminder</span>
      <span className="mcell__repeat"><RepeatIcon /></span><span>routine</span>
      <span><span className="mcell__bot mcell__bot--legend" aria-hidden="true">A</span> made by a bot</span>
    </p>
  );
}

// The clean calendar on a phone (2026-10-26): the month as a Monday-first grid of day buttons that carry only marks:
// up to three task dots (late red, urgent or high in their tone, else the project's colour; a done one a ring), +N,
// a bell when a reminder fires, a repeat mark when a routine runs, and the initials of the bots behind the day.
// Today is outlined, the picked day tinted; its words go to a screen reader.
export function MarksMonthGrid(props: MarksMonthGridProps) {
  return (
    <div className="mgrid" role="group" aria-label="Month">
      {WEEKDAY_HEADS.map((name) => <span key={name} className="mgrid__wd" aria-hidden="true">{name[0]}</span>)}
      {props.days.map((day) => <Cell key={day} day={day} inMonth={day.startsWith(props.month)} props={props} />)}
    </div>
  );
}
