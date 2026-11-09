import { afterEach, describe, expect, it, vi } from "vitest";
import { createTurnCollector, FRAME_MS, openCallMic, type CallMicHandlers } from "../src/lib/callMic";
import { ENDPOINT_DEFAULTS } from "../src/lib/endpointer";

const RATE = 16_000;
const block = (level: number, ms = 20) => new Float32Array((RATE * ms) / 1000).fill(level);
// A worklet's 128-sample blocks of a voiced signal (a sine) at a given RMS.
const voiced = (rms: number, n = 128, phase = 0) => {
  const out = new Float32Array(n);
  for (let i = 0; i < n; i += 1) out[i] = Math.SQRT2 * rms * Math.sin(phase + (i * 2 * Math.PI * 220) / RATE);
  return out;
};

describe("createTurnCollector", () => {
  it("hands over one WAV per turn, with the moment before the start kept", () => {
    const onTurn = vi.fn();
    const turns = createTurnCollector(RATE, onTurn);
    for (let i = 0; i < 25; i += 1) turns.push(block(0));
    for (let i = 0; i < 50; i += 1) turns.push(block(0.2)); // 1 s of voice
    for (let i = 0; i < 50; i += 1) turns.push(block(0)); // 1 s of quiet ends it
    expect(onTurn).toHaveBeenCalledTimes(1);
    const wav = onTurn.mock.calls[0][0] as Blob;
    expect(wav.type).toBe("audio/wav");
    // ~300 ms kept before the start (which holds the first 120 ms of voice), the rest of the voice and the 700 ms
    // pause, 16-bit mono at 16 kHz, after a 44-byte header
    const samples = (wav.size - 44) / 2;
    expect(samples).toBeGreaterThanOrEqual(RATE * 1.85);
    expect(samples).toBeLessThanOrEqual(RATE * 2.05);
  });

  it("steps once per 20 ms frame: small blocks are gathered, and the frame's loudness is returned once", () => {
    const onTurn = vi.fn();
    const turns = createTurnCollector(RATE, onTurn);
    const levels: number[] = [];
    const perFrame = (RATE * FRAME_MS) / 1000 / 128; // 2.5 blocks of 128 samples per frame
    let n = 0;
    const feed = (rms: number, ms: number) => {
      const blocks = Math.round((ms / FRAME_MS) * perFrame);
      for (let i = 0; i < blocks; i += 1, n += 1) {
        const level = turns.push(voiced(rms, 128, n * 128));
        if (level !== null) levels.push(level);
      }
    };
    feed(0, 500);
    feed(0.03, 1000); // quiet speech on a phone
    feed(0, 1000);
    expect(onTurn).toHaveBeenCalledTimes(1);
    // 2.5 s of audio → frames of three blocks (24 ms, the first to reach 20 ms): about 104, never one per block (313)
    expect(levels.length).toBeGreaterThanOrEqual(100);
    expect(levels.length).toBeLessThanOrEqual(130);
    const loud = levels.filter((l) => l > 0.027);
    expect(loud.length).toBeGreaterThanOrEqual(38);
    loud.forEach((l) => expect(l).toBeCloseTo(0.03, 2));
  });

  it("a cough and a reset hand over nothing", () => {
    const onTurn = vi.fn();
    const turns = createTurnCollector(RATE, onTurn);
    for (let i = 0; i < 8; i += 1) turns.push(block(0.2));
    for (let i = 0; i < 50; i += 1) turns.push(block(0));
    for (let i = 0; i < 50; i += 1) turns.push(block(0.2));
    turns.reset();
    for (let i = 0; i < 50; i += 1) turns.push(block(0));
    expect(onTurn).not.toHaveBeenCalled();
  });

  it("flush ends a turn now, and does nothing when nothing was said", () => {
    const onTurn = vi.fn();
    const turns = createTurnCollector(RATE, onTurn);
    turns.flush();
    expect(onTurn).not.toHaveBeenCalled();
    for (let i = 0; i < 30; i += 1) turns.push(block(0.2)); // 600 ms, no closing silence yet
    turns.flush();
    expect(onTurn).toHaveBeenCalledTimes(1);
    const samples = ((onTurn.mock.calls[0][0] as Blob).size - 44) / 2;
    expect(samples).toBeGreaterThanOrEqual(RATE * 0.55);
    for (let i = 0; i < 50; i += 1) turns.push(block(0));
    expect(onTurn).toHaveBeenCalledTimes(1); // the flushed turn is over
  });

  it("setOptions swaps the thresholds mid-stream without losing the turn", () => {
    const onTurn = vi.fn();
    const onStart = vi.fn();
    const turns = createTurnCollector(RATE, onTurn, ENDPOINT_DEFAULTS, onStart);
    for (let i = 0; i < 20; i += 1) turns.push(block(0.2));
    expect(onStart).toHaveBeenCalledTimes(1);
    turns.setOptions({ ...ENDPOINT_DEFAULTS, endSilenceMs: 300 });
    for (let i = 0; i < 16; i += 1) turns.push(block(0));
    expect(onTurn).toHaveBeenCalledTimes(1);
  });
});

