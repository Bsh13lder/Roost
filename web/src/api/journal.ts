// web/src/api/journal.ts — a bot's journal, read-only (obsidian track). Shapes match roost/gateway/routes/journal.py.
import { apiRequest } from "./client";

export interface JournalDaySummary {
  day: string; // "YYYY-MM-DD", a day on the account's calendar
  entries: number;
  tainted: boolean; // an entry was written after the bot read outside content
  updated_at: string;
}

export interface JournalDayOut extends JournalDaySummary {
  bot_id: string;
  content: string; // Obsidian Markdown with front matter
}

const journalPath = (botId: string) => `/api/bots/${encodeURIComponent(botId)}/journal`;

export const listJournalDays = (botId: string) =>
  apiRequest<{ days: JournalDaySummary[] }>("GET", journalPath(botId)).then((out) => out.days);

export const readJournalDay = (botId: string, day: string) =>
  apiRequest<JournalDayOut>("GET", `${journalPath(botId)}/${encodeURIComponent(day)}`);
