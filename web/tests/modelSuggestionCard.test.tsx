import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ModelSuggestionCard } from "../src/components/ModelSuggestionCard";
import { parseModelSuggestion } from "../src/lib/models";
import { makeBot } from "./fixtures";

const CARD = { bot_id: "b1", bot: "Daily Tasks", model: "opus-id", label: "Opus 5.5", effort: null, reason: "Planning needs deeper thought." };

function stubPut() {
  const put = vi.fn();
  vi.stubGlobal("fetch", vi.fn(async (_url: string, init?: RequestInit) => {
    put(String(_url), JSON.parse(String(init?.body)));
    return new Response(JSON.stringify(makeBot()), { status: 200 });
  }));
  return put;
}

beforeEach(() => window.localStorage.clear());
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("ModelSuggestionCard", () => {
  it('the card asks "Switch Daily Tasks to Opus 5.5?" with the reason', () => {
    render(<ModelSuggestionCard messageId="m1" suggestion={CARD} />);
    expect(screen.getByText("Switch Daily Tasks to Opus 5.5?")).toBeInTheDocument();
    expect(screen.getByText("Planning needs deeper thought.")).toBeInTheDocument();
  });

  it("Switch calls PUT and the card shows Switched", async () => {
    const put = stubPut();
    render(<ModelSuggestionCard messageId="m1" suggestion={CARD} />);
    await userEvent.click(screen.getByRole("button", { name: "Switch" }));
    expect(await screen.findByText("Switched Daily Tasks to Opus 5.5")).toBeInTheDocument();
    expect(put).toHaveBeenCalledWith("/api/bots/b1/model", { model: "opus-id", effort: null });
  });

  it("shows a plain error and stays when the switch fails", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "That model isn't available." }), { status: 422 })));
    render(<ModelSuggestionCard messageId="m1" suggestion={CARD} />);
    await userEvent.click(screen.getByRole("button", { name: "Switch" }));
    expect(await screen.findByText("That model isn't available.")).toBeInTheDocument();
  });

  it("Not now hides it in this browser", async () => {
    const { unmount } = render(<ModelSuggestionCard messageId="m1" suggestion={CARD} />);
    await userEvent.click(screen.getByRole("button", { name: "Not now" }));
    expect(screen.queryByText("Switch Daily Tasks to Opus 5.5?")).toBeNull();
    unmount();
    render(<ModelSuggestionCard messageId="m1" suggestion={CARD} />);
    expect(screen.queryByText("Switch Daily Tasks to Opus 5.5?")).toBeNull();
  });

  it("a tainted card shows the outside-content mark", () => {
    render(<ModelSuggestionCard messageId="m1" suggestion={CARD} tainted />);
    expect(screen.getByText("This run read outside content.")).toBeInTheDocument();
  });

  it("parses only a complete body", () => {
    expect(parseModelSuggestion(JSON.stringify(CARD))).toEqual(CARD);
    expect(parseModelSuggestion(JSON.stringify({ ...CARD, effort: "extreme" }))).toBeNull();
    expect(parseModelSuggestion("nope")).toBeNull();
  });
});
