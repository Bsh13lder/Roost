// SPDX-License-Identifier: MIT
// Harvested from LazyClaw web/src/components/notes/noteHelpers.ts lines 56-88, 142-149 @ 21e1002, adapted for Roost

import { appTimeZone } from "../../lib/timeZone";
import { iterWikilinks, wikilinkLabel, type WikilinkMatch } from "./wikilink";

/** "12m ago" / "yesterday" / "Tue 14:32" / "Apr 22" */
export function relativeTimeAgo(iso: string, now = new Date()): string {
  const t = new Date(iso);
  if (Number.isNaN(t.getTime())) return "";
  const ms = now.getTime() - t.getTime();
  const min = Math.floor(ms / 60_000);
  if (min < 1) return "just now";
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const sameDay =
    t.getDate() === now.getDate() &&
    t.getMonth() === now.getMonth() &&
    t.getFullYear() === now.getFullYear();
  if (sameDay) return t.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", timeZone: appTimeZone() });
  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  if (
    t.getDate() === yesterday.getDate() &&
    t.getMonth() === yesterday.getMonth() &&
    t.getFullYear() === yesterday.getFullYear()
  ) {
    return `yesterday ${t.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", timeZone: appTimeZone() })}`;
  }
  const sevenDays = new Date(now);
  sevenDays.setDate(sevenDays.getDate() - 7);
  if (t > sevenDays) {
    return t.toLocaleDateString([], { weekday: "short", timeZone: appTimeZone() }) +
      ` ${t.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", timeZone: appTimeZone() })}`;
  }
  return t.toLocaleDateString([], { month: "short", day: "numeric", timeZone: appTimeZone() });
}

/**
 * Build first-line title (capped at 80 chars) — matches server save_quick_note.
 * Used as a preview in the quick-add ghost row.
 */
export function deriveTitle(content: string): string {
  const first = (content.split(/\r?\n/)[0] || "").trim();
  return (first || content.trim()).slice(0, 80) || "Quick note";
}
// Roost: mirrors roost/constants.py (MAX_NOTE_TITLE_LENGTH, MAX_NOTE_CONTENT_LENGTH, MAX_NOTE_QUERY_LENGTH).
export const MAX_NOTE_TITLE_LENGTH = 200;
export const MAX_NOTE_CONTENT_LENGTH = 100_000;
export const MAX_NOTE_QUERY_LENGTH = 200;

// Roost: the page key a [[wikilink]] resolves by — roost/notes/wikilinks.py's normalize_page.
export function normalizePage(name: string): string {
  return name.trim().toLowerCase().split(/\s+/).filter(Boolean).join(" ");
}

// Roost: the body without its leading --- front-matter block (the list shows tags as chips instead).
export function stripFrontMatter(content: string): string {
  const block = /^---\r?\n[\s\S]*?\r?\n---\r?\n?/.exec(content);
  return block ? content.slice(block[0].length) : content;
}

// Roost: `text` with every [[wikilink]] replaced by what `render` makes of it.
export function mapWikilinks(text: string, render: (link: WikilinkMatch) => string): string {
  let out = "";
  let at = 0;
  for (const link of iterWikilinks(text)) {
    out += text.slice(at, link.start) + render(link);
    at = link.end;
  }
  return out + text.slice(at);
}

// Roost: a list snippet as plain words. The server only flattens a note's
// markdown to one line, so marks, link targets and image URLs would show.
export function plainSnippet(snippet: string): string {
  return mapWikilinks(snippet, wikilinkLabel)
    .replace(/!\[[^\]]*\]\([^)]*\)/g, "") // an image: dropped
    .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1") // a link: its words
    .replace(/(^|\s)#{1,6}\s+/g, "$1") // heading marks (a #tag stays)
    .replace(/\*\*|__|~~|`/g, "")
    .replace(/\s+/g, " ")
    .trim();
}
