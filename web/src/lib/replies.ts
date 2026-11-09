// web/src/lib/replies.ts — reply quotes (replies track). The server makes the stored quote; this is only the
// preview the quote chip and your just-sent message show until the stored one arrives.
import type { MessageOut } from "../api/types";
import { SIGN_IN_WAIT } from "./stuck";

export const REPLY_QUOTE_CHARS = 120; // roost/constants.py REPLY_QUOTE_CHARS

// Only conversation messages can be quoted (roost/talk/replies.py REPLY_KINDS).
const REPLY_KINDS: ReadonlySet<string> = new Set(["text", "card_answer", "handoff", "report"]);

export function canReplyTo(message: MessageOut): boolean {
  return REPLY_KINDS.has(message.kind ?? "text") && (message.role === "user" || message.role === "bot") && message.seq > 0;
}

// The words a reply quotes. A Stuck card (its Reply button) is quoted by its host alone, in the server's fixed words
// (roost/stuck/texts.py stuck_quote): its note may come from a web page, so it never goes in a quote.
export function quoteSource(message: MessageOut): string {
  if (message.kind !== "stuck") return message.body;
  let data: { host?: unknown; sign_in?: unknown } = {};
  try {
    data = JSON.parse(message.body) ?? {};
  } catch {
    return "";
  }
  const host = typeof data.host === "string" ? data.host : "";
  if (data.sign_in === true) return host ? `${SIGN_IN_WAIT} to ${host}` : SIGN_IN_WAIT;
  return host ? `Stuck on ${host}` : "Needs your help";
}

// One line, at most REPLY_QUOTE_CHARS, an ellipsis when cut.
export function quotePreview(text: string): string {
  const flat = text.split(/\s+/).filter(Boolean).join(" ");
  return flat.length <= REPLY_QUOTE_CHARS ? flat : `${flat.slice(0, REPLY_QUOTE_CHARS - 1).trimEnd()}…`;
}
