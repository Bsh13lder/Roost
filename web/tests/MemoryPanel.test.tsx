import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError } from "../src/api/client";
import type { MemoryOut } from "../src/api/types";
import { MemoryPanel } from "../src/components/memory/MemoryPanel";
import { makeBot } from "./fixtures";

const api = { listMemories: vi.fn(), addMemory: vi.fn(), updateMemory: vi.fn(), forgetMemory: vi.fn() };
vi.mock("../src/api/memories", () => ({
  listMemories: (...a: unknown[]) => api.listMemories(...a), addMemory: (...a: unknown[]) => api.addMemory(...a),
  updateMemory: (...a: unknown[]) => api.updateMemory(...a), forgetMemory: (...a: unknown[]) => api.forgetMemory(...a),
}));
let memoriesVersion = 0;
vi.mock("../src/hooks/useLiveStore", () => ({
  useLiveState: () => ({ boardVersion: { tasks: 0, money: 0, notes: 0, documents: 0, memories: memoriesVersion } }),
}));

const BOT = makeBot({ id: "bot-1", name: "Scout" });
const memory = (overrides: Partial<MemoryOut> = {}): MemoryOut => ({
  id: "m-1", bot_id: null, kind: "about_you", text: "Lives in Madrid", source: "user", importance: 3, pinned: false,
  tainted: false, created_at: "2026-10-14T09:00:00Z", updated_at: "2026-10-14T09:00:00Z", last_recalled_at: null,
  archived_at: null, ...overrides,
});
const SHARED = memory();
const OWN = memory({ id: "m-2", bot_id: "bot-1", kind: "preference", text: "Short answers", source: "bot" });

beforeEach(() => {
  memoriesVersion = 0;
  api.listMemories.mockResolvedValue([SHARED, OWN]);
  api.addMemory.mockResolvedValue(SHARED);
  api.updateMemory.mockResolvedValue(SHARED);
  api.forgetMemory.mockResolvedValue(undefined);
});
afterEach(() => { cleanup(); Object.values(api).forEach((m) => m.mockReset()); });

const group = (name: string) => screen.getByRole("group", { name });

