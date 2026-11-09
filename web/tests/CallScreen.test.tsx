import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { CallMicHandlers, CallMicMode } from "../src/lib/callMic";
import type { BotOut, MessageOut } from "../src/api/types";
import type { LiveSource } from "../src/store/speech";
import type { SpeechReady } from "../src/store/live";
import { makeApprovalCard, makeBot, makeMessage, makeStep } from "./fixtures";

// The microphone, faked: a test says a turn, raises a barge-in, and reads the mode the call put it in.
const mic = vi.hoisted(() => ({
  handlers: null as CallMicHandlers | null,
  modes: [] as CallMicMode[],
  flushes: 0,
  resumes: 0,
  closed: 0,
  echo: false,
  audioState: "running" as AudioContextState,
  fail: null as Error | null,
}));
vi.mock("../src/lib/callMic", () => ({
  openCallMic: vi.fn(async (handlers: CallMicHandlers) => {
    if (mic.fail) throw mic.fail;
    mic.handlers = handlers;
    return {
      setMode: (m: CallMicMode) => mic.modes.push(m),
      flush: () => { mic.flushes += 1; },
      resume: async () => { mic.resumes += 1; mic.audioState = "running"; },
      audioState: () => mic.audioState,
      echoCancellation: mic.echo,
      close: () => { mic.closed += 1; },
    };
  }),
}));
// The player, faked: stored replies, live replies and fixed lines are recorded, and the test finishes them.
const speech = vi.hoisted(() => ({
  spoken: [] as string[], finish: null as (() => void) | null, stops: 0,
  lines: [] as string[],
  live: [] as string[], liveSource: null as LiveSource | null, finishLive: null as (() => void) | null,
  failLive: null as ((err: unknown) => void) | null, liveUnavailable: false,
}));
vi.mock("../src/store/speech", () => {
  class LiveSpeechUnavailable extends Error {}
  return {
    LiveSpeechUnavailable,
    speakMessage: vi.fn((_thread: string, id: string) => {
      speech.spoken.push(id);
      return new Promise<void>((resolve) => { speech.finish = resolve; });
    }),
    speakLive: vi.fn((_thread: string, id: string, source: LiveSource) => {
      speech.live.push(id);
      speech.liveSource = source;
      if (speech.liveUnavailable) return Promise.reject(new LiveSpeechUnavailable());
      return new Promise<void>((resolve, reject) => { speech.finishLive = resolve; speech.failLive = reject; });
    }),
    speakLine: vi.fn(async (_bot: string, key: string) => { speech.lines.push(key); }),
    stopSpeech: vi.fn(() => { speech.stops += 1; speech.finish?.(); speech.finishLive?.(); }),
    speechErrorText: (err: unknown) => String(err),
    isSoundBlocked: (err: unknown) => err instanceof DOMException && err.name === "NotAllowedError",
  };
});
vi.mock("../src/lib/audioUnlock", () => ({ takeUnlockedContext: () => null }));

import CallScreen from "../src/components/call/CallScreen";
import {
  CALL_HEARTBEAT_MS, CALL_HEARING_TIMEOUT_MS, CALL_STILL_ON_IT_AFTER_MS, CALL_STILL_ON_IT_EVERY_MS,
  CALL_THINKING_TIMEOUT_MS, SPEAKER_TAIL_MS,
} from "../src/components/call/callConstants";

const WAV = new Blob([new Uint8Array(100)], { type: "audio/wav" });
const GIGS = (status: BotOut["status"] = "resting", activity: string | null = null) =>
  makeBot({ id: "b1", name: "Gigs", status, activity });

interface Hit { url: string; method: string }

function stubServer({ warm = 200, heard = "Add milk to my list", call = 200, holdWarm = false, holdHearing = false } = {}) {
  const hits: Hit[] = [];
  const release = { warm: null as (() => void) | null };
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    hits.push({ url, method: init?.method ?? "GET" });
    if (url === "/api/voice/warm") {
      if (holdWarm) await new Promise<void>((resolve) => { release.warm = resolve; });
      return warm === 200 ? new Response(JSON.stringify({ ok: true }))
        : new Response(JSON.stringify({ detail: "Voice isn't running on your Mac yet." }), { status: warm });
    }
    if (url === "/api/voice/transcribe") {
      if (holdHearing) {
        return new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
        });
      }
      return new Response(JSON.stringify({ text: heard }));
    }
    if (url === "/api/threads/t-1/call") return new Response(JSON.stringify({ ok: true, expires_in: 60 }), { status: call });
    return new Response("{}", { status: 404 });
  }));
  return { hits, release };
}

