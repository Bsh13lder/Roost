import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import {
  addDays, dateToDay, dayText, dayToDate, dueParts, friendlyDue, isIsoDay, joinDue, nextMonday, pickedParts, pickerText,
  todayIn, wallText,
} from "../src/ui/date/dates";

// Far from Madrid, so a helper that leaned on the browser's zone would show it.
const BROWSER_ZONE = "America/Los_Angeles";
let savedZone: string | undefined;
beforeAll(() => { savedZone = process.env.TZ; process.env.TZ = BROWSER_ZONE; });
afterAll(() => { process.env.TZ = savedZone; });
afterEach(() => vi.useRealTimers());

describe("Madrid days", () => {
  it("today is Madrid's day, not UTC's or the browser's", () => {
    // 22:30 UTC on the 15th is 00:30 on the 16th in Madrid (CEST) and 15:30 on the 15th in Los Angeles.
    expect(todayIn(new Date("2026-10-15T22:30:00Z"))).toBe("2026-10-16");
    // In winter (CET) Madrid is UTC+1: 23:30 UTC on 1 Dec is 00:30 on 2 Dec.
    expect(todayIn(new Date("2026-12-01T23:30:00Z"))).toBe("2026-12-02");
  });

  it("adds days across months, years and the night the clocks go back", () => {
    expect(addDays("2026-10-31", 1)).toBe("2026-11-01");
    expect(addDays("2026-12-31", 1)).toBe("2027-01-01");
    expect(addDays("2026-10-25", 1)).toBe("2026-10-26"); // Madrid's last Sunday of October
    expect(addDays("2026-03-01", -1)).toBe("2026-02-28");
  });

  it("next week is the next Monday", () => {
    expect(nextMonday("2026-10-15")).toBe("2026-10-19"); // a Thursday
    expect(nextMonday("2026-10-19")).toBe("2026-10-26"); // a Monday gives the one after
    expect(nextMonday("2026-10-18")).toBe("2026-10-19"); // a Sunday
  });

  it("knows a real day from a near miss", () => {
    expect(isIsoDay("2026-10-16")).toBe(true);
    expect(isIsoDay("2026-02-30")).toBe(false);
    expect(isIsoDay("16/10/2026")).toBe(false);
  });
});

describe("what a picker holds", () => {
  it("reads only a clock that exists: an hour below 24, a minute and a second below 60", () => {
    expect(dueParts("2026-10-16 00:00")).toEqual({ day: "2026-10-16", time: "00:00" });
    expect(dueParts("2026-10-16 23:59")).toEqual({ day: "2026-10-16", time: "23:59" });
    expect(dueParts("2026-10-16T23:59:59+02:00")).toEqual({ day: "2026-10-16", time: "23:59" });
    for (const text of ["2026-10-16 25:99", "2026-10-16 24:00", "2026-10-16 09:60", "2026-10-16 23:59:60"]) {
      expect(dueParts(text)).toBeNull();
      expect(pickedParts(text)).toBeNull();
    }
  });

  it("reads a stored timed due as its Madrid wall time, whatever the browser's zone", () => {
    expect(dueParts("2026-10-14T23:30:00+02:00")).toEqual({ day: "2026-10-14", time: "23:30" });
    expect(pickerText("2026-10-14T09:00:00+02:00")).toBe("2026-10-14 09:00");
    expect(pickerText("2026-10-14")).toBe("2026-10-14");
    expect(pickerText(null)).toBe("");
  });

  it("sends a day, or a day and a wall time, never an instant", () => {
    expect(joinDue("2026-10-17", null)).toBe("2026-10-17");
    expect(joinDue("2026-10-17", "09:00")).toBe("2026-10-17 09:00");
    expect(dueParts("2026-10-17 09:00")).toEqual({ day: "2026-10-17", time: "09:00" });
    expect(dueParts("tomorrow at 9")).toBeNull();
  });

  it("leaves a typed time with a zone to the gateway, which moves it onto Madrid's clock", () => {
    expect(pickedParts("2026-10-16 09:00")).toEqual({ day: "2026-10-16", time: "09:00" });
    expect(pickedParts("2026-10-16")).toEqual({ day: "2026-10-16", time: null });
    expect(pickedParts("2026-10-16T09:00:00Z")).toBeNull(); // 11:00 in Madrid
    expect(pickedParts("2026-10-16T23:30:00-05:00")).toBeNull(); // the 17th, 06:30 in Madrid
    expect(pickedParts("tomorrow at 9")).toBeNull();
  });

  it("says a day the friendly way", () => {
    expect(friendlyDue({ day: "2026-10-16", time: null })).toBe("Fri 16 Oct 2026");
    expect(friendlyDue({ day: "2026-10-16", time: "09:00" })).toBe("Fri 16 Oct 2026, 09:00");
    expect(friendlyDue({ day: "2026-10-16", time: "09:00" }, false)).toBe("Fri 16 Oct 2026");
  });

  it("spells every month with three letters, whatever the ICU says", () => {
    const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    months.forEach((name, index) => {
      const day = `2026-${String(index + 1).padStart(2, "0")}-16`;
      expect(friendlyDue({ day, time: null })).toMatch(new RegExp(`^\\w{3} 16 ${name} 2026$`));
    });
    expect(friendlyDue({ day: "2026-09-16", time: "18:00" })).toBe("Wed 16 Sep 2026, 18:00");
  });

  it("names a day with or without its weekday and year, September as Sep, and leaves a non-day alone", () => {
    expect(dayText("2026-09-15")).toBe("15 Sep");
    expect(dayText("2026-09-15", { weekday: true })).toBe("Tue 15 Sep");
    expect(dayText("2026-09-15", { year: true })).toBe("15 Sep 2026");
    expect(dayText("2026-09-15", { weekday: true, year: true })).toBe("Tue 15 Sep 2026");
    expect(dayText("2026-02-30")).toBe("2026-02-30");
    expect(dayText("soon")).toBe("soon");
  });

  it("shows an instant as Madrid's day and wall time, in winter and summer", () => {
    expect(wallText("2026-11-30T19:00:00+00:00")).toBe("2026-11-30 20:00");
    expect(wallText("2026-07-01T07:00:00Z")).toBe("2026-07-01 09:00");
    expect(wallText("2026-10-24T23:30:00Z")).toBe("2026-10-25 01:30");
    expect(wallText(null)).toBe("");
    expect(wallText("not a time")).toBe("");
  });

  it("the calendar's dates round-trip to the same day in any zone", () => {
    for (const day of ["2026-10-25", "2026-03-29", "2026-12-31"]) expect(dateToDay(dayToDate(day))).toBe(day);
  });

  it("a browser anywhere sees the same Madrid day, the day the clocks change included", () => {
    const zones = ["Pacific/Honolulu", "America/Los_Angeles", "UTC", "Europe/Madrid", "Asia/Kolkata", "Pacific/Kiritimati"];
    try {
      for (const zone of zones) {
        process.env.TZ = zone;
        expect(todayIn(new Date("2026-10-15T22:30:00Z")), zone).toBe("2026-10-16");
        expect(todayIn(new Date("2026-10-25T00:30:00Z")), zone).toBe("2026-10-25"); // 02:30 CEST, the night clocks go back
        for (const day of ["2026-10-25", "2026-03-29", "2026-01-01"]) expect(dateToDay(dayToDate(day)), zone).toBe(day);
      }
    } finally {
      process.env.TZ = BROWSER_ZONE;
    }
  });
});
