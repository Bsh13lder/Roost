import { describe, expect, it } from "vitest";
import { fitsOnOneLine } from "../src/lib/botProfile";
import { checkGroup, checkJob, checkName } from "../src/lib/botFields";

describe("bot fields", () => {
  it("a name or job must fit on one line", () => {
    expect(fitsOnOneLine("HiMap SEO · v2")).toBe(true);
    for (const bad of ["a\nb", "a\tb", "a b", "a\u0085b"]) expect(fitsOnOneLine(bad)).toBe(false);
  });
  it("checks names and jobs the way the server does", () => {
    expect(checkName("HiMap SEO")).toBeNull();
    expect(checkName(" spaced")).not.toBeNull();
    expect(checkName("x".repeat(41))).not.toBeNull();
    expect(checkJob("")).toBe("Say in one line what this bot does.");
    expect(checkJob("a\nb")).toBe("Keep the job to one line of up to 200 characters.");
  });
  it("checks a group label: one line, at most 30 characters, blank clears", () => {
    expect(checkGroup("Work")).toBeNull();
    expect(checkGroup("   ")).toBeNull();
    expect(checkGroup("")).toBeNull();
    expect(checkGroup("x".repeat(30))).toBeNull();
    expect(checkGroup("a\nb")).toBe("A label fits on one line.");
    expect(checkGroup("x".repeat(31))).toBe("A label is at most 30 characters.");
  });
});
