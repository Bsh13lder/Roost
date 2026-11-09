import { mapWikilinks, plainSnippet } from "../components/notes/noteHelpers";
import { wikilinkLabel } from "../components/notes/wikilink";

// A table's rule row ("|---|:---:|") and its cell walls.
const TABLE_RULE = /\|?(?:\s*:?-{3,}:?\s*\|)+(?:\s*:?-{3,}:?\s*)?/g;
const CELL_WALL = /\s*\|\s*/g;
// A quote mark at the very start.
const QUOTE_MARK = /^>\s+/;
// *word* or _word_ between spaces or punctuation; "2 * 3" and snake_case stay as they are.
const EMPHASIS = /(^|[\s(])[*_]([^*_\s](?:[^*_]*[^*_\s])?)[*_](?=[\s).,!?:;]|$)/g;

// A message as one line of plain words (redesign P2), for the chat list's previews and a notification's
// text: a reply's markdown, which the server only flattens to one line, would show its marks, link
// targets and table rules. Builds on the notes list's plainSnippet. [[Target|Label]] goes first: its
// bar is not a table's.
export function plainText(markdown: string): string {
  const words = mapWikilinks(markdown, wikilinkLabel).replace(TABLE_RULE, " ").replace(CELL_WALL, " ");
  return plainSnippet(words).replace(QUOTE_MARK, "").replace(EMPHASIS, "$1$2");
}
