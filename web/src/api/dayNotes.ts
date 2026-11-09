import { apiRequest } from "./client";

// Day notes (Board G11): a line of text on a calendar day, from the user or a bot. The server seals the text;
// a bot's note that came from a web page carries `tainted`.
export interface DayNoteOut {
  id: string;
  day: string; // YYYY-MM-DD, a day on the account's calendar
  author_kind: "user" | "bot";
  bot_id: string | null;
  bot_name: string | null; // "A retired bot" once the bot is gone
  text: string;
  created_at: string;
  tainted: boolean; // written after reading outside content: shown with "from web content"
}

export function listDayNotes(from: string, to: string): Promise<DayNoteOut[]> {
  return apiRequest<DayNoteOut[]>("GET", `/api/day-notes?from=${from}&to=${to}`);
}

export function addDayNote(day: string, text: string): Promise<DayNoteOut> {
  return apiRequest<DayNoteOut>("POST", "/api/day-notes", { day, text });
}

export async function deleteDayNote(id: string): Promise<void> {
  await apiRequest<void>("DELETE", `/api/day-notes/${encodeURIComponent(id)}`);
}
