import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { dueTone, dueWords, formatDueChip, formatEarly, formatReminder } from "../src/components/board/taskChips";

// Local-time constructors keep these independent of the machine's zone.
beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date(2026, 9, 13, 12, 0));
});
afterEach(() => vi.useRealTimers());

describe("formatDueChip", () => {
  it("a reminder later today reads 'today' with its time", () => {
    const chip = formatDueChip(null, new Date(2026, 9, 13, 14, 0).toISOString());
    expect(chip.tone).toBe("soon");
    expect(chip.label).toMatch(/^in 2h|^today /);
  });

  it("a timed due with no reminder uses the due's own time", () => {
    const chip = formatDueChip(new Date(2026, 9, 13, 18, 0).toISOString(), null);
    expect(chip.tone).toBe("soon");
  });

  it("a date-only due reads in days, and overdue says so", () => {
    expect(formatDueChip("2026-10-16", null)).toEqual({ label: "in 3d", tone: "future" });
    expect(formatDueChip("2026-10-14", null)).toEqual({ label: "tomorrow", tone: "soon" });
    expect(formatDueChip("2026-10-10", null)).toEqual({ label: "3d overdue", tone: "overdue" });
  });

  it("no due, no chip", () => {
    expect(formatDueChip(null, null)).toEqual({ label: "", tone: "none" });
  });
});

describe("Roost adaptations", () => {
  it("a date-only due keeps its own day when a reminder rings earlier", () => {
    const reminder = new Date(2026, 9, 15, 8, 0).toISOString();
    expect(formatDueChip("2026-10-16", reminder)).toEqual({ label: "in 3d", tone: "future" });
  });

  it("a reminder on the due's day shows just its time, another day shows the day too", () => {
    const due = new Date(2026, 9, 16, 9, 0).toISOString();
    expect(formatReminder(new Date(2026, 9, 16, 8, 30).toISOString(), due)).toMatch(/^Reminder \d/);
    expect(formatReminder(new Date(2026, 9, 15, 20, 0).toISOString(), due)).not.toMatch(/^Reminder \d/);
    expect(formatReminder(new Date(2026, 9, 13, 18, 0).toISOString(), null)).toMatch(/^Reminder \d/);
  });

  it("advance reminders read as offsets from the reminder", () => {
    const ring = "2026-10-14T07:00:00+00:00";
    expect(formatEarly(["2026-10-14T06:30:00+00:00", "2026-10-14T05:00:00+00:00"], ring)).toBe("30m, 2h before");
    expect(formatEarly(["2026-10-13T07:00:00+00:00"], ring)).toBe("1d before");
    expect(formatEarly(["2026-10-14T06:30:00+00:00"], null)).toBe("1 early");
    expect(formatEarly([], ring)).toBeNull();
  });
});

describe("a row's due, in words (G3)", () => {
  const today = "2026-10-20";

  it("due words: Yesterday, 4d overdue, Today, Tomorrow, Fri, 29 Oct", () => {
    expect(dueWords("2026-10-19", today, false)).toBe("Yesterday");
    expect(dueWords("2026-10-16", today, false)).toBe("4d overdue");
    expect(dueWords("2026-10-20", today, false)).toBe("Today");
    expect(dueWords("2026-10-20T09:00:00+02:00", today, false)).toBe("Today");
    expect(dueWords("2026-10-21", today, false)).toBe("Tomorrow");
    expect(dueWords("2026-10-23", today, false)).toBe("Fri");
    expect(dueWords("2026-10-29", today, false)).toBe("29 Oct");
    expect(dueWords(null, today, false)).toBe("");
  });

  it("a done task shows its day in full", () => {
    expect(dueWords("2026-10-20", today, true)).toBe("Tue 20 Oct");
  });

  it("due tones match the words", () => {
    expect(dueTone("2026-10-19", today)).toBe("over");
    expect(dueTone("2026-10-20", today)).toBe("today");
    expect(dueTone("2026-10-21", today)).toBe("soon");
    expect(dueTone("2026-10-23", today)).toBe("later");
    expect(dueTone("2026-10-29", today)).toBe("later");
    expect(dueTone(null, today)).toBe("later");
  });
});
