import type { RoutineOut, RoutineRunOut } from "../src/api/routines";

export const routine = (over: Partial<RoutineOut> = {}): RoutineOut => ({
  id: "r-1", name: "Morning digest", instructions: "Read the news and summarise it.",
  schedule: { kind: "times", days: [1, 2, 3, 4, 5], times: ["10:07"] }, words: "Weekdays at 10:07", enabled: true,
  builtin: null, tainted: false, created_by: "user", thread_id: "t-log", next_run_at: "2026-10-21T08:07:00Z", last_run_at: null, last_state: null,
  ...over,
});

export const run = (over: Partial<RoutineRunOut> = {}): RoutineRunOut => ({
  id: "run-1", slot_at: "2026-10-20T08:07:00Z", state: "done", missed_count: 0, note: null,
  started_at: "2026-10-20T08:07:05Z", finished_at: "2026-10-20T08:08:00Z", report_message_id: null, ...over,
});
