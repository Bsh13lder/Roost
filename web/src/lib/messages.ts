// web/src/lib/messages.ts — one conversation out of the stored (REST)
// messages and the live (WS) ones.
import type { MessageOut } from "../api/types";

// A live placeholder (seq 0) is a reply still being written: it belongs
// after everything with a real per-thread seq.
function orderKey(message: MessageOut): number {
  return message.seq > 0 ? message.seq : Number.POSITIVE_INFINITY;
}

// Stored messages win a shared id; live ones not yet stored are added.
// The result is in thread order (`seq`, assigned by the server per
// thread), so a reply sits under the message it answers even though your
// own sends are kept with the stored list and replies arrive live. Ties
// (two placeholders) keep their arrival order.
export function mergeMessages(stored: readonly MessageOut[], live: readonly MessageOut[]): MessageOut[] {
  const storedIds = new Set(stored.map((message) => message.id));
  const all = [...stored, ...live.filter((message) => !storedIds.has(message.id))];
  return all
    .map((message, index) => ({ message, index }))
    .sort((a, b) => orderKey(a.message) - orderKey(b.message) || a.index - b.index)
    .map(({ message }) => message);
}

// The seq to show a message you just sent under, before the server's
// real one is known: after everything already shown, before anything the
// server stores after it (whose seq is at least the highest one + 1).
export function nextLocalSeq(shown: readonly MessageOut[]): number {
  return shown.reduce((highest, message) => Math.max(highest, message.seq), 0) + 0.5;
}
