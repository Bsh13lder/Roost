// The computer card's store (docs/plans/2026-10-23-roost-computer-card.md): each run's computer_step frames,
// kept by run id. A run is anchored to the bot's open reply (its seq 0 placeholder) when its first step arrives,
// so the card sits in that reply and stays there, folded, once the reply settles. A run seen first in a snapshot
// (a reload mid-run) has no anchor: the chat draws it at the end. Pure helpers, no mutation.
import type { BotOut, ComputerStepOut, MessageOut } from "../api/types";

export const COMPUTER_STEPS_KEPT = 40; // the server's ring holds the same (COMPUTER_STEPS_KEPT)
export const COMPUTER_RUNS_KEPT = 30; // older runs are forgotten: their folded lines go with them

export interface ComputerRun {
  readonly runId: string;
  readonly botId: string;
  readonly threadId: string | null;
  readonly anchorId: string | null; // the reply this run's card sits in
  readonly order: number; // newer runs are larger
  readonly steps: readonly ComputerStepOut[];
}

export type ComputerRuns = Readonly<Record<string, ComputerRun>>;

const stepOf = (frame: ComputerStepOut): ComputerStepOut => ({
  bot_id: frame.bot_id, thread_id: frame.thread_id, run_id: frame.run_id, step: frame.step, kind: frame.kind,
  line: frame.line, host: frame.host, at: frame.at,
});

function openReplyOf(messagesByThread: Readonly<Record<string, readonly MessageOut[]>>, step: ComputerStepOut): string | null {
  const thread = step.thread_id ? messagesByThread[step.thread_id] ?? [] : [];
  const open = thread.filter((m) => m.seq === 0 && m.role === "bot" && m.author_bot_id === step.bot_id);
  return open.at(-1)?.id ?? null;
}

const nextOrder = (runs: ComputerRuns) => Object.values(runs).reduce((top, run) => Math.max(top, run.order), 0) + 1;

function capped(runs: Record<string, ComputerRun>): ComputerRuns {
  const all = Object.values(runs);
  if (all.length <= COMPUTER_RUNS_KEPT) return runs;
  const kept = [...all].sort((a, b) => b.order - a.order).slice(0, COMPUTER_RUNS_KEPT);
  return Object.fromEntries(kept.map((run) => [run.runId, run]));
}

function withSteps(runs: ComputerRuns, steps: readonly ComputerStepOut[], anchorId: string | null): ComputerRuns {
  const first = steps[0];
  const existing = runs[first.run_id];
  const merged = [...(existing?.steps ?? []), ...steps]
    .filter((s, i, all) => all.findIndex((other) => other.step === s.step) === i)
    .sort((a, b) => a.step - b.step)
    .slice(-COMPUTER_STEPS_KEPT);
  const run: ComputerRun = {
    runId: first.run_id, botId: first.bot_id, threadId: first.thread_id,
    anchorId: existing?.anchorId ?? anchorId, order: existing?.order ?? nextOrder(runs), steps: merged,
  };
  return capped({ ...runs, [run.runId]: run });
}

// One computer_step frame joins its run.
export function withComputerStep(
  runs: ComputerRuns, frame: ComputerStepOut, messagesByThread: Readonly<Record<string, readonly MessageOut[]>>,
): ComputerRuns {
  return withSteps(runs, [stepOf(frame)], openReplyOf(messagesByThread, frame));
}

// The snapshot's computer_steps (bot id -> its current run's steps) join the runs already known.
export function withSnapshotSteps(runs: ComputerRuns, byBot: Readonly<Record<string, readonly ComputerStepOut[]>> | undefined): ComputerRuns {
  return Object.values(byBot ?? {}).reduce<ComputerRuns>(
    (acc, steps) => (steps.length > 0 ? withSteps(acc, steps.map(stepOf), null) : acc), runs);
}

export function latestRunOf(runs: ComputerRuns, botId: string): ComputerRun | null {
  return Object.values(runs).filter((run) => run.botId === botId)
    .reduce<ComputerRun | null>((top, run) => (top === null || run.order > top.order ? run : top), null);
}

// Live: the bot is On it and this is its newest run. Anything else is folded into one line.
export function isLiveRun(runs: ComputerRuns, run: ComputerRun, bot: BotOut | undefined): boolean {
  return bot?.status === "on_it" && latestRunOf(runs, run.botId)?.runId === run.runId;
}

// The site the card names: the newest step that was on a web page.
export function runHost(run: ComputerRun): string | null {
  return [...run.steps].reverse().find((s) => s.host !== null)?.host ?? null;
}

// A thread's runs: those sitting in a reply (by its id) and the loose ones (no reply known), oldest first.
export function runsForThread(runs: ComputerRuns, threadId: string): { byAnchor: ReadonlyMap<string, ComputerRun>; loose: readonly ComputerRun[] } {
  const mine = Object.values(runs).filter((run) => run.threadId === threadId).sort((a, b) => a.order - b.order);
  return {
    byAnchor: new Map(mine.filter((run) => run.anchorId !== null).map((run) => [run.anchorId as string, run])),
    loose: mine.filter((run) => run.anchorId === null),
  };
}

// What placeRuns needs of a run: the computer card's runs and the activity pill's (store/activityRuns.ts) both fit.
export interface PlacedRun {
  readonly runId: string;
  readonly threadId: string | null;
  readonly anchorId: string | null;
  readonly order: number;
  readonly steps: readonly { readonly at: string }[];
}

export interface RunPlaces<R extends PlacedRun = ComputerRun> {
  readonly inRow: ReadonlyMap<string, R>; // drawn inside this reply
  readonly before: ReadonlyMap<string, readonly R[]>; // drawn just above this message
  readonly end: readonly R[]; // drawn after the last message
}

// Where each of a thread's runs is drawn. In its reply while that reply is in the list. A reply that ended with
// nothing kept (a run parked on an Ask card drops its empty placeholder) or no reply known (a reload mid-run): just
// above the bot's first message since the run's first step, else at the end.
export function placeRuns<R extends PlacedRun>(
  runs: Readonly<Record<string, R>>, threadId: string, messages: readonly MessageOut[],
): RunPlaces<R> {
  const mine = Object.values(runs).filter((run) => run.threadId === threadId).sort((a, b) => a.order - b.order);
  const shown = new Set(messages.map((m) => m.id));
  const inRow = new Map<string, R>();
  const before = new Map<string, R[]>();
  const end: R[] = [];
  for (const run of mine) {
    if (run.anchorId !== null && shown.has(run.anchorId)) { inRow.set(run.anchorId, run); continue; }
    const since = Date.parse(run.steps[0]?.at ?? "") || 0;
    const next = messages.find((m) => m.role !== "user" && (Date.parse(m.created_at) || 0) >= since && !inRow.has(m.id));
    if (next) before.set(next.id, [...(before.get(next.id) ?? []), run]);
    else end.push(run);
  }
  return { inRow, before, end };
}
