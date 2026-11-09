import { useState } from "react";
import { ErrorNotice } from "../../ErrorNotice";
import { dayLabel, formatMoney } from "../money";
import { useProjects } from "../../tasks/useProjects";
import * as moneyApi from "../../../api/money";
import { describeError } from "../../../api/client";
import type { RangeExpenseOut } from "../../../api/money";
import { Button } from "../../../ui/Button";
import { Select } from "../../../ui/Select";
import { useToast } from "../../../ui/Toast";

export interface GeneralInboxProps {
  expenses: readonly RangeExpenseOut[];
  hasMore: boolean;
  onMore: () => void;
  onMoved: () => void; // reload: something moved, or an Undo put it back
  onDone: () => void;
}

const moved = (count: number) => `${count} ${count === 1 ? "expense" : "expenses"}`;

// Undo: each moved expense goes back to the project it came from (the route says which, per id).
async function putBack(result: Array<{ id: string; from_project_id: string }>): Promise<void> {
  const byProject = new Map<string, string[]>();
  for (const { id, from_project_id: from } of result) byProject.set(from, [...(byProject.get(from) ?? []), id]);
  for (const [project, ids] of byProject) await moneyApi.moveExpenses(ids, project);
}

// The General inbox (Task 15 addendum): expenses with no project, picked and moved to one, all or none. A bar
// says "N of M picked" over a Move to… menu, Move and Done; Undo moves them back to where they came from.
export function GeneralInbox({ expenses, hasMore, onMore, onMoved, onDone }: GeneralInboxProps) {
  const toast = useToast();
  const projects = useProjects(true);
  const [picked, setPicked] = useState<ReadonlySet<string>>(new Set());
  const [target, setTarget] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const options = projects.map((project) => ({ value: project.id, label: project.name, disabled: project.status === "archived" }));
  const chosen = projects.find((project) => project.id === target);
  const toggle = (id: string) => setPicked((now) => {
    const next = new Set(now);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });
  const allPicked = expenses.length > 0 && picked.size === expenses.length;
  const move = async () => {
    if (!chosen || picked.size === 0 || busy) return;
    setBusy(true);
    setProblem(null);
    try {
      const { moved: result } = await moneyApi.moveExpenses([...picked], chosen.id);
      setPicked(new Set());
      toast.show(`Moved ${moved(result.length)} to ${chosen.name}`, { action: { label: "Undo", run: () => {
        putBack(result).catch((err: unknown) => toast.show(describeError(err), { tone: "danger" })).finally(onMoved);
      } } });
      onMoved();
    } catch (err) {
      setProblem(describeError(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="inbox">
      <div className="inbox-bar">
        <b>No project</b>
        <span className="inbox-bar__count">{picked.size} of {expenses.length} picked</span>
        <Button variant="ghost" size="sm" onClick={() => setPicked(allPicked ? new Set() : new Set(expenses.map((e) => e.id)))}>
          {allPicked ? "Select none" : "Select all"}
        </Button>
        <span className="inbox-bar__end">
          <Select label="Move to…" placeholder="Move to…" size="sm" value={target} options={options} onChange={setTarget} />
          <Button variant="primary" size="sm" disabled={busy || picked.size === 0 || !chosen} onClick={() => void move()}>Move</Button>
          <Button variant="ghost" size="sm" onClick={onDone}>Done</Button>
        </span>
      </div>
      {problem ? <ErrorNotice message={problem} /> : null}
      {expenses.length === 0 ? <p className="board-empty">Nothing waiting: every expense has a project.</p> : (
        <ul className="xp-list" aria-label="Expenses without a project">
          {expenses.map((expense) => (
            <li key={expense.id} className="xp xp--pick">
              <label className="xp__pick">
                <input type="checkbox" aria-label={expense.description || "Expense"} checked={picked.has(expense.id)}
                  onChange={() => toggle(expense.id)} />
                <span className="xp__what">
                  <span className="xp__n">{expense.description || "Expense"}</span>
                  {expense.vendor ? <span className="xp__vendor">{expense.vendor}</span> : null}
                </span>
                <span className="xp__tag">{dayLabel(expense.spent_at)}</span>
                <span className="xp__amt">{formatMoney(expense.amount, expense.currency)}</span>
              </label>
            </li>
          ))}
        </ul>
      )}
      {hasMore ? <Button variant="ghost" size="sm" onClick={onMore}>Show more</Button> : null}
    </div>
  );
}
