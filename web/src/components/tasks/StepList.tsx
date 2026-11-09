import { useState, type FormEvent } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { ChevronDownIcon, ChevronUpIcon, CloseIcon, PencilIcon } from "../icons";
import { formatMoney } from "../board/money";
import { MAX_STEP_TITLE } from "./constants";
import { StepBudget, StepBudgetFigures } from "./StepBudget";
import { stepProgress } from "./progress";
import * as tasksApi from "../../api/tasks";
import { describeError } from "../../api/client";
import type { StepMoneyOut, StepRemovalOut, TaskOut, TaskStepOut } from "../../api/types";
import { Button } from "../../ui/Button";
import { IconButton } from "../../ui/IconButton";
import { Input } from "../../ui/Input";
import { Meter } from "../../ui/Meter";

export interface StepListProps {
  task: TaskOut;
  spent?: Readonly<Record<string, string>>; // what is spent on each step, by id (the server's numbers)
  currency?: string; // the task's currency: its project's, or General's
  money?: Readonly<Record<string, StepMoneyOut>>; // each step's own budget, spent and left (the server's numbers)
  onChanged: () => void; // the drawer reloads the task
}

const NOTHING_SPENT = "0.00";

// One request at a time; the drawer reloads after each, and the server's sentence shows on a refusal.
function useStepAction(onChanged: () => void) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const run = async (request: () => Promise<unknown>, said: (result: unknown) => string | null = () => null) => {
    setBusy(true);
    setError(null);
    try {
      setNote(said(await request()));
      onChanged();
      return true;
    } catch (err) {
      setError(describeError(err));
      return false;
    } finally {
      setBusy(false);
    }
  };
  return { busy, error, note, run };
}

// "Its 1 expense and 2 comments stay on the task." after a delete that moved something, else null.
function movedText(result: unknown): string | null {
  const { moved_expenses: expenses = 0, moved_comments: comments = 0 } = result as Partial<StepRemovalOut>;
  if (!expenses && !comments) return null;
  return `Its ${expenses} expense${expenses === 1 ? "" : "s"} and ${comments} comment${comments === 1 ? "" : "s"} stay on the task.`;
}

interface StepItemProps {
  step: TaskStepOut;
  index: number;
  count: number;
  spent: string | null;
  line: StepMoneyOut | undefined;
  currency: string | undefined;
  busy: boolean;
  act: (request: () => Promise<unknown>, said?: (result: unknown) => string | null) => Promise<boolean>;
  taskId: string;
}

function StepTitle({ step, taskId, busy, act }: Pick<StepItemProps, "step" | "taskId" | "busy" | "act">) {
  const [editing, setEditing] = useState<string | null>(null);
  if (editing === null) {
    return (
      <>
        <span className="step__title">{step.title}</span>
        <IconButton label={`Rename ${step.title}`} icon={<PencilIcon />} size="sm" className="step__action"
          disabled={busy} onClick={() => setEditing(step.title)} />
      </>
    );
  }
  const save = async (event: FormEvent) => {
    event.preventDefault();
    const title = editing.trim();
    if (title && title !== step.title && !(await act(() => tasksApi.updateStep(taskId, step.id, { title })))) return;
    setEditing(null);
  };
  return (
    <form className="step__rename" onSubmit={(event) => void save(event)}>
      <Input aria-label={`New title for ${step.title}`} controlSize="sm" value={editing} maxLength={MAX_STEP_TITLE}
        autoFocus onChange={(e) => setEditing(e.target.value)} />
      <Button type="submit" size="sm" variant="secondary" disabled={busy}>Save</Button>
      <Button size="sm" variant="ghost" onClick={() => setEditing(null)}>Cancel</Button>
    </form>
  );
}

function StepItem({ step, index, count, spent, line, currency, busy, act, taskId }: StepItemProps) {
  const move = (position: number) => act(() => tasksApi.moveStep(taskId, step.id, position));
  return (
    <li className={`step${step.done ? " step--done" : ""}`}>
      <input type="checkbox" className="step__check" aria-label={`Done: ${step.title}`} checked={step.done}
        disabled={busy} onChange={() => void act(() => tasksApi.updateStep(taskId, step.id, { done: !step.done }))} />
      <StepTitle step={step} taskId={taskId} busy={busy} act={act} />
      {line?.planned && currency ? <StepBudgetFigures line={line} currency={currency} /> : null}
      {spent && !line?.planned ? <span className="board-chip">{spent} spent</span> : null}
      {currency ? <StepBudget step={step} taskId={taskId} line={line} currency={currency} busy={busy} act={act} /> : null}
      <IconButton label={`Move ${step.title} up`} icon={<ChevronUpIcon />} size="sm" className="step__action"
        disabled={busy || index === 0} onClick={() => void move(index - 1)} />
      <IconButton label={`Move ${step.title} down`} icon={<ChevronDownIcon />} size="sm" className="step__action"
        disabled={busy || index === count - 1} onClick={() => void move(index + 1)} />
      <IconButton label={`Delete ${step.title}`} icon={<CloseIcon />} size="sm" className="step__action"
        disabled={busy} onClick={() => void act(() => tasksApi.deleteStep(taskId, step.id), movedText)} />
    </li>
  );
}

function AddStep({ taskId, busy, act }: Pick<StepItemProps, "taskId" | "busy" | "act">) {
  const [title, setTitle] = useState("");
  const add = async (event: FormEvent) => {
    event.preventDefault();
    if (title.trim() && (await act(() => tasksApi.addStep(taskId, title.trim())))) setTitle("");
  };
  return (
    <form className="step-add" onSubmit={(event) => void add(event)}>
      <Input aria-label="New step" controlSize="md" placeholder="Add a step…" value={title} maxLength={MAX_STEP_TITLE}
        onChange={(e) => setTitle(e.target.value)} />
      <Button type="submit" size="md" variant="secondary" disabled={busy || !title.trim()}>Add step</Button>
    </form>
  );
}

// The drawer's Steps (redesign P3): progress, then each step with its tick, rename, its own budget (owner,
// 2026-10-26), move up and down, delete and what is spent on it; a new step goes at the end.
export function StepList({ task, spent = {}, currency, money = {}, onChanged }: StepListProps) {
  const { busy, error, note, run } = useStepAction(onChanged);
  const { done, total } = stepProgress(task.steps);
  const spentOn = (step: TaskStepOut) => {
    const amount = spent[step.id];
    return amount && amount !== NOTHING_SPENT && currency ? formatMoney(amount, currency) : null;
  };
  return (
    <section className="task-drawer__section" aria-label="Steps">
      <h3 className="task-drawer__heading">Steps</h3>
      {total > 0 ? (
        <div className="step-progress">
          <Meter label="Steps done" value={done} max={total} valueText={`${done} of ${total} steps done`} />
          <span className="step-progress__text">{done} of {total} done</span>
        </div>
      ) : null}
      {total > 0 ? (
        <ul className="step-list">
          {task.steps.map((step, index) => (
            <StepItem key={step.id} step={step} index={index} count={total} spent={spentOn(step)} line={money[step.id]}
              currency={currency} busy={busy} act={run} taskId={task.id} />
          ))}
        </ul>
      ) : null}
      <AddStep taskId={task.id} busy={busy} act={run} />
      {note ? <p className="step-list__note" role="status">{note}</p> : null}
      {error ? <ErrorNotice message={error} /> : null}
    </section>
  );
}
