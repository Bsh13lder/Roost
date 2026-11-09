import { useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { Button } from "../../ui/Button";
import { cx } from "../../ui/cx";
import { getApproval } from "../../api/approvals";
import { describeError } from "../../api/client";
import type { ApprovalDiffOut } from "../../api/types";
import { OPEN_FULL_DIFF } from "./constants";

function lineKind(line: string): "add" | "remove" | "note" | "context" {
  if (line.startsWith("+++") || line.startsWith("---") || line.startsWith("@@")) return "note";
  if (line.startsWith("+")) return "add";
  if (line.startsWith("-")) return "remove";
  return "context";
}

export interface DiffViewProps {
  cardId: string;
  stepIndex: number;
  diff: ApprovalDiffOut;
}

// A step's diff: added and removed lines on the diff tokens and a "+n −m lines" count. File text is React text only
// (never markup). The server cuts a diff at 400 lines (a live frame carries counts only); Open full diff fetches it all.
export function DiffView({ cardId, stepIndex, diff }: DiffViewProps) {
  const [full, setFull] = useState<ApprovalDiffOut | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const shown = full ?? diff;
  const openFull = async () => {
    setBusy(true);
    setError(null);
    try {
      const card = await getApproval(cardId, true);
      const whole = card.steps[stepIndex]?.diff;
      if (whole) setFull(whole);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  };
  const lines = shown.text === "" ? [] : shown.text.split("\n");
  return (
    <div className="diff">
      <p className="diff__count">+{shown.plus} −{shown.minus} lines</p>
      {lines.length > 0 ? (
        <pre className="diff__text" tabIndex={0} aria-label="Changes">
          {lines.map((line, index) => (
            // eslint-disable-next-line react/no-array-index-key -- lines have no identity but their place
            <span key={index} className={cx("diff__line", `diff__line--${lineKind(line)}`)}>{line}</span>
          ))}
        </pre>
      ) : null}
      {shown.truncated && !full ? (
        <Button size="sm" variant="ghost" loading={busy} onClick={() => void openFull()}>{OPEN_FULL_DIFF}</Button>
      ) : null}
      {error ? <ErrorNotice message={error} /> : null}
    </div>
  );
}
