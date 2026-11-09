import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ACCENTS, ACCENT_KEY, DEFAULT_ACCENT, applyAccent, readAccent, saveAccent } from "../src/lib/accent";
import { contrastRatio, readTokens, resolveToken } from "./tokenScan";

const TOKENS_CSS = readFileSync(join(process.cwd(), "src/styles/tokens.css"), "utf8");
const BASE = readTokens(TOKENS_CSS);
const SURFACES = ["--color-bg", "--color-panel", "--color-raised", "--color-overlay"];

// The accent's own block in tokens.css: :root[data-accent="<id>"] { … }.
function accentBlock(id: string): Map<string, string> {
  const block = TOKENS_CSS.split(`:root[data-accent="${id}"] {`)[1]?.split("\n}")[0] ?? "";
  return new Map([...block.matchAll(/(--[\w-]+):\s*([^;]+);/g)].map((match) => [match[1], match[2].trim()]));
}

afterEach(() => { vi.restoreAllMocks(); localStorage.clear(); delete document.documentElement.dataset.accent; });

describe("the accent colour (restructure slice 3)", () => {
  it("offers the phone's six accents, violet first", () => {
    expect(ACCENTS.map((accent) => accent.id)).toEqual(["violet", "blue", "teal", "green", "orange", "pink"]);
    expect(DEFAULT_ACCENT).toBe("violet");
  });

  it("remembers the choice in this browser, and reads an unknown or missing one as violet", () => {
    expect(readAccent()).toBe("violet");
    saveAccent("teal");
    expect(localStorage.getItem(ACCENT_KEY)).toBe("teal");
    expect(readAccent()).toBe("teal");
    localStorage.setItem(ACCENT_KEY, "plaid");
    expect(readAccent()).toBe("violet");
  });

  it("works with no site data: a blocked store reads violet and a save does not throw", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
    vi.spyOn(console, "warn").mockImplementation(() => undefined);
    expect(readAccent()).toBe("violet");
    expect(() => saveAccent("pink")).not.toThrow();
  });

  it("applies through data-accent on the page root, violet being the tokens' own", () => {
    applyAccent("orange");
    expect(document.documentElement.dataset.accent).toBe("orange");
    applyAccent("violet");
    expect(document.documentElement.dataset.accent).toBeUndefined();
  });

  it("each other accent overrides the accent tokens, keeping white on its fill and its text readable", () => {
    for (const { id } of ACCENTS.filter((accent) => accent.id !== DEFAULT_ACCENT)) {
      const block = accentBlock(id);
      for (const token of ["--color-accent", "--color-accent-hover", "--color-accent-strong", "--color-accent-soft", "--color-accent-tint", "--color-accent-edge"]) {
        expect(block.has(token), `${id} ${token}`).toBe(true);
      }
      const white = resolveToken(BASE, "--color-on-accent");
      for (const fill of ["--color-accent", "--color-accent-hover"]) {
        expect(contrastRatio(white, block.get(fill)!), `${id} ${fill}`).toBeGreaterThanOrEqual(4.5);
      }
      for (const surface of SURFACES) {
        expect(contrastRatio(block.get("--color-accent-strong")!, resolveToken(BASE, surface)), `${id} on ${surface}`)
          .toBeGreaterThanOrEqual(4.5);
      }
    }
  });
});
