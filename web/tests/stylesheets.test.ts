// The stylesheet guard (polish R1): every file in styles/ stays within 800 lines, the entry imports each
// exactly once, and the chat and profile files stay split by feature.
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const STYLES = join(__dirname, "..", "src", "styles");
const ENTRY = join(__dirname, "..", "src", "styles.css");
const MAX_LINES = 800;
const FOCUSED = { "chat.css": 450, "profile.css": 500 } as const;
// calendar.css loads with the lazy Calendar chunk (ui/date/Calendar.tsx), board-calendar.css with the lazy
// task and money calendars (board/calendar/CalendarGrid.tsx): neither goes through the entry.
// plan.css loads with the lazy Plan tab (plan/PlanView.tsx), calendar-marks.css with the phone task calendar.
const LAZY = ["calendar.css", "board-calendar.css", "calendar-marks.css", "plan.css"];
const SPLIT_FILES = ["chat-dock.css", "chat-cards.css", "chat-sheet.css", "instructions.css"];

const files = readdirSync(STYLES).filter((name) => name.endsWith(".css"));
const lines = (name: string): number => readFileSync(join(STYLES, name), "utf8").split("\n").length;

describe("stylesheets", () => {
  it("keeps every stylesheet within 800 lines", () => {
    const tooLong = files.filter((name) => lines(name) > MAX_LINES);
    expect(tooLong).toEqual([]);
  });

  it("imports every stylesheet in styles/ exactly once", () => {
    const entry = readFileSync(ENTRY, "utf8");
    const imported = [...entry.matchAll(/@import "\.\/styles\/([\w-]+\.css)";/g)].map((m) => m[1]);
    expect([...imported].sort()).toEqual(files.filter((name) => !LAZY.includes(name)).sort());
    expect(new Set(imported).size).toBe(imported.length);
  });

  it("keeps the chat and profile stylesheets focused", () => {
    for (const name of SPLIT_FILES) expect(files).toContain(name);
    for (const [name, max] of Object.entries(FOCUSED)) expect(lines(name)).toBeLessThanOrEqual(max);
  });

  it("keeps a popover inside the screen: it scrolls within the height Radix leaves it", () => {
    const css = readFileSync(join(STYLES, "ui-overlays.css"), "utf8");
    const rules = [...css.matchAll(/\n\.popover \{([^}]*)\}/g)].map((m) => m[1]);
    expect(rules.some((body) => /max-height:\s*var\(--radix-popover-content-available-height/.test(body)
      && /overflow-y:\s*auto/.test(body))).toBe(true);
  });

  it("keeps the cozy menu rules: 13px, item padding and radius from tokens", () => {
    const css = readFileSync(join(STYLES, "ui-overlays.css"), "utf8");
    const item = /\n\.select__item,\n\.menu__item \{([^}]*)\}/.exec(css)?.[1] ?? "";
    expect(item).toMatch(/min-height:\s*var\(--control-item\)/);
    expect(item).toMatch(/padding:\s*0 var\(--pad-item\)/);
    expect(item).toMatch(/font-size:\s*var\(--fs-menu\)/);
    expect(item).toMatch(/border-radius:\s*var\(--radius-sm\)/);
    const surface = /\n\.select__content,\n\.menu__list,\n\.popover \{([^}]*)\}/.exec(css)?.[1] ?? "";
    expect(surface).toMatch(/border-radius:\s*var\(--radius-md\)/);
    expect(surface).toMatch(/var\(--edge-inner\)/);
    expect(surface).not.toMatch(/border:/);
  });
});
