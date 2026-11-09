import { describe, expect, it } from "vitest";
import { approvalFor, chatModeOf } from "../src/lib/chatMode";
import { makeBot } from "./fixtures";

const bot = (ask_topics: string[], auto_review?: boolean, mode = "auto_edit") =>
  makeBot({ approval: { mode, ask_topics, locked_topics: ["posting"], auto_review } as never });

describe("chatModeOf", () => {
  it("is Ask me while browsing is an Always ask topic, even with the checker on", () => {
    expect(chatModeOf(bot(["money", "browsing"], true))).toBe("ask");
  });
  it("is Full auto when the checker is on and browsing does not ask", () => {
    expect(chatModeOf(bot(["money"], true))).toBe("auto");
  });
  it("is Just browse otherwise, a missing auto_review counting as off", () => {
    expect(chatModeOf(bot([]))).toBe("browse");
    expect(chatModeOf(bot([], false))).toBe("browse");
  });
});

describe("approvalFor", () => {
  it("Ask me adds browsing once and turns the checker off, keeping the mode and other topics", () => {
    expect(approvalFor(bot(["money"], true), "ask")).toEqual({ mode: "auto_edit", askTopics: ["money", "browsing"], autoReview: false });
    expect(approvalFor(bot(["browsing"]), "ask").askTopics).toEqual(["browsing"]);
  });
  it("Just browse drops browsing and the checker", () => {
    expect(approvalFor(bot(["browsing", "files"], true), "browse")).toEqual({ mode: "auto_edit", askTopics: ["files"], autoReview: false });
  });
  it("Full auto drops browsing and turns the checker on", () => {
    expect(approvalFor(bot(["browsing", "files"]), "auto")).toEqual({ mode: "auto_edit", askTopics: ["files"], autoReview: true });
  });
  it("never changes the bot it was given", () => {
    const given = bot(["files"]);
    approvalFor(given, "ask");
    expect(given.approval.ask_topics).toEqual(["files"]);
  });
});
