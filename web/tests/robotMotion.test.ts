// @vitest-environment node
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// The ghosts (avatars v5) move only for a user with no reduced-motion preference: every animation
// declaration sits inside `@media (prefers-reduced-motion: no-preference)`, and inside `html:not(.calm)`
// (the Calm robots setting) too. The exceptions: the blink, which reduced motion keeps, and the rules that stop motion.
const STYLES = fileURLToPath(new URL("../src/styles/", import.meta.url));
const MOTION_QUERY = "prefers-reduced-motion: no-preference";
const CALM_GUARD = "html:not(.calm)";
const BLINK = /robot-blink\b|animation-(?:duration|delay|play-state)|animation:\s*none/;
const ANIMATION = /^\s*animation(-[a-z-]+)?\s*:/;

/** Every `animation…` declaration that is not inside the no-preference media query (blinks aside). */
function unguardedAnimations(css: string): string[] {
  const open: string[] = []; // the prelude of each block we are inside
  const found: string[] = [];
  let text = "";
  for (const char of css.replace(/\/\*[\s\S]*?\*\//g, "")) {
    if (char === "{") {
      open.push(text.trim());
      text = "";
    } else if (char === "}" || char === ";") {
      const guarded = open.some((prelude) => prelude.includes(MOTION_QUERY));
      if (ANIMATION.test(text) && !guarded && !BLINK.test(text)) {
        found.push(`${open[open.length - 1]} { ${text.trim()} }`);
      }
      text = "";
      if (char === "}") open.pop();
    } else {
      text += char;
    }
  }
  return found;
}

/** The prelude of every block at the top of the file (a rule's selector, an at-rule). */
function topLevelPreludes(css: string): string[] {
  const found: string[] = [];
  let depth = 0;
  let text = "";
  for (const char of css.replace(/\/\*[\s\S]*?\*\//g, "")) {
    if (char === "{") {
      if (depth === 0) found.push(text.trim());
      depth += 1;
      text = "";
    } else if (char === "}") {
      depth -= 1;
      text = "";
    } else if (depth === 0) {
      text += char;
    }
  }
  return found;
}

describe("robot motion", () => {
  it.each(["robot.css", "avatar.css"])("%s animates only when the user has no reduced-motion preference", (file) => {
    const css = readFileSync(`${STYLES}${file}`, "utf8");
    expect(css).toContain(MOTION_QUERY);
    expect(unguardedAnimations(css)).toEqual([]);
  });

  it("robot-keyframes.css only names the keyframes: nothing in it plays on its own", () => {
    const css = readFileSync(`${STYLES}robot-keyframes.css`, "utf8");
    expect(unguardedAnimations(css)).toEqual([]);
    expect(topLevelPreludes(css).filter((prelude) => !prelude.startsWith("@keyframes "))).toEqual([]);
    expect(topLevelPreludes(css).length).toBeGreaterThan(30);
  });

  it("robot.css keeps every motion but the blink behind the Calm robots guard too", () => {
    const css = readFileSync(`${STYLES}robot.css`, "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
    const rules = [...css.matchAll(/([^{}]+)\{([^{}]*animation[^{}]*)\}/g)];
    const unguarded = rules
      .filter(([, selector, body]) => !selector.includes(CALM_GUARD) && !BLINK.test(body) && !selector.trim().startsWith("@keyframes"))
      .map(([, selector]) => selector.trim());
    expect(unguarded).toEqual([]);
  });

  it("the guard sees an animation that is not inside the query", () => {
    const bad = ".robot .spin { animation: spin 1s linear infinite; }\n@media (prefers-reduced-motion: no-preference) { .a { animation: x 1s; } }";
    expect(unguardedAnimations(bad)).toEqual([".robot .spin { animation: spin 1s linear infinite }"]);
  });
});
