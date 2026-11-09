import { describe, expect, it } from "vitest";
import { barHeights, compactCount, tokensLine } from "../src/lib/tokenCount";

describe("compactCount", () => {
  it("keeps small numbers whole", () => {
    expect(compactCount(0)).toBe("0");
    expect(compactCount(999)).toBe("999");
  });
  it("shortens thousands and millions to one decimal, dropping a .0", () => {
    expect(compactCount(1000)).toBe("1k");
    expect(compactCount(12_340)).toBe("12.3k");
    expect(compactCount(1_234_567)).toBe("1.2M");
    expect(compactCount(3_000_000_000)).toBe("3B");
  });
  it("rounds up into the next unit instead of showing 1000k", () => {
    expect(compactCount(999_999)).toBe("1M");
  });
  it("reads a broken value as 0", () => {
    expect(compactCount(Number.NaN)).toBe("0");
    expect(compactCount(-5)).toBe("0");
  });
});

describe("barHeights", () => {
  it("scales each day against the busiest, as a percent", () => {
    expect(barHeights([0, 50, 100])).toEqual([0, 50, 100]);
  });
  it("is all zero when nothing was used", () => {
    expect(barHeights([0, 0])).toEqual([0, 0]);
  });
  it("gives a used day at least a sliver", () => {
    expect(barHeights([1, 10_000])[0]).toBeGreaterThan(0);
  });
});

describe("tokensLine", () => {
  it("names today, the week and the busiest bot", () => {
    expect(tokensLine(1200, 45_000, "Scout")).toBe("Tokens today: 1.2k · this week: 45k · busiest: Scout");
  });
  it("leaves the busiest bot out when there is none", () => {
    expect(tokensLine(0, 0, null)).toBe("Tokens today: 0 · this week: 0");
  });
});
