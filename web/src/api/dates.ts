import { apiRequest } from "./client";

// How the gateway reads a typed date (GET /api/dates/parse), on the account's time. "" reads as no date (null).
// It changes nothing. The reading depends on what the date is for:
//   "due"   a task's due, read by roost/tasks/due.py parse_due (looks ahead: "tomorrow at 9")
//   "spent" an expense's day, read by roost/money/months.py parse_spent_at (looks back: "yesterday",
//           "2 days ago", "hace 3 días"; never a future day)
export type DateKind = "due" | "spent";

export interface DateReadOut {
  due_date: string | null; // "2026-10-16", or "2026-10-16T09:00:00+02:00" when a due's words name a time
}

export function parseDate(text: string, kind: DateKind = "due"): Promise<DateReadOut> {
  return apiRequest<DateReadOut>("GET", `/api/dates/parse?text=${encodeURIComponent(text)}&kind=${kind}`);
}
