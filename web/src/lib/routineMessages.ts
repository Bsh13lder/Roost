// web/src/lib/routineMessages.ts — the bodies of the routines plan's message kinds. Every body is JSON written by
// the server; each parser checks its fields and returns null for anything else, so the row falls back to text.

const isObject = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null;
const text = (value: unknown): string | null => (typeof value === "string" ? value : null);

function parse(body: string): Record<string, unknown> | null {
  try {
    const value: unknown = JSON.parse(body);
    return isObject(value) ? value : null;
  } catch {
    return null;
  }
}

export interface ReportData {
  source: string;
  headline: string;
  text: string;
  routine_id: string | null;
  run_id: string | null;
  log_thread_id: string | null;
  tainted: boolean;
  task_id: string | null; // a single task's reminder: the chat draws it as a card with Done · Failed · Reschedule · Skip
  answer: string | null; // that card's stored answer (done · failed · rescheduled · skipped), the same on every screen
  answer_due: string | null; // a Reschedule's new due; null: no date
  routine_name: string | null; // the routine it came from, for the quiet footer (older Reports have none)
}

export function parseReport(body: string): ReportData | null {
  const data = parse(body);
  const headline = data ? text(data.headline) : null;
  if (!data || !headline) return null;
  return {
    source: text(data.source) ?? "system", headline, text: text(data.text) ?? "", routine_id: text(data.routine_id),
    run_id: text(data.run_id), log_thread_id: text(data.log_thread_id), tainted: data.tainted === true,
    task_id: text(data.task_id), answer: text(data.answer), answer_due: text(data.answer_due),
    routine_name: text(data.routine_name),
  };
}

// The quiet line of a routine_note or question_note: the server's own words.
export function parseNoteLine(body: string): string | null {
  const data = parse(body);
  return data ? text(data.text) : null;
}

export function parseProposalMessage(body: string): string | null {
  const data = parse(body);
  return data ? text(data.proposal_id) : null;
}
