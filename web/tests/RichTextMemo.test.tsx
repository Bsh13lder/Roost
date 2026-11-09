import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { MessageRow, type MessageRowProps } from "../src/components/MessageRow";
import { makeBot, makeMessage } from "./fixtures";

// Final-review fix: every live frame re-renders the open chat, and parsing every reply's markdown on each
// frame stalls a long thread. RichText is memoized on its two strings, so a settled reply is parsed once and
// only the reply whose text changed is drawn again. The renderer is wrapped to count its draws.
const draws = vi.hoisted(() => ({ count: 0 }));
vi.mock("../src/components/markdown/Markdown", async (importOriginal) => {
  const { createElement } = await import("react");
  const actual = await importOriginal<typeof import("../src/components/markdown/Markdown")>();
  return {
    default: (props: Parameters<typeof actual.default>[0]) => {
      draws.count += 1;
      return createElement(actual.default, props);
    },
  };
});

afterEach(() => cleanup());

const SCOUT = makeBot({ id: "bot-1", name: "Scout" });
const REPLY = makeMessage({ id: "r-1", author_bot_id: "bot-1", body: "**Done.** See [[Garden plan]]." });

function row(overrides: Partial<MessageRowProps> = {}) {
  const props: MessageRowProps = { message: REPLY, runStart: true, fallbackName: "Scout", team: [SCOUT], ...overrides };
  return <MemoryRouter><ul><MessageRow {...props} /></ul></MemoryRouter>;
}

describe("RichText re-renders (final-review fix)", () => {
  it("skips a reply whose text is unchanged when its row re-renders with new objects", async () => {
    const { rerender } = render(row());
    expect((await screen.findByText("Done.")).tagName).toBe("STRONG");
    const drawn = draws.count;
    // What a live frame does: a new message object, a new team array, a new run start.
    rerender(row({ message: { ...REPLY }, team: [{ ...SCOUT }] }));
    rerender(row({ message: { ...REPLY }, team: [SCOUT], runStart: false }));
    expect(draws.count).toBe(drawn);
    expect(screen.getByText("Garden plan")).toHaveClass("wikilink-chip");
  });

  it("draws a reply again when its text changes, as it streams", async () => {
    const writing = makeMessage({ id: "r-2", author_bot_id: "bot-1", body: "", seq: 0 });
    const { rerender } = render(row({ message: writing, liveText: "**Here**" }));
    await screen.findByText("Here");
    const drawn = draws.count;
    rerender(row({ message: { ...writing }, liveText: "**Here** is" }));
    expect(draws.count).toBe(drawn + 1);
    rerender(row({ message: { ...writing }, liveText: "**Here** is" }));
    expect(draws.count).toBe(drawn + 1);
  });
});
