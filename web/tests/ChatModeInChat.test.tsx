import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { Chat } from "../src/pages/Chat";
import type { BotOut } from "../src/api/types";
import { makeBot } from "./fixtures";

const threadsApi = { listThreads: vi.fn(), openChat: vi.fn(), listMessages: vi.fn() };
vi.mock("../src/api/threads", () => ({
  listThreads: (id: string) => threadsApi.listThreads(id), openChat: (id: string) => threadsApi.openChat(id),
  listMessages: (id: string) => threadsApi.listMessages(id),
}));
const current = vi.hoisted(() => ({ bot: null as BotOut | null }));
vi.mock("../src/api/bots", () => ({ getBot: () => Promise.resolve(current.bot), setApproval: vi.fn() }));
vi.mock("../src/api/stuck", () => ({ listStuck: () => Promise.resolve([]) }));
vi.mock("../src/api/approvals", () => ({ listApprovals: () => Promise.resolve([]) }));
vi.mock("../src/api/computer", () => ({ getControl: () => Promise.resolve({ held: false, since: null }) }));
vi.mock("../src/hooks/useLiveStore", () => ({
  useLiveState: () => ({
    cursor: 0, bots: {}, messagesByThread: {}, streaming: {}, toolLines: {},
    boardVersion: { tasks: 0, money: 0, notes: 0, documents: 0 }, stuckCards: {}, approvalCards: {},
  }),
}));

const thread = { id: "t-1", bot_id: "bot-1", title: null, kind: "chat", created_at: "2026-10-22T10:00:00Z", updated_at: "2026-10-22T10:00:00Z" };

beforeEach(() => {
  threadsApi.listThreads.mockResolvedValue([thread]);
  threadsApi.openChat.mockResolvedValue(thread);
  threadsApi.listMessages.mockResolvedValue([]);
});
afterEach(() => { cleanup(); Object.values(threadsApi).forEach((m) => m.mockReset()); });

function renderChat() {
  return render(<MemoryRouter initialEntries={["/bots/bot-1"]}><Routes><Route path="/bots/:botId" element={<Chat />} /></Routes></MemoryRouter>);
}

describe("the chat mode pill in a bot's chat", () => {
  it("sits inside the composer pill for a bot on its Linux computer", async () => {
    current.bot = makeBot({ id: "bot-1", name: "Scout", computer: "linux" });
    renderChat();
    const input = await screen.findByPlaceholderText("Message Scout");
    const pill = screen.getByRole("button", { name: "Chat mode: Just browse" });
    expect(input.closest(".composer")?.contains(pill)).toBe(true);
  });

  it("is not shown for a bot on Mac Brave", async () => {
    current.bot = makeBot({ id: "bot-1", name: "Scout", computer: "mac_brave" });
    renderChat();
    await screen.findByPlaceholderText("Message Scout");
    expect(screen.queryByRole("button", { name: /Chat mode/ })).not.toBeInTheDocument();
  });
});
