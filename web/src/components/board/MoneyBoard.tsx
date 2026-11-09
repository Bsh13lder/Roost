import { lazy, Suspense, useCallback, useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { BudgetList } from "./BudgetList";
import { MoneyMain } from "./MoneyMain";
import { ReportsButton } from "./reports/ReportsButton";
import { useGeneralInbox } from "./reports/useGeneralInbox";
import { MoneySummaryCards } from "./MoneySummaryCards";
import { MonthNav } from "./MonthNav";
import { PeriodPicker } from "./PeriodPicker";
import type { DayRange } from "./dateRanges";
import { ProjectMoneyBoard, type MoneyProject } from "./ProjectMoneyBoard";
import { zoneMonth, monthLabel } from "./money";
import { useExpenseActions } from "./useExpenseActions";
import { useMoneyMonth } from "./useMoneyMonth";
import { useMoneyRange, type MoneyRange } from "./useMoneyRange";
import { todayIn } from "../../ui/date/dates";
import { useLiveState } from "../../hooks/useLiveStore";
import * as moneyApi from "../../api/money";

// The Calendar view (G12) is its own chunk, with the grid the task calendar shares.
const ExpenseCalendar = lazy(() => import("./calendar/ExpenseCalendar"));

export type { MoneyProject } from "./ProjectMoneyBoard";

export interface MoneyBoardProps {
  initialMonth?: string;
  project?: MoneyProject;
}

// One period picker: the arrows always show a whole month; Today and This week come back to this month, and a
// custom range shows the month it ends in, so the cards and the heading match what is listed.
function usePeriod(range: MoneyRange, setMonth: (month: string) => void, thisMonth: string) {
  const { clearRange, setPreset, applyCustom } = range;
  return {
    pickMonth: (next: string) => { setMonth(next); clearRange(); },
    pickPreset: (next: "today" | "week" | null) => {
      if (!next) { clearRange(); return; }
      setMonth(thisMonth);
      setPreset(next);
    },
    pickCustom: (next: DayRange) => { setMonth(next.to.slice(0, 7)); applyCustom(next); },
  };
}

function MainMoneyBoard({ initialMonth }: { initialMonth?: string }) {
  const version = useLiveState().boardVersion.money;
  const [month, setMonth] = useState(() => initialMonth ?? zoneMonth(new Date()));
  const { data, error, report, load } = useMoneyMonth(month, version);
  const range = useMoneyRange(data?.range ?? null, version);
  const inbox = useGeneralInbox(version);
  const [inboxOpen, setInboxOpen] = useState(false);
  const { reload: reloadRange } = range;
  const { reload: reloadInbox } = inbox;
  const reload = useCallback(() => { load(); reloadRange(); reloadInbox(); }, [load, reloadRange, reloadInbox]);
  const actions = useExpenseActions(reload, report);
  const thisMonth = zoneMonth(new Date());
  const { pickMonth, pickPreset, pickCustom } = usePeriod(range, setMonth, thisMonth);
  const picker = range.view === "cal" ? null : (
    <PeriodPicker preset={range.preset} custom={range.custom} today={todayIn()} onPreset={pickPreset} onCustom={pickCustom} />
  );
  return (
    <section className="money-board" aria-label="Money">
      <MonthNav month={month} thisMonth={thisMonth} onPick={pickMonth} beside={picker}>
        {data ? <ReportsButton rows={data.summary.by_project} monthLabel={monthLabel(month)} /> : null}
        <a className="btn btn--ghost btn--md money-export" href={moneyApi.exportCsvUrl(month)} download>Export CSV</a>
      </MonthNav>
      {error ? <ErrorNotice message={error} onRetry={load} /> : null}
      {data ? <MoneySummaryCards summary={data.summary} showToday={month === thisMonth} /> : null}
      {!data && !error ? <p className="board-loading">Loading&hellip;</p> : null}
      {data ? (
        <div className="money-grid">
          <MoneyMain data={data} month={month} thisMonth={thisMonth} actions={actions} range={range} onAdded={reload}
            inbox={inbox} inboxOpen={inboxOpen} onToggleInbox={() => setInboxOpen((now) => !now)} onBack={() => pickMonth(thisMonth)}
            calendar={(
              <Suspense fallback={<p className="board-loading">Loading&hellip;</p>}>
                <ExpenseCalendar range={data.range} month={month} actions={actions} onChanged={reload} />
              </Suspense>
            )} />
          <aside className="money-side" aria-label="Budgets">
            <BudgetList rows={data.summary.by_project} onChanged={reload} />
          </aside>
        </div>
      ) : null}
    </section>
  );
}

// The user's money for one month on the account's calendar, shared by every bot (D1); with a project, that project's
// month only (ProjectMoneyBoard).
export function MoneyBoard({ initialMonth, project }: MoneyBoardProps) {
  return project
    ? <ProjectMoneyBoard initialMonth={initialMonth} project={project} />
    : <MainMoneyBoard initialMonth={initialMonth} />;
}
