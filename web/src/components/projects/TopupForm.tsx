import { useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { AMOUNT_HELP, MAX_AMOUNT_TEXT, parseAmountInput } from "../board/money";
import { MAX_TOPUP_SOURCE } from "./projects";
import * as projectsApi from "../../api/projects";
import { describeError } from "../../api/client";

export interface TopupFormProps {
  projectId: string;
  onAdded: () => void;
}

// A top-up raises the project's total budget (H4); where it came from is optional.
export function TopupForm({ projectId, onAdded }: TopupFormProps) {
  const [amount, setAmount] = useState("");
  const [source, setSource] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    const parsed = parseAmountInput(amount);
    if (parsed === null) {
      setError(AMOUNT_HELP);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await projectsApi.addTopup(projectId, source.trim() ? { amount: parsed, source: source.trim() } : { amount: parsed });
      setAmount("");
      setSource("");
      onAdded();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="topup-add" onSubmit={(event) => { event.preventDefault(); void submit(); }}>
      <input className="input" aria-label="Top-up amount" inputMode="decimal" placeholder="50,00" value={amount}
        maxLength={MAX_AMOUNT_TEXT} onChange={(e) => setAmount(e.target.value)} />
      <input className="input" aria-label="Where from" placeholder="Where from? e.g. a gift" value={source}
        maxLength={MAX_TOPUP_SOURCE} onChange={(e) => setSource(e.target.value)} />
      <button type="submit" className="btn btn--primary" disabled={busy}>Add top-up</button>
      {error ? <ErrorNotice message={error} /> : null}
    </form>
  );
}
