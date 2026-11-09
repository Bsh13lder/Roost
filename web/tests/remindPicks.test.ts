import { describe, expect, it } from "vitest";
import { remindPicks } from "../src/components/tasks/remindPicks";

describe("Remind me's quick picks", () => {
  it("counts back from a timed due on Madrid's clock", () => {
    expect(remindPicks("2026-12-01T09:00:00+01:00")).toEqual([
      { label: "At the due time", text: "2026-12-01 09:00" },
      { label: "10 min before", text: "2026-12-01 08:50" },
      { label: "1 hour before", text: "2026-12-01 08:00" },
      { label: "1 day before", text: "2026-11-30 09:00" },
    ]);
  });

  it("crosses midnight backwards", () => {
    expect(remindPicks("2026-12-01 00:05")[1]).toEqual({ label: "10 min before", text: "2026-11-30 23:55" });
  });

  it("offers nothing for a day with no time, words or no due", () => {
    expect(remindPicks("2026-12-01")).toEqual([]);
    expect(remindPicks(null)).toEqual([]);
    expect(remindPicks("tomorrow")).toEqual([]);
  });
});
