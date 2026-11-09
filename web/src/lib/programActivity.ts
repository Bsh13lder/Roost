// web/src/lib/programActivity.ts: a program_activity line's body as words (the same words as roost/programs/wrap.py).
import type { ProgramActivityData } from "../api/types";

const FALLBACK = "Ran a program";

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

export function parseProgramActivity(body: string): ProgramActivityData | null {
  try {
    const data: unknown = JSON.parse(body);
    if (!isRecord(data) || (data.op !== "run" && data.op !== "write")) return null;
    const subject = data.op === "run" ? data.command : data.path;
    if (typeof subject !== "string") return null;
    return {
      op: data.op, command: data.op === "run" ? subject : undefined, path: data.op === "write" ? subject : undefined,
      exit_code: typeof data.exit_code === "number" ? data.exit_code : 0, timed_out: data.timed_out === true,
      output: typeof data.output === "string" ? data.output : "", cut: data.cut === true,
      tainted_basis: data.tainted_basis === true,
    };
  } catch {
    return null;
  }
}

// Control characters never reach the one-line summary (a command with a newline would look like two lines).
const oneLine = (text: string) => text.replace(/[\u0000-\u001f\u007f]+/g, " ").trim();

export function programStatus(data: ProgramActivityData): string {
  return data.timed_out ? "timed out" : `exit ${data.exit_code}`;
}

export function programActivityLine(data: ProgramActivityData | null): string {
  if (!data) return FALLBACK;
  if (data.op === "write") return `Wrote ${oneLine(data.path ?? "")}`;
  return `Ran: ${oneLine(data.command ?? "")} · ${programStatus(data)}`;
}
