// The activity pill's store (docs/plans/2026-10-23-roost-activity-pill.md): each run's run_step frames, kept by
// run id. A step arrives as "start" and again as "done" or "failed" under the same number: the newer state
// replaces the older. A run is anchored to the bot's open reply when its first step arrives, exactly as the
// computer card's runs are (store/computerRuns.ts), and a run first seen in a snapshot has no anchor. Pure helpers.
import type { BotOut, MessageOut, RunStepOut } from "../api/types";
import { runHost, type ComputerRun } from "./computerRuns";

export const RUN_STEPS_KEPT = 60; // the server's ring holds the same (RUN_STEPS_KEPT)
export const ACTIVITY_RUNS_KEPT = 40;

export interface ActivityRun {
  readonly runId: string;
  readonly botId: string;
  readonly threadId: string | null;
  readonly anchorId: string | null;
  readonly order: number;
  readonly steps: readonly RunStepOut[];
  readonly lastAt: string; // the newest frame's time: a finished run's length runs from its first step to here
}

export type ActivityRuns = Readonly<Record<string, ActivityRun>>;

const stepOf = (f: RunStepOut): RunStepOut => ({
  bot_id: f.bot_id, thread_id: f.thread_id, run_id: f.run_id, step: f.step, kind: f.kind, line: f.line,
  host: f.host, at: f.at, state: f.state, ...(f.kind === "note" ? { tainted: f.tainted === true } : {}),
});

function openReplyOf(messagesByThread: Readonly<Record<string, readonly MessageOut[]>>, step: RunStepOut): string | null {
  const thread = step.thread_id ? messagesByThread[step.thread_id] ?? [] : [];
  const open = thread.filter((m) => m.seq === 0 && m.role === "bot" && m.author_bot_id === step.bot_id);
  return open.at(-1)?.id ?? null;
}

const nextOrder = (runs: ActivityRuns) => Object.values(runs).reduce((top, run) => Math.max(top, run.order), 0) + 1;

function capped(runs: Record<string, ActivityRun>): ActivityRuns {
  const all = Object.values(runs);
  if (all.length <= ACTIVITY_RUNS_KEPT) return runs;
  const kept = [...all].sort((a, b) => b.order - a.order).slice(0, ACTIVITY_RUNS_KEPT);
  return Object.fromEntries(kept.map((run) => [run.runId, run]));
}

// A step's newest state wins; a "start" never undoes an ending already seen (frames can cross a snapshot).
function merge(old: RunStepOut | undefined, next: RunStepOut): RunStepOut {
  if (old && old.state !== "start" && next.state === "start") return old;
  return { ...next, at: old?.at ?? next.at }; // the step keeps the time it began
}

function withSteps(runs: ActivityRuns, steps: readonly RunStepOut[], anchorId: string | null): ActivityRuns {
  const first = steps[0];
  const existing = runs[first.run_id];
  const byStep = new Map((existing?.steps ?? []).map((s) => [s.step, s]));
  for (const step of steps) byStep.set(step.step, merge(byStep.get(step.step), step));
  const merged = [...byStep.values()].sort((a, b) => a.step - b.step).slice(-RUN_STEPS_KEPT);
  const lastAt = [existing?.lastAt ?? "", ...steps.map((s) => s.at)]
    .reduce((top, at) => ((Date.parse(at) || 0) > (Date.parse(top) || 0) ? at : top));
  const run: ActivityRun = {
    runId: first.run_id, botId: first.bot_id, threadId: first.thread_id,
    anchorId: existing?.anchorId ?? anchorId, order: existing?.order ?? nextOrder(runs), steps: merged, lastAt,
  };
  return capped({ ...runs, [run.runId]: run });
}

export function withRunStep(
  runs: ActivityRuns, frame: RunStepOut, messagesByThread: Readonly<Record<string, readonly MessageOut[]>>,
): ActivityRuns {
  return withSteps(runs, [stepOf(frame)], openReplyOf(messagesByThread, frame));
}

export function withSnapshotRunSteps(runs: ActivityRuns, byBot: Readonly<Record<string, readonly RunStepOut[]>> | undefined): ActivityRuns {
  return Object.values(byBot ?? {}).reduce<ActivityRuns>(
    (acc, steps) => (steps.length > 0 ? withSteps(acc, steps.map(stepOf), null) : acc), runs);
}

