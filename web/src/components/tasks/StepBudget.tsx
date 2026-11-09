import { useState, type FormEvent } from "react";
import { MAX_AMOUNT_TEXT, formatMoney } from "../board/money";
import * as tasksApi from "../../api/tasks";
import type { StepMoneyOut, TaskStepOut } from "../../api/types";
import { Badge, type BadgeTone } from "../../ui/Badge";
import { Button } from "../../ui/Button";
import { Input } from "../../ui/Input";

type Act = (request: () => Promise<unknown>) => Promise<boolean>;

const TONES: Readonly<Record<NonNullable<StepMoneyOut["tone"]>, BadgeTone>> = { ok: "ok", warn: "warn", over: "danger" };

// "€25.00 of €20.00" and "€5.00 over" / "€15.00 left": the step's own budget, as the server reckons it.
export function StepBudgetFigures({ line, currency }: { line: StepMoneyOut; currency: string }) {
  if (line.planned === null || line.left === null) return null;
  const over = line.left.startsWith("-");
  const left = formatMoney(over ? line.left.slice(1) : line.left, currency);
  return (
    <>
      <span className="board-chip">{formatMoney(line.spent, currency)} of {formatMoney(line.planned, currency)}</span>
      <Badge tone={line.tone ? TONES[line.tone] : "neutral"}>{left} {over ? "over" : "left"}</Badge>
    </>
  );
}

interface StepBudgetProps {
  step: TaskStepOut;
  taskId: string;
  line: StepMoneyOut | undefined;
  currency: string;
  busy: boolean;
  act: Act;
}

// The quiet Budget button on a step, and its small form: the amount as typed (the server reads it), Save, Clear
// when the step has one, and Cancel. The drawer reloads after a save; a refusal shows the server's sentence.
export function StepBudget({ step, taskId, line, currency, busy, act }: StepBudgetProps) {
  const [editing, setEditing] = useState<string | null>(null);
  const planned = line?.planned ?? null;
  if (editing === null) {
    return (
      <Button size="sm" variant="ghost" className="step__action" aria-label={`Budget for ${step.title}`}
        disabled={busy} onClick={() => setEditing(planned ?? "")}>Budget</Button>
    );
  }
  const send = async (budget: string | null) => {
    if (await act(() => tasksApi.updateStep(taskId, step.id, { budget }))) setEditing(null);
  };
  const save = (event: FormEvent) => {
    event.preventDefault();
    const typed = editing.trim();
    void send(typed ? typed : null);
  };
  return (
    <form className="step-budget" onSubmit={save}>
      <Input aria-label={`Budget for ${step.title}, in ${currency}`} controlSize="sm" inputMode="decimal" autoFocus
        value={editing} maxLength={MAX_AMOUNT_TEXT} placeholder="20" onChange={(e) => setEditing(e.target.value)} />
      <Button type="submit" size="sm" variant="secondary" disabled={busy}>Save</Button>
      {planned !== null ? (
        <Button size="sm" variant="ghost" disabled={busy} onClick={() => void send(null)}>Clear budget</Button>
      ) : null}
      <Button size="sm" variant="ghost" onClick={() => setEditing(null)}>Cancel</Button>
    </form>
  );
}
