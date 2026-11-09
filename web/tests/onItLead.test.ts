import { describe, expect, it } from "vitest";
import { shownReply, splitOnItLead } from "../src/lib/onItLead";
import { doingOf, glyphFor } from "../src/components/robot/moments";

describe("the On it lead (owner, 2026-10-27)", () => {
  it("splits the opening line from the answer", () => {
    expect(splitOnItLead("On it: checking the chat.\n\nSent: it went out.")).toEqual({ lead: "checking the chat.", rest: "Sent: it went out." });
    expect(splitOnItLead("On it: checking the chat.")).toEqual({ lead: "checking the chat.", rest: "" });
    expect(splitOnItLead("Hello there")).toEqual({ lead: null, rest: "Hello there" });
    expect(splitOnItLead("I am on it: soon").lead).toBeNull();
  });

  it("shows the answer, or the lead's words when nothing follows", () => {
    expect(shownReply("On it: checking.\n\nAll done.")).toBe("All done.");
    expect(shownReply("On it: checking your tasks.")).toBe("checking your tasks.");
    expect(shownReply("Plain answer")).toBe("Plain answer");
  });
});

describe("what a working robot's eyes do", () => {
  it("maps step kinds to eye work", () => {
    expect(doingOf("search")).toBe("search");
    expect(doingOf("read")).toBe("read");
    expect(doingOf("notes")).toBe("write");
    expect(doingOf("tasks")).toBe("records");
    expect(doingOf(undefined)).toBe("think");
    expect(doingOf("nonsense")).toBe("think");
  });

  it("shows the pupils while it searches or reads, the dots while it thinks, the scan for a program", () => {
    const base = { moment: "onit" as const, playing: null, thinking: false, poked: false, control: false };
    expect(glyphFor({ ...base, doing: "search" })).toBe("");
    expect(glyphFor({ ...base, doing: "think" })).toBe("think");
    expect(glyphFor({ ...base, doing: "program" })).toBe("onit");
    expect(glyphFor({ ...base, playing: "done", doing: "read" })).toBe("done");
    expect(glyphFor(base)).toBe("onit");
  });
});