interface Props {
  bot: BotOut; messages: MessageOut[]; streaming: Record<string, string>; speechReady: Record<string, SpeechReady>;
  approvals: Parameters<typeof CallScreen>[0]["approvals"];
}

function setup(start: Partial<Props> = {}) {
  const onSend = vi.fn(async () => "mine");
  const onClose = vi.fn();
  let props: Props = { bot: GIGS(), messages: [], streaming: {}, speechReady: {}, approvals: [], ...start };
  const draw = () => (
    <CallScreen bot={props.bot} threadId="t-1" messages={props.messages} approvals={props.approvals} stuck={[]}
      streaming={props.streaming} speechReady={props.speechReady} onSend={onSend} onClose={onClose} />
  );
  const view = render(draw());
  const update = (next: Partial<Props>) => {
    props = { ...props, ...next };
    view.rerender(draw());
  };
  return { onSend, onClose, update };
}

const status = () => screen.getByTestId("call-status").textContent;
const say = async () => { await act(async () => { mic.handlers?.onTurn(WAV); }); };
const MINE = makeMessage({ id: "mine", role: "user", body: "Add milk to my list", thread_id: "t-1" });
const PLACEHOLDER = makeMessage({ id: "p1", role: "bot", body: "", thread_id: "t-1", seq: 0, author_bot_id: "b1" });
const REPLY = makeMessage({ id: "p1", role: "bot", body: "Done, milk is on your list.", thread_id: "t-1", seq: 2, author_bot_id: "b1" });

// Hears a turn and brings the bot to the point where its reply streams.
async function askAndStream(update: ReturnType<typeof setup>["update"]) {
  await waitFor(() => expect(status()).toBe("Listening"));
  await say();
  await waitFor(() => expect(status()).toBe("Thinking…"));
  update({ messages: [MINE, PLACEHOLDER], bot: GIGS("on_it"), streaming: { p1: "On it: adding it.\nDone, milk is on your list." } });
}

beforeEach(() => {
  mic.handlers = null; mic.modes = []; mic.flushes = 0; mic.resumes = 0; mic.closed = 0; mic.echo = false;
  mic.audioState = "running"; mic.fail = null;
  speech.spoken = []; speech.finish = null; speech.stops = 0; speech.lines = []; speech.live = []; speech.liveSource = null;
  speech.finishLive = null; speech.failLive = null; speech.liveUnavailable = false;
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers(); });

describe("CallScreen: opening", () => {
  it("listens as soon as the mic is up while the voice wakes, then greets once; the call is started on the server", async () => {
    const { hits, release } = stubServer({ holdWarm: true });
    setup();
    expect(status()).toBe("Warming up…");
    await waitFor(() => expect(status()).toBe("Listening"));
    expect(screen.getByText("Waking the voice up…")).toBeTruthy();
    expect(speech.lines).toEqual([]);
    expect(hits.some((h) => h.url === "/api/threads/t-1/call" && h.method === "POST")).toBe(true);
    await act(async () => { release.warm?.(); });
    await waitFor(() => expect(speech.lines).toEqual(["greeting"]));
    expect(screen.queryByText("Waking the voice up…")).toBeNull();
    expect(screen.getByRole("dialog", { name: "Call with Gigs" })).toBeTruthy();
    expect(mic.modes.at(-1)).toBe("listening");
  });

  it("a turn heard before the voice is warm waits for it", async () => {
    const { hits, release } = stubServer({ holdWarm: true });
    setup();
    await waitFor(() => expect(status()).toBe("Listening"));
    await say();
    expect(status()).toBe("Hearing you…");
    expect(hits.some((h) => h.url === "/api/voice/transcribe")).toBe(false);
    await act(async () => { release.warm?.(); });
    await waitFor(() => expect(hits.some((h) => h.url === "/api/voice/transcribe")).toBe(true));
  });

  it("voice that isn't running says so; a refused microphone says so", async () => {
    stubServer({ warm: 503 });
    setup();
    await waitFor(() => expect(status()).toBe("Voice isn't running on your Mac yet."));
    cleanup();
    stubServer();
    mic.fail = new Error("Roost can't use the microphone. Allow it in the browser's site settings.");
    setup();
    await waitFor(() => expect(status()).toBe("Roost can't use the microphone. Allow it in the browser's site settings."));
  });

  it("a suspended audio graph asks for a tap, and the orb's tap resumes it", async () => {
    stubServer();
    mic.audioState = "suspended";
    setup();
    await waitFor(() => expect(screen.getByText("Tap to start listening")).toBeTruthy());
    fireEvent.click(screen.getByTestId("call-orb"));
    await waitFor(() => expect(mic.resumes).toBe(1));
    await act(async () => { mic.handlers?.onAudioState?.("running"); });
    expect(screen.queryByText("Tap to start listening")).toBeNull();
  });
});

