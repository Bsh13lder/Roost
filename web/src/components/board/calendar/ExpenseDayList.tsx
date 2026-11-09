import { useChoices } from "../ExpenseDays";
import { ExpenseRow } from "../ExpenseList";
import type { MoneyRangeOut } from "../../../api/money";
import type { ExpenseActions } from "../useExpenseActions";
import type { IsoDay } from "../../../ui/date/dates";

export interface ExpenseDayListProps {
  range: MoneyRangeOut;
  day: IsoDay;
  actions: ExpenseActions;
}

// A day's expenses as G9's rows (edit, void and delete with Undo all work here), void ones struck through.
export function ExpenseDayList({ range, day, actions }: ExpenseDayListProps) {
  const choices = useChoices(range.general_project_id);
  const rows = range.expenses.filter((expense) => expense.spent_at === day);
  if (rows.length === 0) return <p className="dpop__none">No expenses.</p>;
  return (
    <ul className="xp-list" aria-label="Expenses">
      {rows.map((expense) => (
        <ExpenseRow key={expense.id} expense={expense} currency={range.currency} showProject actions={actions} projects={choices} />
      ))}
    </ul>
  );
}
