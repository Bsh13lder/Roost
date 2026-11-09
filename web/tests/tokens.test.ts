// @vitest-environment node
import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  componentLiterals, contrastRatio, definedVariables, hardCodedColours, hardCodedFontSizes, readTokens, resolveToken,
  ruleDeclarations, usedVariables,
} from "./tokenScan";

// Look & feel redesign P1: tokens.css is the one place for colours and font sizes.
const SRC = fileURLToPath(new URL("../src/", import.meta.url));
const TOKEN_FILE = "styles/tokens.css";
// Colour data, not styling: the swatches a user picks from. Nothing else in web/src may hold a colour.
const COLOUR_DATA_FILES = ["components/projects/projects.ts", "components/robot/palette.ts"];

const TOKEN_NAMES = [
  "--color-bg", "--color-panel", "--color-raised", "--color-overlay", "--color-sunken", "--color-scrim",
  "--color-text", "--color-text-secondary", "--color-text-faint", "--color-border", "--color-border-strong",
  "--color-accent", "--color-accent-hover", "--color-accent-strong", "--color-accent-soft", "--color-accent-tint",
  "--color-accent-edge", "--color-on-accent", "--color-selection",
  "--color-ok", "--color-warn", "--color-danger", "--color-danger-text", "--color-danger-tint", "--color-danger-edge", "--color-ok-tint", "--color-warn-tint", "--board-width",
  "--color-info", "--color-off",
  "--status-on-it", "--status-asking", "--status-stuck", "--status-off",
  "--lens-visor", "--lens-lid-edge", "--lens-ink", "--lens-pupil", "--lens-sclera-top", "--lens-sclera-mid",
  "--lens-sclera", "--lens-highlight", "--lens-z", "--lens-shadow", "--robot-star", "--robot-star-mark",
  "--space-1", "--space-2", "--space-3", "--space-4", "--space-5", "--space-6", "--space-8", "--space-12",
  "--radius-xs", "--radius-sm", "--radius-md", "--radius-lg", "--radius-pill",
  "--font-sans", "--font-mono",
  "--fs-caption", "--fs-label", "--fs-body", "--fs-lead", "--fs-heading", "--fs-title", "--fs-display",
  "--control-sm", "--control-md", "--control-lg",
  "--shadow-sm", "--shadow-md", "--shadow-lg",
  "--ease-standard", "--duration-fast", "--duration-base", "--duration-slow",
  "--focus-ring",
  "--fs-menu", "--control-item", "--pad-item", "--edge-inner", "--color-hover", "--icon-size", "--gap-tight",
];
// Cozy kit (Section B of docs/design/robots-v2-sketch.html): the proposed values, pinned.
const COZY: Record<string, string> = {
  "--fs-menu": "0.8125rem", "--control-item": "30px", "--control-md": "32px", "--pad-item": "8px",
  "--radius-sm": "8px", "--radius-md": "12px", "--color-overlay": "#1d1d24",
  "--edge-inner": "inset 0 0 0 1px rgb(255 255 255 / 0.06)", "--color-hover": "rgb(255 255 255 / 0.07)",
  "--icon-size": "16px", "--gap-tight": "var(--space-1)", "--color-accent": "#6c5ce0",
  "--color-accent-hover": "#6152cf", "--color-accent-strong": "#b2a6f6",
  "--color-accent-tint": "rgb(108 92 224 / 0.16)",
  "--shadow-lg": "0 0 0 1px rgb(0 0 0 / 0.5), 0 2px 4px rgb(0 0 0 / 0.18), 0 8px 16px rgb(0 0 0 / 0.22), 0 20px 40px rgb(0 0 0 / 0.28)",
};
const SURFACES = ["--color-bg", "--color-panel", "--color-raised", "--color-overlay"];
const TEXT_COLOURS = [
  "--color-text", "--color-text-secondary", "--color-text-faint", "--color-accent-strong", "--color-accent-soft",
  "--color-ok", "--color-warn", "--color-danger", "--color-danger-text", "--color-info", "--color-off",
  "--status-on-it", "--status-asking", "--status-stuck", "--status-off",
];
const READABLE = 4.5;
// WCAG 1.4.11: the part of a control that shows its state needs 3:1 against what it sits on.
const VISIBLE = 3;
const OVERLAYS_CSS = "styles/ui-overlays.css";
const HIGHLIGHTED_ITEMS = [".select__item[data-highlighted]", ".menu__item[data-highlighted]"];
// Set by Radix on its own popper elements at run time (the select's width and room to grow).
// And the chat's accent variables, set on the chat container from the bot's colour (lib/chatAccent.ts);
// every use falls back to the app accent.
const RUNTIME_VARIABLE = /^--(radix-|chat-)/;

function filesUnder(dir: string, extensions: readonly string[]): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return filesUnder(path, extensions);
    return extensions.some((extension) => entry.name.endsWith(extension)) ? [path] : [];
  });
}

const name = (path: string) => relative(SRC, path);
const read = (path: string) => readFileSync(path, "utf8");
const stylesheets = filesUnder(SRC, [".css"]);
const components = filesUnder(SRC, [".ts", ".tsx"]);
const tokens = readTokens(read(join(SRC, TOKEN_FILE)));

