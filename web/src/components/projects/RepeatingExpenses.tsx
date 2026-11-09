import { useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { cadenceText } from "./projects";
import { AMOUNT_HELP, MAX_AMOUNT_TEXT, parseAmountInput } from "../board/money";
import * as moneyApi from "../../api/money";
import type { RecurringOut } from "../../api/money";
import { describeError } from "../../api/client";
import { Button } from "../../ui/Button";
import { Input } from "../../ui/Input";

const name = (rule: RecurringOut) => rule.note ?? "Charge";

interface RuleProps {
  rule: RecurringOut;
  onChanged: () => void;
}

function EditRule({ rule, onChanged, onClose }: RuleProps & { onClose: () => void }) {
  const [amount, setAmount] = useState(rule.amount);
  const [note, setNote] = useState(rule.note ?? "");
  const [error, setError] = useState<string | null>(null);
  const save = () => {
    const parsed = parseAmountInput(amount);
    if (parsed === null) { setError(AMOUNT_HELP); return; }
    moneyApi.updateRecurring(rule.id, { amount: parsed, note: note.trim() || null })
      .then(() => { onClose(); onChanged(); }).catch((err: unknown) => setError(describeError(err)));
  };
  return (
    <form className="charge charge--edit" onSubmit={(event) => { event.preventDefault(); save(); }}>
      <Input aria-label="Amount" inputMode="decimal" value={amount} maxLength={MAX_AMOUNT_TEXT}
        onChange={(event) => setAmount(event.target.value)} />
      <Input aria-label="Note" value={note} onChange={(event) => setNote(event.target.value)} />
      <Button type="submit" size="sm" variant="primary">Save</Button>
      <Button size="sm" variant="ghost" onClick={onClose}>Cancel</Button>
      {error ? <ErrorNotice message={error} /> : null}
    </form>
  );
}

function RuleRow({ rule, onChanged }: RuleProps) {
  const [mode, setMode] = useState<"view" | "edit" | "stop">("view");
  const [error, setError] = useState<string | null>(null);
  const stop = () => moneyApi.stopRecurring(rule.id).then(onChanged).catch((err: unknown) => setError(describeError(err)));
  if (mode === "edit") return <li><EditRule rule={rule} onChanged={onChanged} onClose={() => setMode("view")} /></li>;
  return (
    <li className="charge">
      <span>{name(rule)} <span className="faint">· {cadenceText(rule.cadence, rule.anchor_day)}</span></span>
      <span className="charge__actions">
        {mode === "stop" ? (
          <>
            <Button size="sm" variant="danger" onClick={() => { void stop(); }}>Yes, stop it</Button>
            <Button size="sm" variant="ghost" onClick={() => setMode("view")}>Keep</Button>
          </>
        ) : (
          <>
            <Button size="sm" variant="ghost" aria-label={`Edit ${name(rule)}`} onClick={() => setMode("edit")}>Edit</Button>
            <Button size="sm" variant="ghost" aria-label={`Stop ${name(rule)}`} onClick={() => setMode("stop")}>Stop</Button>
          </>
        )}
      </span>
      {error ? <ErrorNotice message={error} /> : null}
    </li>
  );
}

// "Repeating": each rule with Edit and Stop (G13). Stop asks once, then ends the rule; the charges it made stay.
export function RepeatingExpenses({ rules, onChanged }: { rules: readonly RecurringOut[]; onChanged: () => void }) {
  return (
    <section className="money-card side-card" aria-label="Repeating charges">
      <h2 className="side-card__title">Repeating</h2>
      {rules.length === 0 ? <p className="side-card__empty">Type “monthly” after an expense to repeat it.</p> : (
        <ul className="charge-list">{rules.map((rule) => <RuleRow key={rule.id} rule={rule} onChanged={onChanged} />)}</ul>
      )}
    </section>
  );
}
