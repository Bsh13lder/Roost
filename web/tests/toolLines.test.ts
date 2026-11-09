import { describe, expect, it } from "vitest";
import { toolLineText } from "../src/lib/toolLines";

describe("toolLineText (redesign P2)", () => {
  it("says the current step as it happens", () => {
    expect(toolLineText("adding a task", false)).toBe("Adding a task…");
  });

  it("says a finished step in the past tense", () => {
    expect(toolLineText("adding a task", true)).toBe("Added a task");
    expect(toolLineText("writing a doc", true)).toBe("Wrote a doc");
    expect(toolLineText("reading elpais.com", true)).toBe("Read elpais.com");
    expect(toolLineText("setting a budget", true)).toBe("Set a budget");
    expect(toolLineText("asking Scout", true)).toBe("Asked Scout");
  });

  it("keeps a line it has no past tense for as it is, capitalised", () => {
    expect(toolLineText("waiting: you have control of my computer", true)).toBe("Waiting: you have control of my computer");
  });

  it('says "sending 3 helpers to research x" as "Sent 3 helpers to research x"', () => {
    expect(toolLineText("sending 3 helpers to research x", true)).toBe("Sent 3 helpers to research x");
    expect(toolLineText("sending 1 helper (helper 2)", true)).toBe("Sent 1 helper (helper 2)");
  });
});
