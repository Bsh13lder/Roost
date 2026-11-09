// @vitest-environment node
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { ruleDeclarations } from "./tokenScan";

// A visually hidden file input is focused from the keyboard, but its label is what the eye sees:
// the label has to show the focus ring (WCAG 2.4.7). jsdom has no :has(), so this reads the CSS.
const STYLES = fileURLToPath(new URL("../src/styles/", import.meta.url));
const css = readdirSync(STYLES).filter((file) => file.endsWith(".css")).map((file) => readFileSync(join(STYLES, file), "utf8")).join("\n");

const FILE_BUTTONS = [".avatar-studio__upload", ".presets__file"];

describe("the file buttons show a focus ring (redesign P1)", () => {
  it.each(FILE_BUTTONS)("%s outlines its label while its hidden input has keyboard focus", (label) => {
    const rule = ruleDeclarations(css, `${label}:has(input:focus-visible)`);
    expect(rule.get("outline")).toMatch(/^2px solid var\(--color-accent-strong\)$/);
    expect(rule.get("outline-offset")).toBeDefined();
  });
});
