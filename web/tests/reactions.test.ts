import { describe, expect, it } from "vitest";
import { foldReactions, isReactionMessage } from "../src/lib/reactions";
import { makeMessage } from "./fixtures";

const react = (id: string, seq: number, target: string, key: string | null) =>
  makeMessage({ id, seq, kind: "reaction", role: "user", body: JSON.stringify({ target_id: target, key }) });

describe("foldReactions", () => {
  it("newest reaction wins", () => {
    const folded = foldReactions([react("r1", 2, "m1", "heart"), react("r2", 3, "m1", "laugh"), react("r3", 4, "m2", "check")]);
    expect(folded.get("m1")).toBe("laugh");
    expect(folded.get("m2")).toBe("check");
  });

  it("null clears", () => {
    const folded = foldReactions([react("r1", 2, "m1", "heart"), react("r2", 3, "m1", null)]);
    expect(folded.has("m1")).toBe(false);
  });

  it("no mutation, and a body that is not a tapback is ignored", () => {
    const messages = Object.freeze([
      react("r1", 2, "m1", "heart"), react("r2", 3, "m1", "not-a-key"),
      makeMessage({ id: "bad", kind: "reaction", body: "{nope" }), makeMessage({ id: "m1" }),
    ]);
    const before = JSON.stringify(messages);
    const folded = foldReactions(messages);
    expect(JSON.stringify(messages)).toBe(before);
    expect(folded.get("m1")).toBe("heart");
    expect(isReactionMessage(messages[0])).toBe(true);
    expect(isReactionMessage(messages[3])).toBe(false);
  });
});
