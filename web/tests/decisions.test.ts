import { describe, expect, it } from "vitest";
import { decidedAt, parseDecision } from "../src/lib/decisions";

describe("decisions", () => {
  it("parses a decision", () => {
    expect(parseDecision("Which file?\nDecision: the blue one")).toEqual({ question: "Which file?", answer: "the blue one" });
    expect(parseDecision("Which file? Decision: the blue one")).toEqual({ question: "Which file?", answer: "the blue one" });
  });
  it("parses the structured form the server stores", () => {
    expect(parseDecision('{"q":"Which day?","a":"Monday"}')).toEqual({ question: "Which day?", answer: "Monday" });
    expect(parseDecision('{"q":"Which day?","a":"No (dismissed)\\nDecision: x"}')?.question).toBe("Which day?");
    expect(parseDecision('{"q":"Which day?","a":""}')).toBeNull();
    expect(parseDecision('{"q":1,"a":"x"}')).toBeNull();
    expect(parseDecision("{not json")).toBeNull();
  });
  it("ignores other memory text", () => {
    expect(parseDecision("Likes short answers")).toBeNull();
    expect(parseDecision("\nDecision: x")).toBeNull();
  });
  it("writes the date on the account's clock, without a zone", () => {
    expect(decidedAt("2026-10-22T12:19:00Z")).toBe("22 Oct, 14:19");
    expect(decidedAt("nope")).toBe("");
  });
});
