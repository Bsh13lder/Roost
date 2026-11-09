import { describe, expect, it } from "vitest";
import { robotEventsFor, thinkingBots } from "../src/components/robot/events";
import { applyFrame, initialLiveState, type LiveState } from "../src/store/live";
import type { ServerFrame } from "../src/api/types";
import { makeBot, makeMessage } from "./fixtures";

// Live frames become ghost events (avatars v5 "Statuses and events"): a creating step that ends →
// created; a run that settles → done; a reply in a chat you are not viewing → msg; a bot turning Stuck →
// stuck once. Thinking is a state: a run started with no text yet.
const scout = makeBot({ id: "scout", status: "on_it", activity: "adding a task" });
const ledger = makeBot({ id: "ledger", name: "Ledger", status: "resting" });

function withBots(...bots: ReturnType<typeof makeBot>[]): LiveState {
  return applyFrame(initialLiveState(), { type: "snapshot", cursor: 1, bots });
}

const placeholder = makeMessage({ id: "r-1", thread_id: "t-scout", role: "bot", seq: 0, body: "", author_bot_id: "scout" });

describe("robotEventsFor", () => {
  it("a creating step that ends is Created something", () => {
    const state = withBots(scout, ledger);
    const next: ServerFrame = { type: "bot_status", seq: 2, bot_id: "scout", status: "on_it", activity: "opening elpais.com" };
    expect(robotEventsFor(next, state, null)).toEqual([{ botId: "scout", name: "created" }]);
    const settled: ServerFrame = { type: "bot_status", seq: 2, bot_id: "scout", status: "resting", activity: null };
    expect(robotEventsFor(settled, state, null)).toEqual([{ botId: "scout", name: "created" }]);
  });

  it("a step that was not creating anything, or the same step again, is nothing", () => {
    const reading = withBots(makeBot({ id: "scout", status: "on_it", activity: "reading the page" }));
    expect(robotEventsFor({ type: "bot_status", seq: 2, bot_id: "scout", status: "on_it", activity: "adding a task" }, reading, null)).toEqual([]);
    const same: ServerFrame = { type: "bot_status", seq: 2, bot_id: "scout", status: "on_it", activity: "adding a task" };
    expect(robotEventsFor(same, withBots(scout), null)).toEqual([]);
  });

  it("a bot turning Stuck glitches once; already Stuck, it does not again", () => {
    const stuck: ServerFrame = { type: "bot_status", seq: 2, bot_id: "ledger", status: "stuck", activity: "a sign-in page" };
    expect(robotEventsFor(stuck, withBots(ledger), null)).toEqual([{ botId: "ledger", name: "stuck" }]);
    expect(robotEventsFor(stuck, withBots(makeBot({ id: "ledger", status: "stuck" })), null)).toEqual([]);
  });

  it("a run that settles is Done, for the reply's bot", () => {
    const state = applyFrame(withBots(scout), { type: "message", seq: 2, thread_id: "t-scout", message: placeholder });
    const done: ServerFrame = { type: "message_done", seq: 3, thread_id: "t-scout", message_id: "r-1" };
    expect(robotEventsFor(done, state, "scout")).toEqual([{ botId: "scout", name: "done" }]);
    expect(robotEventsFor({ ...done, message_id: "unknown" }, state, null)).toEqual([]);
  });

  it("a reply that lands in a chat you are not viewing is New message; in the open chat it is not", () => {
    const reply = makeMessage({ id: "r-2", thread_id: "t-scout", role: "bot", seq: 7, body: "Done!", author_bot_id: "scout" });
    const frame: ServerFrame = { type: "message", seq: 4, thread_id: "t-scout", message: reply };
    expect(robotEventsFor(frame, withBots(scout), "ledger")).toEqual([{ botId: "scout", name: "msg" }]);
    expect(robotEventsFor(frame, withBots(scout), null)).toEqual([{ botId: "scout", name: "msg" }]);
    expect(robotEventsFor(frame, withBots(scout), "scout")).toEqual([]);
    // The empty placeholder, a user's message and a handoff line are not replies.
    expect(robotEventsFor({ ...frame, message: placeholder }, withBots(scout), null)).toEqual([]);
    expect(robotEventsFor({ ...frame, message: { ...reply, role: "user", author_bot_id: null } }, withBots(scout), null)).toEqual([]);
    expect(robotEventsFor({ ...frame, message: { ...reply, kind: "handoff" } }, withBots(scout), null)).toEqual([]);
  });

  it("other frames are nothing", () => {
    expect(robotEventsFor({ type: "tasks_changed", seq: 9, change: "created", task_id: "t" }, withBots(scout), null)).toEqual([]);
  });
});

describe("thinkingBots", () => {
  it("is every bot with a reply started and no text yet", () => {
    const started = applyFrame(withBots(scout, ledger), { type: "message", seq: 2, thread_id: "t-scout", message: placeholder });
    expect([...thinkingBots(started)]).toEqual(["scout"]);
    const streaming = applyFrame(started, { type: "text_delta", seq: 3, thread_id: "t-scout", message_id: "r-1", delta: "On" });
    expect([...thinkingBots(streaming)]).toEqual([]);
    const done = applyFrame(started, { type: "message_done", seq: 3, thread_id: "t-scout", message_id: "r-1" });
    expect([...thinkingBots(done)]).toEqual([]);
  });
});
