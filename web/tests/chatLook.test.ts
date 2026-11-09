// @vitest-environment node
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { formatChatTime, formatClock } from "../src/lib/chatTime";

// Audit finding 8 (redesign P2): in the chat, mono is for code only, never chips, times, dates or amounts,
// and every time is one 24-hour clock on Madrid time.
const STYLES = fileURLToPath(new URL("../src/styles/", import.meta.url));
const CHAT_STYLESHEETS = ["chat.css", "chat-dock.css", "chat-cards.css", "chat-sheet.css", "chat-steps.css", "team.css", "rooms.css", "markdown.css", "sidebar.css"];
// Code, and a Stuck card's full address, which is shown verbatim on purpose.
const CODE_SELECTOR = /\b(?:code|pre)\b|stuck-card__url/;
const COMMENT = /\/\*[\s\S]*?\*\//g;
const RULE = /([^{}]+)\{([^{}]*)\}/g;
const MONO = /font(?:-family)?\s*:[^;]*var\(--font-mono\)/;

function monoSelectors(css: string): string[] {
  return [...css.replace(COMMENT, "").matchAll(RULE)]
    .filter(([, , body]) => MONO.test(body))
    .map(([, selector]) => selector.trim());
}

describe("the chat's type and time (audit finding 8)", () => {
  it("uses mono only for code in the chat's stylesheets", () => {
    const found = CHAT_STYLESHEETS.flatMap((file) => monoSelectors(readFileSync(STYLES + file, "utf8"))
      .filter((selector) => !CODE_SELECTOR.test(selector))
      .map((selector) => `${file}: ${selector}`));
    expect(found).toEqual([]);
  });

  it("finds a mono rule when there is one (the scanner works)", () => {
    const css = ".a { font-family: var(--font-mono); }\n@media (x) {\n  .b code { font: var(--fs-label) var(--font-mono); }\n}";
    expect(monoSelectors(css)).toEqual([".a", ".b code"]);
  });

  it("says every message and chat-list time on one 24-hour Madrid clock", () => {
    expect(formatClock("2026-10-14T12:19:00Z")).toBe("14:19");
    expect(formatClock("2026-01-14T12:19:00Z")).toBe("13:19"); // winter time
    expect(formatChatTime("2026-10-14T12:19:00Z", new Date("2026-10-14T13:00:00Z"))).toBe(formatClock("2026-10-14T12:19:00Z"));
    expect(formatClock("not a time")).toBe("");
  });
});
