import { useCallback, useMemo } from "react";
import { CalendarGrid } from "./CalendarGrid";
import { CalendarToolbar } from "./CalendarToolbar";
import { dueDay, isLate, placeTasks } from "./taskPlacement";
import { TaskAgenda } from "./TaskAgenda";
import { TaskPill } from "./TaskPill";
import { useCalendarData } from "./useCalendarData";
import { useCalendarDrag } from "./useCalendarDrag";
import { useCalendarSpan } from "./useCalendarSpan";
import { useDayNotes } from "./useDayNotes";
import { RoutineLines } from "./RoutineChip";
import { useRoutineDays } from "./useRoutineDays";
import { useTaskDayPanel } from "./useTaskDayPanel";
import { WeekGrid } from "./WeekGrid";
import type { TaskCalendarProps } from "./calendarProps";
import type { TaskRowOut } from "../../../api/tasks";
import { ErrorNotice } from "../../ErrorNotice";
import { CAL_CELL_MAX_PILLS, CAL_CELL_MAX_ROUTINES, PHONE_MEDIA, SCREEN_BOARD_CALENDAR } from "../constants";
import { formatMoneyShort } from "../money";
import { useReschedule } from "../useReschedule";
import { useLiveState } from "../../../hooks/useLiveStore";
import { useMediaQuery } from "../../../hooks/useMediaQuery";
import { useScreenToggle } from "../../../hooks/useScreenToggle";
import { todayIn, type IsoDay } from "../../../ui/date/dates";

const MONTH_CAPTION = "Click a day to add a task, or drag a chip to another day to reschedule. Overdue tasks sit on today with a red tint.";
const WEEK_CAPTION = "Drag a chip to another day to reschedule. Click an empty spot to add.";

const hourTime = (hour: number) => `${String(hour).padStart(2, "0")}:00`;

// The month grid and the week grid (G11): a month of rounded day cards or a week with a 07–22 time grid. Pills carry their
// project's colour and name, open tasks first; a click on a day, or its "+", adds a task on it (an empty day says so); "+N more" and the note mark open the day's panel
// (tasks, Day note, Add task); a pill dragged to another day is rescheduled with Undo. With Routines on, each day
// also lists its routines' runs as quiet lines (board toggles). A lazy chunk.
function TaskGridCalendar({ projects, onOpen, scope, ownDone }: TaskCalendarProps) {
  const version = useLiveState().boardVersion;
  const span = useCalendarSpan();
  const data = useCalendarData(span.first, span.last, version.tasks, version.money, scope, ownDone);
  const notes = useDayNotes(span.first, span.last, version.dayNotes);
  const [showRoutines] = useScreenToggle(SCREEN_BOARD_CALENDAR, "routines");
  const routines = useRoutineDays({ first: span.first, last: span.last, show: showRoutines });
  const reschedule = useReschedule(data.reload);
  const today = todayIn();
  const tasks = useMemo(() => data.tasks ?? [], [data.tasks]);
  const placed = useMemo(() => placeTasks(tasks, today, span.days), [tasks, today, span.days]);

  const drag = useCalendarDrag(useCallback((taskId: string, day: IsoDay, hour: number | null) => {
    const task = tasks.find((one) => one.id === taskId);
    if (!task || (hour === null && dueDay(task) === day && !isLate(task, today))) return; // already there

    void reschedule.one(task, { day, time: hour === null ? null : hourTime(hour) });
  }, [tasks, today, reschedule]));

  const project = (task: TaskRowOut) => (task.project_id ? projects.get(task.project_id) : undefined);
  const pill = (task: TaskRowOut, draggable = true) => (
    <TaskPill key={task.id} task={task} today={today} project={project(task)} onOpen={onOpen}
      drag={draggable ? drag.pillDrag(task.id) : undefined} />
  );
  const spendOf = (day: IsoDay) => data.spend?.byDay.get(day) ?? null;
  const { wrap, add, openDay, noteMark } = useTaskDayPanel({
    today, placed, notes, project, spend: data.spend, onOpen, onChanged: data.reload,
    onReschedule: (task, pick) => void reschedule.one(task, pick),
  });

  const monthBody = (day: IsoDay) => {
    const list = placed.get(day) ?? [];
    const runs = routines.get(day) ?? [];
    const more = list.length - CAL_CELL_MAX_PILLS;
    return (
      <>
        {list.length === 0 && runs.length === 0 ? <span className="ccell__hint" aria-hidden="true">Add task</span> : null}
        {list.slice(0, CAL_CELL_MAX_PILLS).map((task) => pill(task))}
        {more > 0 ? <button type="button" className="cmore" onClick={() => openDay(day)}>+{more} more</button> : null}
        <RoutineLines entries={runs} max={CAL_CELL_MAX_ROUTINES} />
      </>
    );
  };
  const corner = (day: IsoDay, inMonth: boolean) => {
    const count = placed.get(day)?.length ?? 0;
    const spent = spendOf(day);
    if (!inMonth || (!count && !spent)) return null;
    return (
      <span className="csum">
        {count ? <span className="csum__n" title={`${count} task${count === 1 ? "" : "s"}`}><i className="cdot" aria-hidden="true" />{count}</span> : null}
        {spent && data.spend ? <span className="csum__spent">{formatMoneyShort(spent, data.spend.currency)}</span> : null}
      </span>
    );
  };

  return (
    <section className="taskcal" aria-label="Task calendar">
      <CalendarToolbar span={span} allowFuture onMode={span.setMode} />
      {data.error ? <ErrorNotice message={data.error} onRetry={data.reload} /> : null}
      {span.mode === "month" ? (
        <CalendarGrid label={span.label} days={span.days} month={span.month} today={today} noteMark={noteMark}
          corner={corner} body={(day) => monthBody(day)} onAdd={add} onCell={add} drop={(day) => drag.dayDrop(day)}
          wrap={wrap} caption={MONTH_CAPTION} />
      ) : (
        <WeekGrid label={`Week ${span.label}`} days={span.days} today={today} tasksByDay={placed} pill={(task) => pill(task)}
          noteMark={noteMark} onAdd={add} drop={drag.dayDrop} wrap={wrap} caption={WEEK_CAPTION}
          extras={(day) => <RoutineLines entries={routines.get(day) ?? []} />} />
      )}
    </section>
  );
}

// The Tasks tab's Calendar: the grids, or on a phone the month of marks and the picked day (clean calendar). A lazy chunk.
export default function TaskCalendar(props: TaskCalendarProps) {
  const phone = useMediaQuery(PHONE_MEDIA);
  return phone ? <TaskAgenda {...props} /> : <TaskGridCalendar {...props} />;
}
