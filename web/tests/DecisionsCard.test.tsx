import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DecisionsCard } from "../src/components/profile/DecisionsCard";
import type { MemoryOut } from "../src/api/types";

const api = { listMemories: vi.fn(), forgetMemory: vi.fn() };
vi.mock("../src/api/memories", () => ({
  listMemories: (...a: unknown[]) => api.listMemories(...a),
  forgetMemory: (...a: unknown[]) => api.forgetMemory(...a),
}));
vi.mock("../src/hooks/useLiveStore", () => ({
  useLiveState: () => ({ boardVersion: { tasks: 0, money: 0, notes: 0, documents: 0, memories: 0 } }),
}));

const memory = (over: Partial<MemoryOut> = {}): MemoryOut => ({
  id: "d-1", bot_id: "bot-1", kind: "decision", text: "Which invoice first?\nDecision: The new one", source: "bot",
  importance: 3, pinned: false, tainted: false, created_at: "2026-10-22T12:19:00Z", updated_at: "2026-10-22T12:19:00Z",
  last_recalled_at: null, archived_at: null, ...over,
});
beforeEach(() => { api.listMemories.mockResolvedValue([memory()]); api.forgetMemory.mockResolvedValue(undefined); });
afterEach(() => { cleanup(); api.listMemories.mockReset(); api.forgetMemory.mockReset(); });

describe("DecisionsCard", () => {
  it("lists decisions with its date, without a zone", async () => {
    render(<DecisionsCard botId="bot-1" />);
    expect(await screen.findByText("Which invoice first?")).toBeInTheDocument();
    expect(screen.getByText("The new one")).toBeInTheDocument();
    expect(screen.getByText("22 Oct, 14:19")).toBeInTheDocument();
    expect(api.listMemories).toHaveBeenCalledWith("bot-1", { kind: "decision" });
  });

  it("forget removes it and calls the API", async () => {
    render(<DecisionsCard botId="bot-1" />);
    await userEvent.click(await screen.findByRole("button", { name: "Forget" }));
    expect(api.forgetMemory).toHaveBeenCalledWith("d-1");
    await waitFor(() => expect(screen.queryByText("Which invoice first?")).not.toBeInTheDocument());
  });

  it("says when there are none", async () => {
    api.listMemories.mockResolvedValue([]);
    render(<DecisionsCard botId="bot-1" />);
    expect(await screen.findByText("No decisions yet.")).toBeInTheDocument();
  });
});
