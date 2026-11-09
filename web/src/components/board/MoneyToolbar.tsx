import type { ReactNode } from "react";
import { Segmented } from "../../ui/Segmented";

export type MoneyView = "list" | "days" | "cal";

export interface MoneyToolbarProps {
  views: ReadonlyArray<{ id: MoneyView; label: string }>;
  view: MoneyView;
  onView: (view: MoneyView) => void;
  children?: ReactNode; // filter chips after the switch, such as No project
}

// The row over the expense list: the "Expenses view" switch (hidden while it has one choice) and its filter chips.
// Today's figure is the Spent card's sub-line (MoneySummaryCards).
export function MoneyToolbar({ views, view, onView, children }: MoneyToolbarProps) {
  if (views.length < 2 && !children) return null;
  return (
    <div className="mtools">
      {views.length > 1 ? <Segmented label="Expenses view" options={views} value={view} onChange={onView} /> : null}
      {children}
    </div>
  );
}