describe("MemoryPanel", () => {
  it("shows About you and This bot's, each with its kind, date and source", async () => {
    render(<MemoryPanel bot={BOT} />);
    expect(await screen.findByRole("heading", { name: "What I remember" })).toBeInTheDocument();
    const about = within(await screen.findByRole("group", { name: "About you" }));
    expect(about.getByText("Lives in Madrid")).toBeInTheDocument();
    expect(about.getByText("14 Oct")).toBeInTheDocument();
    expect(about.getByText("You")).toBeInTheDocument();
    const own = within(group("This bot's"));
    expect(own.getByText("Short answers")).toBeInTheDocument();
    expect(own.getByText("Preference")).toBeInTheDocument();
    expect(own.getByText("A bot")).toBeInTheDocument();
    expect(api.listMemories).toHaveBeenCalledWith("bot-1", { faded: false });
  });

  it("says Nothing yet in an empty group", async () => {
    api.listMemories.mockResolvedValue([SHARED]);
    render(<MemoryPanel bot={BOT} />);
    await screen.findByText("Lives in Madrid");
    expect(within(group("This bot's")).getByText("Nothing yet.")).toBeInTheDocument();
  });

  it("adds a memory to About you or to this bot", async () => {
    render(<MemoryPanel bot={BOT} />);
    await screen.findByText("Lives in Madrid");
    await userEvent.click(within(group("About you")).getByRole("button", { name: "Add" }));
    await userEvent.type(screen.getByRole("textbox"), "Likes tea");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(api.addMemory).toHaveBeenLastCalledWith({ text: "Likes tea", kind: "about_you" });
    await userEvent.click(within(group("This bot's")).getByRole("button", { name: "Add" }));
    await userEvent.type(screen.getByRole("textbox"), "Be brief");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(api.addMemory).toHaveBeenLastCalledWith({ text: "Be brief", kind: "preference", bot_id: "bot-1" });
    await waitFor(() => expect(api.listMemories.mock.calls.length).toBeGreaterThan(2));
  });

  it("edits a memory's text and kind in place", async () => {
    render(<MemoryPanel bot={BOT} />);
    await screen.findByText("Short answers");
    const row = within(screen.getByText("Short answers").closest("li") as HTMLElement);
    await userEvent.click(row.getByRole("button", { name: "Edit" }));
    const field = screen.getByRole("textbox");
    await userEvent.clear(field);
    await userEvent.type(field, "Very short answers");
    await userEvent.click(screen.getByRole("combobox"));
    await userEvent.click(await screen.findByRole("option", { name: "Lesson" }));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(api.updateMemory).toHaveBeenCalledWith("m-2", { text: "Very short answers", kind: "lesson" });
  });

  it("pins and unpins a memory", async () => {
    api.listMemories.mockResolvedValue([SHARED, { ...OWN, pinned: true }]);
    render(<MemoryPanel bot={BOT} />);
    await screen.findByText("Lives in Madrid");
    await userEvent.click(within(group("About you")).getByRole("button", { name: "Pin" }));
    expect(api.updateMemory).toHaveBeenLastCalledWith("m-1", { pinned: true });
    const unpin = within(group("This bot's")).getByRole("button", { name: "Unpin" });
    expect(unpin).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(unpin);
    expect(api.updateMemory).toHaveBeenLastCalledWith("m-2", { pinned: false });
  });

  it("forgets a memory", async () => {
    render(<MemoryPanel bot={BOT} />);
    await screen.findByText("Short answers");
    await userEvent.click(within(group("This bot's")).getByRole("button", { name: "Forget" }));
    expect(api.forgetMemory).toHaveBeenCalledWith("m-2");
  });

  it("shows faded memories behind Show faded, each with Restore", async () => {
    const faded = memory({ id: "m-3", bot_id: "bot-1", kind: "fact", text: "Old fact", archived_at: "2026-10-01T00:00:00Z" });
    api.listMemories.mockImplementation((_id: string, opts: { faded: boolean }) =>
      Promise.resolve(opts.faded ? [SHARED, OWN, faded] : [SHARED, OWN]));
    render(<MemoryPanel bot={BOT} />);
    await screen.findByText("Lives in Madrid");
    expect(screen.queryByText("Old fact")).toBeNull();
    const toggle = screen.getByRole("button", { name: "Show faded" });
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    await userEvent.click(toggle);
    const row = within((await screen.findByText("Old fact")).closest("li") as HTMLElement);
    expect(api.listMemories).toHaveBeenLastCalledWith("bot-1", { faded: true });
    expect(row.queryByRole("button", { name: /Pin/ })).toBeNull();
    await userEvent.click(row.getByRole("button", { name: "Restore" }));
    expect(api.updateMemory).toHaveBeenLastCalledWith("m-3", { restore: true });
  });

  it("says why when a change is refused, and keeps the list", async () => {
    api.forgetMemory.mockRejectedValue(new ApiError(404, "Memory not found"));
    render(<MemoryPanel bot={BOT} />);
    await screen.findByText("Short answers");
    await userEvent.click(within(group("This bot's")).getByRole("button", { name: "Forget" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Memory not found");
    expect(screen.getByText("Short answers")).toBeInTheDocument();
    api.addMemory.mockRejectedValue(new ApiError(422, "That looks like a secret."));
    await userEvent.click(within(group("About you")).getByRole("button", { name: "Add" }));
    await userEvent.type(screen.getByRole("textbox"), "pw");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("That looks like a secret.")).toBeInTheDocument();
    expect(screen.getByRole("textbox")).toHaveValue("pw");
  });

  it("marks a memory from web content and shows its text as plain text", async () => {
    api.listMemories.mockResolvedValue([memory({ text: "<b>bold</b> <img src=x>", tainted: true, source: "bot" })]);
    const { container } = render(<MemoryPanel bot={BOT} />);
    expect(await screen.findByText("<b>bold</b> <img src=x>")).toBeInTheDocument();
    expect(screen.getByText("from web content")).toBeInTheDocument();
    expect(container.querySelector("b, img")).toBeNull();
  });

  it("reloads when a memories_changed frame arrives", async () => {
    const { rerender } = render(<MemoryPanel bot={BOT} />);
    await screen.findByText("Lives in Madrid");
    const calls = api.listMemories.mock.calls.length;
    memoriesVersion = 1;
    rerender(<MemoryPanel bot={BOT} />);
    await waitFor(() => expect(api.listMemories.mock.calls.length).toBe(calls + 1));
  });
});
