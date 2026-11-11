import type { FinishedOut, LastErrorOut } from "../../api/routines";
import { LAST_ERROR_FALLBACK, LAST_ERROR_WORDS } from "./constants";
import { zoneClock, zoneStamp } from "./zoneTime";

// "Finished: booked · deleted Wed 18 Nov 10:07" for a routine the bot finished (v48); "" otherwise.
export function finishedLine(finished: FinishedOut | null | undefined): string {
  if (!finished) return "";
  const head = finished.reason ? `Finished: ${finished.reason}` : "Finished";
  const when = zoneStamp(finished.delete_at);
  return when ? `${head} · deleted ${when}` : head;
}

// "Couldn't check (computer didn't answer) · 12:40" on the account's clock (owner, 2026-11-10); "" with no error.
export function lastErrorLine(error: LastErrorOut | null | undefined, now: Date = new Date()): string {
  if (!error) return "";
  const words = LAST_ERROR_WORDS[error.kind] ?? LAST_ERROR_FALLBACK;
  const when = zoneClock(error.at, now);
  return when ? `${words} · ${when}` : words;
}
