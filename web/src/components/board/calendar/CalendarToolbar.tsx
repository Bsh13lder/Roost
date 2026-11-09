import type { CalendarMode, CalendarSpan } from "./useCalendarSpan";
import { MonthNav } from "../MonthNav";
import { Button } from "../../../ui/Button";
import { Segmented } from "../../../ui/Segmented";
import { monthOfDay } from "./monthCells";
import { todayIn } from "../../../ui/date/dates";

const SPANS = [{ id: "month", label: "Month" }, { id: "week", label: "Week" }] as const;

export interface CalendarToolbarProps {
  span: CalendarSpan;
  allowFuture: boolean;
  onMode: (mode: CalendarMode) => void;
}

// "‹ October 2026 ›" (or "‹ 19–25 Oct ›" in week mode) with the Month / Week switch (G11), and Today once you have
// moved away from today's month or week.
export function CalendarToolbar({ span, allowFuture, onMode }: CalendarToolbarProps) {
  const thisMonth = monthOfDay(todayIn());
  return (
    <div className="caltools">
      <MonthNav month={span.month} thisMonth={thisMonth} onPick={() => undefined} allowFuture={allowFuture}
        unit={span.mode} label={span.label} onShift={span.shift}
        nextDisabled={allowFuture ? false : span.mode === "week" ? span.last >= todayIn() : span.month >= thisMonth}>
        {span.showsToday ? null : <Button variant="ghost" size="sm" onClick={span.goToday}>Today</Button>}
      </MonthNav>
      <Segmented label="Calendar span" options={SPANS} value={span.mode} onChange={onMode} />
    </div>
  );
}
