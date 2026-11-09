import { LONG_REPLY_CHARS, LONG_REPLY_LINES } from "./constants";

// A heading, a fenced code block, a list item or a table row at the start of a line.
const BLOCK_MARKDOWN = /^(?:#{1,6}\s|```|\s*[-*+]\s|\s*\d+[.)]\s|\s*\|.*\|)/m;

// A reply that reads better full width (redesign P2): long, or built of markdown blocks.
export function isLongReply(text: string): boolean {
  return text.length >= LONG_REPLY_CHARS || text.split("\n").length > LONG_REPLY_LINES || BLOCK_MARKDOWN.test(text);
}
