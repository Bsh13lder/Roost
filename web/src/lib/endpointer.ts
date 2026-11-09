// When you start and stop talking on a call (voice call mode, contract E): a small pure state machine over the
// microphone's loudness, one step per 20 ms frame. While waiting it follows the room's noise floor (the 10th
// percentile of the last two seconds) and only a voice well above it, loud for most of a short window, starts a
// turn (a click or a tap on the desk doesn't count, nor does a fan). A turn ends after a pause longer than one
// between words, a sound too short to be words is dropped, and a long talk is cut at the cap. The floor keeps
// following the room through a turn too (so a fan that started a false turn ends it and never restarts it), and is
// frozen only in the guarded set (the bot is speaking: only a clearly louder voice counts). The caller keeps the
// samples; this only says when.

export interface EndpointOptions {
  readonly startLevel: number; // the least RMS that counts as voice (-40 dBFS); the floor can only raise it
  readonly endLevel: number; // the least RMS below which counts as quiet; lower than the start (hysteresis)
  readonly startRatio: number; // start threshold = max(startLevel, startRatio × floor), about +10 dB
  readonly endRatio: number; // end threshold = max(endLevel, endRatio × floor)
  readonly startMs: number; // this much voice within the start window starts a turn
  readonly startWindowMs: number; // the sliding window the start counts in (one dipped frame doesn't reset it)
  readonly endSilenceMs: number; // quiet this long ends the turn
  readonly minSpeechMs: number; // shorter than this (without the closing silence) is dropped; a short "no" still counts
  readonly maxMs: number; // one turn is cut here
  readonly prerollMs: number; // how much before the start the caller keeps, so the first syllable isn't lost
  readonly floorMs: number; // how far back the noise floor looks
  readonly floorMinMs: number; // the floor counts only once this much has been heard (a first word is not the room)
  readonly frozenFloor: boolean; // guarded: the floor stays where it was
}

export const ENDPOINT_DEFAULTS: EndpointOptions = {
  startLevel: 0.01,
  endLevel: 0.006,
  startRatio: 3,
  endRatio: 1.5,
  startMs: 120,
  startWindowMs: 200,
  endSilenceMs: 700,
  minSpeechMs: 350,
  maxMs: 30_000,
  prerollMs: 300,
  floorMs: 2000,
  floorMinMs: 500,
  frozenFloor: false,
};

// While the bot speaks and the browser cancels its echo: only a voice clearly over the echo, held longer, counts.
export const ENDPOINT_GUARDED: EndpointOptions = {
  ...ENDPOINT_DEFAULTS,
  startLevel: 0.05,
  startMs: 300,
  startWindowMs: 400,
  frozenFloor: true,
};

export interface EndpointState {
  readonly speaking: boolean;
  readonly loudMs: number; // voice within the start window, while waiting
  readonly quietMs: number; // how long it has been quiet, while speaking
  readonly speechMs: number; // how long this turn has run
  readonly floor: number; // the room's noise floor (RMS)
  readonly levels: readonly number[]; // the last floorMs of frame levels
  readonly window: readonly { readonly loud: boolean; readonly ms: number }[]; // the start window's frames
}

export type EndpointEvent = "start" | "end" | "drop" | "cut" | null;

export const ENDPOINT_IDLE: EndpointState = {
  speaking: false, loudMs: 0, quietMs: 0, speechMs: 0, floor: 0, levels: [], window: [],
};

const FLOOR_PERCENTILE = 0.1;

// The root mean square of one block of float samples.
export function rmsLevel(chunk: Float32Array): number {
  if (chunk.length === 0) return 0;
  let sum = 0;
  for (let i = 0; i < chunk.length; i += 1) sum += chunk[i] * chunk[i];
  return Math.sqrt(sum / chunk.length);
}

