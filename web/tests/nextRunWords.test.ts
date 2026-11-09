import { describe, expect, it } from "vitest";
import { nextRunWords } from "../src/components/routines/zoneTime";

// Wednesday 21 October 2026, 10:00 in Madrid.
const NOW = new Date("2026-10-21T08:00:00Z");

describe("nextRunWords (owner, 2026-10-26: \"Next run: in 10 hr.\", like Grok)", () => {
  it("says how long while it is today", () => {
    expect(nextRunWords("2026-10-21T08:30:00Z", NOW)).toBe("in 30 min");
    expect(nextRunWords("2026-10-21T11:00:00Z", NOW)).toBe("in 3 h");
    expect(nextRunWords("2026-10-21T11:20:00Z", NOW)).toBe("in 3 h");
    expect(nextRunWords("2026-10-21T08:00:30Z", NOW)).toBe("in 1 min");
  });

  it("says tomorrow, then the weekday, then the date, each with the clock alone", () => {
    expect(nextRunWords("2026-10-22T07:00:00Z", NOW)).toBe("tomorrow 09:00");
    expect(nextRunWords("2026-10-24T07:00:00Z", NOW)).toBe("Sat 09:00");
    expect(nextRunWords("2026-11-05T08:00:00Z", NOW)).toBe("Thu 5 Nov 09:00");
  });

  it("a time already here reads now, and nothing reads as nothing", () => {
    expect(nextRunWords("2026-10-21T07:59:00Z", NOW)).toBe("now");
    expect(nextRunWords(null, NOW)).toBe("");
    expect(nextRunWords("not a time", NOW)).toBe("");
  });
});
