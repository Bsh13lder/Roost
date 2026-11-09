import { describe, expect, it } from "vitest";
import { formatChatTime, formatDayLabel } from "../src/lib/chatTime";

const NOW = new Date("2026-10-14T12:30:00Z"); // Wednesday, 14:30 in Madrid

describe("formatChatTime", () => {
  it("shows the Madrid time for today", () => {
    expect(formatChatTime("2026-10-14T12:19:00Z", NOW)).toBe("14:19");
    expect(formatChatTime("2026-10-13T22:30:00Z", NOW)).toBe("00:30"); // already the 14th in Madrid
  });
  it("says Yesterday, then the weekday, then the date", () => {
    expect(formatChatTime("2026-10-13T08:00:00Z", NOW)).toBe("Yesterday");
    expect(formatChatTime("2026-10-09T10:00:00Z", NOW)).toBe("Friday");
    expect(formatChatTime("2026-10-04T10:00:00Z", NOW)).toBe("Oct 4");
  });
  it("shows nothing for a broken time", () => {
    expect(formatChatTime("not a time", NOW)).toBe("");
  });
});

describe("formatDayLabel", () => {
  it("names the Madrid day: Today, Yesterday, then the weekday and date", () => {
    expect(formatDayLabel("2026-10-13T22:30:00Z", NOW)).toBe("Today"); // already the 14th in Madrid
    expect(formatDayLabel("2026-10-13T08:00:00Z", NOW)).toBe("Yesterday");
    expect(formatDayLabel("2026-10-12T10:00:00Z", NOW)).toMatch(/^Monday,? 12 October$/);
    expect(formatDayLabel("not a time", NOW)).toBe("");
  });
});
