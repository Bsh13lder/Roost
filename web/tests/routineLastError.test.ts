import { describe, expect, it } from "vitest";
import { lastErrorLine } from "../src/components/routines/lastError";

// The account's zone in tests is Madrid (CEST on 2026-10-20: UTC+2).
const NOW = new Date("2026-10-20T12:00:00Z");

describe("a routine's last error (self-healing, 2026-11-10)", () => {
  it("names the kind in plain words with the time on the account's clock", () => {
    expect(lastErrorLine({ kind: "no_answer", at: "2026-10-20T10:40:00Z" }, NOW))
      .toBe("Couldn't check (computer didn't answer) · 12:40");
    expect(lastErrorLine({ kind: "no_room", at: "2026-10-20T10:40:00Z" }, NOW))
      .toBe("Couldn't check (no free computer) · 12:40");
    expect(lastErrorLine({ kind: "run_error", at: "2026-10-20T10:40:00Z" }, NOW)).toBe("Didn't finish · 12:40");
  });

  it("an older error shows its day, an unknown kind falls back, and no error is empty", () => {
    expect(lastErrorLine({ kind: "no_answer", at: "2026-10-18T10:40:00Z" }, NOW))
      .toBe("Couldn't check (computer didn't answer) · Sun 18 Oct 12:40");
    expect(lastErrorLine({ kind: "mystery", at: "2026-10-20T10:40:00Z" }, NOW)).toBe("Something went wrong · 12:40");
    expect(lastErrorLine(null, NOW)).toBe("");
    expect(lastErrorLine(undefined, NOW)).toBe("");
  });
});
