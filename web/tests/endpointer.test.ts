import { describe, expect, it } from "vitest";
import {
  ENDPOINT_DEFAULTS, ENDPOINT_GUARDED, ENDPOINT_IDLE, endpointThresholds, rmsLevel, stepEndpoint,
  type EndpointEvent, type EndpointOptions, type EndpointState,
} from "../src/lib/endpointer";

const LOUD = 0.2;
const QUIET = 0.001;
const DIP = 0.004; // between words
const FRAME = 20; // ms per step (contract E)

// Speech: 400 ms of voice, a 100 ms dip between words, for about `ms` (a steady tone is not speech, and the
// floor would learn it).
function speech(ms: number, level = LOUD): (readonly [number, number])[] {
  const out: (readonly [number, number])[] = [];
  for (let t = 0; t < ms; t += 500) out.push([level, Math.min(400, ms - t)], [DIP, Math.max(0, Math.min(100, ms - t - 400))]);
  return out;
}

// Runs the endpointer over a list of [level, ms-long] stretches and collects the events it raised.
function run(
  stretches: readonly (readonly [number, number])[], options: EndpointOptions = ENDPOINT_DEFAULTS,
  from: EndpointState = ENDPOINT_IDLE,
) {
  let state = from;
  const events: { event: Exclude<EndpointEvent, null>; at: number }[] = [];
  let at = 0;
  for (const [level, ms] of stretches) {
    for (let t = 0; t < ms; t += FRAME) {
      at += FRAME;
      const next = stepEndpoint(state, level, FRAME, options);
      state = next.state;
      if (next.event) events.push({ event: next.event, at });
    }
  }
  return { state, events };
}

const kinds = (events: { event: string }[]) => events.map((e) => e.event);

describe("rmsLevel", () => {
  it("is 0 for silence and the amplitude for a steady signal", () => {
    expect(rmsLevel(new Float32Array(160))).toBe(0);
    expect(rmsLevel(new Float32Array(160).fill(0.5))).toBeCloseTo(0.5);
    expect(rmsLevel(new Float32Array(0))).toBe(0);
  });
});

describe("the defaults (contract E)", () => {
  it("are the shared numbers", () => {
    expect(ENDPOINT_DEFAULTS).toMatchObject({
      startMs: 120, endSilenceMs: 700, minSpeechMs: 350, maxMs: 30_000, prerollMs: 300, startLevel: 0.01, endLevel: 0.006,
    });
    expect(ENDPOINT_GUARDED).toMatchObject({ startLevel: 0.05, startMs: 300, frozenFloor: true });
    expect(ENDPOINT_DEFAULTS.frozenFloor).toBe(false);
  });
});

