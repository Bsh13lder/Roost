// The sidebar's pure parts (polish R1): the chat rows filtered, ordered and split into sections by each bot's
// group label, the row of avatars, and the labels already in use. No React here.
import { plainText } from "./plainText";
import type { BotOut, ChatRowOut } from "../api/types";

export interface ChatSection {
  label: string | null;
  rows: readonly ChatRowOut[];
}

type BotsById = Readonly<Record<string, BotOut>>;

const byLabel = (a: string, b: string): number => a.localeCompare(b, undefined, { sensitivity: "base" });

export function filterChats(rows: readonly ChatRowOut[], query: string): ChatRowOut[] {
  const wanted = query.trim().toLowerCase();
  if (!wanted) return [...rows];
  return rows.filter((row) => row.name.toLowerCase().includes(wanted) || plainText(row.preview ?? "").toLowerCase().includes(wanted));
}

// The main bot sits first, wearing its star; the rest stay newest first.
export function mainFirst(rows: readonly ChatRowOut[], bots: BotsById): ChatRowOut[] {
  const isMain = (row: ChatRowOut) => row.kind === "bot" && bots[row.id]?.is_primary === true;
  return [...rows.filter(isMain), ...rows.filter((row) => !isMain(row))];
}

// A bot's row carries its live name: a rename (a bot_updated frame) shows, and is found, at once.
export function withLiveNames(rows: readonly ChatRowOut[], bots: BotsById): ChatRowOut[] {
  return rows.map((row) => (row.kind === "bot" && bots[row.id] ? { ...row, name: bots[row.id].name } : row));
}

// The trimmed label as typed; rooms and unlabelled bots have none.
export function groupOf(row: ChatRowOut, bots: BotsById): string | null {
  if (row.kind !== "bot") return null;
  return bots[row.id]?.group?.trim() || null;
}

// The main bot is always pinned.
export function isPinned(bot: BotOut): boolean {
  return bot.pinned || bot.is_primary;
}

// Pinned bots live in the robot row, not in the list; a search looks at every chat, pinned or not.
function withoutPinned(rows: readonly ChatRowOut[], bots: BotsById): ChatRowOut[] {
  return rows.filter((row) => !(row.kind === "bot" && bots[row.id] && isPinned(bots[row.id])));
}

export function chatSections(rows: readonly ChatRowOut[], bots: BotsById, query: string): ChatSection[] {
  const searching = query.trim() !== "";
  const listed = searching ? rows : withoutPinned(rows, bots);
  const shown = filterChats(mainFirst(withLiveNames(listed, bots), bots), query);
  const labelled = new Map<string, ChatRowOut[]>();
  const first: ChatRowOut[] = [];
  for (const row of shown) {
    const label = groupOf(row, bots);
    if (label === null) first.push(row);
    else labelled.set(label, [...(labelled.get(label) ?? []), row]);
  }
  const named = [...labelled.keys()].sort(byLabel).map((label) => ({ label, rows: labelled.get(label) ?? [] }));
  return [...(first.length > 0 ? [{ label: null, rows: first }] : []), ...named];
}

// The main bot, then the pinned bots in the order they were pinned.
export function avatarRow(bots: readonly BotOut[]): BotOut[] {
  const pins = bots.filter((bot) => !bot.is_primary && bot.pinned)
    .sort((a, b) => (a.pinned_at ?? "").localeCompare(b.pinned_at ?? ""));
  return [...bots.filter((bot) => bot.is_primary), ...pins];
}

// The labels the other bots use, once each, for the label popover's suggestions.
export function usedLabels(bots: readonly BotOut[], exceptBotId?: string): string[] {
  const labels = bots.filter((bot) => bot.id !== exceptBotId).map((bot) => bot.group?.trim() ?? "").filter(Boolean);
  return [...new Set(labels)].sort(byLabel);
}
