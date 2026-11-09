import type { MemoryKind, MemoryNoteBody } from "../api/types";
import { KIND_LABELS } from "../components/memory/constants";

export const isMemoryKind = (value: unknown): value is MemoryKind =>
  typeof value === "string" && Object.prototype.hasOwnProperty.call(KIND_LABELS, value);

// A memory_note message's body is JSON written by the server; anything else is not a note (null).
export function parseMemoryNote(body: string): MemoryNoteBody | null {
  let data: unknown;
  try {
    data = JSON.parse(body);
  } catch {
    return null;
  }
  if (typeof data !== "object" || data === null) return null;
  const { memory_id, kind, text } = data as Record<string, unknown>;
  if (typeof memory_id !== "string" || !memory_id || !isMemoryKind(kind) || typeof text !== "string" || !text) return null;
  return { memory_id, kind, text };
}
