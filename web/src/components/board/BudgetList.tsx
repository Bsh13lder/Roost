import { useState } from "react";
import { BudgetRow, type BudgetRowData } from "./BudgetRow";
import { PinIcon } from "../icons";
import { ErrorNotice } from "../ErrorNotice";
import { isGeneral } from "../projects/projects";
import { describeError } from "../../api/client";
import { pinProject } from "../../api/projects";
import type { BoardProjectTotalOut } from "../../api/money";
import { IconButton } from "../../ui/IconButton";

export interface BudgetListProps {
  rows: readonly BoardProjectTotalOut[]; // the server's order
  onChanged: () => void; // a pin changed: the Board reloads
}

const asRow = (row: BoardProjectTotalOut): BudgetRowData => ({
  id: row.project_id, name: row.project, color: row.color, currency: row.currency, spent: row.spent,
  month: row.month, total: row.total,
});

// Pinned projects first, each group in the server's order.
const pinnedFirst = (rows: readonly BoardProjectTotalOut[]) => [...rows.filter((row) => row.pinned), ...rows.filter((row) => !row.pinned)];

// "Budgets this month" (Board redesign G8): one row per project, pinned ones on top, then the server's order.
// Hovering a row shows a pin toggle that puts the project at the top (PUT /api/projects/{id}/pin).
export function BudgetList({ rows, onChanged }: BudgetListProps) {
  const [problem, setProblem] = useState<string | null>(null);
  const toggle = (row: BoardProjectTotalOut) => {
    pinProject(row.project_id, !row.pinned).then(() => { setProblem(null); onChanged(); })
      .catch((err: unknown) => setProblem(describeError(err)));
  };
  return (
    <section className="money-card money-side__card" aria-label="Budgets this month">
      <h3 className="money-side__title">Budgets this month</h3>
      {rows.length === 0 ? <p className="money-side__none">Nothing spent yet.</p> : null}
      {pinnedFirst(rows).map((row) => (
        <BudgetRow key={row.project_id} data={asRow(row)} action={isGeneral({ name: row.project }) ? null : (
          <IconButton className="bud__pin" size="sm" pressed={row.pinned} icon={<PinIcon />}
            label={row.pinned ? "Unpin" : "Pin to the top"} onClick={() => toggle(row)} />
        )} />
      ))}
      {problem ? <ErrorNotice message={problem} /> : null}
    </section>
  );
}