describe("design tokens (redesign P1)", () => {
  it("defines every token the design names", () => {
    expect(TOKEN_NAMES.filter((token) => !tokens.has(token))).toEqual([]);
  });

  it("keeps hard-coded colours out of every stylesheet but the token file", () => {
    const found = stylesheets.filter((path) => name(path) !== TOKEN_FILE)
      .flatMap((path) => hardCodedColours(read(path)).map(({ line, value }) => `${name(path)}:${line} ${value}`));
    expect(found).toEqual([]);
  });

  it("keeps hard-coded font sizes out of every stylesheet", () => {
    const found = stylesheets.filter((path) => name(path) !== TOKEN_FILE)
      .flatMap((path) => hardCodedFontSizes(read(path)).map(({ line, value }) => `${name(path)}:${line} ${value}`));
    expect(found).toEqual([]);
  });

  it("keeps colour literals and font sizes out of components", () => {
    const allowed = new Set(COLOUR_DATA_FILES);
    const found = components.filter((path) => !allowed.has(name(path)))
      .flatMap((path) => componentLiterals(read(path)).map(({ line, text }) => `${name(path)}:${line} ${text}`));
    expect(found).toEqual([]);
  });

  it("uses only CSS variables that a stylesheet defines", () => {
    const defined = new Set(stylesheets.flatMap((path) => [...definedVariables(read(path))]));
    const used = [...stylesheets, ...components].flatMap((path) => [...usedVariables(read(path))].map((v) => `${name(path)} ${v}`));
    const unknown = used.filter((entry) => {
      const variable = entry.split(" ")[1];
      return !defined.has(variable) && !RUNTIME_VARIABLE.test(variable);
    });
    expect(unknown).toEqual([]);
  });

  it("keeps every text colour at 4.5:1 or more on every surface", () => {
    const low = TEXT_COLOURS.flatMap((text) => SURFACES.flatMap((surface) => {
      const ratio = contrastRatio(resolveToken(tokens, text), resolveToken(tokens, surface));
      return ratio < READABLE ? [`${text} on ${surface}: ${ratio.toFixed(2)}`] : [];
    }));
    const onAccent = ["--color-accent", "--color-accent-hover"].flatMap((fill) => {
      const ratio = contrastRatio(resolveToken(tokens, "--color-on-accent"), resolveToken(tokens, fill));
      return ratio < READABLE ? [`--color-on-accent on ${fill}: ${ratio.toFixed(2)}`] : [];
    });
    expect([...low, ...onAccent]).toEqual([]);
  });

  it("pins the cozy kit's token values", () => {
    const css = read(join(SRC, TOKEN_FILE));
    const wrong = Object.entries(COZY).flatMap(([token, value]) => {
      const found = new RegExp(`${token}:\\s*([^;]+);`).exec(css)?.[1]?.trim();
      return found === value ? [] : [`${token}: ${found}`];
    });
    expect(wrong).toEqual([]);
  });

  it("paints the highlighted Select and Menu item with a hover fill, not an outline", () => {
    const css = read(join(SRC, OVERLAYS_CSS));
    const found = HIGHLIGHTED_ITEMS.flatMap((selector) => {
      const rule = ruleDeclarations(css, selector);
      const bad: string[] = [];
      if (rule.get("background") !== "var(--color-hover)") bad.push(`${selector} background`);
      if (rule.get("color") !== "var(--color-text)") bad.push(`${selector} color`);
      if (rule.has("box-shadow")) bad.push(`${selector} has an outline`);
      return bad;
    });
    expect(found).toEqual([]);
  });

  it("keeps the text readable on a hovered item", () => {
    const overlay = resolveToken(tokens, "--color-overlay");
    // white at 0.07 over the overlay, about #2a2a30
    const lifted = "#2a2a31";
    expect(contrastRatio(resolveToken(tokens, "--color-text"), lifted)).toBeGreaterThanOrEqual(READABLE);
    expect(contrastRatio(resolveToken(tokens, "--color-text"), overlay)).toBeGreaterThanOrEqual(READABLE);
  });

  it("keeps the tick of a chosen Select option readable on the highlighted item", () => {
    const css = read(join(SRC, OVERLAYS_CSS));
    const fill = resolveToken(tokens, "--color-accent");
    const check = ruleDeclarations(css, ".select__item[data-highlighted] .select__check").get("color");
    expect(check).toBe("inherit");
    expect(contrastRatio(resolveToken(tokens, "--color-on-accent"), fill)).toBeGreaterThanOrEqual(READABLE);
  });

  it("catches a new hard-coded colour, font size or unknown variable (the scanner works)", () => {
    const css = ".x {\n  color: #fff;\n  background: rgb(0 0 0 / 0.5);\n  font-size: 13px;\n  font: 600 14px var(--font-sans);\n}";
    expect(hardCodedColours(css).map(({ line }) => line)).toEqual([2, 3]);
    expect(hardCodedFontSizes(css).map(({ line }) => line)).toEqual([4, 5]);
    expect(componentLiterals('const a = "#10b981";\n<text fontSize={11} />\n&#8230;').map(({ line }) => line)).toEqual([1, 2]);
    expect([...usedVariables("a { color: var(--nope); }")]).toEqual(["--nope"]);
    expect(contrastRatio("#ffffff", "#000000")).toBeCloseTo(21, 5);
  });
});
