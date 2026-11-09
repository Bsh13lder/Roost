import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  LIVE_POLL_MS, LiveSpeechUnavailable, speakLine, speakLive, stopSpeech, unlockSpeech, resetSpeech,
  type LiveReady, type LiveSource,
} from "../src/store/speech";

const PLAN_URL = "/api/threads/t-1/live-speech/m-1";
const LINE_URL = "/api/bots/b1/voice/line/greeting";

let played: HTMLMediaElement[];
let paused: number;
let fetched: string[];

interface Server {
  plan: () => { status: number; parts?: number; done?: boolean };
  part: (index: number) => number; // the status for that part
  line: number;
}

function stubServer(server: Partial<Server> = {}) {
  const s: Server = { plan: () => ({ status: 200, parts: 0, done: false }), part: () => 200, line: 200, ...server };
  fetched = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    fetched.push(url);
    if (url === PLAN_URL) {
      const { status, parts, done } = s.plan();
      return status === 200 ? new Response(JSON.stringify({ parts, done, speed: 1.25 }))
        : new Response(JSON.stringify({ detail: "No such reply." }), { status });
    }
    if (url.startsWith(`${PLAN_URL}/`)) {
      const status = s.part(Number(url.slice(PLAN_URL.length + 1)));
      return status === 200 ? new Response(new Blob([url], { type: "audio/wav" }))
        : new Response(JSON.stringify({ detail: "Not ready." }), { status });
    }
    if (url === LINE_URL) {
      return s.line === 200 ? new Response(new Blob(["line"], { type: "audio/wav" }))
        : new Response(JSON.stringify({ detail: "Unknown." }), { status: s.line });
    }
    return new Response("{}", { status: 404 });
  }));
}

// The live store's knowledge of the reply, as the test moves it.
function liveSource(start: LiveReady = { parts: 0, done: false }) {
  let ready = start;
  let settled = false;
  const listeners = new Set<() => void>();
  const parts: number[] = [];
  const source: LiveSource = {
    ready: () => ready,
    onChange: (listener) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    settled: () => settled,
    onPart: (index) => { parts.push(index); },
  };
  const set = (next: Partial<LiveReady> & { settled?: boolean }) => {
    ready = { ...ready, ...next };
    if (next.settled !== undefined) settled = next.settled;
    listeners.forEach((listener) => listener());
  };
  return { source, set, parts, listeners };
}

const flush = async () => { for (let i = 0; i < 40; i += 1) await Promise.resolve(); };
const endPart = async (element: HTMLMediaElement) => { element.dispatchEvent(new Event("ended")); await flush(); };

beforeEach(() => {
  played = [];
  paused = 0;
  vi.spyOn(window.HTMLMediaElement.prototype, "play").mockImplementation(function play(this: HTMLMediaElement) {
    played.push(this);
    return Promise.resolve();
  });
  vi.spyOn(window.HTMLMediaElement.prototype, "pause").mockImplementation(() => { paused += 1; });
  let n = 0;
  URL.createObjectURL = vi.fn(() => `blob:part-${n++}`);
  URL.revokeObjectURL = vi.fn();
});