// The microphone, faked: a ScriptProcessor whose blocks the test pushes.
class FakeAudioContext {
  static last: FakeAudioContext | null = null;
  readonly sampleRate = RATE;
  readonly destination = {};
  state: AudioContextState = "running";
  processor: { onaudioprocess: ((event: { inputBuffer: { getChannelData: () => Float32Array } }) => void) | null; connect: () => void; disconnect: () => void } | null = null;
  readonly listeners: (() => void)[] = [];
  readonly close = vi.fn(async () => undefined);
  readonly resume = vi.fn(async () => { this.state = "running"; });
  constructor() { FakeAudioContext.last = this; }
  createMediaStreamSource() { return { connect: () => undefined }; }
  createScriptProcessor() {
    this.processor = { onaudioprocess: null, connect: () => undefined, disconnect: () => undefined };
    return this.processor;
  }
  addEventListener(_name: string, fn: () => void) { this.listeners.push(fn); }
  removeEventListener() { /* nothing */ }
}

function stubMic(settings: MediaTrackSettings = { echoCancellation: true }) {
  const track = { stop: vi.fn(), getSettings: () => settings };
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true, value: { getUserMedia: vi.fn(async () => ({ getTracks: () => [track] })) },
  });
  vi.stubGlobal("AudioContext", FakeAudioContext);
  return track;
}

const feed = (samples: Float32Array) => {
  FakeAudioContext.last?.processor?.onaudioprocess?.({ inputBuffer: { getChannelData: () => samples } });
};

afterEach(() => { vi.unstubAllGlobals(); FakeAudioContext.last = null; });

describe("openCallMic", () => {
  const handlers = (): CallMicHandlers & { levels: number[]; turns: Blob[]; barges: number } => {
    const made = {
      levels: [] as number[], turns: [] as Blob[], barges: 0,
      onLevel: (l: number) => { made.levels.push(l); },
      onTurn: (w: Blob) => { made.turns.push(w); },
      onBargeIn: () => { made.barges += 1; },
    };
    return made;
  };

  it("listening: hears a turn; off: ignores everything and drops a half-heard turn", async () => {
    stubMic();
    const h = handlers();
    const mic = await openCallMic(h);
    expect(mic.echoCancellation).toBe(true);
    for (let i = 0; i < 50; i += 1) feed(block(0.2));
    for (let i = 0; i < 50; i += 1) feed(block(0));
    expect(h.turns).toHaveLength(1);
    mic.setMode("off");
    expect(h.levels.at(-1)).toBe(0);
    for (let i = 0; i < 50; i += 1) feed(block(0.2));
    mic.setMode("listening");
    for (let i = 0; i < 50; i += 1) feed(block(0));
    expect(h.turns).toHaveLength(1);
    expect(h.barges).toBe(0);
  });

  it("guarded: a loud voice over the bot says barge-in, and the turn goes on once listening", async () => {
    stubMic();
    const h = handlers();
    const mic = await openCallMic(h);
    mic.setMode("guarded");
    for (let i = 0; i < 20; i += 1) feed(block(0.03)); // the bot's echo: never a start
    expect(h.barges).toBe(0);
    for (let i = 0; i < 20; i += 1) feed(block(0.3));
    expect(h.barges).toBe(1);
    mic.setMode("listening"); // the call stopped the bot: the words already heard are kept
    for (let i = 0; i < 20; i += 1) feed(block(0.3));
    for (let i = 0; i < 50; i += 1) feed(block(0));
    expect(h.turns).toHaveLength(1);
    const samples = (h.turns[0].size - 44) / 2;
    expect(samples).toBeGreaterThanOrEqual(RATE * 1.3); // both loud stretches and the pause
  });

  it("flush sends what was heard so far; close stops the track", async () => {
    const track = stubMic({ echoCancellation: false });
    const h = handlers();
    const mic = await openCallMic(h);
    expect(mic.echoCancellation).toBe(false);
    for (let i = 0; i < 30; i += 1) feed(block(0.2));
    mic.flush();
    expect(h.turns).toHaveLength(1);
    mic.close();
    expect(track.stop).toHaveBeenCalled();
  });

  it("says when the browser's audio is suspended, and resume wakes it", async () => {
    stubMic();
    const states: AudioContextState[] = [];
    const h = { ...handlers(), onAudioState: (s: AudioContextState) => { states.push(s); } };
    const mic = await openCallMic(h);
    const context = FakeAudioContext.last!;
    context.state = "suspended";
    context.listeners.forEach((fn) => fn());
    expect(states.at(-1)).toBe("suspended");
    await mic.resume();
    expect(context.resume).toHaveBeenCalled();
    expect(mic.audioState()).toBe("running");
  });
});
