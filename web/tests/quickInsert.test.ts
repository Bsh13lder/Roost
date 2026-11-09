import { describe, expect, it } from "vitest";
import { dateWords, filterNames, insertWords, tagWords, withoutWords } from "../src/components/tasks/quickInsert";

describe("the pickers' words", () => {
  it("turns a picked day and time into words the server reads", () => {
    expect(dateWords("2026-10-21")).toBe("2026-10-21");
    expect(dateWords("2026-10-21 09:00")).toBe("2026-10-21 at 09:00");
    expect(dateWords(" tomorrow at 9 ")).toBe("tomorrow at 9");
    expect(dateWords("")).toBe("");
  });

  it("adds words at the end, or replaces the chip's earlier words", () => {
    expect(insertWords("Call Ana", "!high")).toBe("Call Ana !high");
    expect(insertWords("Call Ana !low", "!high", ["!low"])).toBe("Call Ana !high");
    expect(insertWords("Call tomorrow at 9 Ana", "2026-10-30", ["tomorrow", "at 9"])).toBe("Call Ana 2026-10-30");
    expect(insertWords("Call Ana tomorrow", "", ["tomorrow"])).toBe("Call Ana");   // No date
    expect(insertWords("", "/Reno")).toBe("/Reno");
  });

  it("removes whole words only, in any case", () => {
    expect(withoutWords("Tomorrowland plan Tomorrow", ["tomorrow"])).toBe("Tomorrowland plan");
    expect(withoutWords("Pay *rent* (a+b) *", ["(a+b)"])).toBe("Pay *rent* *");
  });

  it("makes a tag from what was typed", () => {
    expect(tagWords("shopping")).toBe("#shopping");
    expect(tagWords("#home life")).toBe("#home-life");
    expect(tagWords("123")).toBeNull();
    expect(tagWords("  ")).toBeNull();
  });

  it("searches names, those that start with the query first", () => {
    expect(filterNames(["Casa Nueva", "Trip", "Renovation"], "")).toEqual(["Casa Nueva", "Trip", "Renovation"]);
    expect(filterNames(["Casa Nueva", "Trip", "Renovation"], "ren")).toEqual(["Renovation"]);
    expect(filterNames(["Old Trip", "Trip"], "trip")).toEqual(["Trip", "Old Trip"]);
  });
});
