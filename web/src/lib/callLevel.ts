// The orb's loudness (call mode): the microphone's frame levels arrive 50 times a second, the orb is drawn once per
// animation frame from a smoothed envelope (a fast attack so it jumps with your voice, a slow release so it eases
// down instead of flickering). Pure, apart from the scheduler it is handed.

export const LEVEL_ATTACK = 0.6;
export const LEVEL_RELEASE = 0.08;
const LEVEL_STEPS = 10; // the orb moves in tenths, so a frame rarely re-renders it
const LEVEL_GAIN = 6; // speech sits around 0.02–0.15 RMS

const clamp01 = (value: number) => Math.min(1, Math.max(0, value));

// The envelope's next value: towards `level` by the attack when rising, by the release when falling.
export function smoothLevel(previous: number, level: number, attack = LEVEL_ATTACK, release = LEVEL_RELEASE): number {
  const target = clamp01(level);
  const factor = target > previous ? attack : release;
  return clamp01(previous + (target - previous) * factor);
}

// A frame's RMS → the orb's 0–1 size, in tenths.
export function orbLevel(rms: number): number {
  return Math.round(clamp01(rms * LEVEL_GAIN) * LEVEL_STEPS) / LEVEL_STEPS;
}

export interface LevelMeter {
  readonly push: (rms: number) => void; // a frame's loudness
  readonly reset: () => void; // the orb goes still at once (the mic went off)
}

type Schedule = (fn: () => void) => number;
type Cancel = (handle: number) => void;

const defaultSchedule: Schedule = (fn) =>
  typeof requestAnimationFrame === "function" ? requestAnimationFrame(fn) : (setTimeout(fn, 16) as unknown as number);
const defaultCancel: Cancel = (handle) =>
  typeof cancelAnimationFrame === "function" ? cancelAnimationFrame(handle) : clearTimeout(handle);

// Shows at most one level per animation frame: every pushed frame moves the envelope, the next frame shows it.
export function createLevelMeter(
  show: (level: number) => void, schedule: Schedule = defaultSchedule, cancel: Cancel = defaultCancel,
): LevelMeter {
  let envelope = 0;
  let pending: number | null = null;
  const flush = () => {
    pending = null;
    show(orbLevel(envelope));
  };
  return {
    push: (rms) => {
      envelope = smoothLevel(envelope, rms);
      if (pending === null) pending = schedule(flush);
    },
    reset: () => {
      if (pending !== null) cancel(pending);
      pending = null;
      envelope = 0;
      show(0);
    },
  };
}
