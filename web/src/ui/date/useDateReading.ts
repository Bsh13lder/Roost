import { useEffect, useState } from "react";
import { parseDate, type DateKind } from "../../api/dates";
import { describeError } from "../../api/client";
import { DATE_PREVIEW_DELAY_MS } from "../constants";
import { dueParts, pickedParts, type DueParts } from "./dates";

export type DateReading =
  | { kind: "empty" }
  | { kind: "reading" }
  | { kind: "read"; parts: DueParts }
  | { kind: "error"; message: string };

// A picked value needs no gateway; words do.
function readLocally(text: string): DateReading | null {
  const value = text.trim();
  if (!value) return { kind: "empty" };
  const parts = pickedParts(value);
  return parts ? { kind: "read", parts } : null;
}

function fromServer(due: string | null): DateReading {
  if (!due) return { kind: "empty" };
  const parts = dueParts(due);
  return parts ? { kind: "read", parts } : { kind: "error", message: `I could not read “${due}”.` };
}

// How the gateway reads what the user typed, once they pause (the existing natural-language parsers,
// on the account's time: a task's due by default, an expense's day for kind "spent"). Only the newest text's
// answer is kept.
export function useDateReading(text: string, kind: DateKind = "due"): DateReading {
  const local = readLocally(text);
  const [answer, setAnswer] = useState<{ text: string; reading: DateReading } | null>(null);
  const needsServer = local === null;
  useEffect(() => {
    if (!needsServer) return;
    let current = true;
    const timer = window.setTimeout(() => {
      parseDate(text.trim(), kind)
        .then((out) => { if (current) setAnswer({ text, reading: fromServer(out.due_date) }); })
        .catch((err: unknown) => { if (current) setAnswer({ text, reading: { kind: "error", message: describeError(err) } }); });
    }, DATE_PREVIEW_DELAY_MS);
    return () => { current = false; window.clearTimeout(timer); };
  }, [text, kind, needsServer]);
  if (local) return local;
  return answer && answer.text === text ? answer.reading : { kind: "reading" };
}
