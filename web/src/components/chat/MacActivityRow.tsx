import { useState } from "react";
import { undoActivity } from "../../api/mac";
import { describeError } from "../../api/client";
import type { MessageOut } from "../../api/types";
import { UNDO } from "../approvals/constants";
import { macActivityLine, parseMacActivity } from "../../lib/macActivity";

// A Mac file change as one quiet line, with Undo while the change can still be undone. Undo runs at once with no
// card; its "Undid ..." line arrives as a message of its own, so the button just goes. A refusal (the file changed
// since) is said in plain words.
export function MacActivityRow({ message }: { message: MessageOut }) {
  const data = parseMacActivity(message.body);
  const [spent, setSpent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const undo = async () => {
    setBusy(true);
    setError(null);
    try {
      await undoActivity(message.id);
      setSpent(true);
    } catch (err) {
      setError(describeError(err));
      setSpent(true);
    } finally {
      setBusy(false);
    }
  };
  const canUndo = data !== null && data.undo !== null && data.op !== "undo" && !spent;
  return (
    <li className="message message--activity message--mac">
      <span className="message__activity-text">{macActivityLine(data)}</span>
      {canUndo ? (
        <button type="button" className="mac-activity__undo" disabled={busy} onClick={() => void undo()}>{UNDO}</button>
      ) : null}
      {error ? <span className="mac-activity__error" role="alert">{error}</span> : null}
    </li>
  );
}
