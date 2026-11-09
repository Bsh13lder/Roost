import { describe, expect, it } from "vitest";
import { chatAccentStyle, contrastOf, readableOn } from "../src/lib/chatAccent";

const WHITE_BOT = "#ffffff";
const YELLOW_BOT = "#eab308";
const BLUE_BOT = "#3b82f6";
const GREY_BOT = "#9ca3af";
const VIOLET_BOT = "#8b5cf6";

describe("readableOn", () => {
  it("picks dark text on a white, yellow, blue or grey bot, whichever side reaches 4.5:1", () => {
    for (const bot of [WHITE_BOT, YELLOW_BOT, BLUE_BOT, GREY_BOT]) {
      const text = readableOn(bot);
      expect(contrastOf(text, bot)).toBeGreaterThanOrEqual(4.5);
    }
    expect(readableOn(WHITE_BOT)).toBe(readableOn(YELLOW_BOT));
  });

  it("picks white on a dark colour", () => {
    expect(readableOn("#1e1b4b")).toBe("rgb(255 255 255)");
    expect(contrastOf(readableOn("#1e1b4b"), "#1e1b4b")).toBeGreaterThanOrEqual(4.5);
  });

  it("every palette colour gets text at 4.5:1 or better", () => {
    for (const bot of [WHITE_BOT, YELLOW_BOT, BLUE_BOT, GREY_BOT, VIOLET_BOT, "#ef4444", "#22c55e", "#ec4899", "#6366f1"]) {
      expect(contrastOf(readableOn(bot), bot)).toBeGreaterThanOrEqual(4.5);
    }
  });
});

describe("chatAccentStyle", () => {
  it("sets --chat-accent from the bot's colour, with its text, hover and pressed shades", () => {
    const style = chatAccentStyle(BLUE_BOT) as Record<string, string>;
    expect(style["--chat-accent"]).toBe(BLUE_BOT);
    expect(style["--chat-on-accent"]).toBe(readableOn(BLUE_BOT));
    expect(style["--chat-accent-hover"]).toBeTruthy();
    expect(style["--chat-accent-press"]).toBeTruthy();
    expect(style["--chat-accent-hover"]).not.toBe(style["--chat-accent-press"]);
    expect(style["--chat-accent-soft"]).toBeTruthy();
  });

  it("reads an upper-case or short colour", () => {
    expect((chatAccentStyle("#3B82F6") as Record<string, string>)["--chat-accent"]).toBe("#3b82f6");
  });

  it("sets nothing for a missing or unreadable colour, so the app accent stays", () => {
    for (const bad of [undefined, null, "", "blue", "#12", "rgb(0,0,0)"]) expect(chatAccentStyle(bad)).toEqual({});
  });
});
