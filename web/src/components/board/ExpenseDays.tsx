import { useMemo } from "react";
import { ExpenseRow } from "./ExpenseList";
import type { ProjectChoice } from "./ExpenseEditRow";
import type { ExpenseActions } from "./useExpenseActions";
import { currencyList, dayLabel } from "./money";
import { useProjects } from "../tasks/useProjects";
import type { MoneyRangeOut } from "../../api/money";
import { addDays, todayIn } from "../../ui/date/dates";

export interface ExpenseDaysProps {
  data: MoneyRangeOut;
  showProject: boolean; // false on a project page, where every row is that project
  actions: ExpenseActions;
  today?: string; // the account's today, "YYYY-MM-DD" (tests pass one)
  only?: string; // show just this day's group (By days)
}

/** "Today", "Yesterday" or "Sun 18 Oct". */
export function dayHeading(day: string, today: string): string {
  if (day === today) return "Today";
  return day === addDays(today, -1) ? "Yesterday" : dayLabel(day);
}

// The projects an edited expense may move to: every live one, and General (the projects list hides it).
export function useChoices(generalId: string | null): readonly ProjectChoice[] {
  const projects = useProjects(true);
  return useMemo(() => [
    ...projects.map((project): ProjectChoice => ({ id: project.id, name: project.name, archived: project.status === "archived" })),
    ...(generalId ? [{ id: generalId, name: "General", archived: false }] : []),
  ], [projects, generalId]);
}

// Expenses grouped by day (Board redesign G9): a heading per day with the day's totals per currency, all the
// server's, then that day's rows. Nothing is added here.
export function ExpenseDays({ data, showProject, actions, today = todayIn(), only }: ExpenseDaysProps) {
  const choices = useChoices(data.general_project_id);
  const days = data.days.filter((day) => only === undefined || day.day === only);
  if (days.length === 0) return <p className="board-empty">No expenses in this range.</p>;
  return (
    <ul className="xp-list" aria-label="Expenses">
      {days.flatMap((day) => [
        <li key={`day-${day.day}`} role="presentation" className="xp-day" data-testid="xp-day">
          <span>{dayHeading(day.day, today)}</span>
          <span className="num">{currencyList(day.totals)}</span>
        </li>,
        ...data.expenses.filter((expense) => expense.spent_at === day.day).map((expense) => (
          <ExpenseRow key={expense.id} expense={expense} currency={data.currency} showProject={showProject}
            actions={actions} projects={choices} />
        )),
      ])}
    </ul>
  );
}
