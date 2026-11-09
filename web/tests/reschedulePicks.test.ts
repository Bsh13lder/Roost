import { describe, expect, it } from "vitest";
import { pickLabel, RESCHEDULE_PICKS } from "../src/components/board/reschedulePicks";
import { isWallTime } from "../src/ui/date/dates";

const days = (today: string) => Object.fromEntries(RESCHEDULE_PICKS.map((pick) => [pick.label, pick.day(today)]));

describe("the reschedule picks", () => {
  it("gives each pick its Madrid day", () => {
    expect(RESCHEDULE_PICKS.map((pick) => pick.label)).toEqual(
      ["Today", "Tomorrow", "This weekend", "Next Monday", "Next week", "+1 week", "No date"]);
    expect(days("2026-10-20")).toEqual({
      Today: "2026-10-20", Tomorrow: "2026-10-21", "This weekend": "2026-10-24", "Next Monday": "2026-10-26",
      "Next week": "2026-10-30", "+1 week": "2026-10-27", "No date": null,
    });
  });

  it("on a Saturday This weekend is today", () => {
    expect(days("2026-10-24")["This weekend"]).toBe("2026-10-24");
    expect(days("2026-10-26")["Next Monday"]).toBe("2026-11-02"); // never today
  });

  it("writes a short label and reads wall times", () => {
    expect(pickLabel("2026-10-21")).toBe("Wed 21");
    expect(["09:30", "9:30", "23:59"].every(isWallTime)).toBe(true);
    expect(["25:00", "9:5", "abc", ""].some(isWallTime)).toBe(false);
  });
});
