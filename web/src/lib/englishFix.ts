// Correct my English: an english_fix line is the server's corrected copy of a spoken message of yours (role
// "activity", kind "english_fix", body roost/voice/correct.py). This module reads one and turns it into what the
// chat and the call screen draw: the corrected sentence with each fix inline (the wrong words struck through, the
// right words beside them), and the fixes that could not be placed, shown at the end as wrong → right.
import type { EnglishFix, EnglishFixBody, MessageOut } from "../api/types";

export const ENGLISH_FIX_KIND = "english_fix";

export type FixSegment =
  | { readonly kind: "text"; readonly text: string }
  | { readonly kind: "wrong"; readonly text: string }
  | { readonly kind: "right"; readonly text: string };

export interface FixDisplay {
  readonly segments: readonly FixSegment[];
  readonly trailing: readonly EnglishFix[];
}

const isFix = (value: unknown): value is EnglishFix =>
  typeof value === "object" && value !== null
  && typeof (value as EnglishFix).wrong === "string" && typeof (value as EnglishFix).right === "string";

// The server's body, or null for anything that is not a whole one.
export function parseEnglishFix(body: string): EnglishFixBody | null {
  let data: unknown;
  try {
    data = JSON.parse(body);
  } catch {
    return null;
  }
  if (typeof data !== "object" || data === null || Array.isArray(data)) return null;
  const { message_id, said, corrected, fixes } = data as Record<string, unknown>;
  if (typeof message_id !== "string" || !message_id || typeof said !== "string") return null;
  if (typeof corrected !== "string" || !corrected || !Array.isArray(fixes) || !fixes.every(isFix)) return null;
  return { message_id, said, corrected, fixes: fixes.map(({ wrong, right }) => ({ wrong, right })) };
}

// Where a fix sits in the corrected sentence, searching on from `from`; -1 when it cannot be placed: its wrong
// words are not in what was said, or its right words are not ahead in the corrected sentence.
function placeOf(fix: EnglishFix, said: string, corrected: string, from: number): number {
  if (!fix.right || !said.includes(fix.wrong)) return -1;
  return corrected.indexOf(fix.right, from);
}

// The display: the corrected sentence in pieces, each placed fix as wrong then right, and the rest trailing.
// What a fix display reads: a stored english_fix line or the composer's check before the send (read-only).
export interface FixShown {
  readonly said: string;
  readonly corrected: string;
  readonly fixes: readonly EnglishFix[];
}

export function fixSegments({ said, corrected, fixes }: FixShown): FixDisplay {
  const placed = fixes.reduce<{ cursor: number; segments: FixSegment[]; trailing: EnglishFix[] }>((acc, fix) => {
    const at = placeOf(fix, said, corrected, acc.cursor);
    if (at < 0) return { ...acc, trailing: [...acc.trailing, fix] };
    const before = corrected.slice(acc.cursor, at);
    const segments: FixSegment[] = [
      ...acc.segments,
      ...(before ? [{ kind: "text", text: before } as const] : []),
      ...(fix.wrong ? [{ kind: "wrong", text: fix.wrong } as const] : []),
      { kind: "right", text: fix.right },
    ];
    return { cursor: at + fix.right.length, segments, trailing: acc.trailing };
  }, { cursor: 0, segments: [], trailing: [] });
  const rest = corrected.slice(placed.cursor);
  return {
    segments: rest ? [...placed.segments, { kind: "text", text: rest }] : placed.segments,
    trailing: placed.trailing,
  };
}

export const isEnglishFix = (message: MessageOut): boolean =>
  message.role === "activity" && message.kind === ENGLISH_FIX_KIND;

export interface PlacedFixes {
  readonly rows: readonly MessageOut[]; // the conversation without the lifted lines
  readonly under: ReadonlyMap<string, readonly MessageOut[]>; // the lines to draw under each message, by its id
}

// Each english_fix line is drawn right under the message of yours it names; one whose message is not in this
// list (or that cannot be read) stays where it is in the flow.
export function placeEnglishFixes(messages: readonly MessageOut[]): PlacedFixes {
  const ids = new Set(messages.map((message) => message.id));
  const under = new Map<string, MessageOut[]>();
  const rows = messages.filter((message) => {
    if (!isEnglishFix(message)) return true;
    const target = parseEnglishFix(message.body)?.message_id;
    if (!target || !ids.has(target)) return true;
    under.set(target, [...(under.get(target) ?? []), message]);
    return false;
  });
  return { rows, under };
}

// The newest english_fix line for your message, read; null when there is none.
export function englishFixFor(messages: readonly MessageOut[], messageId: string): EnglishFixBody | null {
  const fixes = messages.filter(isEnglishFix).map((message) => parseEnglishFix(message.body));
  return fixes.reverse().find((fix) => fix?.message_id === messageId) ?? null;
}
