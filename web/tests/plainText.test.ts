import { describe, expect, it } from "vitest";
import { plainText } from "../src/lib/plainText";

describe("plainText (redesign P2)", () => {
  it("drops the marks a flattened reply carries and keeps its words", () => {
    expect(plainText("## Plan **Done.** See [the docs](https://docs.example/x) and [[Garden plan|my garden]]."))
      .toBe("Plan Done. See the docs and my garden.");
    expect(plainText("Use `npm run build` and *really* check ~~old~~ _new_ steps"))
      .toBe("Use npm run build and really check old new steps");
    expect(plainText("> Quoted: | Day | Task | |---|:---:| | Mon | Dentist |")).toBe("Quoted: Day Task Mon Dentist");
    expect(plainText("## Week\n\n| Day | Task |\n| --- | --- |\n| Mon | Dentist |")).toBe("Week Day Task Mon Dentist");
  });

  it("leaves plain words alone: sums, snake_case, ranges and a lone star", () => {
    expect(plainText("2 * 3 = 6, snake_case_name, 3 - 4 EUR, rated 5 *")).toBe("2 * 3 = 6, snake_case_name, 3 - 4 EUR, rated 5 *");
  });
});