// The start and end thresholds this state listens with.
export function endpointThresholds(state: EndpointState, o: EndpointOptions): { start: number; end: number } {
  return {
    start: Math.max(o.startLevel, o.startRatio * state.floor),
    end: Math.max(o.endLevel, o.endRatio * state.floor),
  };
}

function percentile(values: readonly number[], fraction: number): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * fraction))];
}

// The floor after one more frame: frozen, or the low percentile of the recent levels once enough were heard.
function nextFloor(state: EndpointState, level: number, ms: number, o: EndpointOptions) {
  if (o.frozenFloor) return { floor: state.floor, levels: state.levels };
  const frameMs = Math.max(1, ms);
  const keep = Math.max(1, Math.round(o.floorMs / frameMs));
  const levels = [...state.levels, level].slice(-keep);
  const enough = levels.length * frameMs >= o.floorMinMs;
  return { floor: enough ? percentile(levels, FLOOR_PERCENTILE) : 0, levels };
}

function nextWindow(state: EndpointState, loud: boolean, ms: number, o: EndpointOptions) {
  const window = [...state.window, { loud, ms }];
  let total = window.reduce((sum, frame) => sum + frame.ms, 0);
  let from = 0;
  while (from < window.length - 1 && total - window[from].ms >= o.startWindowMs) {
    total -= window[from].ms;
    from += 1;
  }
  const kept = window.slice(from);
  return { window: kept, loudMs: kept.reduce((sum, frame) => sum + (frame.loud ? frame.ms : 0), 0) };
}

function waiting(state: EndpointState, level: number, ms: number, o: EndpointOptions) {
  const { floor, levels } = nextFloor(state, level, ms, o);
  const loud = level >= endpointThresholds({ ...state, floor }, o).start;
  const { window, loudMs } = nextWindow(state, loud, ms, o);
  if (loudMs >= o.startMs) {
    const speechMs = window.reduce((sum, frame) => sum + frame.ms, 0);
    return { state: { ...ENDPOINT_IDLE, speaking: true, speechMs, floor, levels }, event: "start" as const };
  }
  return { state: { ...ENDPOINT_IDLE, loudMs, floor, levels, window }, event: null };
}

function speaking(state: EndpointState, level: number, ms: number, o: EndpointOptions) {
  const { floor, levels } = nextFloor(state, level, ms, o);
  const speechMs = state.speechMs + ms;
  const quietMs = level < endpointThresholds({ ...state, floor }, o).end ? state.quietMs + ms : 0;
  const idle = { ...ENDPOINT_IDLE, floor, levels };
  if (speechMs >= o.maxMs) return { state: idle, event: "cut" as const };
  if (quietMs >= o.endSilenceMs) {
    const voiced = speechMs - quietMs;
    return { state: idle, event: voiced >= o.minSpeechMs ? ("end" as const) : ("drop" as const) };
  }
  return { state: { ...state, loudMs: 0, quietMs, speechMs, floor, levels, window: [] }, event: null };
}

// One frame of `ms` milliseconds at loudness `level`: the next state and what happened, if anything.
export function stepEndpoint(
  state: EndpointState, level: number, ms: number, options: EndpointOptions = ENDPOINT_DEFAULTS,
): { state: EndpointState; event: EndpointEvent } {
  return state.speaking ? speaking(state, level, ms, options) : waiting(state, level, ms, options);
}

// Ends a running turn now (the orb was tapped): "end" when enough was said, "drop" otherwise, null when waiting.
export function flushEndpoint(state: EndpointState, options: EndpointOptions = ENDPOINT_DEFAULTS): {
  state: EndpointState; event: Exclude<EndpointEvent, "start" | "cut">;
} {
  if (!state.speaking) return { state, event: null };
  const idle = { ...ENDPOINT_IDLE, floor: state.floor, levels: state.levels };
  const voiced = state.speechMs - state.quietMs;
  return { state: idle, event: voiced >= options.minSpeechMs ? "end" : "drop" };
}
