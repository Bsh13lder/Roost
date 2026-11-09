import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { formatClock } from "../src/lib/chatTime";
import { todayIn, wallText } from "../src/ui/date/dates";
import {
  appTimeZone, browserTimeZone, isTimeZone, setAppTimeZone, supportedTimeZones, zoneCity,
} from "../src/lib/timeZone";

const ZONE_MODULE = join("src", "lib", "timeZone.ts"); // the one place that builds a format on another zone

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sources(path);
    return /\.(ts|tsx)$/.test(name) ? [path] : [];
  });
}

// The text of each call, from its opening parenthesis to the matching close, and what follows it.
function calls(text: string, pattern: RegExp): { call: string; after: string }[] {
  const found: { call: string; after: string }[] = [];
  for (const match of text.matchAll(pattern)) {
    let depth = 0;
    let end = (match.index ?? 0) + match[0].length - 1;
    for (; end < text.length; end += 1) {
      if (text[end] === "(") depth += 1;
      if (text[end] === ")" && --depth === 0) break;
    }
    found.push({ call: text.slice(match.index, end + 1), after: text.slice(end + 1, end + 20) });
  }
  return found;
}

// A format is on the account's zone, or on UTC for a bare day already reckoned (no clock, no zone).
const ON_ACCOUNT_ZONE = /timeZone:\s*(appTimeZone\(\)|"UTC")/;

afterEach(() => { setAppTimeZone("Europe/Madrid"); });

describe("the account's time zone", () => {
  it("every date or time format in web/src passes appTimeZone()", () => {
    const bad: string[] = [];
    for (const file of sources(join(__dirname, "../src"))) {
      if (file.endsWith(ZONE_MODULE)) continue;
      const text = readFileSync(file, "utf8");
      for (const { call, after } of calls(text, /(toLocaleTimeString|toLocaleDateString|toLocaleString|Intl\.DateTimeFormat)\(/g)) {
        if (after.startsWith(".resolvedOptions()")) continue;
        if (!ON_ACCOUNT_ZONE.test(call)) bad.push(`${file}: ${call.slice(0, 60)}`);
      }
    }
    expect(bad).toEqual([]);
  });

  it("no zone is written into web/src", () => {
    const bad = sources(join(__dirname, "../src")).filter((file) => /"Europe\/Madrid"/.test(readFileSync(file, "utf8")));
    expect(bad).toEqual([]);
  });

  it("the message time is just the clock", () => {
    expect(formatClock("2026-10-21T12:19:00Z")).toBe("14:19"); // CEST
    expect(formatClock("2026-01-21T12:19:00Z")).toBe("13:19"); // CET
    expect(formatClock("nope")).toBe("");
  });

  it("formats follow a zone that is not Madrid", () => {
    expect(setAppTimeZone("America/New_York")).toBe(true);
    expect(appTimeZone()).toBe("America/New_York");
    expect(formatClock("2026-10-21T12:19:00Z")).toBe("08:19");
    expect(wallText("2026-10-21T02:00:00Z")).toBe("2026-10-20 22:00");
    expect(todayIn(new Date("2026-10-21T02:00:00Z"))).toBe("2026-10-20");
    setAppTimeZone("Asia/Tokyo");
    expect(formatClock("2026-10-21T12:19:00Z")).toBe("21:19");
  });

  it("refuses a zone the browser does not know", () => {
    expect(setAppTimeZone("Mars/Olympus")).toBe(false);
    expect(appTimeZone()).toBe("Europe/Madrid");
    expect(isTimeZone("")).toBe(false);
    expect(isTimeZone(42)).toBe(false);
    expect(isTimeZone("UTC")).toBe(true);
  });

  it("names a zone by its city", () => {
    expect(zoneCity("America/New_York")).toBe("New York");
    expect(zoneCity("America/Argentina/Buenos_Aires")).toBe("Buenos Aires");
    expect(zoneCity("UTC")).toBe("UTC");
  });

  it("lists the zones with the ones it must keep", () => {
    const zones = supportedTimeZones(["Etc/Unknown-Kept"]);
    expect(zones).toContain("Etc/Unknown-Kept");
    expect([...zones].sort()).toEqual(zones);
    expect(isTimeZone(browserTimeZone())).toBe(true);
  });
});
