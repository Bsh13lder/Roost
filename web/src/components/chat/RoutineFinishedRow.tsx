import { useState } from "react";
import { ApiError, describeError } from "../../api/client";
import { deleteRoutine, resumeRoutine } from "../../api/routines";
import type { MessageOut } from "../../api/types";
import { parseFinished } from "../../lib/routineMessages";
import { Button } from "../../ui/Button";
import { WebMark } from "./WebMark";

type Outcome = { state: "finished" } | { state: "resumed" } | { state: "deleted" } | { state: "gone" } | { state: "failed"; message: string };

const ALREADY_GONE = "That routine is already gone.";

// "Finished routine · Watch physio: booked. I'll delete it in 7 days." with Resume and Delete now (owner, 2026-11-11).
// A line from a tainted run (a page-watch change) wears the web mark: its reason came out of page content.
export function RoutineFinishedRow({ message }: { message: MessageOut }) {
  const data = parseFinished(message.body);
  const [outcome, setOutcome] = useState<Outcome>({ state: "finished" });
  const [busy, setBusy] = useState<"resume" | "delete" | null>(null);
  if (!data) return <li className="message message--memory">{message.body}</li>;
  const act = async (which: "resume" | "delete") => {
    setBusy(which);
    try {
      if (which === "resume") await resumeRoutine(data.routine_id);
      else await deleteRoutine(data.routine_id);
      setOutcome({ state: which === "resume" ? "resumed" : "deleted" });
    } catch (err) {
      setOutcome(err instanceof ApiError && err.status === 404
        ? { state: "gone" } : { state: "failed", message: describeError(err) });
    } finally {
      setBusy(null);
    }
  };
  if (outcome.state === "resumed") return <li className="message message--memory">{`Resumed routine · ${data.name}`}</li>;
  if (outcome.state === "deleted") return <li className="message message--memory">{`Deleted routine · ${data.name}`}</li>;
  if (outcome.state === "gone") return <li className="message message--memory">{ALREADY_GONE}</li>;
  return (
    <li className="message message--memory" data-message-id={message.id}>
      <span>{data.text}</span>
      {message.tainted ? <WebMark className="message__taint" /> : null}
      <Button variant="ghost" size="sm" loading={busy === "resume"} disabled={busy !== null}
        aria-label={`Resume routine ${data.name}`} onClick={() => void act("resume")}>
        Resume
      </Button>
      <Button variant="ghost" size="sm" loading={busy === "delete"} disabled={busy !== null}
        aria-label={`Delete routine ${data.name} now`} onClick={() => void act("delete")}>
        Delete now
      </Button>
      {outcome.state === "failed" ? <span role="alert">{outcome.message}</span> : null}
    </li>
  );
}
