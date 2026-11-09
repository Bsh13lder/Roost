// web/src/lib/routineDays.ts: routine run times grouped for a calendar (board toggles, 2026-10-26). The server
// reckons every time (GET /api/routines/occurrences, days on the account's calendar); the web only groups them: one entry per routine
// per day, its times in order, so a routine that runs every 15 minutes is one quiet line, not ninety-six.
import type { RoutineOccurrenceOut } from "../api/routines";

export interface RoutineDayEntry {
  routineId: string;
  routineName: string;
  botId: string;
  botName: string;
  times: readonly string[]; // account-zone HH:MM, earliest first
}

export type RoutineDays = ReadonlyMap<string, readonly RoutineDayEntry[]>;

const entryOf = (one: RoutineOccurrenceOut, times: readonly string[]): RoutineDayEntry => ({
  routineId: one.routine_id, routineName: one.routine_name, botId: one.bot_id, botName: one.bot_name, times,
});

/** Each day's routines, ordered by their first time, with no array or map mutated after it is shared. */
export function groupRoutineDays(occurrences: readonly RoutineOccurrenceOut[]): RoutineDays {
  const sorted = [...occurrences].sort((a, b) => a.at.localeCompare(b.at));
  const days = sorted.reduce<ReadonlyMap<string, readonly RoutineDayEntry[]>>((byDay, one) => {
    const entries = byDay.get(one.day) ?? [];
    const found = entries.find((entry) => entry.routineId === one.routine_id);
    const next = found
      ? entries.map((entry) => (entry === found ? { ...entry, times: [...entry.times, one.time] } : entry))
      : [...entries, entryOf(one, [one.time])];
    return new Map([...byDay, [one.day, next]]);
  }, new Map());
  return days;
}

/** "09:00", or "09:00 +3" when the routine runs four times that day. */
export function routineTimeWords(entry: RoutineDayEntry): string {
  const more = entry.times.length - 1;
  return more > 0 ? `${entry.times[0]} +${more}` : entry.times[0] ?? "";
}

/** "Routine: Morning news · 09:00 and 15:00 · Gela": what the entry says on hover and to a screen reader. */
export function routineWords(entry: RoutineDayEntry): string {
  const times = entry.times.length > 1
    ? `${entry.times.slice(0, -1).join(", ")} and ${entry.times[entry.times.length - 1]}` : entry.times[0] ?? "";
  return `Routine: ${entry.routineName} · ${times}${entry.botName ? ` · ${entry.botName}` : ""}`;
}

/** Where a tap on the entry goes: the routine's run log (its runs and Reports). */
export const routineLink = (entry: Pick<RoutineDayEntry, "botId" | "routineId">): string =>
  `/bots/${encodeURIComponent(entry.botId)}/routines/${encodeURIComponent(entry.routineId)}/log`;