export function latestActivityOf(runs: ActivityRuns, botId: string): ActivityRun | null {
  return Object.values(runs).filter((run) => run.botId === botId)
    .reduce<ActivityRun | null>((top, run) => (top === null || run.order > top.order ? run : top), null);
}

export function isLiveActivity(runs: ActivityRuns, run: ActivityRun, bot: BotOut | undefined): boolean {
  return bot?.status === "on_it" && latestActivityOf(runs, run.botId)?.runId === run.runId;
}

// The steps that did something: Thinking and Writing the reply are the pill's mood, not steps of their own, and a
// note (the bot's own words between steps, owner 2026-11-04) is not a step either.
export const workSteps = (run: ActivityRun) => timelineSteps(run).filter((s) => s.kind !== "note");

// What the sheet lists: the work steps with the bot's notes between them, in order.
export const timelineSteps = (run: ActivityRun) =>
  run.steps.filter((s) => s.kind !== "think" && s.kind !== "message");

// Past words while a step runs: "Searched the web for …" reads "Searching the web for …".
const NOW_WORDS: Readonly<Record<string, string>> = {
  Searched: "Searching", Opened: "Opening", Read: "Reading", Looked: "Looking", Clicked: "Clicking",
  Typed: "Typing", Pressed: "Pressing", Scrolled: "Scrolling", Waited: "Waiting", Ran: "Running",
  Checked: "Checking", Wrote: "Writing", Added: "Adding", Updated: "Updating", Finished: "Finishing",
  Deleted: "Deleting", Removed: "Removing", Moved: "Moving", Commented: "Commenting", Started: "Starting",
  Edited: "Editing", Made: "Making", Filed: "Filing", Logged: "Logging", Set: "Setting", Changed: "Changing",
  Created: "Creating", Asked: "Asking", Sent: "Sending", Remembered: "Remembering", Forgot: "Forgetting",
  Suggested: "Suggesting", Installed: "Installing", Saved: "Saving", Renamed: "Renaming", Switched: "Switching",
  Closed: "Closing", Used: "Using", Paused: "Pausing", Resumed: "Resuming", Noted: "Noting", Undid: "Undoing",
  Ticked: "Ticking", Thinking: "Thinking", Writing: "Writing",
};

export function nowLine(line: string): string {
  const [first, ...rest] = line.split(" ");
  const verb = NOW_WORDS[first];
  const words = verb ? [verb, ...rest].join(" ") : line;
  // "Checking that x answers" → "Checking x"; "Opening web.x.com" reads as browsing.
  if (first === "Opened" && rest.length === 1 && rest[0].includes(".")) return `Browsing ${rest[0]}…`;
  return `${words}…`;
}

// What the pill says right now: the reply being written, else the bot's newest note (its own words for what it
// is on, like Grok's thinking line), else the step still running, else (between steps) Thinking.
export function currentLine(run: ActivityRun): string {
  const newest = [...run.steps].reverse();
  const running = newest.find((s) => s.state === "start");
  if (running?.kind === "message") return nowLine(running.line);
  const note = newest.find((s) => s.kind === "note");
  if (note) return note.line;
  return running ? nowLine(running.line) : "Thinking…";
}

export function currentKind(run: ActivityRun): RunStepOut["kind"] {
  return [...run.steps].reverse().find((s) => s.state === "start")?.kind ?? "think";
}

function seconds(run: ActivityRun): number {
  const first = Date.parse(run.steps[0]?.at ?? "");
  const last = Date.parse(run.lastAt);
  if (Number.isNaN(first) || Number.isNaN(last)) return 0;
  return Math.max(1, Math.round((last - first) / 1000));
}

export function durationWords(total: number): string {
  if (total < 60) return `${total} s`;
  const minutes = Math.floor(total / 60);
  const rest = total % 60;
  return rest === 0 ? `${minutes} min` : `${minutes} min ${rest} s`;
}

// The quiet line a finished run folds into.
export function foldedActivityLine(run: ActivityRun): string {
  const count = workSteps(run).length;
  const time = durationWords(seconds(run));
  if (count === 0) return `Thought for ${time}`;
  return `Worked for ${time} · ${count} ${count === 1 ? "step" : "steps"}`;
}

// The folded line with the site the computer card was on, when the run used the computer.
export function foldedPillLine(run: ActivityRun, computer?: ComputerRun): string {
  const host = computer ? runHost(computer) : null;
  return [foldedActivityLine(run), host].filter(Boolean).join(" · ");
}
