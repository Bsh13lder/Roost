import { useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { Button } from "../../ui/Button";
import { getApproval } from "../../api/approvals";
import { describeError } from "../../api/client";
import type { ApprovalRowOut } from "../../api/types";
import { DRAFT_ROW_KEY, OPEN_FULL_ROWS } from "./constants";

// A Send card's text row: shown whole, scrolling in its own box when long (an older row may carry no key).
const isDraftRow = (key: string | undefined): boolean => typeof key === "string" && key.startsWith(DRAFT_ROW_KEY);

export interface ArgRowsProps {
  cardId: string;
  stepIndex: number;
  rows: readonly ApprovalRowOut[];
}

// Every argument the step will run with, as label and value (React text only, never markup). The server cuts a long
// value (a bot's instructions, sheet cells) and says so; Open full fetches the whole card the way a diff does.
export function ArgRows({ cardId, stepIndex, rows }: ArgRowsProps) {
  const [full, setFull] = useState<readonly ApprovalRowOut[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const shown = full ?? rows;
  if (shown.length === 0) return null;
  const cut = shown.some((row) => row.truncated);
  const openFull = async () => {
    setBusy(true);
    setError(null);
    try {
      const card = await getApproval(cardId, true);
      const whole = card.steps[stepIndex]?.rows;
      if (whole) setFull(whole);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div>
      <dl className="arg-rows" aria-label="Details">
        {shown.map((row) => (
          <div key={row.key} className="arg-rows__pair">
            <dt className="arg-rows__label">{row.label}</dt>
            <dd className={isDraftRow(row.key) ? "arg-rows__value arg-rows__value--draft" : "arg-rows__value"}>{row.truncated ? `${row.value}…` : row.value}</dd>
          </div>
        ))}
      </dl>
      {cut ? <Button size="sm" variant="ghost" loading={busy} onClick={() => void openFull()}>{OPEN_FULL_ROWS}</Button> : null}
      {error ? <ErrorNotice message={error} /> : null}
    </div>
  );
}
