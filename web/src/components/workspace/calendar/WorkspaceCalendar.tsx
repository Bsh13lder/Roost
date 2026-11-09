import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { DayAgenda } from "./DayAgenda";
import { DotMonth } from "./DotMonth";
import { CalendarToolbar } from "../../board/calendar/CalendarToolbar";
import type { ProjectLook } from "../../board/calendar/calendarProps";
import { monthOfDay } from "../../board/calendar/monthCells";
import { placeTasks } from "../../board/calendar/taskPlacement";
import { useCalendarTasks, useShownCalendarTasks } from "../../board/calendar/useCalendarData";
import { useCalendarSpan, type CalendarSpan } from "../../board/calendar/useCalendarSpan";
import { useDayNotes } from "../../board/calendar/useDayNotes";
import { useRoutineDays } from "../../board/calendar/useRoutineDays";
import { SCREEN_BOARD_CALENDAR } from "../../board/constants";
import { ShowToggles } from "../../board/ShowToggles";
import { useScreenToggle } from "../../../hooks/useScreenToggle";
import { ErrorNotice } from "../../ErrorNotice";
import { useOpenTask } from "../../tasks/useOpenTask";
import { useProjects } from "../../tasks/useProjects";
import { formatClock } from "../../../lib/chatTime";
import { useLiveState } from "../../../hooks/useLiveStore";
import type { TaskRowOut } from "../../../api/tasks";
import { isIsoDay, todayIn, type IsoDay } from "../../../ui/date/dates";

// The week grid is the Tasks calendar's own (G11), its own chunk; so is the drawer.
const TaskCalendar = lazy(() => import("../../board/calendar/TaskCalendar"));
const TaskDrawer = lazy(() => import("../../tasks/TaskDrawer"));

const DAY_PARAM = "day";
const CLOCK_TICK_MS = 30_000; // the now line moves with the account's clock

// The account's "HH:MM", again every half minute.
function useZoneClock(): string {
  const [now, setNow] = useState(() => formatClock(new Date().toISOString()));
  useEffect(() => {
    const timer = window.setInterval(() => setNow(formatClock(new Date().toISOString())), CLOCK_TICK_MS);
    return () => window.clearInterval(timer);
  }, []);
  return now;
}

// The day picked (?day=): the address's day in the month shown, else today in today's month, else the 1st.
function usePickedDay(month: string, today: IsoDay): [IsoDay, (day: IsoDay) => void] {
  const [params, setParams] = useSearchParams();
  const raw = params.get(DAY_PARAM);
  const picked = raw && isIsoDay(raw) && monthOfDay(raw) === month ? raw : monthOfDay(today) === month ? today : `${month}-01`;
  const pick = (day: IsoDay) => setParams((current) => {
    const next = new URLSearchParams(current);
    next.set(DAY_PARAM, day);
    return next;
  }, { replace: true });
  return [picked, pick];
}

// Each project's name and colour, by id: the week grid's pills and the month's dots.
function useProjectLooks() {
  const projects = useProjects();
  return useMemo(() => {
    const looks: ReadonlyMap<string, ProjectLook> = new Map(projects.map((project) => [project.id, { name: project.name, color: project.color }]));
    const colorOf = (task: TaskRowOut) => (task.project_id ? looks.get(task.project_id)?.color : undefined);
    return { looks, colorOf };
  }, [projects]);
}

interface MonthViewProps {
  span: CalendarSpan;
  colorOf: (task: TaskRowOut) => string | undefined;
  onOpen: (taskId: string) => void;
}

function MonthView({ span, colorOf, onOpen }: MonthViewProps) {
  const version = useLiveState().boardVersion;
  const today = todayIn();
  const now = useZoneClock();
  const found = useCalendarTasks(span.first, span.last, version.tasks);
  const shown = useShownCalendarTasks(found.tasks, true);
  const notes = useDayNotes(span.first, span.last, version.dayNotes);
  const [showRoutines] = useScreenToggle(SCREEN_BOARD_CALENDAR, "routines");
  const routines = useRoutineDays({ first: span.first, last: span.last, show: showRoutines });
  const routineCounts = useMemo(() => new Map([...routines].map(([day, entries]) => [day, entries.length])), [routines]);
  const [picked, pick] = usePickedDay(span.month, today);
  const placed = useMemo(() => placeTasks(shown ?? [], today, span.days), [shown, today, span.days]);
  return (
    <>
      {found.error ? <ErrorNotice message={found.error} onRetry={found.reload} /> : null}
      <DotMonth label={span.label} month={span.month} days={span.days} today={today} picked={picked} placed={placed}
        colorOf={colorOf} onPick={pick} routineCounts={routineCounts} />
      <DayAgenda day={picked} today={today} now={now} tasks={placed.get(picked) ?? []} routines={routines.get(picked) ?? []} notes={notes}
        loaded={found.tasks !== null} colorOf={colorOf} onOpen={onOpen} />
    </>
  );
}

// The Workspace's Calendar (app restructure), a lazy chunk: a month of days with dots and the picked day's agenda
// under it (a now line on today, and the day notes), or the week grid the Tasks calendar has. Its
// show / hide switches (Routines, Done, Made by bots; board toggles) sit under the toolbar and rule both.
export default function WorkspaceCalendar() {
  const span = useCalendarSpan();
  const { openId, open, close } = useOpenTask();
  const { looks, colorOf } = useProjectLooks();
  const toggles = <div className="wcal__toggles"><ShowToggles screen={SCREEN_BOARD_CALENDAR} routines ownDone /></div>;
  return (
    <section className="wcal" aria-label="Calendar">
      {span.mode === "week" ? (
        <>
          {toggles}
          <Suspense fallback={<p className="board-loading">Loading&hellip;</p>}>
            <TaskCalendar projects={looks} onOpen={open} ownDone />
          </Suspense>
        </>
      ) : (
        <>
          <CalendarToolbar span={span} allowFuture onMode={span.setMode} />
          {toggles}
          <MonthView span={span} colorOf={colorOf} onOpen={open} />
        </>
      )}
      {openId ? <Suspense fallback={null}><TaskDrawer taskId={openId} onClose={close} /></Suspense> : null}
    </section>
  );
}
