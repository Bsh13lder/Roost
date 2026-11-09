import { useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { ExpenseLine } from "./ExpenseLine";
import { ExpenseDays } from "./ExpenseDays";
import { MonthNav } from "./MonthNav";
import { PastMonth } from "./PastMonth";
import { formatMoney, zoneMonth, monthLabel } from "./money";
import { useExpenseActions } from "./useExpenseActions";
import { useMoneyMonth, type MonthData } from "./useMoneyMonth";
import { useLiveState } from "../../hooks/useLiveStore";
import type { ProjectOut } from "../../api/types";

// The project a MoneyBoard is narrowed to: a project page's Money tab (H14).
export type MoneyProject = Pick<ProjectOut, "id" | "name" | "currency">;

interface ProjectMonthProps {
  data: MonthData;
  project: MoneyProject;
  isThisMonth: boolean;
}

// One project's month: what it spent in its own currency, from its row of the summary.
function ProjectMonthTotals({ data, project, isThisMonth }: ProjectMonthProps) {
  if (data.range.expenses.length === 0) {
    return isThisMonth
      ? <p className="board-empty">Nothing spent on this project yet this month.</p>
      : <p className="board-empty">Nothing spent on this project in {monthLabel(data.month)}.</p>;
  }
  const row = data.summary.by_project.find((candidate) => candidate.project_id === project.id);
  if (!row) return null;
  return (
    <>
      <p className="money-board__total">Spent <strong>{formatMoney(row.spent, row.currency)}</strong></p>
      {Object.entries(row.other_currencies).map(([code, total]) => (
        <p key={code} className="money-board__other">Also {formatMoney(total, code)} (not in the total)</p>
      ))}
    </>
  );
}

// A project page's Money tab: the expense line fixed to the project, then that project's month only. Reloads whenever a
// money_changed frame arrives (a bot or another tab logged one).
export function ProjectMoneyBoard({ initialMonth, project }: { initialMonth?: string; project: MoneyProject }) {
  const live = useLiveState();
  const [month, setMonth] = useState(() => initialMonth ?? zoneMonth(new Date()));
  const { data, error, report, load } = useMoneyMonth(month, live.boardVersion.money, project.id);
  const actions = useExpenseActions(load, report);
  const thisMonth = zoneMonth(new Date());
  const atThisMonth = month >= thisMonth; // new expenses land today, so the form lives on this month
  return (
    <section className="money-board" aria-label="Money">
      <ExpenseLine projectId={project.id} onAdded={load}
        placeholder={`Add an expense to ${project.name}… “€45 paint yesterday vendor:Leroy”`} />
      <MonthNav month={month} thisMonth={thisMonth} onPick={setMonth} />
      {error ? <ErrorNotice message={error} onRetry={load} /> : null}
      {data ? <ProjectMonthTotals data={data} project={project} isThisMonth={atThisMonth} /> : null}
      {!data && !error ? <p className="board-loading">Loading&hellip;</p> : null}
      {atThisMonth ? null : <PastMonth month={month} thisMonth={thisMonth} onBack={() => setMonth(thisMonth)} />}
      {data && data.range.expenses.length > 0 ? (
        <ExpenseDays data={data.range} showProject={false} actions={actions} />
      ) : null}
    </section>
  );
}
