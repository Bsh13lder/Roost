import { afterEach, describe, expect, it, vi } from "vitest";
import { clearStuck, giveUpStuck, listStuck, openInMainBrowser } from "../src/api/stuck";
import { mergeStuck, myTurnLine, openStuckCards, parseStuckMessage, stuckTitle } from "../src/lib/stuck";
import { makeStuckCard, STUCK_LINE } from "./fixtures";

afterEach(() => vi.unstubAllGlobals());

const BODY = {
  card_id: "card-1", bot_id: "bot-1", reason: "login", host: "shop.example", url: "https://shop.example/login",
  note: "", suggest_main_browser: false, line: STUCK_LINE,
};

describe("parseStuckMessage", () => {
  it("reads the card a stuck message carries", () => {
    expect(parseStuckMessage(JSON.stringify(BODY))).toEqual(BODY);
  });

  it("keeps only the card's own fields", () => {
    expect(parseStuckMessage(JSON.stringify({ ...BODY, extra: "<b>x</b>" }))).toEqual(BODY);
  });

  it("reads a card with no address, when the bot asked for help", () => {
    const asked = { ...BODY, reason: "asked", host: "", url: "", note: "Approve the payment" };
    expect(parseStuckMessage(JSON.stringify(asked))).toEqual(asked);
  });

  it.each([
    ["card_id", 7], ["card_id", ""], ["bot_id", null], ["reason", "captcha"], ["host", 1],
    ["url", 5], ["note", undefined], ["suggest_main_browser", "yes"], ["line", 3],
  ])("refuses a body whose %s is %s", (field, value) => {
    expect(parseStuckMessage(JSON.stringify({ ...BODY, [field]: value }))).toBeNull();
  });

  // Task 4 already sends no address for a fresh tab's about:blank, but the body is still checked here.
  // The card must keep its buttons, or it could never be cleared from the chat, so only the address goes.
  it.each(["about:blank", "javascript:alert(1)", "file:///etc/passwd"])(
    "treats the address %s as none: the card stays, but never shows or opens it",
    (url) => {
      expect(parseStuckMessage(JSON.stringify({ ...BODY, url, host: url }))).toEqual({ ...BODY, url: "", host: "" });
    },
  );

  it("refuses a body that is not JSON or not an object", () => {
    expect(parseStuckMessage("I'm stuck")).toBeNull();
    expect(parseStuckMessage("null")).toBeNull();
    expect(parseStuckMessage("[]")).toBeNull();
  });
});

describe("mergeStuck and openStuckCards", () => {
  it("adds the live cards to the loaded ones, and the live copy wins", () => {
    const loaded = [makeStuckCard({ id: "a" }), makeStuckCard({ id: "b" })];
    const live = { b: makeStuckCard({ id: "b", state: "cleared" }), c: makeStuckCard({ id: "c" }) };
    const merged = mergeStuck(loaded, live);
    expect(Object.keys(merged).sort()).toEqual(["a", "b", "c"]);
    expect(merged.b.state).toBe("cleared");
    expect(loaded[1].state).toBe("open"); // never mutated
  });

  it("keeps the cards still open, newest first", () => {
    const cards = mergeStuck([
      makeStuckCard({ id: "old", created_at: "2026-10-14T09:00:00Z" }),
      makeStuckCard({ id: "new", created_at: "2026-10-14T11:00:00Z" }),
      makeStuckCard({ id: "done", state: "given_up" }),
    ], {});
    expect(openStuckCards(cards).map((card) => card.id)).toEqual(["new", "old"]);
  });
});

describe("myTurnLine", () => {
  it("a Sign-in card asks you to sign in; any other card keeps its title", () => {
    expect(myTurnLine("Scout", makeStuckCard({ sign_in: true }))).toBe("Scout needs you to sign in to shop.example");
    expect(myTurnLine("Scout", makeStuckCard())).toBe("Scout · Stuck on shop.example");
  });
});

describe("stuckTitle", () => {
  it("names the site, or asks for help when the card has no web address", () => {
    expect(stuckTitle("shop.example", "https://shop.example/login")).toBe("Stuck on shop.example");
    expect(stuckTitle("", "")).toBe("Needs your help");
    expect(stuckTitle("about:blank", "about:blank")).toBe("Needs your help");
  });
});

describe("the Stuck API", () => {
  it("lists your open cards and presses each button with the card's id", async () => {
    const card = makeStuckCard();
    const fetchMock = vi.fn(async (_path: string, _init: RequestInit) =>
      new Response(JSON.stringify(card), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    await listStuck();
    await clearStuck("card-1");
    await giveUpStuck("card-1");
    await openInMainBrowser("card-1");
    expect(fetchMock.mock.calls.map(([path, init]) => [init.method, path])).toEqual([
      ["GET", "/api/stuck"],
      ["POST", "/api/stuck/card-1/clear"],
      ["POST", "/api/stuck/card-1/give-up"],
      ["POST", "/api/stuck/card-1/open-in-main-browser"],
    ]);
  });
});
