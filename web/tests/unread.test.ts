import { afterEach, describe, expect, it, vi } from "vitest";
import type { ChatRowOut } from "../src/api/types";
import { markSeen, readSeen, SEEN_STORAGE_KEY, unreadChats, writeSeen } from "../src/lib/unread";

const row = (id: string, last_at: string, from_you = false): ChatRowOut => ({
  kind: "bot", id, name: id, thread_id: null, preview: "hi", preview_kind: "text", from_you, last_at, tainted: false,
});

afterEach(() => { vi.restoreAllMocks(); localStorage.clear(); });

describe("unread chats (redesign P2)", () => {
  it("counts a chat seen for the first time as read, then dots it when a newer message comes", () => {
    const first = markSeen([row("a", "2026-10-14T10:00:00Z")], {}, null);
    expect(first).toEqual({ a: "2026-10-14T10:00:00Z" });
    const rows = [row("a", "2026-10-14T11:00:00Z")];
    expect(markSeen(rows, first, null)).toBe(first); // nothing new to remember
    expect([...unreadChats(rows, first, null)]).toEqual(["a"]);
  });

  it("never dots the chat you have open, nor one whose newest message is yours", () => {
    const seen = { a: "2026-10-14T10:00:00Z", b: "2026-10-14T10:00:00Z" };
    const rows = [row("a", "2026-10-14T11:00:00Z"), row("b", "2026-10-14T11:00:00Z", true)];
    expect([...unreadChats(rows, seen, "a")]).toEqual([]);
    expect(markSeen(rows, seen, "a")).toEqual({ a: "2026-10-14T11:00:00Z", b: "2026-10-14T11:00:00Z" });
  });

  it("remembers what you saw in this browser", () => {
    writeSeen({ a: "2026-10-14T10:00:00Z" });
    expect(readSeen()).toEqual({ a: "2026-10-14T10:00:00Z" });
  });

  // Review Focus 5: a private window, blocked site data, or a value another version left behind.
  it("starts fresh and never breaks when the browser refuses storage or holds garbage", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    localStorage.setItem(SEEN_STORAGE_KEY, "{not json");
    expect(readSeen()).toEqual({});
    localStorage.setItem(SEEN_STORAGE_KEY, JSON.stringify({ a: 42 }));
    expect(readSeen()).toEqual({});
    const refusing = {
      getItem: () => { throw new DOMException("denied", "SecurityError"); },
      setItem: () => { throw new DOMException("full", "QuotaExceededError"); },
    };
    expect(readSeen(refusing)).toEqual({});
    expect(() => writeSeen({ a: "2026-10-14T10:00:00Z" }, refusing)).not.toThrow();
    vi.spyOn(window, "localStorage", "get").mockImplementation(() => { throw new DOMException("denied", "SecurityError"); });
    expect(readSeen()).toEqual({});
    expect(() => writeSeen({ a: "2026-10-14T10:00:00Z" })).not.toThrow();
    expect(warn).toHaveBeenCalled();
  });
});
