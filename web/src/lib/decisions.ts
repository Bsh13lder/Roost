import { zonedFormat } from "./timeZone";

// A decision is a memory "{question}\nDecision: {answer}" (roost/choices/decisions.py DECISION_SEPARATOR).
const SEPARATOR = "\nDecision: ";
const STORED_SEPARATOR = " Decision: "; // the memory service folds the newline into a space
const dayFormat = () => zonedFormat("en-GB", { day: "numeric", month: "short" });
const clockFormat = () => zonedFormat("en-GB", { hour: "2-digit", minute: "2-digit" });

export interface ParsedDecision {
  question: string;
  answer: string;
}

// The server stores {"q": question, "a": answer} (roost/choices/decisions.py decision_text); older rows hold the
// "question Decision: answer" form.
function parseStructured(text: string): ParsedDecision | null {
  try {
    const data: unknown = JSON.parse(text);
    if (typeof data !== "object" || data === null) return null;
    const { q, a } = data as { q?: unknown; a?: unknown };
    if (typeof q !== "string" || typeof a !== "string") return null;
    const question = q.trim();
    const answer = a.trim();
    return question && answer ? { question, answer } : null;
  } catch {
    return null;
  }
}

export function parseDecision(text: string): ParsedDecision | null {
  if (text.trimStart().startsWith("{")) return parseStructured(text);
  let at = text.indexOf(SEPARATOR);
  let width = SEPARATOR.length;
  if (at < 0) { at = text.indexOf(STORED_SEPARATOR); width = STORED_SEPARATOR.length; }
  if (at < 0) return null;
  const question = text.slice(0, at).trim();
  const answer = text.slice(at + width).trim();
  return question && answer ? { question, answer } : null;
}

// "22 Oct, 14:19" on the account's clock
export function decidedAt(iso: string): string {
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return "";
  return `${dayFormat().format(when)}, ${clockFormat().format(when)}`;
}
