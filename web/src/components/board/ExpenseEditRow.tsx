import { useState, type KeyboardEvent } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { AMOUNT_HELP, MAX_AMOUNT_TEXT, MAX_NOTE, parseAmountInput } from "./money";
import { describeError } from "../../api/client";
import type { ExpensePatchIn, RangeExpenseOut } from "../../api/money";
import { Button } from "../../ui/Button";
import { DatePicker } from "../../ui/date/DatePicker";
import { todayIn } from "../../ui/date/dates";
import { PAST_PICKS } from "../../ui/date/picks";
import { Input } from "../../ui/Input";
import { Select } from "../../ui/Select";

export interface ProjectChoice {
  id: string;
  name: string;
  archived: boolean; // an expense can't be moved into an archived project
}

export interface ExpenseEditRowProps {
  expense: RangeExpenseOut;
  projects: readonly ProjectChoice[]; // none: the project can't change (a task's expense stays in its project)
  onSave: (patch: ExpensePatchIn) => Promise<void>;
  onCancel: () => void;
}

const MAX_VENDOR = 80; // roost/constants.py MAX_EXPENSE_VENDOR_LENGTH

// The patch: only the fields that differ from the expense. The amount is read here (a comma decimal works);
// `null` is an amount that can't be read.
function patchOf(expense: RangeExpenseOut, draft: Draft): ExpensePatchIn | null {
  const amount = parseAmountInput(draft.amount);
  if (amount === null) return null;
  return {
    ...(amount !== Number(expense.amount).toFixed(2) ? { amount } : {}),
    ...(draft.note.trim() !== (expense.description ?? "") ? { note: draft.note.trim() } : {}),
    ...(draft.vendor.trim() !== (expense.vendor ?? "") ? { vendor: draft.vendor.trim() } : {}),
    ...(draft.day.trim() && draft.day.trim() !== expense.spent_at ? { spent_at: draft.day.trim() } : {}),
    ...(draft.projectId !== expense.project_id ? { project_id: draft.projectId } : {}),
  };
}

interface Draft {
  amount: string;
  note: string;
  vendor: string;
  day: string;
  projectId: string;
}

// An expense row turned into its fields (Board redesign G9): amount, note, vendor, day and project. Enter saves
// through the gateway, Esc cancels, and a refusal shows its sentence under the row.
export function ExpenseEditRow({ expense, projects, onSave, onCancel }: ExpenseEditRowProps) {
  const [draft, setDraft] = useState<Draft>({
    amount: Number(expense.amount).toFixed(2), note: expense.description ?? "", vendor: expense.vendor ?? "",
    day: expense.spent_at, projectId: expense.project_id,
  });
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const set = (field: keyof Draft) => (value: string) => { setDraft((now) => ({ ...now, [field]: value })); setProblem(null); };

  const save = async () => {
    if (busy) return;
    const patch = patchOf(expense, draft);
    if (patch === null) { setProblem(AMOUNT_HELP); return; }
    if (Object.keys(patch).length === 0) { onCancel(); return; }
    setBusy(true);
    try {
      await onSave(patch);
      onCancel();
    } catch (err) {
      setProblem(describeError(err));
    } finally {
      setBusy(false);
    }
  };
  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key === "Escape") { event.stopPropagation(); onCancel(); }
    else if (event.key === "Enter" && !(event.target instanceof HTMLButtonElement)) { event.preventDefault(); void save(); }
  };
  const choices = projects.map((project) => ({
    value: project.id, label: project.name, disabled: project.archived && project.id !== expense.project_id,
  }));
  return (
    <li className="xp xp--edit" onKeyDown={onKeyDown}>
      <div className="xp-edit__fields">
        <Input controlSize="md" aria-label="Amount" inputMode="decimal" value={draft.amount} maxLength={MAX_AMOUNT_TEXT}
          onChange={(e) => set("amount")(e.target.value)} autoFocus />
        <Input controlSize="md" aria-label="Note" value={draft.note} maxLength={MAX_NOTE}
          onChange={(e) => set("note")(e.target.value)} />
        <Input controlSize="md" aria-label="Vendor" value={draft.vendor} maxLength={MAX_VENDOR} placeholder="Vendor"
          onChange={(e) => set("vendor")(e.target.value)} />
        <DatePicker label="Day" value={draft.day} onChange={set("day")} picks={PAST_PICKS} max={todayIn()} kind="spent" />
        {choices.length > 0 ? (
          <Select label="Project" size="md" value={draft.projectId} options={choices} onChange={set("projectId")} />
        ) : null}
      </div>
      <div className="xp-edit__actions">
        <Button variant="primary" size="sm" disabled={busy} onClick={() => void save()}>Save</Button>
        <Button variant="ghost" size="sm" onClick={onCancel}>Cancel</Button>
      </div>
      {problem ? <div className="xp-edit__problem"><ErrorNotice message={problem} /></div> : null}
    </li>
  );
}
