import type { ReactNode } from "react";
import { MoneyEmpty } from "./BoardEmpty";
import { ExpenseDays } from "./ExpenseDays";
import { ExpenseDaysChart } from "./ExpenseDaysChart";
import { ExpenseLine } from "./ExpenseLine";
import { MoneyToolbar, type MoneyView } from "./MoneyToolbar";
import { PastMonth } from "./PastMonth";
import { DayChip } from "./PeriodPicker";
import { PinnedCards } from "./PinnedCards";
import { RangeSummary } from "./RangeSummary";
import { rangeFor, rangeLabel } from "./dateRanges";
import { GeneralInbox } from "./reports/GeneralInbox";
import { NoProjectChip } from "./reports/NoProjectChip";
import type { useGeneralInbox } from "./reports/useGeneralInbox";
import { dayLabel, monthLabel } from "./money";
import type { ExpenseActions } from "./useExpenseActions";
import type { MonthData } from "./useMoneyMonth";
import type { MoneyRange } from "./useMoneyRange";
import { todayIn } from "../../ui/date/dates";

export interface MoneyMainProps {
  data: MonthData;
  month: string;
  thisMonth: string;
  actions: ExpenseActions;
  range: MoneyRange;
  onAdded: () => void; // the expense line added one: reload
  inbox: ReturnType<typeof useGeneralInbox>; // the expenses with no project: a chip, and the list it opens
  inboxOpen: boolean; // the inbox replaces the expense list
  onToggleInbox: () => void;
  onBack: () => void; // from a past month to this one
  calendar: ReactNode; // the Calendar view (G12), a lazy chunk the board owns
}

const VIEWS: ReadonlyArray<{ id: MoneyView; label: string }> = [
  { id: "list", label: "List" }, { id: "days", label: "By days" }, { id: "cal", label: "Calendar" },
];

// The summary line under the filter: the server's count and totals for the range, or for the picked day.
function Summary({ range, currency }: { range: MoneyRange; currency: string }) {
  const { shown, preset, custom, day } = range;
  if (!shown || (!preset && !day)) return null;
  const entry = day ? shown.days.find((candidate) => candidate.day === day) : null;
  const label = preset ? rangeLabel(preset, custom ?? rangeFor("today", todayIn())) : "";
  return (
    <RangeSummary count={day ? entry?.count ?? 0 : shown.summary.count} totals={day ? entry?.totals ?? {} : shown.summary.totals}
      currency={currency} label={label} day={day ? dayLabel(day) : null} />
  );
}

// The Money tab's main column: the expense line, Pinned, the view switch, the picked day's chip, the period's
// summary, and the expenses by day (List) or the strip of bars (By days). The period is picked beside the month nav.
export function MoneyMain(props: MoneyMainProps) {
  const { data, month, thisMonth, actions, range, onAdded, inbox, inboxOpen, onToggleInbox, onBack, calendar } = props;
  const { summary } = data;
  const { shown } = range;
  const chip = <NoProjectChip count={inbox.expenses.length} more={inbox.hasMore} open={inboxOpen} onToggle={onToggleInbox} />;
  if (inboxOpen) {
    return (
      <div className="money-main">
        <div className="mtools">{chip}</div>
        <GeneralInbox expenses={inbox.expenses} hasMore={inbox.hasMore} onMore={inbox.more} onDone={onToggleInbox}
          onMoved={() => { inbox.reload(); onAdded(); }} />
      </div>
    );
  }
  const colors = Object.fromEntries(summary.by_project.map((row) => [row.project_id, row.color]));
  const calendarView = range.view === "cal"; // the month follows the month nav; the date filter and its summary stay out
  const ranged = range.preset !== null && !calendarView;
  const monthEmpty = !ranged && summary.expense_count === 0 && data.range.expenses.length === 0;
  return (
    <div className="money-main">
      <ExpenseLine onAdded={onAdded} />
      {month >= thisMonth ? null : <PastMonth month={month} thisMonth={thisMonth} onBack={onBack} />}
      <PinnedCards projects={summary.pinned_projects} expenses={summary.pinned_expenses} colors={colors}
        onUnstar={(id) => actions.star(id, false)} />
      <MoneyToolbar views={VIEWS} view={range.view} onView={range.setView}>{calendarView ? null : chip}</MoneyToolbar>
      {!calendarView && range.day ? <DayChip day={range.day} onClear={() => range.setDay(null)} /> : null}
      {calendarView ? null : <Summary range={range} currency={summary.currency} />}
      {calendarView ? calendar : null}
      {range.error && !calendarView ? <p className="board-empty" role="alert">{range.error}</p> : null}
      {calendarView ? null : !shown ? <p className="board-loading">Loading&hellip;</p> : monthEmpty ? (
        month >= thisMonth ? <MoneyEmpty /> : <p className="board-empty">Nothing spent in {monthLabel(month)}.</p>
      ) : range.view === "days" ? (
        <ExpenseDaysChart data={shown} selected={range.day} onPick={range.setDay} actions={actions} />
      ) : (
        <ExpenseDays data={shown} showProject actions={actions} only={range.day ?? undefined} />
      )}
    </div>
  );
}
