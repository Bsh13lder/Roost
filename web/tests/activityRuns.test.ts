import { describe, expect, it } from "vitest";
import type { BotOut, MessageOut, RunStepOut } from "../src/api/types";
import {
  currentKind, currentLine, foldedActivityLine, isLiveActivity, nowLine, timelineSteps, withRunStep,
  withSnapshotRunSteps, workSteps, type ActivityRuns,
} from "../src/store/activityRuns";

const step = (n: number, kind: RunStepOut["kind"], line: string, state: RunStepOut["state"], at: string,
  run = "r1"): RunStepOut => ({
  bot_id: "b1", thread_id: "t1", run_id: run, step: n, kind, line, host: null, at, state,
});

const placeholder: MessageOut = {
  id: "reply-1", thread_id: "t1", role: "bot", body: "", tainted: false, seq: 0,
  created_at: "2026-10-23T20:00:00Z", author_bot_id: "b1",
} as MessageOut;

const play = (frames: RunStepOut[], messages: MessageOut[] = [placeholder]): ActivityRuns =>
  frames.reduce<ActivityRuns>((runs, f) => withRunStep(runs, f, { t1: messages }), {});

describe("activity runs", () => {
  it("anchors a run to the bot's open reply and lets a step's ending replace its start", () => {
    const runs = play([
      step(1, "think", "Thinking", "start", "2026-10-23T20:00:00Z"),
      step(1, "think", "Thinking", "done", "2026-10-23T20:00:02Z"),
      step(2, "search", "Searched the web for “x”", "start", "2026-10-23T20:00:02Z"),
    ]);
    const run = runs.r1;
    expect(run.anchorId).toBe("reply-1");
    expect(run.steps.map((s) => [s.step, s.state])).toEqual([[1, "done"], [2, "start"]]);
    expect(run.steps[0].at).toBe("2026-10-23T20:00:00Z"); // a step keeps the time it began
    expect(currentLine(run)).toBe("Searching the web for “x”…");
    expect(currentKind(run)).toBe("search");
  });

  it("never lets a late start undo an ending, and says Thinking between steps", () => {
    const runs = play([
      step(2, "program", "Ran a program", "done", "2026-10-23T20:00:05Z"),
      step(2, "program", "Ran a program", "start", "2026-10-23T20:00:01Z"),
    ]);
    expect(runs.r1.steps[0].state).toBe("done");
    expect(currentLine(runs.r1)).toBe("Thinking…");
    expect(currentKind(runs.r1)).toBe("think");
  });

  it("folds into how long it worked and how many real steps it took", () => {
    const runs = play([
      step(1, "think", "Thinking", "start", "2026-10-23T20:00:00Z"),
      step(2, "read", "Opened web.whatsapp.com", "start", "2026-10-23T20:00:03Z"),
      step(2, "read", "Opened web.whatsapp.com", "done", "2026-10-23T20:00:20Z"),
      step(3, "message", "Writing the reply", "start", "2026-10-23T20:00:42Z"),
    ]);
    expect(workSteps(runs.r1)).toHaveLength(1);
    expect(foldedActivityLine(runs.r1)).toBe("Worked for 42 s · 1 step");
    const thought = play([step(1, "think", "Thinking", "start", "2026-10-23T20:00:00Z"),
      step(1, "think", "Thinking", "done", "2026-10-23T20:00:04Z")]);
    expect(foldedActivityLine(thought.r1)).toBe("Thought for 4 s");
  });

  it("reads browsing and other verbs in the present", () => {
    expect(nowLine("Opened web.whatsapp.com")).toBe("Browsing web.whatsapp.com…");
    expect(nowLine("Checked that web.whatsapp.com answers")).toBe("Checking that web.whatsapp.com answers…");
    expect(nowLine("Something odd")).toBe("Something odd…");
  });

  it("joins a snapshot's steps with no anchor and knows which run is live", () => {
    const runs = withSnapshotRunSteps({}, { b1: [step(1, "think", "Thinking", "start", "2026-10-23T20:00:00Z")] });
    expect(runs.r1.anchorId).toBeNull();
    const onIt = { id: "b1", status: "on_it" } as BotOut;
    expect(isLiveActivity(runs, runs.r1, onIt)).toBe(true);
    expect(isLiveActivity(runs, runs.r1, { ...onIt, status: "resting" } as BotOut)).toBe(false);
  });
});

// Owner, 2026-11-04: the bot's words between steps belong inside the pill's steps, never as chat bubbles.
describe("notes", () => {
  const note = (n: number, line: string, at: string, tainted = false): RunStepOut =>
    ({ ...step(n, "note", line, "done", at), tainted });

  it("the pill says the newest note while it works, and Writing once the reply streams", () => {
    const runs = play([
      step(1, "think", "Thinking", "done", "2026-10-23T20:00:00Z"),
      note(2, "Search is done. I'm picking the Acme job.", "2026-10-23T20:00:02Z", true),
      step(3, "read", "Opened upwork.com", "start", "2026-10-23T20:00:03Z"),
    ]);
    expect(currentLine(runs.r1)).toBe("Search is done. I'm picking the Acme job.");
    expect(currentKind(runs.r1)).toBe("read"); // the robot still acts out the step
    expect(runs.r1.steps[1].tainted).toBe(true);
    const writing = withRunStep(runs, step(4, "message", "Writing the reply", "start", "2026-10-23T20:00:09Z"),
      { t1: [placeholder] });
    expect(currentLine(writing.r1)).toBe("Writing the reply…");
  });

  it("notes are not counted as steps, but the sheet's timeline keeps them in order", () => {
    const runs = play([
      note(1, "First the search.", "2026-10-23T20:00:00Z"),
      step(2, "search", "Searched the web for “x”", "done", "2026-10-23T20:00:02Z"),
      note(3, "Found two; opening the first.", "2026-10-23T20:00:10Z"),
      step(4, "think", "Thinking", "done", "2026-10-23T20:00:11Z"),
    ]);
    expect(workSteps(runs.r1)).toHaveLength(1);
    expect(foldedActivityLine(runs.r1)).toBe("Worked for 11 s · 1 step");
    expect(timelineSteps(runs.r1).map((s) => s.kind)).toEqual(["note", "search", "note"]);
  });
});