describe("CallScreen: a turn", () => {
  it("sends what you say as a call turn, shows the reply as it streams, speaks it live once, then listens again", async () => {
    stubServer();
    const { onSend, update } = setup();
    await askAndStream(update);
    expect(onSend).toHaveBeenCalledWith("Add milk to my list", { call: true, spoken: true });
    expect(mic.modes.at(-1)).toBe("off");
    expect(screen.getByText("Add milk to my list")).toBeTruthy();
    await waitFor(() => expect(speech.live).toEqual(["p1"]));
    expect(screen.getByText("Done, milk is on your list.")).toBeTruthy(); // the caption, without the On it lead
    expect(status()).toBe("Thinking…");
    await act(async () => { speech.liveSource?.onPart?.(0); });
    expect(status()).toBe("Speaking");
    update({ messages: [MINE, REPLY], bot: GIGS("resting") });
    expect(speech.spoken).toEqual([]); // never also from /speech
    await act(async () => { speech.finishLive?.(); });
    await waitFor(() => expect(status()).toBe("Listening"), { timeout: SPEAKER_TAIL_MS + 900 });
    expect(mic.modes.at(-1)).toBe("listening");
  });

  it("an english_fix line for this turn takes the place of the plain caption of your words", async () => {
    stubServer();
    const { update } = setup();
    await askAndStream(update);
    expect(screen.getByText("Add milk to my list")).toHaveClass("call__heard");
    const fix = makeMessage({
      id: "f1", role: "activity", kind: "english_fix", thread_id: "t-1", seq: 3,
      body: JSON.stringify({ message_id: "mine", said: "Add milk to my list", corrected: "Add milk to my list, please",
        fixes: [{ wrong: "list", right: "list, please" }] }),
    });
    update({ messages: [MINE, PLACEHOLDER, fix] });
    expect(screen.getByText("list, please").tagName).toBe("INS");
    expect(screen.getByText("You said: Add milk to my list")).toBeTruthy();
    expect(screen.queryByText("Add milk to my list", { selector: ".call__heard" })).toBeNull();
    // A line for another message changes nothing here.
    const other = { ...fix, id: "f2", body: JSON.stringify({ message_id: "someone-else", said: "x", corrected: "y", fixes: [] }) };
    update({ messages: [MINE, PLACEHOLDER, fix, other] });
    expect(screen.queryByText("y")).toBeNull();
  });

  it("on an old server the stored reply is spoken instead", async () => {
    stubServer();
    speech.liveUnavailable = true;
    const { update } = setup();
    await askAndStream(update);
    await waitFor(() => expect(speech.live).toEqual(["p1"]));
    update({ messages: [MINE, REPLY], bot: GIGS("resting"), streaming: {} });
    await waitFor(() => expect(speech.spoken).toEqual(["p1"]));
    expect(status()).toBe("Speaking");
    await act(async () => { speech.finish?.(); });
    await waitFor(() => expect(status()).toBe("Listening"), { timeout: SPEAKER_TAIL_MS + 900 });
  });

  it("while thinking, the bot's own words show instead of Thinking…", async () => {
    stubServer();
    const { update } = setup();
    await waitFor(() => expect(status()).toBe("Listening"));
    await say();
    await waitFor(() => expect(status()).toBe("Thinking…"));
    update({ messages: [MINE], bot: GIGS("on_it", "Checking your inbox…") });
    expect(status()).toBe("Checking your inbox…");
  });

  it("an empty hearing says so, says the line, sends nothing", async () => {
    stubServer({ heard: "  " });
    const { onSend } = setup();
    await waitFor(() => expect(status()).toBe("Listening"));
    await say();
    await waitFor(() => expect(screen.getByText("I didn't catch that.")).toBeTruthy());
    await waitFor(() => expect(speech.lines).toContain("not_caught"));
    expect(status()).toBe("Listening");
    expect(onSend).not.toHaveBeenCalled();
  });

  it("a goodbye word says bye and ends the call without sending", async () => {
    stubServer({ heard: "Bye!" });
    const { onSend, onClose } = setup();
    await waitFor(() => expect(status()).toBe("Listening"));
    await say();
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
    expect(speech.lines).toContain("bye");
    expect(onSend).not.toHaveBeenCalled();
  });

  it("a card waiting on you is said, and it keeps listening", async () => {
    stubServer();
    const { update } = setup();
    await waitFor(() => expect(status()).toBe("Listening"));
    await say();
    const card = makeApprovalCard({ bot_id: "b1", state: "open", steps: [makeStep({ title: "Send the proposal" })] });
    update({ messages: [MINE], bot: GIGS("asking_you"), approvals: [card] });
    await waitFor(() => expect(screen.getByText(
      "Gigs is asking: Send the proposal. Say yes or no, or answer in the chat.")).toBeTruthy());
    await waitFor(() => expect(speech.lines).toContain("asking"));
    expect(status()).toBe("Listening");
  });
});

