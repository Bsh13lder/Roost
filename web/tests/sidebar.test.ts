import { describe, expect, it } from "vitest";
import { avatarRow, chatSections, usedLabels } from "../src/lib/sidebar";
import type { BotOut, ChatRowOut } from "../src/api/types";
import { makeBot } from "./fixtures";

function row(id: string, name: string, lastAt: string, kind: ChatRowOut["kind"] = "bot", preview = "hello"): ChatRowOut {
  return { kind, id, name, thread_id: null, preview, preview_kind: "text", from_you: false, last_at: lastAt, tainted: false };
}

function byId(...bots: BotOut[]): Record<string, BotOut> {
  return Object.fromEntries(bots.map((bot) => [bot.id, bot]));
}

const star = makeBot({ id: "m", name: "Chief", is_primary: true });
const scout = makeBot({ id: "s", name: "Scout", group: "Work" });
const quill = makeBot({ id: "q", name: "Quill", group: "Work" });
const mole = makeBot({ id: "o", name: "Mole" });

describe("chatSections", () => {
  it("puts ungrouped bots and rooms first (the main bot is pinned, so it is not here)", () => {
    const rows = [
      row("o", "Mole", "2026-10-20T10:00:00Z"),
      row("r1", "Trip", "2026-10-20T09:00:00Z", "room"),
      row("m", "Chief", "2026-10-20T08:00:00Z"),
      row("s", "Scout", "2026-10-20T07:00:00Z"),
    ];
    const sections = chatSections(rows, byId(star, scout, mole), "");
    expect(sections.map((s) => s.label)).toEqual([null, "Work"]);
    expect(sections[0].rows.map((r) => r.id)).toEqual(["o", "r1"]);
    expect(sections[1].rows.map((r) => r.id)).toEqual(["s"]);
  });

  it("makes one section per label, sorted by label, each newest first", () => {
    const home = makeBot({ id: "h", name: "Homer", group: "Home" });
    const rows = [
      row("s", "Scout", "2026-10-20T10:00:00Z"),
      row("h", "Homer", "2026-10-20T09:00:00Z"),
      row("q", "Quill", "2026-10-20T08:00:00Z"),
    ];
    const sections = chatSections(rows, byId(scout, quill, home), "");
    expect(sections.map((s) => s.label)).toEqual(["Home", "Work"]);
    expect(sections[1].rows.map((r) => r.id)).toEqual(["s", "q"]);
  });

  it("keeps a label's spelling as typed and sorts without regard to case", () => {
    const a = makeBot({ id: "a", name: "A", group: "work" });
    const b = makeBot({ id: "b", name: "B", group: "Alpha" });
    const c = makeBot({ id: "c", name: "C", group: " Work " });
    const rows = [row("a", "A", "2026-10-20T10:00:00Z"), row("b", "B", "2026-10-20T09:00:00Z"), row("c", "C", "2026-10-20T08:00:00Z")];
    const sections = chatSections(rows, byId(a, b, c), "");
    expect(sections.map((s) => s.label)).toEqual(["Alpha", "work", "Work"]);
  });

  it("drops a section that search empties", () => {
    const rows = [row("o", "Mole", "2026-10-20T10:00:00Z"), row("s", "Scout", "2026-10-20T09:00:00Z")];
    const sections = chatSections(rows, byId(mole, scout), "scout");
    expect(sections.map((s) => s.label)).toEqual(["Work"]);
  });

  it("shows a bot's live name", () => {
    const renamed = makeBot({ id: "o", name: "Moley" });
    const sections = chatSections([row("o", "Mole", "2026-10-20T10:00:00Z")], byId(renamed), "");
    expect(sections[0].rows[0].name).toBe("Moley");
  });
});

describe("avatarRow", () => {
  it("is the main bot first, then the pinned bots in pin order", () => {
    const a = makeBot({ id: "a", name: "A", pinned: true, pinned_at: "2026-10-20T09:00:00Z" });
    const b = makeBot({ id: "b", name: "B", pinned: true, pinned_at: "2026-10-20T08:00:00Z" });
    expect(avatarRow([a, b, mole, star]).map((bot) => bot.id)).toEqual(["m", "b", "a"]);
  });

  it("holds only the main bot while nothing is pinned", () => {
    expect(avatarRow([star, mole, scout]).map((bot) => bot.id)).toEqual(["m"]);
  });

  it("counts the main bot as pinned even if the flag is missing", () => {
    expect(avatarRow([makeBot({ id: "m", is_primary: true, pinned: false })]).map((bot) => bot.id)).toEqual(["m"]);
  });

  it("works without a main bot", () => {
    expect(avatarRow([makeBot({ id: "s", pinned: true, pinned_at: "x" })]).map((bot) => bot.id)).toEqual(["s"]);
  });
});

describe("pinned bots and the chat list", () => {
  const pinnedMole = makeBot({ id: "o", name: "Mole", pinned: true, pinned_at: "x" });
  const rows = [row("o", "Mole", "2026-10-20T10:00:00Z"), row("m", "Chief", "2026-10-20T09:00:00Z"), row("s", "Scout", "2026-10-20T08:00:00Z")];

  it("leaves pinned bots, and the main bot, out of the sections", () => {
    const sections = chatSections(rows, byId(star, pinnedMole, scout), "");
    expect(sections.flatMap((s) => s.rows.map((r) => r.id))).toEqual(["s"]);
  });

  it("finds a pinned bot again when you search", () => {
    const sections = chatSections(rows, byId(star, pinnedMole, scout), "mole");
    expect(sections.flatMap((s) => s.rows.map((r) => r.id))).toEqual(["o"]);
  });

  it("keeps rooms", () => {
    const sections = chatSections([...rows, row("r1", "Trip", "x", "room")], byId(star, pinnedMole, scout), "");
    expect(sections.flatMap((s) => s.rows.map((r) => r.id))).toContain("r1");
  });
});

describe("usedLabels", () => {
  it("lists the labels the other bots use, once each, sorted", () => {
    const home = makeBot({ id: "h", name: "Homer", group: "Home" });
    const bots = [scout, quill, home, mole];
    expect(usedLabels(bots)).toEqual(["Home", "Work"]);
    expect(usedLabels(bots, "h")).toEqual(["Work"]);
    expect(usedLabels(bots, "s")).toEqual(["Home", "Work"]);
  });
});