describe("stepEndpoint", () => {
  it("starts once the voice has been loud for the start time, not on a click", () => {
    expect(run([[LOUD, 40], [QUIET, 500]]).events).toEqual([]);
    const { events, state } = run([[QUIET, 200], [LOUD, 300]]);
    expect(events).toEqual([{ event: "start", at: 200 + ENDPOINT_DEFAULTS.startMs }]);
    expect(state.speaking).toBe(true);
  });

  it("ends after the silence time and is ready for the next one", () => {
    const { events, state } = run([...speech(1000), [QUIET, 1000]]);
    expect(kinds(events)).toEqual(["start", "end"]);
    expect(events[1].at).toBe(900 + ENDPOINT_DEFAULTS.endSilenceMs); // the last 100 ms dip already counted as quiet
    expect(state.speaking).toBe(false);
    expect(state.quietMs).toBe(0);
    expect(state.speechMs).toBe(0);
  });

  it("a short pause inside a sentence doesn't end it", () => {
    const { events } = run([...speech(600), [QUIET, 500], ...speech(600), [QUIET, 1000]]);
    expect(kinds(events)).toEqual(["start", "end"]);
  });

  it("drops a cough too short to be words", () => {
    const { events } = run([[LOUD, 200], [QUIET, 1000]]);
    expect(kinds(events)).toEqual(["start", "drop"]);
  });

  it("cuts a long talk at the cap", () => {
    const { events } = run(speech(ENDPOINT_DEFAULTS.maxMs + 500));
    expect(kinds(events)).toEqual(["start", "cut", "start"]);
  });

  it("one dipped frame inside the start window doesn't reset the start", () => {
    // 100 ms loud, one quiet frame, then loud again: the window still counts 120 ms of voice soon after.
    const { events } = run([[LOUD, 100], [QUIET, 20], [LOUD, 200]]);
    expect(kinds(events)).toEqual(["start"]);
    expect(events[0].at).toBeLessThanOrEqual(100 + 20 + 60);
  });

  it("tracks the room's noise floor and starts only well above it", () => {
    const NOISE = 0.02; // a fan: louder than the fixed startLevel
    const quietRoom = run([[QUIET, 2000]]);
    expect(endpointThresholds(quietRoom.state, ENDPOINT_DEFAULTS).start).toBeCloseTo(ENDPOINT_DEFAULTS.startLevel);
    const noisyRoom = run([[NOISE, 6000]]);
    expect(noisyRoom.state.speaking).toBe(false);
    const { start, end } = endpointThresholds(noisyRoom.state, ENDPOINT_DEFAULTS);
    expect(start).toBeCloseTo(NOISE * 3);
    expect(end).toBeCloseTo(NOISE * 1.5);
    expect(end).toBeLessThan(start);
    // The fan itself starts nothing more; voice at twice the noise doesn't start; at four times it does.
    expect(run([[NOISE, 2000]], ENDPOINT_DEFAULTS, noisyRoom.state).events).toEqual([]);
    expect(run([[NOISE * 2, 500]], ENDPOINT_DEFAULTS, noisyRoom.state).events).toEqual([]);
    expect(kinds(run([[NOISE * 4, 500]], ENDPOINT_DEFAULTS, noisyRoom.state).events)).toEqual(["start"]);
  });

  it("a fan heard from the first frame ends its one false turn and never starts another", () => {
    const NOISE = 0.02;
    const { events, state } = run([[NOISE, 6000]]);
    expect(kinds(events).slice(0, 2)).toEqual(["start", "end"]); // one short false turn while the floor settles
    expect(events[1].at).toBeLessThan(4000);
    expect(events).toHaveLength(2);
    expect(state.speaking).toBe(false);
    expect(endpointThresholds(state, ENDPOINT_DEFAULTS).start).toBeCloseTo(NOISE * 3);
  });

  it("a first word is not the room: the floor needs half a second of hearing before it counts", () => {
    const { events } = run([[LOUD, 200]]);
    expect(kinds(events)).toEqual(["start"]);
  });

  it("the end threshold sits lower than the start, so a soft word keeps the turn going", () => {
    const soft = ENDPOINT_DEFAULTS.endLevel + 0.001; // under start, over end
    const { events } = run([[LOUD, 500], [soft, 400], [LOUD, 500], [QUIET, 1000]]);
    expect(kinds(events)).toEqual(["start", "end"]);
    expect(events[1].at).toBe(500 + 400 + 500 + ENDPOINT_DEFAULTS.endSilenceMs);
    expect(kinds(run([[QUIET, 1000], [soft, 1000]]).events)).toEqual([]); // soft alone never starts one
  });

  it("guarded: a louder, longer voice is needed and the floor stays put", () => {
    expect(run([[0.03, 1000]], ENDPOINT_GUARDED).events).toEqual([]); // the bot's own echo, say
    expect(run([[LOUD, 200], [QUIET, 1000]], ENDPOINT_GUARDED).events).toEqual([]);
    const { events, state } = run([[LOUD, 400]], ENDPOINT_GUARDED);
    expect(events).toEqual([{ event: "start", at: ENDPOINT_GUARDED.startMs }]);
    expect(state.speaking).toBe(true);
    const noisy = run([[0.04, 2000]], ENDPOINT_GUARDED);
    expect(endpointThresholds(noisy.state, ENDPOINT_GUARDED).start).toBeCloseTo(ENDPOINT_GUARDED.startLevel);
  });

  it("never mutates the state it was given", () => {
    const frozen = Object.freeze({ ...ENDPOINT_IDLE });
    expect(() => stepEndpoint(frozen, LOUD, FRAME)).not.toThrow();
    expect(frozen).toEqual(ENDPOINT_IDLE);
  });
});
