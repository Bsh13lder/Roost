import { describe, expect, it } from "vitest";
import { rangeFor, rangeLabel } from "../src/components/board/dateRanges";

describe("the Money date ranges (G10)", () => {
  it("Today is today alone", () => {
    expect(rangeFor("today", "2026-10-21")).toEqual({ from: "2026-10-21", to: "2026-10-21" });
  });

  it("This week is Monday to today in Madrid", () => {
    expect(rangeFor("week", "2026-10-21")).toEqual({ from: "2026-10-19", to: "2026-10-21" }); // a Wednesday
    expect(rangeFor("week", "2026-10-25")).toEqual({ from: "2026-10-19", to: "2026-10-25" }); // a Sunday
    expect(rangeFor("week", "2026-10-19")).toEqual({ from: "2026-10-19", to: "2026-10-19" }); // a Monday
    expect(rangeFor("week", "2026-11-01")).toEqual({ from: "2026-10-26", to: "2026-11-01" }); // across a month
  });

  it("This month on the 1st is one day", () => {
    expect(rangeFor("month", "2026-10-01")).toEqual({ from: "2026-10-01", to: "2026-10-01" });
    expect(rangeFor("month", "2026-10-21")).toEqual({ from: "2026-10-01", to: "2026-10-21" });
  });

  it("Last month is the whole previous month", () => {
    expect(rangeFor("last", "2026-10-21")).toEqual({ from: "2026-09-01", to: "2026-09-30" });
    expect(rangeFor("last", "2026-03-05")).toEqual({ from: "2026-02-01", to: "2026-02-28" });
    expect(rangeFor("last", "2028-03-05")).toEqual({ from: "2028-02-01", to: "2028-02-29" });
    expect(rangeFor("last", "2026-01-15")).toEqual({ from: "2025-12-01", to: "2025-12-31" });
  });

  it("names a range for the summary and the custom chip", () => {
    expect(rangeLabel("week", rangeFor("week", "2026-10-21"))).toBe("this week");
    expect(rangeLabel("last", rangeFor("last", "2026-10-21"))).toBe("last month");
    expect(rangeLabel("custom", { from: "2026-10-12", to: "2026-10-18" })).toBe("12 Oct–18 Oct");
    expect(rangeLabel("custom", { from: "2026-10-12", to: "2026-10-12" })).toBe("12 Oct");
  });
});
