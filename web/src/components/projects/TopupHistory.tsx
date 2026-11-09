import { useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { TopupForm } from "./TopupForm";
import { AMOUNT_HELP, MAX_AMOUNT_TEXT, formatMoney, parseAmountInput } from "../board/money";
import { momentDay, signedMoney, topupLabel } from "./projects";
import * as projectsApi from "../../api/projects";
import { describeError } from "../../api/client";
import type { TopupOut } from "../../api/types";

export interface TopupHistoryProps {
  topups: readonly TopupOut[]; // newest first, undone ones included (H4)
  onChanged: () => void;
}

// A credit shows its amount; an edit shows the change it made, with its sign.
function shownAmount(topup: TopupOut): string {
  return topup.kind === "credit" ? formatMoney(topup.amount, topup.currency) : signedMoney(topup.amount, topup.currency);
}

interface TopupRowProps {
  topup: TopupOut;
  onChange: () => void;
  onUndo: () => void;
}

function TopupRow({ topup, onChange, onUndo }: TopupRowProps) {
  const amount = shownAmount(topup);
  const live = topup.can_change; // the server's say-so: not undone, not taken back by a cleared budget, not an edit row
  return (
    <li className={`topup-row${topup.undone ? " topup-row--undone" : ""}`}>
      <span className="topup-row__day">{momentDay(topup.created_at)}</span>
      <span className="topup-row__what">
        <span className="topup-row__label">{topupLabel(topup)}</span>
        {topup.source ? <span className="topup-row__source">{topup.source}</span> : null}
        {topup.undone ? <span className="board-chip">undone</span> : null}
      </span>
      <span className="topup-row__amount">{amount}</span>
      {live ? (
        <span className="topup-row__actions">
          <button type="button" className="btn btn--quiet btn--small" aria-label={`Change the top-up of ${amount}`}
            onClick={onChange}>Change</button>
          <button type="button" className="btn btn--quiet btn--small" aria-label={`Undo the top-up of ${amount}`}
            onClick={onUndo}>Undo</button>
        </span>
      ) : null}
    </li>
  );
}

interface ChangeFormProps {
  topup: TopupOut;
  onDone: () => void;
  onCancel: () => void;
}

// The top-up's new amount; the server writes the difference as a "Top-up changed" row (H4).
function TopupChangeForm({ topup, onDone, onCancel }: ChangeFormProps) {
  const [amount, setAmount] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const save = async () => {
    const parsed = parseAmountInput(amount);
    if (parsed === null) {
      setError(AMOUNT_HELP);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await projectsApi.editTopup(topup.id, parsed);
      onDone();
    } catch (err) {
      setError(describeError(err));
      setBusy(false);
    }
  };
  return (
    <li className="topup-row topup-row--editing">
      <form className="topup-change" aria-label={`Change the top-up of ${shownAmount(topup)}`}
        onSubmit={(event) => { event.preventDefault(); void save(); }}>
        <input className="input" aria-label="New amount" inputMode="decimal" placeholder="New amount" value={amount}
          maxLength={MAX_AMOUNT_TEXT} onChange={(e) => setAmount(e.target.value)} />
        <button type="submit" className="btn btn--primary btn--small" disabled={busy}>Save</button>
        <button type="button" className="btn btn--quiet btn--small" onClick={onCancel}>Cancel</button>
        {error ? <ErrorNotice message={error} /> : null}
      </form>
    </li>
  );
}

export function TopupHistory({ topups, onChanged }: TopupHistoryProps) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const undo = (topupId: string) => {
    setError(null);
    projectsApi.undoTopup(topupId).then(onChanged).catch((err: unknown) => setError(describeError(err)));
  };
  const doneEditing = () => { setEditingId(null); onChanged(); };
  if (topups.length === 0) return <p className="board-empty">No top-ups yet.</p>;
  return (
    <>
      {error ? <ErrorNotice message={error} /> : null}
      <ul className="topup-list" aria-label="Top-up history">
        {topups.map((topup) => (topup.id === editingId
          ? <TopupChangeForm key={topup.id} topup={topup} onDone={doneEditing} onCancel={() => setEditingId(null)} />
          : <TopupRow key={topup.id} topup={topup} onChange={() => setEditingId(topup.id)} onUndo={() => undo(topup.id)} />))}
      </ul>
    </>
  );
}

export interface TopupsCardProps {
  projectId: string;
  topups: readonly TopupOut[];
  onChanged: () => void;
}

// The Top-ups card of a project's Money tab (G13). The history is folded behind its count, and the form
// opens only on Add top-up, which turns into Cancel while it is open.
export function TopupsCard({ projectId, topups, onChanged }: TopupsCardProps) {
  const [open, setOpen] = useState(false);
  const [adding, setAdding] = useState(false);
  const added = () => { setAdding(false); onChanged(); };
  return (
    <section className="money-card side-card" aria-label="Top-ups">
      <div className="side-card__head">
        <button type="button" className="side-card__fold" aria-expanded={open} onClick={() => setOpen((now) => !now)}>
          <span className="side-card__title">Top-ups</span> <span className="count">{topups.length}</span>
        </button>
        <button type="button" className="btn btn--ghost btn--sm" onClick={() => setAdding((now) => !now)}>
          {adding ? "Cancel" : "Add top-up"}
        </button>
      </div>
      {adding ? <TopupForm projectId={projectId} onAdded={added} /> : null}
      {open ? <TopupHistory topups={topups} onChanged={onChanged} /> : null}
    </section>
  );
}
