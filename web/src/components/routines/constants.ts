import type { RunState } from "../../api/routines";

export const PREVIEW_DEBOUNCE_MS = 300;
export const BUILTIN_DAY_SUMMARY = "day_summary";
export const BUILTIN_TITLE = "End-of-day summary";
export const FULL_LIMIT_LABEL = "Use the full limit until it resets";
export const FULL_LIMIT_REFUSAL = "Roost can't read your usage limit yet, so this stays off.";
export const DEFAULT_TIME = "09:00";
export const WATCH_LABEL = "Only run when the page changes";
export const WATCH_MIN_MINUTES = 5; // the server's WATCH_EVERY_MIN_MINUTES
export const WATCH_DEFAULT_MINUTES = 5;
export const WATCH_HINT =
  "Roost reads the page itself, with no model, and runs this routine only when that part changed.";
export const WORKDAYS = [1, 2, 3, 4, 5];
export const WEEKDAY_CHIPS = [
  { day: 1, label: "Mon" }, { day: 2, label: "Tue" }, { day: 3, label: "Wed" }, { day: 4, label: "Thu" },
  { day: 5, label: "Fri" }, { day: 6, label: "Sat" }, { day: 7, label: "Sun" },
] as const;

// A routine's last error, by the server's fixed word (ROUTINE_ERROR_*); the History shows it with its time.
export const LAST_ERROR_WORDS: Readonly<Record<string, string>> = {
  no_answer: "Couldn't check (computer didn't answer)",
  no_room: "Couldn't check (no free computer)",
  run_error: "Didn't finish",
};
export const LAST_ERROR_FALLBACK = "Something went wrong";

export const RUN_STATE_WORDS: Readonly<Record<RunState, string>> = {
  queued: "Waiting", running: "Running", done: "Done", missed: "Missed", skipped: "Skipped", held: "Held",
  expired: "Waited for you", error: "Didn't finish",
};
