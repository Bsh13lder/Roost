import { afterEach, describe, expect, it, vi } from "vitest";
import {
  askNotificationPermission, attentionFor, attentionSnapshot, clearAttention, markAttention,
  notificationPermission, showNotification,
} from "../src/lib/attention";
import type { BotStatusFrame, MessageFrame } from "../src/api/types";
import { makeBot, makeMessage, makeStuckCard, stuckBody } from "./fixtures";

const SCOUT = makeBot({ id: "bot-1", name: "Scout", notify: true });
const message = (overrides = {}): MessageFrame => ({
  type: "message", seq: 3, thread_id: "t",
  message: makeMessage({ role: "bot", body: "Done: the market opens at 9.", author_bot_id: "bot-1", ...overrides }),
});

afterEach(() => {
  vi.unstubAllGlobals();
  clearAttention("bot-1");
});

describe("attention", () => {
  it("a finished reply from a bot with notifications on asks for attention", () => {
    expect(attentionFor(message(), { "bot-1": SCOUT })).toEqual({
      botId: "bot-1", title: "Scout replied", body: "Done: the market opens at 9.",
    });
  });

  it("says a reply in plain words, without its markdown", () => {
    const frame = message({ body: "## Done\n\n**Booked** [the table](https://x.example/t) for [[Saturday]]." });
    expect(attentionFor(frame, { "bot-1": SCOUT })?.body).toBe("Done Booked the table for Saturday.");
  });

  it("the empty placeholder, a card, your own message or a switched-off bot never do", () => {
    expect(attentionFor(message({ body: "" }), { "bot-1": SCOUT })).toBeNull();
    expect(attentionFor(message({ kind: "bot_created" }), { "bot-1": SCOUT })).toBeNull();
    expect(attentionFor(message({ role: "user", author_bot_id: null }), { "bot-1": SCOUT })).toBeNull();
    expect(attentionFor(message(), { "bot-1": { ...SCOUT, notify: false } })).toBeNull();
  });

  it("Asking you asks for attention", () => {
    const frame: BotStatusFrame = { type: "bot_status", seq: 4, bot_id: "bot-1", status: "asking_you", activity: "Which day?" };
    expect(attentionFor(frame, { "bot-1": SCOUT })).toEqual({ botId: "bot-1", title: "Scout needs you", body: "Which day?" });
  });

  it("a bot that turns Stuck asks for attention", () => {
    const frame: BotStatusFrame = { type: "bot_status", seq: 5, bot_id: "bot-1", status: "stuck", activity: null };
    expect(attentionFor(frame, { "bot-1": SCOUT })).toEqual({ botId: "bot-1", title: "Scout is stuck", body: "" });
    expect(attentionFor(frame, { "bot-1": { ...SCOUT, notify: false } })).toBeNull();
  });

  it("a bot waiting on a Sign-in card asks you to sign in, never says stuck", () => {
    const activity = "Waiting for you to sign in to accounts.google.com.";
    const frame: BotStatusFrame = { type: "bot_status", seq: 6, bot_id: "bot-1", status: "stuck", activity };
    expect(attentionFor(frame, { "bot-1": SCOUT })).toEqual({ botId: "bot-1", title: "Scout needs you to sign in", body: activity });
  });

  it("the Stuck card's own message does not notify a second time", () => {
    expect(attentionFor(message({ kind: "stuck", body: stuckBody(makeStuckCard()) }), { "bot-1": SCOUT })).toBeNull();
  });

  it("marks and clears a bot", () => {
    markAttention("bot-1");
    expect(attentionSnapshot().has("bot-1")).toBe(true);
    clearAttention("bot-1");
    expect(attentionSnapshot().has("bot-1")).toBe(false);
  });

  it("shows a browser notification only when the user allowed them", () => {
    const shown: unknown[] = [];
    const fake = (permission: string) =>
      Object.assign(function Fake(title: string, options: unknown) { shown.push([title, options]); }, { permission });
    vi.stubGlobal("Notification", fake("granted"));
    showNotification({ botId: "bot-1", title: "Scout replied", body: "Done" });
    vi.stubGlobal("Notification", fake("denied"));
    showNotification({ botId: "bot-1", title: "Scout replied", body: "Done" });
    expect(shown).toEqual([["Scout replied", { body: "Done", tag: "bot-1" }]]);
  });

  it("reads and asks for the browser's permission, and copes without the API", async () => {
    const requestPermission = vi.fn().mockResolvedValue("granted");
    vi.stubGlobal("Notification", Object.assign(function () {}, { permission: "default", requestPermission }));
    expect(notificationPermission()).toBe("default");
    expect(await askNotificationPermission()).toBe("granted");
    vi.stubGlobal("Notification", undefined);
    expect(notificationPermission()).toBe("unsupported");
    expect(await askNotificationPermission()).toBe("unsupported");
  });
});
