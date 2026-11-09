import { describe, expect, it } from "vitest";
import { stillQueued } from "../src/lib/queued";
import { makeMessage } from "./fixtures";

const mine = makeMessage({ id: "u1", role: "user", created_at: "2026-10-22T10:00:10Z", seq: 2 });
const running = makeMessage({ id: "b0", role: "bot", created_at: "2026-10-22T10:00:00Z", seq: 0 });
const answer = makeMessage({ id: "b1", role: "bot", created_at: "2026-10-22T10:00:30Z", seq: 3 });

describe("stillQueued", () => {
  it("a queued message stays queued until a bot message follows it", () => {
    const ids = new Set(["u1"]);
    expect(stillQueued([mine], ids).has("u1")).toBe(true);
    // the reply already being written when you sent it does not count
    expect(stillQueued([running, mine], ids).has("u1")).toBe(true);
    expect(stillQueued([mine, answer], ids).has("u1")).toBe(false);
  });

  it("a new set each time", () => {
    const ids = new Set(["u1"]);
    const next = stillQueued([mine, answer], ids);
    expect(next).not.toBe(ids);
    expect(ids.has("u1")).toBe(true);
    expect(stillQueued([mine], ids)).not.toBe(ids);
  });
});
