import { useId, useState, type FormEvent } from "react";
import { agendaItems } from "./agendaItems";
import { DayNoteLine } from "../../board/calendar/DayNoteLine";
import { RoutineChip } from "../../board/calendar/RoutineChip";
import { useLiveState } from "../../../hooks/useLiveStore";
import type { RoutineDayEntry } from "../../../lib/routineDays";
import type { DayNotes } from "../../board/calendar/useDayNotes";
import { ErrorNotice } from "../../ErrorNotice";
import { CheckIcon } from "../../icons";
import type { TaskRowOut } from "../../../api/tasks";
import { cx } from "../../../ui/cx";
import { dayText, type IsoDay, type WallTime } from "../../../ui/date/dates";

export interface DayAgendaProps {
  day: IsoDay;
  today: IsoDay;
  now: WallTime; // the account's clock, "HH:MM"
  tasks: readonly TaskRowOut[];
  routines?: readonly RoutineDayEntry[]; // the day's routine runs, when Routines is on
  notes: DayNotes;
  loaded: boolean;
  colorOf: (task: TaskRowOut) => string | undefined;
  onOpen: (taskId: string) => void;
}

const MAX_NOTE = 500; // the server's day-note limit
const OPEN: ReadonlySet<TaskRowOut["status"]> = new Set(["todo", "in_progress"]);

function TaskLine({ task, time, color, onOpen }: { task: TaskRowOut; time: WallTime | null; color?: string; onOpen: (id: string) => void }) {
  const done = !OPEN.has(task.status);
  const bots = useLiveState().bots;
  const maker = task.created_by_bot ? bots[task.created_by_bot]?.name : undefined;
  return (
    <li className={cx("wcal__item", done && "is-done")} style={color ? { borderColor: color } : undefined}>
      <button type="button" className="wcal__open" onClick={() => onOpen(task.id)}>
        <span className="wcal__time">{time ?? "All day"}{maker ? <span className="wcal__by"> · by {maker}</span> : null}</span>
        <span className="wcal__title">{done ? <span className="wcal__tick" aria-label="Done"><CheckIcon /></span> : null}{task.title}</span>
      </button>
    </li>
  );
}

// One routine's runs that day (board toggles): a quiet line that opens the routine's run log.
function RoutineLine({ entry }: { entry: RoutineDayEntry }) {
  return <li className="wcal__item wcal__item--routine"><RoutineChip entry={entry} /></li>;
}

function NoteForm({ day, notes }: { day: IsoDay; notes: DayNotes }) {
  const [text, setText] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!text.trim()) return;
    const said = await notes.add(day, text.trim());
    setProblem(said);
    if (!said) setText("");
  };
  return (
    <form className="wcal__noteform" onSubmit={(event) => void submit(event)}>
      <input className="wcal__noteinput" aria-label="Add a day note" placeholder="Add a day note…" value={text}
        maxLength={MAX_NOTE} onChange={(event) => setText(event.target.value)} />
      {problem ? <ErrorNotice message={problem} /> : null}
    </form>
  );
}

// The picked day under the month (app restructure): "Today · Fri 23 Oct", its day notes, its tasks (All day first,
// then by time, with the day's routine runs among them) and, on today, a line at the current time. A task
// opens its drawer, a routine its run log.
export function DayAgenda({ day, today, now, tasks, routines = [], notes, loaded, colorOf, onOpen }: DayAgendaProps) {
  const headingId = useId();
  const isToday = day === today;
  const title = `${isToday ? "Today · " : ""}${dayText(day, { weekday: true })}`;
  const items = agendaItems(tasks, isToday ? now : null, routines);
  return (
    <section className="wcal__agenda" aria-label={`Agenda for ${title}`}>
      <h2 id={headingId} className={cx("wcal__dayhead", isToday && "is-today")}>{title}</h2>
      {(notes.byDay.get(day) ?? []).map((note) => <DayNoteLine key={note.id} note={note} onDelete={(one) => void notes.remove(one)} />)}
      {!loaded ? <p className="board-loading">Loading&hellip;</p> : null}
      {loaded && tasks.length === 0 && routines.length === 0 ? <p className="wcal__none">Nothing planned.</p> : null}
      <ul className="wcal__list" aria-labelledby={headingId}>
        {items.map((item) => {
          if (item.kind === "now") {
            return <li key="now" className="wcal__now"><time>{item.time}</time><span className="sr-only"> now</span></li>;
          }
          if (item.kind === "routine") return <RoutineLine key={`r-${item.entry.routineId}`} entry={item.entry} />;
          return <TaskLine key={item.task.id} task={item.task} time={item.time} color={colorOf(item.task)} onOpen={onOpen} />;
        })}
      </ul>
      <NoteForm day={day} notes={notes} />
    </section>
  );
}
