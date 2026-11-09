import { useMemo, useState } from "react";
import { buildDayMarks, dayPlan } from "./dayMarks";
import { MarksDayPanel } from "./MarksDayPanel";
import { MarksLegend, MarksMonthGrid } from "./MarksMonthGrid";
import { monthDays, monthOfDay } from "./monthCells";
import { placeTasks } from "./taskPlacement";
import { useCalendarData } from "./useCalendarData";
import { useCalendarSpan } from "./useCalendarSpan";
import { useDayNotes } from "./useDayNotes";
import { useRoutineDays } from "./useRoutineDays";
import { useTaskDayPanel } from "./useTaskDayPanel";
import type { TaskCalendarProps } from "./calendarProps";
import type { TaskRowOut } from "../../../api/tasks";
import { ErrorNotice } from "../../ErrorNotice";
import { SCREEN_BOARD_CALENDAR } from "../constants";
import { MonthNav } from "../MonthNav";
import { useReschedule } from "../useReschedule";
import { useLiveState } from "../../../hooks/useLiveStore";
import { useScreenToggle } from "../../../hooks/useScreenToggle";
import { Button } from "../../../ui/Button";
import { todayIn, type IsoDay } from "../../../ui/date/dates";

/** The day a month opens on: today in today's month, else the month's first day. */
export const openingDay = (month: string, today: IsoDay): IsoDay => (monthOfDay(today) === month ? today : `${month}-01`);

// The Tasks Calendar on a phone (clean calendar, 2026-10-26): a month grid of marks (task dots, a bell, a repeat mark,
// bot initials), a one-line legend, and the picked day's Tasks, Reminders and Routines under it. Today is picked to
// start; the arrows move by month and Today comes back. Show's Routines, Done and Made by bots apply to both.
export function TaskAgenda({ projects, onOpen, scope, ownDone }: TaskCalendarProps) {
  const live = useLiveState();
  const version = live.boardVersion;
  const span = useCalendarSpan();
  const today = todayIn();
  const days = useMemo(() => monthDays(span.month), [span.month]);
  const data = useCalendarData(days[0], days[days.length - 1], version.tasks, version.money, scope, ownDone);
  const notes = useDayNotes(days[0], days[days.length - 1], version.dayNotes);
  const [showRoutines] = useScreenToggle(SCREEN_BOARD_CALENDAR, "routines");
  const routines = useRoutineDays({ first: days[0], last: days[days.length - 1], show: showRoutines });
  const reschedule = useReschedule(data.reload);
  const [pickedRaw, setPicked] = useState<IsoDay | null>(null);
  const picked = pickedRaw && days.includes(pickedRaw) ? pickedRaw : openingDay(span.month, today);
  const tasks = useMemo(() => data.tasks ?? [], [data.tasks]);
  const placed = useMemo(() => placeTasks(tasks, today, days), [tasks, today, days]);
  const marks = useMemo(() => buildDayMarks({ placed, tasks, routines }), [placed, tasks, routines]);
  const plan = useMemo(() => dayPlan(picked, { placed, tasks, routines, today }), [picked, placed, tasks, routines, today]);
  const project = (task: TaskRowOut) => (task.project_id ? projects.get(task.project_id) : undefined);
  const { wrap, add, noteMark } = useTaskDayPanel({
    today, placed, notes, project, spend: data.spend, onOpen, onChanged: data.reload,
    onReschedule: (task, pick) => void reschedule.one(task, pick),
  });
  const goMonth = (next: string) => { setPicked(null); span.goMonth(next); };

  return (
    <section className="taskcal agenda" aria-label="Task calendar">
      <MonthNav month={span.month} thisMonth={monthOfDay(today)} onPick={goMonth} allowFuture>
        {span.month === monthOfDay(today) ? null : <Button variant="ghost" size="sm" onClick={() => goMonth(monthOfDay(today))}>Today</Button>}
      </MonthNav>
      {data.error ? <ErrorNotice message={data.error} onRetry={data.reload} /> : null}
      <MarksMonthGrid days={days} month={span.month} today={today} picked={picked} marks={marks} bots={live.bots}
        project={project} onPick={setPicked} />
      <MarksLegend />
      {data.tasks === null && !data.error ? <p className="board-loading">Loading&hellip;</p> : null}
      <MarksDayPanel day={picked} today={today} plan={plan} notes={notes} bots={live.bots} project={project} onOpen={onOpen}
        onAdd={() => add(picked)} head={(content) => wrap(picked, content)} noteMark={noteMark(picked)} />
    </section>
  );
}
