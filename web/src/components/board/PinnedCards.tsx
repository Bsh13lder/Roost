import type { CSSProperties } from "react";
import { BudgetRow, type BudgetRowData } from "./BudgetRow";
import { dayLabel, formatAmount } from "./money";
import { PinIcon } from "../icons";
import type { PinnedProjectOut } from "../../api/money";
import type { ExpenseOut } from "../../api/types";

export interface PinnedCardsProps {
  projects: readonly PinnedProjectOut[];
  expenses: readonly ExpenseOut[]; // starred
  colors: Readonly<Record<string, string>>; // a project's colour by id, for a starred expense's dot
  onUnstar: (expenseId: string) => void;
}

const asRow = (project: PinnedProjectOut): BudgetRowData => ({
  id: project.project_id, name: project.project, color: project.color, currency: project.currency,
  spent: project.spent_month, month: project.month, total: project.total,
});

// Pinned (Board redesign G8, §7.3): the user's pinned projects and starred expenses, on top of the tab.
// It hides when there is nothing in it.
export function PinnedCards({ projects, expenses, colors, onUnstar }: PinnedCardsProps) {
  const count = projects.length + expenses.length;
  if (count === 0) return null;
  return (
    <section className="pinned" aria-label="Pinned">
      <div className="pinned__head"><h3 className="pinned__title">Pinned</h3><span className="pinned__count">{count}</span></div>
      <div className="pinned__grid">
        {projects.map((project) => (
          <div key={project.project_id} className="money-card pin">
            <div className="pin__head"><span className="eyebrow">Project</span>
              <span className="pin__mark" title="Pinned"><PinIcon /></span></div>
            <BudgetRow data={asRow(project)} />
          </div>
        ))}
        {expenses.map((expense) => (
          <div key={expense.id} className="money-card pin" style={{ "--pc": colors[expense.project_id] ?? "" } as CSSProperties}>
            <div className="pin__head">
              <span className="money-dot" aria-hidden="true" />
              <span className="pin__note">{expense.description || expense.project}</span>
              <button type="button" className="pin__star" aria-label={`Unstar ${expense.description || expense.project}`}
                onClick={() => onUnstar(expense.id)}>★</button>
            </div>
            <span className="pin__amt">{formatAmount(expense.amount, expense.currency)}</span>
            <span className="pin__sub">{dayLabel(expense.spent_at)} · {expense.project}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
