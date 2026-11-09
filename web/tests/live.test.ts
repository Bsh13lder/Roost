import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import {
  applyFrame,
  initialLiveState,
  LiveStore,
  MIN_RECONNECT_DELAY_MS,
  type MinimalSocket,
} from "../src/store/live";
import type { BotOut, MessageOut, ServerFrame } from "../src/api/types";
import { mergeMessages, nextLocalSeq } from "../src/lib/messages";
import { makeApprovalCard, makeBot, makeMessage, makeStuckCard } from "./fixtures";

const BOT: BotOut = {
  id: "bot-1",
  name: "Scout",
  job: "researcher",
  instructions: "",
  avatar: { shape: "round", color: "#10b981", badge: "none" },
  template_id: null,
  status: "resting",
  activity: null,
  model_override: null,
  off_duty: false,
  is_primary: false,
  roles: ["web"],
  created_at: "2026-10-13T00:00:00Z",
  updated_at: "2026-10-13T00:00:00Z",
};

describe("applyFrame (pure reducer)", () => {
  it("applies a snapshot frame", () => {
    const next = applyFrame(initialLiveState(), { type: "snapshot", cursor: 5, bots: [BOT] });
    expect(next.cursor).toBe(5);
    expect(next.bots["bot-1"]).toEqual(BOT);
  });

  it("applies a bot_status frame onto an already-known bot", () => {
    const withBot = applyFrame(initialLiveState(), { type: "snapshot", cursor: 1, bots: [BOT] });
    const next = applyFrame(withBot, {
      type: "bot_status",
      seq: 2,
      bot_id: "bot-1",
      status: "on_it",
      activity: "opening a page",
    });
    expect(next.bots["bot-1"].status).toBe("on_it");
    expect(next.bots["bot-1"].activity).toBe("opening a page");
    expect(next.cursor).toBe(2);
    // The reducer never mutates its input (immutability rule).
    expect(withBot.bots["bot-1"].status).toBe("resting");
  });

  it("accumulates text_delta and clears it on message_done without inventing a message", () => {
    let state = initialLiveState();
    state = applyFrame(state, {
      type: "text_delta",
      seq: 1,
      thread_id: "t1",
      message_id: "m1",
      delta: "I heard: ",
    });
    state = applyFrame(state, {
      type: "text_delta",
      seq: 2,
      thread_id: "t1",
      message_id: "m1",
      delta: "hello",
    });
    expect(state.streaming["m1"]).toBe("I heard: hello");

    // The server sends every reply it stores as a `message` frame before
    // message_done; none came, so it kept nothing and neither does the page.
    state = applyFrame(state, { type: "message_done", seq: 3, thread_id: "t1", message_id: "m1" });
    expect(state.streaming["m1"]).toBeUndefined();
    expect(state.messagesByThread["t1"] ?? []).toEqual([]);
    expect(state.cursor).toBe(3);
  });

  it("replays the real server sequence for a live reply as one message, not two (Ruling 15)", () => {
    // roost/talk/turn.py's run_turn publishes, in order: a placeholder
    // `message` frame (empty body, pre-generated id), then text_delta
    // frames, then the FINAL `message` frame carrying the SAME id, then
    // message_done. Final-review finding 2: the reducer used to append
    // every `message` frame unconditionally, so the placeholder and the
    // final reply landed as two separate entries sharing one id.
    let state = initialLiveState();
    const placeholder: MessageOut = {
      id: "m1",
      thread_id: "t1",
      role: "bot",
      body: "",
      tainted: false,
      seq: 0,
      created_at: "2026-10-13T00:00:00Z",
    };
    state = applyFrame(state, { type: "message", seq: 1, thread_id: "t1", message: placeholder });
    state = applyFrame(state, { type: "text_delta", seq: 1, thread_id: "t1", message_id: "m1", delta: "Hi " });
    state = applyFrame(state, { type: "text_delta", seq: 1, thread_id: "t1", message_id: "m1", delta: "there" });
    const final: MessageOut = { ...placeholder, body: "Hi there", seq: 4 };
    state = applyFrame(state, { type: "message", seq: 4, thread_id: "t1", message: final });
    state = applyFrame(state, { type: "message_done", seq: 5, thread_id: "t1", message_id: "m1" });

    expect(state.messagesByThread["t1"]).toHaveLength(1);
    expect(state.messagesByThread["t1"][0].body).toBe("Hi there");
  });

  it("message upserts by id even without a message_done in between", () => {
    let state = initialLiveState();
    const first: MessageOut = {
      id: "m1", thread_id: "t1", role: "bot", body: "", tainted: false, seq: 0, created_at: "2026-10-13T00:00:00Z",
    };
    state = applyFrame(state, { type: "message", seq: 1, thread_id: "t1", message: first });
    const second: MessageOut = { ...first, body: "final", seq: 2 };
    state = applyFrame(state, { type: "message", seq: 2, thread_id: "t1", message: second });

    expect(state.messagesByThread["t1"]).toHaveLength(1);
    expect(state.messagesByThread["t1"][0].body).toBe("final");
  });

  it("a message frame with a new id is appended, not merged into an existing one", () => {
    let state = initialLiveState();
    const m1: MessageOut = {
      id: "m1", thread_id: "t1", role: "user", body: "hi", tainted: false, seq: 1, created_at: "2026-10-13T00:00:00Z",
    };
    const m2: MessageOut = { ...m1, id: "m2", body: "hello back", role: "bot", seq: 2 };
    let next = applyFrame(state, { type: "message", seq: 1, thread_id: "t1", message: m1 });
    next = applyFrame(next, { type: "message", seq: 2, thread_id: "t1", message: m2 });

    expect(next.messagesByThread["t1"]).toHaveLength(2);
    expect(next.messagesByThread["t1"].map((m) => m.id)).toEqual(["m1", "m2"]);
  });
});

