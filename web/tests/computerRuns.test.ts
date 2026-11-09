import { describe, expect, it } from "vitest";
import { applyFrame, initialLiveState } from "../src/store/live";
import {
  COMPUTER_RUNS_KEPT, COMPUTER_STEPS_KEPT, isLiveRun, latestRunOf, placeRuns, runHost, runsForThread,
} from "../src/store/computerRuns";
import type { ComputerStepFrame, ComputerStepOut } from "../src/api/types";
import { makeBot, makeMessage } from "./fixtures";

function step(n: number, over: Partial<ComputerStepOut> = {}): ComputerStepOut {
  return {
    bot_id: "bot-1", thread_id: "t-1", run_id: "run-1", step: n, kind: "click", line: `Clicked 'Item ${n}'`,
    host: "shop.example", at: "2026-10-23T14:00:00+00:00", ...over,
  };
}

const frame = (n: number, over: Partial<ComputerStepOut> = {}): ComputerStepFrame =>
  ({ type: "computer_step", seq: 4, ...step(n, over) });

function withPlaceholder() {
  const placeholder = makeMessage({ id: "reply-1", thread_id: "t-1", role: "bot", seq: 0, body: "", author_bot_id: "bot-1" });
  return applyFrame(initialLiveState(), { type: "message", seq: 1, thread_id: "t-1", message: placeholder });
}

describe("computer runs (the computer card's store)", () => {
  it("anchors a run to the bot's open reply and keeps its steps in order", () => {
    let state = withPlaceholder();
    state = applyFrame(state, frame(1, { kind: "look", line: "Looked at the screen" }));
    state = applyFrame(state, frame(2));
    const run = state.computerRuns["run-1"];
    expect(run.anchorId).toBe("reply-1");
    expect(run.steps.map((s) => s.step)).toEqual([1, 2]);
    expect(runsForThread(state.computerRuns, "t-1").byAnchor.get("reply-1")?.runId).toBe("run-1");
    expect(runsForThread(state.computerRuns, "t-2").loose).toEqual([]);
  });

  it("keeps only the newest steps of a long run", () => {
    let state = withPlaceholder();
    for (let n = 1; n <= COMPUTER_STEPS_KEPT + 5; n += 1) state = applyFrame(state, frame(n));
    const steps = state.computerRuns["run-1"].steps;
    expect(steps).toHaveLength(COMPUTER_STEPS_KEPT);
    expect(steps.at(-1)?.step).toBe(COMPUTER_STEPS_KEPT + 5);
  });

  it("a run without an open reply (a reload mid-run) is loose, from the snapshot too", () => {
    const state = applyFrame(initialLiveState(), {
      type: "snapshot", cursor: 3, bots: [makeBot({ id: "bot-1", status: "on_it" })],
      computer_steps: { "bot-1": [step(1), step(2)] },
    });
    const { loose } = runsForThread(state.computerRuns, "t-1");
    expect(loose.map((run) => run.steps.length)).toEqual([2]);
  });

  it("the snapshot keeps a run's anchor it already knew", () => {
    let state = applyFrame(withPlaceholder(), frame(1));
    state = applyFrame(state, { type: "snapshot", cursor: 9, bots: [], computer_steps: { "bot-1": [step(1), step(2)] } });
    expect(state.computerRuns["run-1"].anchorId).toBe("reply-1");
    expect(state.computerRuns["run-1"].steps).toHaveLength(2);
  });

  it("only the bot's newest run is live, and only while it is On it", () => {
    let state = applyFrame(withPlaceholder(), frame(1, { run_id: "run-1" }));
    state = applyFrame(state, frame(1, { run_id: "run-2" }));
    const working = makeBot({ id: "bot-1", status: "on_it" });
    expect(latestRunOf(state.computerRuns, "bot-1")?.runId).toBe("run-2");
    expect(isLiveRun(state.computerRuns, state.computerRuns["run-2"], working)).toBe(true);
    expect(isLiveRun(state.computerRuns, state.computerRuns["run-1"], working)).toBe(false);
    expect(isLiveRun(state.computerRuns, state.computerRuns["run-2"], { ...working, status: "resting" })).toBe(false);
  });

  it("the card's host is the newest step that had one", () => {
    let state = applyFrame(withPlaceholder(), frame(1, { host: "www.upwork.com" }));
    state = applyFrame(state, frame(2, { host: null, kind: "open_app", line: "Opened Files" }));
    expect(runHost(state.computerRuns["run-1"])).toBe("www.upwork.com");
  });

  it("a run sits in its reply; once that reply is gone (parked on a card) it sits above the bot's next message", () => {
    const state = applyFrame(withPlaceholder(), frame(1, { at: "2026-10-23T14:00:00+00:00" }));
    const you = makeMessage({ id: "you-1", thread_id: "t-1", role: "user", created_at: "2026-10-23T13:59:00Z" });
    const reply = state.messagesByThread["t-1"][0];
    expect(placeRuns(state.computerRuns, "t-1", [you, reply]).inRow.get("reply-1")?.runId).toBe("run-1");
    const ask = makeMessage({ id: "ask-1", thread_id: "t-1", role: "bot", seq: 3, created_at: "2026-10-23T14:00:05Z" });
    const placed = placeRuns(state.computerRuns, "t-1", [you, ask]);
    expect(placed.inRow.size).toBe(0);
    expect(placed.before.get("ask-1")?.map((run) => run.runId)).toEqual(["run-1"]);
    expect(placeRuns(state.computerRuns, "t-1", [you]).end.map((run) => run.runId)).toEqual(["run-1"]);
  });

  it("forgets the oldest runs past the cap", () => {
    let state = initialLiveState();
    for (let n = 0; n < COMPUTER_RUNS_KEPT + 3; n += 1) state = applyFrame(state, frame(1, { run_id: `run-${n}` }));
    expect(Object.keys(state.computerRuns)).toHaveLength(COMPUTER_RUNS_KEPT);
    expect(state.computerRuns["run-0"]).toBeUndefined();
  });
});
