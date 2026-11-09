import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { describeError } from "../../../api/client";
import { getRange } from "../../../api/money";
import type { TaskRowOut } from "../../../api/tasks";
import { todayIn, type IsoDay } from "../../../ui/date/dates";
import { useShowFinished } from "../../../hooks/useShowFinished";
import { useScreenToggle } from "../../../hooks/useScreenToggle";
import { keepShown } from "../../../lib/finished";
import { keepMade } from "../../../lib/madeBy";
import { SCREEN_BOARD_CALENDAR } from "../constants";
import { ALL_TASKS, parseScope, scopeParam, type TaskScope } from "../taskScope";
import { askTasks } from "../scopedTasks";

export interface CalendarTasks {
  tasks: readonly TaskRowOut[] | null; // null until the first answer
  error: string | null;
  reload: () => void;
}

// The tasks the calendar shows for its first and last visible day (GET /api/tasks?from&to): due in the span, plus
// the late ones when today is in it. Only the newest answer paints; it reloads on every tasks_changed (`version`).
export function useCalendarTasks(first: IsoDay, last: IsoDay, version: number, given: TaskScope = ALL_TASKS): CalendarTasks {
  const scopeKey = scopeParam(given);
  const scope = useMemo(() => parseScope(scopeKey), [scopeKey]);
  const [tasks, setTasks] = useState<readonly TaskRowOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef(0);
  const reload = useCallback(() => {
    const ticket = ++latest.current;
    askTasks(scope, { from: first, to: last })
      .then((found) => { if (ticket === latest.current) { setTasks(found); setError(null); } })
      .catch((err: unknown) => { if (ticket === latest.current) setError(describeError(err)); });
  }, [first, last, scope]);
  useEffect(() => reload(), [reload, version]);
  return { tasks, error, reload };
}

export interface DaySpend {
  currency: string; // the main currency
  byDay: ReadonlyMap<IsoDay, string>; // each day's total in it, as the server added it
}

// What was spent each day in the main currency (GET /api/money/range): the corner of a task cell. The web adds
// nothing. A span wholly in the future has nothing to ask for, and a failed load only leaves the corners bare.
export function useDaySpend(first: IsoDay, last: IsoDay, version: number): DaySpend | null {
  const [spend, setSpend] = useState<DaySpend | null>(null);
  useEffect(() => {
    if (first > todayIn()) { setSpend(null); return undefined; }
    let current = true;
    getRange(first, last)
      .then((range) => {
        if (!current) return;
        const entries = range.days.flatMap((day) => (day.totals[range.currency] ? [[day.day, day.totals[range.currency]] as const] : []));
        setSpend({ currency: range.currency, byDay: new Map(entries) });
      })
      .catch((err: unknown) => console.warn("Could not load the days' spending:", describeError(err)));
    return () => { current = false; };
  }, [first, last, version]);
  return useMemo(() => spend, [spend]);
}

export interface CalendarData extends CalendarTasks {
  spend: DaySpend | null;
}

/** The calendar's show / hide choices applied (board toggles): finished tasks by the calendar's own Done switch
 *  (`ownDone`, the Workspace's Calendar) or else by Show finished, and bot-made ones by its Made by bots. */
export function useShownCalendarTasks(tasks: readonly TaskRowOut[] | null, ownDone = false): readonly TaskRowOut[] | null {
  const [finished] = useShowFinished();
  const [done] = useScreenToggle(SCREEN_BOARD_CALENDAR, "done");
  const [made] = useScreenToggle(SCREEN_BOARD_CALENDAR, "botMade");
  const show = ownDone ? done : finished;
  return useMemo(() => (tasks ? keepMade(keepShown(tasks, show), made) : null), [tasks, show, made]);
}

/** The tasks (of the `scope` the rail picked) and the day's spending for the visible span, with the calendar's
 *  show / hide choices applied. The spending stays the whole day's: a day's corner is what you spent that day. */
export function useCalendarData(first: IsoDay, last: IsoDay, tasksVersion: number, moneyVersion: number,
  scope: TaskScope = ALL_TASKS, ownDone = false): CalendarData {
  const found = useCalendarTasks(first, last, tasksVersion, scope);
  const spend = useDaySpend(first, last, moneyVersion);
  const tasks = useShownCalendarTasks(found.tasks, ownDone);
  return { ...found, tasks, spend };
}
