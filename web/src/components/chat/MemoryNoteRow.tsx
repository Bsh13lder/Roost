import { useState } from "react";
import { ApiError, describeError } from "../../api/client";
import { forgetMemory } from "../../api/memories";
import type { MessageOut } from "../../api/types";
import { parseMemoryNote } from "../../lib/memoryNote";
import { Button } from "../../ui/Button";

type Outcome = { state: "asked" } | { state: "forgot" } | { state: "gone" } | { state: "failed"; message: string };

const ALREADY_FORGOTTEN = "Already forgotten.";

// "Remembered: ..." in the chat, with Undo: forgets that memory (a bot saved it, you may take it back).
export function MemoryNoteRow({ message }: { message: MessageOut }) {
  const note = parseMemoryNote(message.body);
  const [outcome, setOutcome] = useState<Outcome>({ state: "asked" });
  const [busy, setBusy] = useState(false);
  if (!note) return <li className="message message--memory">{message.body}</li>;
  const undo = async () => {
    setBusy(true);
    try {
      await forgetMemory(note.memory_id);
      setOutcome({ state: "forgot" });
    } catch (err) {
      setOutcome(err instanceof ApiError && err.status === 404
        ? { state: "gone" } : { state: "failed", message: describeError(err) });
    } finally {
      setBusy(false);
    }
  };
  if (outcome.state === "forgot") return <li className="message message--memory">{`Forgot: ${note.text}`}</li>;
  if (outcome.state === "gone") return <li className="message message--memory">{ALREADY_FORGOTTEN}</li>;
  return (
    <li className="message message--memory" data-message-id={message.id}>
      <span>{`Remembered: ${note.text}`}</span>
      <Button variant="ghost" size="sm" loading={busy} aria-label={`Undo: forget ${note.text}`} onClick={() => void undo()}>
        Undo
      </Button>
      {outcome.state === "failed" ? <span role="alert">{outcome.message}</span> : null}
    </li>
  );
}
