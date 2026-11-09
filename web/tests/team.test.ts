import { describe, expect, it } from "vitest";
import { freshest, orderTeam, parseCreatedCard, parseSuggestion, primaryBot } from "../src/lib/team";
import { mergeMessages, nextLocalSeq } from "../src/lib/messages";
import type { BotOut } from "../src/api/types";
import { makeBot, makeMessage } from "./fixtures";

describe("team helpers", () => {
  it("puts the main bot first and keeps the rest in order", () => {
    const team = [makeBot({ id: "a" }), makeBot({ id: "b", is_primary: true }), makeBot({ id: "c" })];
    expect(orderTeam(team).map((bot) => bot.id)).toEqual(["b", "a", "c"]);
    expect(primaryBot(team)?.id).toBe("b");
  });

  it("still puts the main bot first next to a bot without the flag", () => {
    // Number(undefined) is NaN, and sort keeps a NaN-compared pair in place.
    const legacy = { ...makeBot({ id: "old" }), is_primary: undefined } as unknown as BotOut;
    expect(orderTeam([legacy, makeBot({ id: "main", is_primary: true })]).map((bot) => bot.id)).toEqual(["main", "old"]);
  });

  it("reads a suggestion card body and rejects anything else", () => {
    const card = { name: "Ledger", job: "Keeps the books", avatar: { shape: "wide", color: "#3b82f6", badge: "finance", screen: "pixel" } };
    expect(parseSuggestion(JSON.stringify(card))).toEqual(card);
    expect(parseSuggestion("not json")).toBeNull();
    expect(parseSuggestion(JSON.stringify({ name: 3 }))).toBeNull();
  });

  it("ignores a card's roles: every bot has every tool now", () => {
    const card = { name: "Life admin", job: "Tasks and money", avatar: { shape: "crest", color: "#3b82f6", badge: "none", screen: "glow" } };
    expect(parseSuggestion(JSON.stringify({ ...card, roles: ["tasks", "finance"] }))).toEqual(card);
    expect(parseSuggestion(JSON.stringify({ ...card, roles: "tasks" }))).toEqual(card);
  });

  it("a card from before the robots shows the glow screen, and an unknown screen is refused", () => {
    const card = { name: "Ledger", job: "Keeps the books", avatar: { shape: "classic", color: "#3b82f6", badge: "none" } };
    expect(parseSuggestion(JSON.stringify(card))?.avatar.screen).toBe("glow");
    expect(parseSuggestion(JSON.stringify({ ...card, avatar: { ...card.avatar, screen: "neon" } }))).toBeNull();
    expect(parseSuggestion(JSON.stringify({ ...card, avatar: { ...card.avatar, shape: "hexagon" } }))).toBeNull();
  });

  it("reads a Created card and refuses a broken one", () => {
    const card = { bot_id: "b", name: "HiMap SEO", job: "SEO", instructions: "", avatar: { shape: "egg", color: "#14b8a6", badge: "none", screen: "signal" } };
    expect(parseCreatedCard(JSON.stringify(card))).toEqual(card);
    expect(parseCreatedCard(JSON.stringify({ ...card, bot_id: 3 }))).toBeNull();
    expect(parseCreatedCard(JSON.stringify({ ...card, checked: true }))).toEqual({ ...card, checked: true });
    expect(parseCreatedCard(JSON.stringify({ ...card, checked: "yes" }))).toEqual(card);
    expect(parseCreatedCard("not json")).toBeNull();
  });

  it("carries a card's role when it is one it knows, and drops one it does not", () => {
    const created = { bot_id: "b", name: "HiMap SEO", job: "SEO", instructions: "",
      avatar: { shape: "egg", color: "#14b8a6", badge: "none", screen: "glow", role: "seo" } };
    expect(parseCreatedCard(JSON.stringify(created))?.avatar.role).toBe("seo");
    expect(parseCreatedCard(JSON.stringify({ ...created, avatar: { ...created.avatar, role: "hacker" } }))?.avatar)
      .not.toHaveProperty("role");
    const suggested = { name: "Ads", job: "Posts ads", avatar: { shape: "pod", color: "#14b8a6", badge: "none", screen: "glow", role: "social" } };
    expect(parseSuggestion(JSON.stringify(suggested))?.avatar.role).toBe("social");
  });

  it("freshest keeps the newer edit and the live status", () => {
    const local = makeBot({ name: "New name", updated_at: "2026-10-14T10:00:01Z" });
    const live = makeBot({ name: "Old name", updated_at: "2026-10-14T10:00:00Z", status: "on_it" });
    expect(freshest(local, live)).toMatchObject({ name: "New name", status: "on_it" });
  });

  it("merges stored and live messages without duplicates", () => {
    const stored = [makeMessage({ id: "a" })];
    expect(mergeMessages(stored, [makeMessage({ id: "a" }), makeMessage({ id: "b" })]).map((m) => m.id)).toEqual(["a", "b"]);
  });

  it("keeps the conversation in thread order, a reply still streaming last", () => {
    const stored = [makeMessage({ id: "u1", role: "user", seq: 1 }), makeMessage({ id: "u2", role: "user", seq: 3.5 })];
    const live = [
      makeMessage({ id: "b1", seq: 2 }),
      makeMessage({ id: "line", role: "activity", kind: "handoff", seq: 3 }),
      makeMessage({ id: "streaming", seq: 0, body: "" }),
      makeMessage({ id: "b2", seq: 5 }),
    ];
    expect(mergeMessages(stored, live).map((m) => m.id)).toEqual(["u1", "b1", "line", "u2", "b2", "streaming"]);
  });

  it("places a message you just sent after everything already shown", () => {
    const shown = [makeMessage({ id: "a", seq: 4 }), makeMessage({ id: "p", seq: 0 }), makeMessage({ id: "b", seq: 2 })];
    expect(nextLocalSeq(shown)).toBe(4.5);
    expect(nextLocalSeq([])).toBe(0.5);
  });
});
