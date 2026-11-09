import { describe, expect, it } from "vitest";
import { isWeekend, monthDays, weekDays } from "../src/components/board/calendar/monthCells";

describe("monthCells", () => {
  it("October 2026 starts on Monday 28 Sep and has 5 weeks", () => {
    const days = monthDays("2026-10");
    expect(days).toHaveLength(35);
    expect(days[0]).toBe("2026-09-28");
    expect(days[34]).toBe("2026-11-01");
  });

  it("a month that needs six weeks has 42 cells", () => {
    const days = monthDays("2026-08");
    expect(days).toHaveLength(42);
    expect(days[0]).toBe("2026-07-27");
    expect(days[41]).toBe("2026-09-06");
  });

  it("a week runs Monday to Sunday in Madrid", () => {
    expect(weekDays("2026-10-21")).toEqual([
      "2026-10-19", "2026-10-20", "2026-10-21", "2026-10-22", "2026-10-23", "2026-10-24", "2026-10-25",
    ]);
    expect(weekDays("2026-10-25")[0]).toBe("2026-10-19");
    expect(weekDays("2026-10-26")[0]).toBe("2026-10-26");
    expect(isWeekend("2026-10-24")).toBe(true);
    expect(isWeekend("2026-10-23")).toBe(false);
  });
});