class FakeSocket implements MinimalSocket {
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  sent: string[] = [];
  closed = false;

  send(data: string): void {
    this.sent.push(data);
  }

  close(): void {
    this.closed = true;
  }

  open(): void {
    this.onopen?.();
  }

  receive(frame: ServerFrame): void {
    this.onmessage?.({ data: JSON.stringify(frame) });
  }

  drop(): void {
    this.onclose?.();
  }
}

describe("LiveStore", () => {
  let sockets: FakeSocket[];
  let store: LiveStore;

  beforeEach(() => {
    vi.useFakeTimers();
    sockets = [];
    store = new LiveStore("ws://test/api/events", () => {
      const socket = new FakeSocket();
      sockets.push(socket);
      return socket;
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("sends no resume on the first connection -- the snapshot is the starting point", () => {
    // Final review, finding 3: sending `resume` with cursor 0 on every
    // first connection makes the server replay the user's entire stored
    // event history (every message/bot_status frame ever stored) on
    // every page load -- the snapshot already covers "now", so a fresh
    // connection has nothing to resume FROM.
    store.connect();
    sockets[0].open();
    expect(sockets[0].sent).toEqual([]);
  });

  it("notifies subscribers as frames are applied", () => {
    const seen: number[] = [];
    store.subscribe((state) => seen.push(state.cursor));
    store.connect();
    sockets[0].open();
    sockets[0].receive({ type: "snapshot", cursor: 5, bots: [BOT] });
    expect(seen).toContain(5);
    expect(store.getState().bots["bot-1"]).toEqual(BOT);
  });

  it("reconnects after a drop and resumes from the last cursor", () => {
    store.connect();
    sockets[0].open();
    sockets[0].receive({ type: "snapshot", cursor: 7, bots: [BOT] });

    sockets[0].drop();
    expect(sockets).toHaveLength(1); // reconnect is scheduled, not immediate

    vi.advanceTimersByTime(MIN_RECONNECT_DELAY_MS);
    expect(sockets).toHaveLength(2);

    sockets[1].open();
    expect(sockets[1].sent).toEqual([JSON.stringify({ type: "resume", cursor: 7 })]);
  });

  it("tells frame listeners about every frame before applying it", () => {
    store.connect();
    sockets[0].open();
    const seen: string[] = [];
    const before: number[] = [];
    const stop = store.onFrame((frame, state) => { seen.push(frame.type); before.push(state.cursor); });
    sockets[0].receive({ type: "bot_removed", seq: 2, bot_id: "x" });
    stop();
    sockets[0].receive({ type: "bot_removed", seq: 3, bot_id: "y" });
    expect(seen).toEqual(["bot_removed"]);
    expect(before).toEqual([0]);
  });

  it("does not reconnect after an explicit close", () => {
    store.connect();
    sockets[0].open();
    store.close();
    sockets[0].drop();
    vi.advanceTimersByTime(MIN_RECONNECT_DELAY_MS * 4);
    expect(sockets).toHaveLength(1);
  });
});

describe("teamwork frames", () => {
  it("applies a bot_updated frame", () => {
    const withBot = applyFrame(initialLiveState(), { type: "snapshot", cursor: 1, bots: [makeBot()] });
    const next = applyFrame(withBot, { type: "bot_updated", seq: 2, bot: makeBot({ is_primary: true, off_duty: true }) });
    expect(next.bots["bot-1"].is_primary).toBe(true);
    expect(next.bots["bot-1"].off_duty).toBe(true);
    expect(next.cursor).toBe(2);
  });

  it("a bot_updated frame with new voice settings (set_my_voice, the Voice fold) replaces the bot's voice", () => {
    const withBot = applyFrame(initialLiveState(), { type: "snapshot", cursor: 1, bots: [makeBot()] });
    const voice = { speaker: "ryan", tone: "calm", speed: 0.75, read_aloud: true, correct_english: true };
    const next = applyFrame(withBot, { type: "bot_updated", seq: 2, bot: makeBot({ voice, updated_at: "y" }) });
    expect(next.bots["bot-1"].voice).toEqual(voice);
  });

  it("moves a final reply after the handoff lines posted while it streamed", () => {
    let state = applyFrame(initialLiveState(), { type: "message", seq: 1, thread_id: "t", message: makeMessage({ id: "reply", thread_id: "t", seq: 0, body: "" }) });
    state = applyFrame(state, { type: "message", seq: 2, thread_id: "t", message: makeMessage({ id: "line", thread_id: "t", role: "activity", kind: "handoff", seq: 5, body: "Chief → Scout: x" }) });
    state = applyFrame(state, { type: "message", seq: 3, thread_id: "t", message: makeMessage({ id: "reply", thread_id: "t", seq: 6, body: "done" }) });
    expect(state.messagesByThread.t.map((m) => m.id)).toEqual(["line", "reply"]);
  });

  it("drops a placeholder that closes with nothing streamed (a Stop before any text)", () => {
    let state = applyFrame(initialLiveState(), { type: "message", seq: 1, thread_id: "t", message: makeMessage({ id: "r", thread_id: "t", seq: 0, body: "" }) });
    state = applyFrame(state, { type: "message_done", seq: 2, thread_id: "t", message_id: "r" });
    expect(state.messagesByThread.t).toEqual([]);
  });

  it("drops a placeholder the server closed without storing what streamed", () => {
    let state = applyFrame(initialLiveState(), { type: "message", seq: 1, thread_id: "t", message: makeMessage({ id: "r", thread_id: "t", seq: 0, body: "" }) });
    state = applyFrame(state, { type: "text_delta", seq: 2, thread_id: "t", message_id: "r", delta: "Dear landl" });
    state = applyFrame(state, { type: "message_done", seq: 43, thread_id: "t", message_id: "r" });
    expect(state.messagesByThread.t).toEqual([]);
    expect(state.streaming.r).toBeUndefined();
  });

  it("adds no empty bubble for a reply it never saw that closes with nothing streamed", () => {
    // The page connected after the placeholder frame went out, then a Stop closed it.
    const state = applyFrame(initialLiveState(), { type: "message_done", seq: 2, thread_id: "t", message_id: "r" });
    expect(state.messagesByThread.t ?? []).toEqual([]);
    expect(state.cursor).toBe(2);
  });

  it("keeps a Stop-shortened reply in its chronological slot once later messages are stored", () => {
    // Fix round 2: frame seqs are the hub's per-USER cursor (every thread's
    // and bot's frames), far ahead of this thread's own per-thread seqs.
    // The server stores the cut-short reply and sends it with its real
    // per-thread seq; the page must never put the cursor (43) in its place.
    let state = applyFrame(initialLiveState(), {
      type: "message",
      seq: 40,
      thread_id: "t",
      message: makeMessage({ id: "r1", thread_id: "t", seq: 0, body: "" }),
    });
    state = applyFrame(state, { type: "text_delta", seq: 41, thread_id: "t", message_id: "r1", delta: "partial" });
    state = applyFrame(state, { type: "message", seq: 42, thread_id: "t", message: makeMessage({ id: "r1", thread_id: "t", seq: 2, body: "partial" }) });
    state = applyFrame(state, { type: "message_done", seq: 43, thread_id: "t", message_id: "r1" }); // Stop

    const stored = [
      makeMessage({ id: "u1", role: "user", thread_id: "t", seq: 1 }),
      makeMessage({ id: "u2", role: "user", thread_id: "t", seq: 3 }),
      makeMessage({ id: "r2", thread_id: "t", seq: 4 }),
    ];
    const merged = mergeMessages(stored, state.messagesByThread.t);
    expect(merged.map((m) => m.id)).toEqual(["u1", "r1", "u2", "r2"]);
    expect(nextLocalSeq(merged)).toBe(4.5);
  });

  it("never puts the hub's cursor into a thread's messages when it closes a reply", () => {
    let state = applyFrame(initialLiveState(), { type: "message", seq: 40, thread_id: "t", message: makeMessage({ id: "r1", thread_id: "t", seq: 0, body: "" }) });
    state = applyFrame(state, { type: "text_delta", seq: 41, thread_id: "t", message_id: "r1", delta: "partial" });
    state = applyFrame(state, { type: "message_done", seq: 43, thread_id: "t", message_id: "r1" });
    state = applyFrame(state, { type: "text_delta", seq: 44, thread_id: "t", message_id: "r9", delta: "unseen" });
    state = applyFrame(state, { type: "message_done", seq: 45, thread_id: "t", message_id: "r9" });

    const stored = [makeMessage({ id: "u1", role: "user", thread_id: "t", seq: 1 })];
    expect(nextLocalSeq(mergeMessages(stored, state.messagesByThread.t))).toBe(1.5);
  });
});

describe("board frames", () => {
  it("counts tasks_changed and money_changed frames so the Board can reload", () => {
    const afterTasks = applyFrame(initialLiveState(), { type: "tasks_changed", seq: 5, change: "created", task_id: "t1" });
    const afterMoney = applyFrame(afterTasks, { type: "money_changed", seq: 6, change: "expense_created", id: "e1" });
    expect(afterMoney.boardVersion).toEqual({ tasks: 1, money: 1, notes: 0, documents: 0, memories: 0, dayNotes: 0 });
    expect(afterMoney.cursor).toBe(6);
  });

  it("counts notes_changed frames so the Notes tab can reload", () => {
    const next = applyFrame(initialLiveState(), { type: "notes_changed", seq: 7, change: "created", note_id: "n1" });
    expect(next.boardVersion.notes).toBe(1);
    expect(next.cursor).toBe(7);
  });

  it("day_notes_changed bumps the day notes version", () => {
    const next = applyFrame(initialLiveState(), { type: "day_notes_changed", seq: 11, change: "created", id: "n1", day: "2026-10-21" });
    expect(next.boardVersion.dayNotes).toBe(1);
    expect(next.boardVersion.tasks).toBe(0);
    expect(next.cursor).toBe(11);
  });

  it("bumps the memories version on memories_changed", () => {
    const next = applyFrame(initialLiveState(), { type: "memories_changed", seq: 9, change: "created", memory_id: "m1", bot_id: null });
    expect(next.boardVersion.memories).toBe(1);
    expect(next.cursor).toBe(9);
  });

  it("counts documents_changed frames so the Documents tab can reload", () => {
    const next = applyFrame(initialLiveState(), {
      type: "documents_changed", seq: 8, change: "created", document_id: "d1", kind: "doc",
    });
    expect(next.boardVersion.documents).toBe(1);
  });

  // Review Focus 4: deleting a project unlinks its tasks, notes and documents with no frame of their own.
  it("refreshes tasks, notes and documents when a project is deleted", () => {
    const before = initialLiveState();
    const deleted = applyFrame(before, { type: "money_changed", seq: 9, change: "project_deleted", id: "p1" });
    expect(deleted.boardVersion).toEqual({ tasks: 1, money: 1, notes: 1, documents: 1, memories: 0, dayNotes: 0 });
    expect(deleted.cursor).toBe(9);
    const toppedUp = applyFrame(deleted, { type: "money_changed", seq: 10, change: "topup_added", id: "tu1" });
    expect(toppedUp.boardVersion).toEqual({ tasks: 1, money: 2, notes: 1, documents: 1, memories: 0, dayNotes: 0 });
    // The reducer never mutates its input (immutability rule).
    expect(before.boardVersion).toEqual({ tasks: 0, money: 0, notes: 0, documents: 0, memories: 0, dayNotes: 0 });
  });
});

describe("stuck frames", () => {
  it("starts with no Stuck cards", () => {
    expect(initialLiveState().stuckCards).toEqual({});
  });

  it("a stuck_card frame upserts the card by id and advances the cursor", () => {
    const card = makeStuckCard();
    const opened = applyFrame(initialLiveState(), { type: "stuck_card", seq: 9, card });
    const cleared = applyFrame(opened, {
      type: "stuck_card", seq: 10, card: { ...card, state: "cleared", closed_at: "2026-10-14T10:05:00Z" },
    });
    expect(opened.stuckCards).toEqual({ "card-1": card });
    expect(Object.keys(cleared.stuckCards)).toEqual(["card-1"]);
    expect(cleared.stuckCards["card-1"].state).toBe("cleared");
    expect(cleared.cursor).toBe(10);
    // The reducer never mutates its input (immutability rule).
    expect(opened.stuckCards["card-1"].state).toBe("open");
  });
});

describe("approval frames", () => {
  it("keeps the newest approval_card frame per card", () => {
    expect(initialLiveState().approvalCards).toEqual({});
    const card = makeApprovalCard();
    const opened = applyFrame(initialLiveState(), { type: "approval_card", seq: 4, card });
    const closed = applyFrame(opened, { type: "approval_card", seq: 5, card: { ...card, state: "approved", closed_at: "x" } });
    expect(Object.keys(closed.approvalCards)).toEqual(["card-a"]);
    expect(closed.approvalCards["card-a"].state).toBe("approved");
    expect(closed.cursor).toBe(5);
    expect(opened.approvalCards["card-a"].state).toBe("open");
  });
});

describe("tool lines (redesign P2)", () => {
  const placeholder = (id: string): ServerFrame => ({
    type: "message", seq: 1, thread_id: "t", message: makeMessage({ id, thread_id: "t", seq: 0, body: "", author_bot_id: "bot-1" }),
  });
  const status = (seq: number, activity: string | null, botId = "bot-1", state: BotOut["status"] = "on_it"): ServerFrame =>
    ({ type: "bot_status", seq, bot_id: botId, status: state, activity });

  it("starts with none", () => {
    expect(initialLiveState().toolLines).toEqual({});
  });

  it("adds each new activity of a working bot to the reply it is writing, once", () => {
    const before = applyFrame(initialLiveState(), placeholder("r1"));
    let state = applyFrame(before, status(2, "adding a task"));
    state = applyFrame(state, status(3, "adding a task"));
    state = applyFrame(state, status(4, "saving a note"));
    expect(state.toolLines).toEqual({ r1: ["adding a task", "saving a note"] });
    expect(before.toolLines).toEqual({}); // the reducer never mutates its input
  });

  it("keeps the lines on the stored reply, which takes the placeholder's id", () => {
    let state = applyFrame(initialLiveState(), placeholder("r1"));
    state = applyFrame(state, status(2, "adding a task"));
    state = applyFrame(state, {
      type: "message", seq: 3, thread_id: "t", message: makeMessage({ id: "r1", thread_id: "t", seq: 4, body: "Added.", author_bot_id: "bot-1" }),
    });
    state = applyFrame(state, { type: "message_done", seq: 5, thread_id: "t", message_id: "r1" });
    state = applyFrame(state, status(6, "checking your tasks")); // no reply is open now: it joins none
    expect(state.toolLines).toEqual({ r1: ["adding a task"] });
  });

  it("ignores another bot's steps, a status with no activity, and a Stuck bot's line", () => {
    let state = applyFrame(initialLiveState(), placeholder("r1"));
    state = applyFrame(state, status(2, "opening elpais.com", "bot-2"));
    state = applyFrame(state, status(3, null));
    state = applyFrame(state, status(4, "waiting for login.example to let me in", "bot-1", "stuck"));
    expect(state.toolLines).toEqual({});
  });

  it("drops the lines of a reply that closed with nothing stored", () => {
    let state = applyFrame(initialLiveState(), placeholder("r1"));
    state = applyFrame(state, status(2, "adding a task"));
    state = applyFrame(state, { type: "message_done", seq: 3, thread_id: "t", message_id: "r1" });
    expect(state.toolLines).toEqual({});
  });
});

describe("routines frames (routines plan)", () => {
  it("count routine, question and proposal changes and keep the newest Plan revision per bot", () => {
    let state = initialLiveState();
    state = applyFrame(state, { type: "routines_changed", seq: 1, bot_id: "bot-1" });
    state = applyFrame(state, { type: "questions_changed", seq: 2, bot_id: "bot-1" });
    state = applyFrame(state, { type: "proposals_changed", seq: 3, bot_id: "bot-1" });
    expect(state.routineVersion).toEqual({ routines: 1, questions: 1, proposals: 1 });
    state = applyFrame(state, { type: "plan_changed", seq: 4, bot_id: "bot-1", revision: 5 });
    state = applyFrame(state, { type: "plan_changed", seq: 5, bot_id: "bot-1", revision: 3 });
    expect(state.planRevisions).toEqual({ "bot-1": 5 });
    expect(state.cursor).toBe(5);
    expect(state.boardVersion.tasks).toBe(0);
  });
});

describe("speech_ready frames (call mode, contract B)", () => {
  it("keeps how many parts of a reply can be heard, and when the last one is in", () => {
    let state = applyFrame(initialLiveState(), {
      type: "speech_ready", seq: 4, thread_id: "t1", message_id: "m1", part: 0, done: false,
    });
    expect(state.speechReady["m1"]).toEqual({ parts: 1, done: false });
    expect(state.cursor).toBe(4);
    state = applyFrame(state, { type: "speech_ready", seq: 5, thread_id: "t1", message_id: "m1", part: 1, done: false });
    state = applyFrame(state, { type: "speech_ready", seq: 6, thread_id: "t1", message_id: "m1", part: 1, done: true });
    expect(state.speechReady["m1"]).toEqual({ parts: 2, done: true });
    // A replayed older frame never lowers the count.
    state = applyFrame(state, { type: "speech_ready", seq: 7, thread_id: "t1", message_id: "m1", part: 0, done: false });
    expect(state.speechReady["m1"]).toEqual({ parts: 2, done: true });
  });

  it("an unknown frame type is still ignored", () => {
    const start = initialLiveState();
    expect(applyFrame(start, { type: "something_new", seq: 9 } as unknown as ServerFrame)).toBe(start);
  });
});
