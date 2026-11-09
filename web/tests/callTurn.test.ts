import { describe, expect, it } from "vitest";
import type { ApprovalCardOut, MessageOut, StuckCardOut } from "../src/api/types";
import { askingLine, askingTitle, replyPlaceholder, turnOutcome } from "../src/lib/callTurn";

const msg = (id: string, role: "user" | "bot", kind = "text", seq = 1): MessageOut => ({
  id, thread_id: "t1", role, body: `${id} body`, tainted: false, seq, created_at: "2026-10-30T12:00:00Z", kind,
  author_bot_id: role === "bot" ? "b1" : null,
} as MessageOut);

describe("turnOutcome", () => {
  const before = [msg("old", "bot"), msg("mine", "user")];

  it("waits while the bot hasn't answered or is still On it", () => {
    expect(turnOutcome(before, "mine", "resting", false)).toBeNull();
    expect(turnOutcome([...before, msg("r", "bot")], "mine", "on_it", true)).toBeNull();
    expect(turnOutcome(before, "missing", "resting", true)).toBeNull();
  });

  it("speaks the first stored reply after your message once the bot is done", () => {
    const all = [...before, msg("tool", "bot", "tool_line"), msg("r1", "bot"), msg("r2", "bot", "report")];
    expect(turnOutcome(all, "mine", "resting", true)).toEqual({ kind: "reply", messageId: "r1" });
  });

  it("never speaks a reply still being written (seq 0) or the one before your message", () => {
    expect(turnOutcome([...before, msg("p", "bot", "text", 0)], "mine", "resting", true))
      .toEqual({ kind: "done" });
  });

  it("says the bot is asking when it waits on a card", () => {
    expect(turnOutcome(before, "mine", "asking_you", true)).toEqual({ kind: "asking" });
    expect(turnOutcome(before, "mine", "stuck", false)).toEqual({ kind: "asking" });
  });

  it("finishes quietly when the bot worked and said nothing", () => {
    expect(turnOutcome(before, "mine", "resting", true)).toEqual({ kind: "done" });
  });
});

describe("askingTitle", () => {
  const card = (over: Partial<ApprovalCardOut>): ApprovalCardOut => ({
    id: "c", bot_id: "b1", thread_id: "t1", kind: "ask", state: "open", tainted: false, session_offer: false,
    created_at: "2026-10-30T12:00:00Z", closed_at: null, steps: [{ title: "Send the email" } as never], ...over,
  });

  it("names the open card of this bot: an options card by its question", () => {
    expect(askingTitle([card({})], [], "b1")).toBe("Send the email");
    expect(askingTitle([card({ choice: { question: "Which one?", options: [], safe: 0, own: false, why: "" } })], [], "b1"))
      .toBe("Which one?");
    expect(askingTitle([card({ state: "approved" }), card({ bot_id: "b2" })], [], "b1")).toBeNull();
  });

  it("names an open Stuck card by its site", () => {
    const stuck = { id: "s", bot_id: "b1", state: "open", host: "upwork.com" } as StuckCardOut;
    expect(askingTitle([], [stuck], "b1")).toBe("Help on upwork.com");
  });

  it("builds the line the call shows", () => {
    expect(askingLine("Gigs", "Send the email")).toBe("Gigs is asking: Send the email. Say yes or no, or answer in the chat.");
    expect(askingLine("Gigs", null)).toBe("Gigs is asking you something. Say yes or no, or answer in the chat.");
  });
});

describe("replyPlaceholder", () => {
  it("finds the reply being written after your message, never one before it or a stored one", () => {
    const before = [msg("old-p", "bot", "text", 0), msg("mine", "user")];
    expect(replyPlaceholder(before, "mine")).toBeNull();
    const placeholder = msg("p", "bot", "text", 0);
    expect(replyPlaceholder([...before, msg("tool", "bot", "tool_line"), placeholder], "mine")).toBe(placeholder);
    expect(replyPlaceholder([...before, msg("r", "bot", "text", 3)], "mine")).toBeNull();
    expect(replyPlaceholder(before, "missing")).toBeNull();
  });
});
