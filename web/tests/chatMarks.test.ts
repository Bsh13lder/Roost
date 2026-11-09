import { describe, expect, it } from "vitest";
import { chatMarks, firstUnreadId } from "../src/lib/chatMarks";
import { makeMessage } from "./fixtures";

const NOW = new Date("2026-10-14T12:00:00Z");
const msg = (id: string, created_at: string, over: Parameters<typeof makeMessage>[0] = {}) =>
  makeMessage({ id, created_at, ...over });

describe("chatMarks", () => {
  it("puts a day line before the first message of each Madrid day", () => {
    const items = chatMarks([
      msg("a", "2026-10-13T09:00:00Z"), msg("b", "2026-10-13T10:00:00Z"), msg("c", "2026-10-14T09:00:00Z"),
    ], null, NOW);
    expect(items.map((item) => item.kind)).toEqual(["day", "message", "message", "day", "message"]);
    expect(items[0]).toMatchObject({ kind: "day", label: "Yesterday" });
    expect(items[3]).toMatchObject({ kind: "day", label: "Today" });
    expect(items[1]).toMatchObject({ kind: "message", dayStart: true });
    expect(items[2]).toMatchObject({ kind: "message", dayStart: false });
  });

  it("puts New above the first message after the seen time that is not yours", () => {
    const messages = [
      msg("a", "2026-10-14T09:00:00Z", { role: "bot" }),
      msg("b", "2026-10-14T10:00:00Z", { role: "user" }),
      msg("c", "2026-10-14T11:00:00Z", { role: "bot" }),
      msg("d", "2026-10-14T11:05:00Z", { role: "bot" }),
    ];
    expect(firstUnreadId(messages, "2026-10-14T09:30:00Z")).toBe("c");
    const items = chatMarks(messages, "2026-10-14T09:30:00Z", NOW);
    expect(items.map((item) => item.kind === "message" ? item.message.id : item.kind)).toEqual(["day", "a", "b", "new", "c", "d"]);
    expect(items.find((item) => item.kind === "new")).toMatchObject({ id: "new-c" });
  });

  it("puts New after the day line when the first unread message starts a day", () => {
    const items = chatMarks([msg("a", "2026-10-13T09:00:00Z"), msg("b", "2026-10-14T09:00:00Z")], "2026-10-13T10:00:00Z", NOW);
    expect(items.map((item) => item.kind)).toEqual(["day", "message", "day", "new", "message"]);
  });

  it("no New on a first visit, when nothing is new, or when only your messages are newer", () => {
    const messages = [msg("a", "2026-10-14T09:00:00Z"), msg("b", "2026-10-14T10:00:00Z", { role: "user" })];
    expect(chatMarks(messages, null, NOW).some((item) => item.kind === "new")).toBe(false);
    expect(chatMarks(messages, "2026-10-14T10:00:00Z", NOW).some((item) => item.kind === "new")).toBe(false);
    expect(chatMarks(messages, "2026-10-14T09:30:00Z", NOW).some((item) => item.kind === "new")).toBe(false);
    expect(firstUnreadId([msg("p", "2026-10-14T11:00:00Z", { seq: 0 })], "2026-10-14T09:00:00Z")).toBeNull();
  });

  it("a message with no readable time joins the day before", () => {
    const items = chatMarks([msg("a", "2026-10-14T09:00:00Z"), msg("b", "x")], null, NOW);
    expect(items.map((item) => item.kind)).toEqual(["day", "message", "message"]);
    expect(items[2]).toMatchObject({ dayStart: false });
  });

  it("an english_fix line is never the first unread message", () => {
    const messages = [
      msg("a", "2026-10-14T09:00:00Z", { role: "user" }),
      msg("f", "2026-10-14T10:00:00Z", { role: "activity", kind: "english_fix", body: "{}" }),
      msg("c", "2026-10-14T11:00:00Z", { role: "bot" }),
    ];
    expect(firstUnreadId(messages, "2026-10-14T09:30:00Z")).toBe("c");
    expect(firstUnreadId(messages.slice(0, 2), "2026-10-14T09:30:00Z")).toBeNull();
  });
});
