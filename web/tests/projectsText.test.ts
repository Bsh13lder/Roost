import { describe, expect, it } from "vitest";
import { dateLabel, momentDay } from "../src/components/projects/projects";

describe("project day labels (redesign P3)", () => {
  it("say September as Sep, like the pickers, and leave a non-day alone", () => {
    expect(dateLabel("2026-09-20")).toBe("20 Sep 2026");
    expect(dateLabel("2026-12-20")).toBe("20 Dec 2026");
    expect(dateLabel("someday")).toBe("someday");
  });

  it("name a moment by its Madrid day", () => {
    expect(momentDay("2026-09-30T22:30:00Z")).toBe("1 Oct 2026"); // 00:30 in Madrid
    expect(momentDay("2026-09-10T08:00:00Z")).toBe("10 Sep 2026");
    expect(momentDay("not a time")).toBe("not a time");
  });
});

describe("the project page's day words (G13)", () => {
  it("reckons days left, due today and ended from Madrid's today", async () => {
    const { daysLeftText, monthToGoText, cadenceText, ordinal } = await import("../src/components/projects/projects");
    expect(daysLeftText("2026-10-22", "2026-10-21")).toBe("1 day left");
    expect(daysLeftText("2027-02-17", "2026-10-21")).toBe("119 days left");
    expect(daysLeftText("2026-10-21", "2026-10-21")).toBe("due today");
    expect(daysLeftText("2026-10-18", "2026-10-21")).toBe("ended 3 days ago");
    expect(monthToGoText("2026-10-20")).toBe("11 days to go");
    expect(monthToGoText("2026-10-31")).toBe("last day of the month");
    expect([1, 2, 3, 5, 11, 21, 22].map(ordinal)).toEqual(["1st", "2nd", "3rd", "5th", "11th", "21st", "22nd"]);
    expect(cadenceText("monthly", "2026-09-05")).toBe("monthly, 5th");
    expect(cadenceText("weekly", "2026-10-19")).toBe("weekly, Mon");
    expect(cadenceText("yearly", "2026-11-05")).toBe("yearly, 5 Nov");
  });
});