describe("CallScreen: the orb and the controls", () => {
  it("a tap while listening sends now; while speaking it interrupts and tells the server; Space interrupts too", async () => {
    const { hits } = stubServer();
    const { update } = setup();
    await waitFor(() => expect(status()).toBe("Listening"));
    fireEvent.click(screen.getByRole("button", { name: "Send now" }));
    expect(mic.flushes).toBe(1);
    await askAndStream(update);
    await waitFor(() => expect(speech.live).toEqual(["p1"]));
    await act(async () => { speech.liveSource?.onPart?.(0); });
    fireEvent.click(screen.getByRole("button", { name: "Stop speaking" }));
    await waitFor(() => expect(status()).toBe("Listening"));
    expect(speech.stops).toBeGreaterThan(0);
    const interrupted = hits.filter((h) => h.url === "/api/threads/t-1/call" && h.method === "POST");
    expect(interrupted.length).toBeGreaterThanOrEqual(2);
    expect((fetch as unknown as ReturnType<typeof vi.fn>).mock.calls.some(([, init]: [string, RequestInit?]) =>
      init?.body === JSON.stringify({ interrupted: "p1" }))).toBe(true);
  });

  it("Mute shows Muted in every phase, a muted call still speaks; End and Escape close it and tell the server", async () => {
    const { hits } = stubServer();
    const { onClose, update } = setup();
    await waitFor(() => expect(status()).toBe("Listening"));
    fireEvent.click(screen.getByRole("button", { name: "Mute" }));
    expect(status()).toBe("Muted");
    expect(mic.modes.at(-1)).toBe("off");
    fireEvent.click(screen.getByRole("button", { name: "Unmute" }));
    expect(status()).toBe("Listening");
    await say();
    await waitFor(() => expect(status()).toBe("Thinking…"));
    fireEvent.click(screen.getByRole("button", { name: "Mute" }));
    expect(status()).toBe("Muted");
    update({ messages: [MINE, PLACEHOLDER], bot: GIGS("on_it"), streaming: { p1: "Done." } });
    await waitFor(() => expect(speech.live).toEqual(["p1"]));
    await act(async () => { speech.liveSource?.onPart?.(0); });
    expect(status()).toBe("Muted");
    fireEvent.click(screen.getByRole("button", { name: "End call" }));
    expect(onClose).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(2);
    cleanup();
    expect(mic.closed).toBe(1);
    await waitFor(() => expect(hits.some((h) => h.url === "/api/threads/t-1/call" && h.method === "DELETE")).toBe(true));
  });

  it("with echo cancellation the mic stays guarded while the bot speaks, and talking over it stops the reply", async () => {
    stubServer();
    mic.echo = true;
    const { update } = setup();
    await askAndStream(update);
    await waitFor(() => expect(speech.live).toEqual(["p1"]));
    await act(async () => { speech.liveSource?.onPart?.(0); });
    expect(mic.modes.at(-1)).toBe("guarded");
    await act(async () => { mic.handlers?.onBargeIn?.(); });
    expect(speech.stops).toBeGreaterThan(0);
    await waitFor(() => expect(status()).toBe("Listening"));
    expect(mic.modes.at(-1)).toBe("listening");
  });

  it("without echo cancellation the mic is off while the bot speaks, and a barge-in means nothing", async () => {
    stubServer();
    const { update } = setup();
    await askAndStream(update);
    await waitFor(() => expect(speech.live).toEqual(["p1"]));
    await act(async () => { speech.liveSource?.onPart?.(0); });
    expect(mic.modes.at(-1)).toBe("off");
    await act(async () => { mic.handlers?.onBargeIn?.(); });
    expect(speech.stops).toBe(0);
    expect(status()).toBe("Speaking");
  });
});

