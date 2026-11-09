import { describe, expect, it } from "vitest";
import { GOODBYE_WORDS, isGoodbye } from "../src/lib/callWords";

describe("isGoodbye (call mode, contract D)", () => {
  it("matches the whole utterance only, in either language", () => {
    for (const word of ["bye", "goodbye", "bye bye", "hang up", "end call", "end the call", "that's all", "that is all",
      "adiós", "adios", "hasta luego", "cuelga", "chao"]) {
      expect(isGoodbye(word), word).toBe(true);
    }
    expect(GOODBYE_WORDS.size).toBe(13);
  });

  it("forgives case, spaces and punctuation", () => {
    expect(isGoodbye("  Bye!  ")).toBe(true);
    expect(isGoodbye("Goodbye.")).toBe(true);
    expect(isGoodbye("Hang up?")).toBe(true);
    expect(isGoodbye("That’s all")).toBe(true); // a curly apostrophe
    expect(isGoodbye("ADIÓS")).toBe(true);
  });

  it("never matches a substring or a longer sentence", () => {
    expect(isGoodbye("bye the way")).toBe(false);
    expect(isGoodbye("say goodbye to the team")).toBe(false);
    expect(isGoodbye("hang up the coat")).toBe(false);
    expect(isGoodbye("that's all for the list, add milk")).toBe(false);
    expect(isGoodbye("")).toBe(false);
    expect(isGoodbye("   ")).toBe(false);
  });
});
