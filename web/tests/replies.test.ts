import { describe, expect, it } from "vitest";
import type { MessageOut } from "../src/api/types";
import { canReplyTo, quotePreview, quoteSource, REPLY_QUOTE_CHARS } from "../src/lib/replies";

const base: MessageOut = {
  id: "m1", thread_id: "t", role: "bot", body: "hi", tainted: false, seq: 1, created_at: "2026-10-22T10:00:00Z",
  kind: "text", author_bot_id: null,
};

describe("replies", () => {
  it("quotes one flat line, cut with an ellipsis", () => {
    expect(quotePreview("  a\n\nb  ")).toBe("a b");
    const cut = quotePreview("word ".repeat(100));
    expect(cut.length).toBe(REPLY_QUOTE_CHARS);
    expect(cut.endsWith("…")).toBe(true);
  });

  it("lets you reply to conversation messages only", () => {
    expect(canReplyTo(base)).toBe(true);
    expect(canReplyTo({ ...base, role: "user" })).toBe(true);
    expect(canReplyTo({ ...base, kind: "skill_proposal" })).toBe(false);
    expect(canReplyTo({ ...base, role: "activity" })).toBe(false);
    expect(canReplyTo({ ...base, seq: 0 })).toBe(false); // still being written
  });
});

describe("quoteSource", () => {
  const stuckBody = (signIn: boolean) => JSON.stringify({
    card_id: "c1", bot_id: "b1", reason: "login", host: "shop.example", url: "https://shop.example/x",
    note: "words from a web page", suggest_main_browser: false, line: "I'm stuck", sign_in: signIn,
  });

  it("quotes a Stuck card in the server's fixed words, never its note", () => {
    expect(quoteSource({ ...base, kind: "stuck", body: stuckBody(false) })).toBe("Stuck on shop.example");
    expect(quoteSource({ ...base, kind: "stuck", body: stuckBody(true) })).toBe("Waiting for you to sign in to shop.example");
    expect(quoteSource({ ...base, kind: "stuck", body: JSON.stringify({ host: "" }) })).toBe("Needs your help");
  });

  it("quotes anything else by its words", () => {
    expect(quoteSource(base)).toBe("hi");
  });
});
