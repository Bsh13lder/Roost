import type { MemoryOfferBody } from "../api/types";
import { isMemoryKind } from "./memoryNote";

const REASON = "I read a web page in this run, so I can't save memories myself.";
const END_MARKS = [".", "!", "?", "…"];

const sentence = (text: string) => (END_MARKS.some((mark) => text.endsWith(mark)) ? text : `${text}.`);

export const notRememberedLine = (text: string) => `Not remembered: ${sentence(text)} ${REASON}`;
export const rememberedLine = (text: string) => `Remembered: ${sentence(text)}`;
export const forgotLine = (text: string) => `Forgot: ${sentence(text)}`;

// A memory_offer message's body is JSON written by the server; anything else is not an offer (null).
export function parseMemoryOffer(body: string): MemoryOfferBody | null {
  let data: unknown;
  try {
    data = JSON.parse(body);
  } catch {
    return null;
  }
  if (typeof data !== "object" || data === null) return null;
  const { text, kind, memory_id } = data as Record<string, unknown>;
  if (typeof text !== "string" || !text || !isMemoryKind(kind)) return null;
  return { text, kind, memory_id: typeof memory_id === "string" && memory_id ? memory_id : null };
}