describe("CallScreen: clocks", () => {
  const useFakeClock = () => vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval"] });
  const tick = async (ms: number) => { await act(async () => { await vi.advanceTimersByTimeAsync(ms); }); };
  const settle = async () => { await act(async () => { for (let i = 0; i < 30; i += 1) await Promise.resolve(); }); };

  it("beats the call every 20 s while open", async () => {
    useFakeClock();
    const { hits } = stubServer();
    setup();
    await settle();
    const beats = () => hits.filter((h) => h.url === "/api/threads/t-1/call" && h.method === "POST").length;
    expect(beats()).toBe(1);
    await tick(CALL_HEARTBEAT_MS);
    expect(beats()).toBe(2);
    await tick(CALL_HEARTBEAT_MS);
    expect(beats()).toBe(3);
  });

  it("a hearing that takes too long is cut off: Say that again?, then listening", async () => {
    useFakeClock();
    stubServer({ holdHearing: true });
    const { onSend } = setup();
    await settle();
    expect(status()).toBe("Listening");
    await say();
    await settle();
    expect(status()).toBe("Hearing you…");
    await tick(CALL_HEARING_TIMEOUT_MS);
    await settle();
    expect(speech.lines).toContain("say_again");
    expect(status()).toBe("Listening");
    expect(onSend).not.toHaveBeenCalled();
  });

  it("while thinking with nothing streamed yet it says Still on it after 15 s, then every 30 s, three times at most", async () => {
    useFakeClock();
    stubServer();
    const { update } = setup();
    await settle();
    await say();
    await settle();
    expect(status()).toBe("Thinking…");
    update({ messages: [MINE], bot: GIGS("on_it") });
    await tick(CALL_STILL_ON_IT_AFTER_MS);
    expect(speech.lines.filter((l) => l === "still_on_it")).toHaveLength(1);
    await tick(CALL_STILL_ON_IT_EVERY_MS);
    await tick(CALL_STILL_ON_IT_EVERY_MS);
    await tick(CALL_STILL_ON_IT_EVERY_MS); // 105 s: a fourth would have fired here, before the 120 s watchdog
    expect(speech.lines.filter((l) => l === "still_on_it")).toHaveLength(3);
    expect(status()).toBe("Thinking…");
  });

  it("a bot that never answers: after 120 s the call says so and listens again", async () => {
    useFakeClock();
    stubServer();
    const { update } = setup();
    await settle();
    await say();
    await settle();
    update({ messages: [MINE], bot: GIGS("on_it") });
    await tick(CALL_THINKING_TIMEOUT_MS);
    expect(status()).toBe("Listening");
    expect(screen.getByText("Gigs is taking long. Ask again, or wait for the reply in the chat.")).toBeTruthy();
  });
});
