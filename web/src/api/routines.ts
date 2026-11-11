// web/src/api/routines.ts — a bot's routines (routines plan, Task 15). Shapes match roost/gateway/routes/routines.py.
import { apiRequest } from "./client";

export type TimesSchedule = { kind: "times"; days: number[]; times: string[] }; // days: 1 = Mon … 7 = Sun
export type CronSchedule = { kind: "cron"; expr: string };
export type ScheduleIn = TimesSchedule | CronSchedule;

export type RunState = "queued" | "running" | "done" | "missed" | "skipped" | "held" | "expired" | "error";

// "Only run when the page changes" (owner, 2026-11-04): Roost reads the page itself every every_min minutes and
// runs the routine only when the part changed. Sent as null on a PATCH, it stops watching.
export interface WatchIn {
  url: string;
  part: string; // what to watch, in plain words ("the physio chat"); "" is the whole page
  every_min: number; // the server refuses fewer than 5
}

export interface WatchOut extends WatchIn {
  host: string;
  last_checked_at: string | null;
  last_changed_at: string | null;
}

export interface RoutineOut {
  id: string;
  name: string;
  instructions: string;
  schedule: ScheduleIn;
  words: string;
  enabled: boolean;
  builtin: string | null;
  tainted: boolean;
  created_by: "user" | "bot";
  thread_id: string; // its run log
  next_run_at: string | null;
  last_run_at: string | null;
  last_state: RunState | null;
  watch?: WatchOut | null; // next_run_at is then the next check
  model?: string | null; // its own model id; null: the bot's (owner, 2026-11-09)
  last_error?: LastErrorOut | null; // v47: the last failure, cleared by the next good check or finished run
  finished?: FinishedOut | null; // v48: the bot finished it in its own run; deleted on delete_at unless resumed
}

// A finished routine (owner, 2026-11-11): when, the bot's short reason, and when the server deletes it.
export interface FinishedOut {
  at: string;
  reason: string;
  delete_at: string;
}

// A routine's last error: a fixed word (the server's ROUTINE_ERROR_*) and when, shown in its History.
export interface LastErrorOut {
  kind: string;
  at: string;
}

export interface RoutineRunOut {
  id: string;
  slot_at: string;
  state: RunState;
  missed_count: number;
  note: string | null;
  started_at: string | null;
  finished_at: string | null;
  report_message_id: string | null;
}

export interface RoutineDraftIn {
  name: string;
  instructions: string;
  schedule: ScheduleIn;
  enabled?: boolean;
  watch?: WatchIn | null;
  model?: string | null; // null: the bot's own model
}

export interface SchedulePreview {
  words: string;
  next: string[]; // account-zone ISO times
}

const routinePath = (id: string) => `/api/routines/${encodeURIComponent(id)}`;

export const listRoutines = (botId: string) =>
  apiRequest<{ routines: RoutineOut[] }>("GET", `/api/bots/${encodeURIComponent(botId)}/routines`).then((r) => r.routines);
export const createRoutine = (botId: string, draft: RoutineDraftIn) =>
  apiRequest<RoutineOut>("POST", `/api/bots/${encodeURIComponent(botId)}/routines`, draft);
export const patchRoutine = (id: string, changes: Partial<RoutineDraftIn>) =>
  apiRequest<RoutineOut>("PATCH", routinePath(id), changes);
export const deleteRoutine = (id: string) => apiRequest<void>("DELETE", routinePath(id));
// Resume on a "Finished routine" line: no longer finished, on again and planned from now.
export const resumeRoutine = (id: string) => apiRequest<RoutineOut>("POST", `${routinePath(id)}/resume`);
export const runRoutineNow = (id: string) => apiRequest<{ run: RoutineRunOut }>("POST", `${routinePath(id)}/run-now`);
export const listRuns = (id: string, before?: string) =>
  apiRequest<{ runs: RoutineRunOut[] }>("GET", `${routinePath(id)}/runs${before ? `?before=${encodeURIComponent(before)}` : ""}`)
    .then((r) => r.runs);
export const previewSchedule = (schedule: ScheduleIn) =>
  apiRequest<SchedulePreview>("POST", "/api/routines/preview", { schedule });

// All routines in one place (roost/gateway/routes/routines_hub.py).
export interface HubRoutineOut extends RoutineOut {
  bot_id: string;
  bot_name: string;
  next_run_madrid: string | null; // account-zone ISO, null while paused
  last_note: string | null;
  last_finished_at: string | null;
}

export interface HubRunOut extends RoutineRunOut {
  routine_id: string;
  routine_name: string;
  bot_id: string;
  bot_name: string;
}

export interface RoutineTemplateOut {
  id: string;
  name: string;
  instructions: string;
  schedule: ScheduleIn;
  words: string;
  needs_edit: boolean; // its instructions hold a <placeholder>; it is added paused
}

export const listAllRoutines = () =>
  apiRequest<{ routines: HubRoutineOut[] }>("GET", "/api/routines").then((r) => r.routines);
export const listRecentRuns = (limit: number) =>
  apiRequest<{ runs: HubRunOut[] }>("GET", `/api/routines/runs?limit=${limit}`).then((r) => r.runs);
export const listRoutineTemplates = () =>
  apiRequest<{ templates: RoutineTemplateOut[] }>("GET", "/api/routine-templates").then((r) => r.templates);
export const addTemplate = (botId: string, templateId: string) =>
  apiRequest<RoutineOut>("POST", `/api/bots/${encodeURIComponent(botId)}/routines/from-template`, { template_id: templateId });

// Routine run times for the calendars (GET /api/routines/occurrences): days on the account's calendar, from now on, paused ones left out.
export interface RoutineOccurrenceOut {
  routine_id: string;
  routine_name: string;
  bot_id: string;
  bot_name: string;
  at: string; // UTC ISO
  day: string; // account-zone YYYY-MM-DD
  time: string; // account-zone HH:MM
  log_thread_id: string;
}

export interface RoutineOccurrences {
  occurrences: RoutineOccurrenceOut[];
  truncated: boolean; // more fell in the span than the server's cap
}

export const listRoutineOccurrences = (from: string, to: string, botId?: string) => {
  const query = new URLSearchParams({ from, to, ...(botId ? { bot_id: botId } : {}) });
  return apiRequest<RoutineOccurrences>("GET", `/api/routines/occurrences?${query.toString()}`);
};
