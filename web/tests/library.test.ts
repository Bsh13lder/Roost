import { describe, expect, it } from "vitest";
import { groupLibrary, libraryItems } from "../src/lib/library";
import type { DocumentOut, LinkOut, MadeOut, NoteSummaryOut } from "../src/api/types";

const NOW = new Date("2026-10-23T12:00:00Z");

const doc = (id: string, title: string, at: string) =>
  ({ id, title, kind: "doc", tainted: false, created_at: at, updated_at: at }) as unknown as DocumentOut;
const note = (id: string, title: string, at: string) =>
  ({ id, title, tainted: true, created_at: at, updated_at: at }) as unknown as NoteSummaryOut;
const link = (url: string, host: string, at: string): LinkOut => ({ url, host, message_id: "m", thread_id: "t", created_at: at });

const made = (documents: DocumentOut[], notes: NoteSummaryOut[]): MadeOut => ({ tasks: [], expenses: [], notes, documents });

describe("the bot's Library", () => {
  it("holds its documents, notes and links, newest first", () => {
    const items = libraryItems(
      made([doc("d1", "Report", "2026-10-20T10:00:00Z")], [note("n1", "Ideas", "2026-10-23T09:00:00Z")]),
      [link("https://shop.example/a?b=1", "shop.example", "2026-10-01T09:00:00Z")],
    );
    expect(items.map((item) => [item.kind, item.label])).toEqual([
      ["note", "Ideas"], ["document", "Report"], ["link", "shop.example"],
    ]);
    expect(items[0].tainted).toBe(true);
    expect(items[2]).toMatchObject({ external: true, href: "https://shop.example/a?b=1", detail: "/a?b=1" });
  });

  it("groups by Today, This week and Earlier on Madrid's days, leaving out empty groups", () => {
    const items = libraryItems(
      made([doc("d1", "Report", "2026-10-20T10:00:00Z"), doc("d2", "Old", "2026-09-01T10:00:00Z")],
        [note("n1", "Ideas", "2026-10-23T09:00:00Z")]),
      [],
    );
    expect(groupLibrary(items, NOW).map((group) => [group.title, group.items.map((item) => item.label)])).toEqual([
      ["Today", ["Ideas"]], ["This week", ["Report"]], ["Earlier", ["Old"]],
    ]);
    expect(groupLibrary([], NOW)).toEqual([]);
  });

  it("a time just after Madrid's midnight is today", () => {
    const items = libraryItems(made([doc("d1", "Late", "2026-10-22T22:30:00Z")], []), []);
    expect(groupLibrary(items, NOW)[0].title).toBe("Today");
  });
});
