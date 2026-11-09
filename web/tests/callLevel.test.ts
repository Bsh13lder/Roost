import { describe, expect, it, vi } from "vitest";
import { createLevelMeter, LEVEL_ATTACK, LEVEL_RELEASE, orbLevel, smoothLevel } from "../src/lib/callLevel";

describe("smoothLevel (the orb's envelope)", () => {
  it("rises fast and falls slowly", () => {
    const up = smoothLevel(0, 1);
    expect(up).toBeCloseTo(LEVEL_ATTACK);
    const down = smoothLevel(1, 0);
    expect(down).toBeCloseTo(1 - LEVEL_RELEASE);
    expect(up).toBeGreaterThan(1 - down);
  });

  it("settles on a steady level and never leaves 0..1", () => {
    let level = 0;
    for (let i = 0; i < 40; i += 1) level = smoothLevel(level, 0.5);
    expect(level).toBeCloseTo(0.5, 3);
    expect(smoothLevel(0, 5)).toBeLessThanOrEqual(1);
    expect(smoothLevel(0, -1)).toBeGreaterThanOrEqual(0);
  });
});

describe("orbLevel", () => {
  it("maps speech loudness (RMS) onto 0..1 in tenths", () => {
    expect(orbLevel(0)).toBe(0);
    expect(orbLevel(0.05)).toBeGreaterThan(0.2);
    expect(orbLevel(1)).toBe(1);
    expect(Number.isInteger(orbLevel(0.07) * 10)).toBe(true);
  });
});

describe("createLevelMeter", () => {
  it("shows at most one level per animation frame, smoothed", () => {
    const frames: (() => void)[] = [];
    const shown: number[] = [];
    const meter = createLevelMeter((level) => shown.push(level), (fn) => { frames.push(fn); return frames.length; });
    for (let i = 0; i < 50; i += 1) meter.push(0.1); // a worklet's blocks between two frames
    expect(frames).toHaveLength(1);
    expect(shown).toEqual([]);
    frames[0]();
    expect(shown).toHaveLength(1);
    expect(shown[0]).toBeGreaterThan(0);
    for (let i = 0; i < 5; i += 1) meter.push(0);
    frames[1]();
    expect(shown[1]).toBeLessThan(shown[0]); // released...
    expect(shown[1]).toBeGreaterThan(0); // ...not snapped to 0
  });

  it("reset shows 0 at once and drops a pending frame", () => {
    const cancel = vi.fn();
    const shown: number[] = [];
    const meter = createLevelMeter((level) => shown.push(level), () => 7, cancel);
    meter.push(0.3);
    meter.reset();
    expect(cancel).toHaveBeenCalledWith(7);
    expect(shown).toEqual([0]);
  });
});