afterEach(() => {
  resetSpeech();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("speakLive (contract B: the reply spoken as it streams)", () => {
  it("plays the parts in the order the frames announce them, and ends after the done part", async () => {
    stubServer();
    const live = liveSource();
    const done = speakLive("t-1", "m-1", live.source);
    await flush();
    expect(fetched).toEqual([PLAN_URL]);
    expect(played).toEqual([]);
    live.set({ parts: 1 });
    await flush();
    expect(fetched.at(-1)).toBe(`${PLAN_URL}/0`);
    expect(played).toHaveLength(1);
    expect(played[0].playbackRate).toBe(1.25);
    expect(live.parts).toEqual([0]);
    live.set({ parts: 2, done: true });
    await endPart(played[0]);
    expect(fetched.at(-1)).toBe(`${PLAN_URL}/1`);
    expect(played).toHaveLength(2);
    await endPart(played[1]);
    await expect(done).resolves.toBeUndefined();
    expect(live.parts).toEqual([0, 1]);
    expect(live.listeners.size).toBe(0);
  });

  it("a part that isn't there yet (404) is fetched again on the next frame", async () => {
    let tries = 0;
    stubServer({ part: () => (tries++ === 0 ? 404 : 200) });
    const live = liveSource({ parts: 1, done: true });
    const done = speakLive("t-1", "m-1", live.source);
    await flush();
    expect(fetched.filter((u) => u === `${PLAN_URL}/0`)).toHaveLength(1);
    expect(played).toEqual([]);
    live.set({ parts: 1 });
    await flush();
    expect(fetched.filter((u) => u === `${PLAN_URL}/0`)).toHaveLength(2);
    expect(played).toHaveLength(1);
    await endPart(played[0]);
    await expect(done).resolves.toBeUndefined();
  });

  it("a stop between parts ends it quietly, fetching nothing more", async () => {
    stubServer();
    const live = liveSource({ parts: 1, done: false });
    const done = speakLive("t-1", "m-1", live.source);
    await flush();
    expect(played).toHaveLength(1);
    live.set({ parts: 2 });
    stopSpeech();
    await flush();
    await expect(done).resolves.toBeUndefined();
    expect(fetched).not.toContain(`${PLAN_URL}/1`);
    expect(live.listeners.size).toBe(0);
  });

  it("an old server (the plan 404s) says live speech is unavailable", async () => {
    stubServer({ plan: () => ({ status: 404 }) });
    await expect(speakLive("t-1", "m-1", liveSource().source)).rejects.toBeInstanceOf(LiveSpeechUnavailable);
  });

  it("with no frames it polls the plan every 400 ms", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] }); // a Response body is read through setImmediate
    let polls = 0;
    stubServer({ plan: () => (polls++ === 0 ? { status: 200, parts: 0, done: false } : { status: 200, parts: 1, done: true }) });
    const live = liveSource();
    const done = speakLive("t-1", "m-1", live.source);
    await flush();
    expect(fetched).toEqual([PLAN_URL]);
    await vi.advanceTimersByTimeAsync(LIVE_POLL_MS);
    await flush();
    expect(fetched.filter((u) => u === PLAN_URL)).toHaveLength(2);
    expect(played).toHaveLength(1);
    await endPart(played[0]);
    await expect(done).resolves.toBeUndefined();
  });

  it("a stored reply with no more parts coming ends after one more look", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] }); // a Response body is read through setImmediate
    stubServer({ plan: () => ({ status: 200, parts: 1, done: false }) });
    const live = liveSource({ parts: 1, done: false });
    const done = speakLive("t-1", "m-1", live.source);
    await flush();
    await endPart(played[0]);
    live.set({ settled: true });
    await vi.advanceTimersByTimeAsync(LIVE_POLL_MS);
    await flush();
    await expect(done).resolves.toBeUndefined();
  });
});

describe("speakLine (contract C)", () => {
  it("plays the bot's fixed line", async () => {
    stubServer();
    const done = speakLine("b1", "greeting");
    await flush();
    expect(fetched).toEqual([LINE_URL]);
    expect(played).toHaveLength(1);
    await endPart(played[0]);
    await expect(done).resolves.toBeUndefined();
  });

  it("says nothing on an old server (404), without failing", async () => {
    stubServer({ line: 404 });
    await expect(speakLine("b1", "greeting")).resolves.toBeUndefined();
    expect(played).toEqual([]);
  });
});

describe("unlockSpeech", () => {
  it("plays a silent moment through the shared element in the tap, then pauses", async () => {
    await unlockSpeech();
    expect(played).toHaveLength(1);
    expect(played[0].src.startsWith("data:audio/wav")).toBe(true);
    expect(paused).toBeGreaterThan(0);
  });

  it("never throws when the browser refuses", async () => {
    vi.spyOn(window.HTMLMediaElement.prototype, "play").mockRejectedValue(new DOMException("no", "NotAllowedError"));
    await expect(unlockSpeech()).resolves.toBeUndefined();
  });
});
