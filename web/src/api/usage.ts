// web/src/api/usage.ts — the usage reading and a bot's full-limit switch (routines plan, Task 12 and 15), and the
// token counts every model call adds up (docs/plans/2026-11-04-roost-token-usage.md).
import { apiRequest } from "./client";
import type { BotOut } from "./types";

// tokens_in = input + cache_read + cache_write, tokens_out = output, tokens = both.
export interface UsageCounts {
  input: number;
  output: number;
  cache_read: number;
  cache_write: number;
  calls: number;
  tokens_in: number;
  tokens_out: number;
  tokens: number;
}

export interface UsageDay extends UsageCounts {
  day: string; // YYYY-MM-DD, a day on the account's calendar
}

export interface UsageSpan {
  total: UsageCounts;
  today_total: UsageCounts;
  per_day: UsageDay[]; // dense, oldest first
}

export interface BotUsageRow extends UsageSpan {
  bot_id: string;
  name: string;
}

export interface UsageOut {
  readable: boolean;
  remaining_fraction: number | null;
  resets_at: string | null;
  // The token counts (an older server leaves them out).
  days?: number;
  today?: string;
  total?: UsageCounts;
  today_total?: UsageCounts;
  per_day?: UsageDay[];
  bots?: BotUsageRow[];
  background?: UsageSpan | null;
  busiest?: { bot_id: string; name: string; tokens: number } | null;
}

export interface BotUsageOut extends UsageSpan {
  bot_id: string;
  days: number;
  today: string;
}

const daysQuery = (days?: number) => (days === undefined ? "" : `?days=${encodeURIComponent(String(days))}`);

export const getUsage = (days?: number) => apiRequest<UsageOut>("GET", `/api/usage${daysQuery(days)}`);
export const getBotUsage = (botId: string, days?: number) =>
  apiRequest<BotUsageOut>("GET", `/api/bots/${encodeURIComponent(botId)}/usage${daysQuery(days)}`);
export const setFullLimit = (botId: string, on: boolean) =>
  apiRequest<BotOut>("PUT", `/api/bots/${encodeURIComponent(botId)}/full-limit`, { on });
