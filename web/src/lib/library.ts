// The bot's Library (restructure slice 3): the documents and notes it made and the links from its chats, in one
// list grouped by the account's days: Today, This week, Earlier. Built from the old Documents and Links data.
import type { LinkOut, MadeOut } from "../api/types";
import { documentHref, noteHref } from "../pages/boardPaths";
import { zoneDayKey } from "./chatTime";

export type LibraryKind = "document" | "note" | "link";
export type LibraryGroupTitle = "Today" | "This week" | "Earlier";

export interface LibraryItem {
  readonly id: string;
  readonly kind: LibraryKind;
  readonly label: string;
  readonly detail: string; // a link's path; empty for a document or note
  readonly href: string;
  readonly external: boolean; // a link opens in a new tab, with no opener and no referrer
  readonly at: string; // ISO time it was made or said
  readonly tainted: boolean;
}

export interface LibraryGroup { readonly title: LibraryGroupTitle; readonly items: readonly LibraryItem[] }

const DAY_MS = 86_400_000;
const WEEK_DAYS = 7;
const GROUP_ORDER: readonly LibraryGroupTitle[] = ["Today", "This week", "Earlier"];

function pathOf(url: string): string {
  try {
    const parsed = new URL(url);
    return parsed.pathname + parsed.search;
  } catch {
    return ""; // the server only lists parseable http(s) links; an odd one shows its host alone
  }
}

const newestFirst = (a: LibraryItem, b: LibraryItem) => Date.parse(b.at) - Date.parse(a.at);

export function libraryItems(made: MadeOut, links: readonly LinkOut[]): LibraryItem[] {
  const documents = made.documents.map((d): LibraryItem => ({
    id: `document-${d.id}`, kind: "document", label: d.title, detail: "", href: documentHref(d.id), external: false,
    at: d.created_at, tainted: d.tainted,
  }));
  const notes = made.notes.map((n): LibraryItem => ({
    id: `note-${n.id}`, kind: "note", label: n.title, detail: "", href: noteHref(n.id), external: false,
    at: n.created_at, tainted: n.tainted,
  }));
  const said = links.map((l): LibraryItem => ({
    id: `link-${l.url}`, kind: "link", label: l.host, detail: pathOf(l.url), href: l.url, external: true,
    at: l.created_at, tainted: false,
  }));
  return [...documents, ...notes, ...said].sort(newestFirst);
}

function groupOf(at: string, now: Date): LibraryGroupTitle {
  const when = new Date(at);
  if (Number.isNaN(when.getTime())) return "Earlier";
  const days = Math.round((Date.parse(zoneDayKey(now)) - Date.parse(zoneDayKey(when))) / DAY_MS);
  if (days <= 0) return "Today";
  return days < WEEK_DAYS ? "This week" : "Earlier";
}

export function groupLibrary(items: readonly LibraryItem[], now: Date = new Date()): LibraryGroup[] {
  return GROUP_ORDER
    .map((title) => ({ title, items: items.filter((item) => groupOf(item.at, now) === title) }))
    .filter((group) => group.items.length > 0);
}
