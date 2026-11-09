import type { ReactNode } from "react";
import { monthLabel, shiftMonth } from "./money";
import { IconButton } from "../../ui/IconButton";

export interface MonthNavProps {
  month: string; // "YYYY-MM"
  thisMonth: string; // the month today falls in, on the account's calendar: › stops here
  onPick: (month: string) => void;
  children?: ReactNode; // what sits at the right, such as Export CSV
  beside?: ReactNode; // what sits right after the arrows, such as the Money tab's period dropdown
  allowFuture?: boolean; // › goes on past this month (the task calendar looks ahead; the money calendar does not)
  unit?: string; // "month" (default) or "week": names the arrows
  label?: string; // the heading, instead of the month's name ("19–25 Oct")
  onShift?: (step: -1 | 1) => void; // the arrows, instead of moving by a month
  nextDisabled?: boolean;
}

// ‹ October 2026 › (Board redesign G8; the money calendar G11 reuses it). The next month is disabled on the current one.
export function MonthNav({
  month, thisMonth, onPick, children, beside, allowFuture = false, unit = "month", label, onShift, nextDisabled,
}: MonthNavProps) {
  const move = (step: -1 | 1) => (onShift ? onShift(step) : onPick(shiftMonth(month, step)));
  return (
    <header className="month-nav">
      <IconButton label={`Previous ${unit}`} icon={<span aria-hidden="true">‹</span>} tooltip={false}
        onClick={() => move(-1)} />
      <h2 className="month-nav__month">{label ?? monthLabel(month)}</h2>
      <IconButton label={`Next ${unit}`} icon={<span aria-hidden="true">›</span>} tooltip={false}
        disabled={nextDisabled ?? (!allowFuture && month >= thisMonth)} onClick={() => move(1)} />
      {beside}
      {children ? <span className="month-nav__end">{children}</span> : null}
    </header>
  );
}
