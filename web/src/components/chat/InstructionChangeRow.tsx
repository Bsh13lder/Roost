import { useState } from "react";
import { undoInstructionChange } from "../../api/instructions";
import { describeError } from "../../api/client";
import type { MessageOut } from "../../api/types";
import { UNDO } from "../approvals/constants";
import { instructionChangeLine, parseInstructionChange } from "../../lib/instructionChange";

// A bot changed a section of its own instructions in your chat (update_my_instructions): one quiet line with Undo.
// Undo restores the text it replaced at once, only while nothing newer changed them; a refusal is said in plain
// words, and the button goes either way.
export function InstructionChangeRow({ message }: { message: MessageOut }) {
  const [data, setData] = useState(() => parseInstructionChange(message.body));
  const [busy, setBusy] = useState(false);
  const [spent, setSpent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const undo = async () => {
    setBusy(true);
    setError(null);
    try {
      const { message: undone } = await undoInstructionChange(message.id);
      setData(parseInstructionChange(undone.body));
    } catch (err) {
      setError(describeError(err));
    } finally {
      setSpent(true);
      setBusy(false);
    }
  };
  const canUndo = data !== null && !data.undone && !spent;
  return (
    <li className="message message--activity message--mac">
      <span className="message__activity-text">{instructionChangeLine(data)}</span>
      {canUndo ? (
        <button type="button" className="mac-activity__undo" disabled={busy} onClick={() => void undo()}>{UNDO}</button>
      ) : null}
      {error ? <span className="mac-activity__error" role="alert">{error}</span> : null}
    </li>
  );
}
