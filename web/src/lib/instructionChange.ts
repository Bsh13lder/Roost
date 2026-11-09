// web/src/lib/instructionChange.ts: an instruction_change line's body (roost/instruction_proposals/changes.py) and
// its words (the same as change_line in roost/instruction_proposals/texts.py).

export interface InstructionChangeData {
  section: string;
  undone: boolean;
}

export const CHANGE_FALLBACK = "Updated my instructions";
export const CHANGE_UNDONE = "Undone";

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

export function parseInstructionChange(body: string): InstructionChangeData | null {
  try {
    const data: unknown = JSON.parse(body);
    if (!isRecord(data) || typeof data.section !== "string") return null;
    return { section: data.section, undone: data.undone === true };
  } catch {
    return null;
  }
}

export function instructionChangeLine(data: InstructionChangeData | null): string {
  if (data === null) return CHANGE_FALLBACK;
  const line = `${CHANGE_FALLBACK}: ${data.section}`;
  return data.undone ? `${line} · ${CHANGE_UNDONE}` : line;
}
