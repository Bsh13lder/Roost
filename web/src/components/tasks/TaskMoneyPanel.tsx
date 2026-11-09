import { useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { ExpenseLine } from "../board/ExpenseLine";
import { ExpenseList } from "../board/ExpenseList";
import { useExpenseActions } from "../board/useExpenseActions";
import { formatMoney } from "../board/money";
import type { TaskDetailMoneyOut, TaskDetailOut, TaskStepOut } from "../../api/types";
import { Badge } from "../../ui/Badge";
import { Meter } from "../../ui/Meter";
import { Select, type SelectOption } from "../../ui/Select";

const NO_MONEY_TEXT = "Its expenses show here.";
const NO_SLICE_TEXT = "No budget yet. Set one under Budget above.";
const generalText = (currency: string) => `In no project, so its money counts in General, in ${currency}.`;
const LINE_HINT = "Add an expense for this task… try “€12 tiles yesterday”";
const WHOLE_TASK = "task"; // a Select option is never "" (ui/Select.tsx)

// "The whole task" and each step: where in the task the money went.
function forOptions(steps: readonly TaskStepOut[]): ReadonlyArray<SelectOption> {
  return [{ value: WHOLE_TASK, label: "The whole task" }, ...steps.map((step) => ({ value: step.id, label: step.title }))];
}

// The expense line with the task's project and the task fixed, and For (a step) when the task has steps.
function AddForTask({ task, onChanged }: { task: TaskDetailOut; onChanged: () => void }) {
  const [target, setTarget] = useState(WHOLE_TASK);
  const step = task.steps.find((one) => one.id === target);
  const fixed = { projectId: task.project_id ?? null, taskId: task.id, label: step?.title ?? task.title, stepId: step?.id };
  return (
    <div className="task-money__add">
      {task.steps.length > 0 ? (
        <Select label="For" value={target} options={forOptions(task.steps)} onChange={setTarget} size="sm" />
      ) : null}
      <ExpenseLine fixed={fixed} placeholder={LINE_HINT} onAdded={onChanged} />
    </div>
  );
}

// "Also spent: $7.00 · £3.00": spending in other currencies, which no budget counts.
function alsoSpent(money: TaskDetailMoneyOut): string | null {
  const parts = Object.entries(money.other_currencies).map(([code, total]) => formatMoney(total, code));
  return parts.length > 0 ? `Also spent: ${parts.join(" · ")}` : null;
}

// "€80 left" (ok) or "€30 over" (danger).
function LeftBadge({ money }: { money: TaskDetailMoneyOut }) {
  if (money.left === null) return null;
  const over = money.left.startsWith("-");
  const amount = formatMoney(over ? money.left.slice(1) : money.left, money.currency);
  return <Badge tone={over ? "danger" : "ok"}>{amount} {over ? "over" : "left"}</Badge>;
}

// Planned, Spent and Left as the server reckons them, and its bar in the server's tone.
function SliceFigures({ money }: { money: TaskDetailMoneyOut }) {
  if (money.planned === null || money.left === null) return <p className="task-money__line">{NO_SLICE_TEXT}</p>;
  const cells = [["Planned", money.planned], ["Spent", money.spent], ["Left", money.left]] as const;
  return (
    <>
      <div className="money3" role="group" aria-label="Planned, spent and left">
        {cells.map(([label, amount]) => (
          <div key={label}><span className="eyebrow">{label}</span><b>{formatMoney(amount, money.currency)}</b></div>
        ))}
      </div>
      <Meter label="Budget used" value={money.used_percent ?? 0} tone={money.tone ?? "accent"}
        valueText={`${money.used_percent ?? 0}% of the budget used`} />
    </>
  );
}

// The drawer's Money (redesign P3): the task's slice, spent and left (in General's currency for a task in no
// project, owner 2026-10-26), its expenses, and the expense line to add one for the task or one of its steps.
// Keep, star, void and delete (with Undo) act on an expense as on the Board.
export function TaskMoneyPanel({ task, onChanged }: { task: TaskDetailOut; onChanged: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const actions = useExpenseActions(onChanged, setError);
  const { money } = task;
  return (
    <section className="task-drawer__section" aria-label="Money">
      <div className="section__head">
        <h3 className="task-drawer__heading">Money</h3>
        {money ? <LeftBadge money={money} /> : null}
      </div>
      {money && !task.project_id ? <p className="task-money__line">{generalText(money.currency)}</p> : null}
      {money ? <SliceFigures money={money} /> : <p className="task-money__line">{NO_MONEY_TEXT}</p>}
      {money && alsoSpent(money) ? <p className="task-money__line">{alsoSpent(money)}</p> : null}
      {task.expenses.length > 0 ? (
        <ExpenseList expenses={task.expenses} currency={money?.currency ?? task.expenses[0].currency}
          showProject={!task.project_id} actions={actions} />
      ) : null}
      <AddForTask task={task} onChanged={onChanged} />
      {error ? <ErrorNotice message={error} /> : null}
    </section>
  );
}
