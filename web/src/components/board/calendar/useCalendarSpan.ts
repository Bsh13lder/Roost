import { useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import { monthDays, monthOfDay, mondayOf, weekDays } from "./monthCells";
import { monthLabel, shiftMonth } from "../money";
import { addDays, dayText, isIsoDay, todayIn, type IsoDay } from "../../../ui/date/dates";

export type CalendarMode = "month" | "week";
const WEEK_DAYS = 7;
const MIDWEEK = 3; // Thursday: the month a week belongs to
const MONTH_PATTERN = /^\d{4}-(0[1-9]|1[0-2])$/;

export interface CalendarSpan {
  mode: CalendarMode;
  month: string; // "YYYY-MM", the grid's month
  days: readonly IsoDay[]; // the visible days
  first: IsoDay;
  last: IsoDay;
  label: string; // "October 2026" or "19–25 Oct"
  setMode: (mode: CalendarMode) => void;
  shift: (step: -1 | 1) => void;
  goMonth: (month: string) => void; // the phone agenda's month, whatever the mode
  showsToday: boolean; // today is in the month (or week) on screen
  goToday: () => void; // back to today's month or week
}

// "19–25 Oct", or "29 Sep – 5 Oct" across two months.
export function weekLabel(days: readonly IsoDay[]): string {
  const first = days[0];
  const last = days[days.length - 1];
  return monthOfDay(first) === monthOfDay(last) ? `${Number(first.slice(-2))}–${dayText(last)}` : `${dayText(first)} – ${dayText(last)}`;
}

// What the calendar shows, kept in the address (?cmode=week&month=2026-10&week=2026-10-19) so a reload or a shared
// link lands in the same place. The month and the week are each remembered, and switching span keeps the day in view.
export function useCalendarSpan(): CalendarSpan {
  const [params, setParams] = useSearchParams();
  const today = todayIn();
  const mode: CalendarMode = params.get("cmode") === "week" ? "week" : "month";
  const monthParam = params.get("month");
  const month = monthParam && MONTH_PATTERN.test(monthParam) ? monthParam : monthOfDay(today);
  const weekParam = params.get("week");
  const monday = mondayOf(weekParam && isIsoDay(weekParam) ? weekParam : today);
  const days = mode === "week" ? weekDays(monday) : monthDays(month);

  const patch = useCallback((changes: Record<string, string | null>) => {
    setParams((current) => {
      const next = new URLSearchParams(current);
      for (const [key, value] of Object.entries(changes)) {
        if (value === null) next.delete(key); else next.set(key, value);
      }
      return next;
    }, { replace: true });
  }, [setParams]);

  const setMode = (next: CalendarMode) => {
    if (next === mode) return;
    if (next === "week") {
      const inView = monthOfDay(today) === month ? today : `${month}-01`;
      patch({ cmode: "week", week: mondayOf(inView) });
    } else {
      patch({ cmode: null, month: monthOfDay(addDays(monday, MIDWEEK)) });
    }
  };
  const shift = (step: -1 | 1) => {
    if (mode === "week") patch({ week: addDays(monday, step * WEEK_DAYS) });
    else patch({ month: shiftMonth(month, step) });
  };
  return {
    mode, month, days, first: days[0], last: days[days.length - 1], setMode, shift,
    goMonth: (next: string) => patch({ month: next }),
    showsToday: mode === "week" ? days.includes(today) : month === monthOfDay(today),
    goToday: () => patch({ month: null, week: null }),
    label: mode === "week" ? weekLabel(days) : monthLabel(month),
  };
}
