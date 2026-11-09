import { describe, expect, it } from "vitest";
import { cronFor, repeatOf } from "../src/components/tasks/repeat";

describe("a task's repeat (redesign P3)", () => {
  it("names the crons the drawer builds, and anything else Custom", () => {
    expect(repeatOf(null)).toBe("never");
    expect(repeatOf("0 9 * * *")).toBe("daily");
    expect(repeatOf("30 18 * * 1-5")).toBe("weekdays");
    expect(repeatOf("0 9 * * 5")).toBe("weekly");
    expect(repeatOf("0 9 16 * *")).toBe("monthly");
    expect(repeatOf("0 9 * * 1,3")).toBe("custom");
    expect(repeatOf("*/15 * * * *")).toBe("custom");
  });

  it("builds each repeat at the due's wall time, on its weekday or day of the month", () => {
    const due = "2026-10-16T18:30:00+02:00"; // a Friday, 18:30 in Madrid
    expect(cronFor("daily", due)).toBe("30 18 * * *");
    expect(cronFor("weekdays", due)).toBe("30 18 * * 1-5");
    expect(cronFor("weekly", due)).toBe("30 18 * * 5");
    expect(cronFor("monthly", due)).toBe("30 18 16 * *");
    expect(cronFor("never", due)).toBeNull();
    expect(cronFor("custom", due)).toBeNull();
  });

  it("uses 09:00 for a due with no time, and round-trips through repeatOf", () => {
    expect(cronFor("weekly", "2026-10-19")).toBe("0 9 * * 1");
    for (const kind of ["daily", "weekdays", "weekly", "monthly"] as const) {
      expect(repeatOf(cronFor(kind, "2026-10-19 07:05"))).toBe(kind);
    }
  });
});
