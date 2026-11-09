import type { ReactElement, ReactNode } from "react";
import { Link } from "react-router-dom";
import { AgendaDayHead, agendaLabel } from "./AgendaDayHead";
import { DayNoteLine } from "./DayNoteLine";
import { LATE_WORD, type DayPlan } from "./dayMarks";
import type { ProjectLook } from "./calendarProps";
import type { DayNotes } from "./useDayNotes";
import type { TaskRowOut } from "../../../api/tasks";
import type { BotOut } from "../../../api/types";
import { routineLink, routineTimeWords } from "../../../lib/routineDays";
import { BellIcon, RepeatIcon } from "../../icons";
import { Button } from "../../../ui/Button";
import { cx } from "../../../ui/cx";
import { dayText, type IsoDay } from "../../../ui/date/dates";

export interface MarksDayPanelProps {
  day: IsoDay;
  today: IsoDay;
  plan: DayPlan;
  notes: DayNotes;
  bots: Readonly<Record<string, BotOut>>;
  project: (task: TaskRowOut) => ProjectLook | undefined;
  onOpen: (taskId: string) => void;
  onAdd: () => void;
  head: (content: ReactElement) => ReactNode; // wraps the header: the quick add's popover anchors on it
  noteMark: ReactNode;
}

interface RowProps {
  time: string;
  title: string;
  who?: string; // the bot's name
  where?: string; // the project's name
  done?: boolean;
  late?: boolean;
  icon?: ReactNode;
}

function RowBody({ time, title, who, where, done, late, icon }: RowProps) {
  const meta = [who, where].filter(Boolean);
  return (
    <>
      <span className={cx("dplan__time", late && "is-late")}>{time}</span>
      {icon ? <span className="dplan__icon" aria-hidden="true">{icon}</span> : null}
      <span className="dplan__main">
        <span className={cx("dplan__title", done && "is-done")}>{title}</span>
        {meta.length ? <span className="dplan__meta">{meta.join(" · ")}</span> : null}
      </span>
    </>
  );
}

function Section({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="dplan__section">
      <h4 className="dplan__label">{label}</h4>
      <ul className="dplan__list" aria-label={label}>{children}</ul>
    </div>
  );
}

// A picked day under the phone grid (clean calendar, 2026-10-26): its header and notes, then Tasks, Reminders and
// Routines, each row a time on the account's clock, the title, the bot and the project. A task row opens the task drawer, a routine
// its run log. Empty sections are left out; a day with nothing says so and offers Add a task.
export function MarksDayPanel(props: MarksDayPanelProps) {
  const { day, today, plan, notes, bots, project, onOpen } = props;
  const who = (task: TaskRowOut) => (task.created_by_bot ? bots[task.created_by_bot]?.name : undefined);
  const dayNotes = notes.byDay.get(day) ?? [];
  const empty = !plan.tasks.length && !plan.reminders.length && !plan.routines.length && !dayNotes.length;
  const taskRow = (task: TaskRowOut, body: RowProps, key: string) => (
    <li key={key}>
      <button type="button" className="dplan__row" onClick={() => onOpen(task.id)}>
        <RowBody {...body} who={who(task)} where={project(task)?.name} />
      </button>
    </li>
  );
  return (
    <section className="dplan" aria-label={`Day: ${agendaLabel(day, today)}`}>
      {props.head(<div className="agenda__headwrap"><AgendaDayHead day={day} today={today} noteMark={props.noteMark} onAdd={props.onAdd} /></div>)}
      {dayNotes.map((note) => <DayNoteLine key={note.id} note={note} onDelete={(one) => void notes.remove(one)} />)}
      {plan.tasks.length ? (
        <Section label="Tasks">
          {plan.tasks.map(({ task, time }) => taskRow(task, {
            time, title: task.title, done: task.status === "done", late: time === LATE_WORD,
          }, task.id))}
        </Section>
      ) : null}
      {plan.reminders.length ? (
        <Section label="Reminders">
          {plan.reminders.map(({ task, time, more }) => taskRow(task, {
            time: more ? `${time} +${more}` : time, title: task.title, icon: <BellIcon />,
          }, `r-${task.id}`))}
        </Section>
      ) : null}
      {plan.routines.length ? (
        <Section label="Routines">
          {plan.routines.map((entry) => (
            <li key={entry.routineId}>
              <Link className="dplan__row" to={routineLink(entry)}>
                <RowBody time={routineTimeWords(entry)} title={entry.routineName} who={entry.botName} icon={<RepeatIcon />} />
              </Link>
            </li>
          ))}
        </Section>
      ) : null}
      {empty ? (
        <div className="agenda__empty">
          <p className="agenda__none">Nothing on this day.</p>
          <Button variant="ghost" size="sm" aria-label={`Add a task on ${dayText(day, { weekday: true })}`} onClick={props.onAdd}>
            Add a task
          </Button>
        </div>
      ) : null}
    </section>
  );
}
