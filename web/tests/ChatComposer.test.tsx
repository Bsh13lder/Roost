import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { Chat } from "../src/pages/Chat";
import { makeBot, makeMessage } from "./fixtures";

const threadsApi = { listThreads: vi.fn(), openChat: vi.fn(), listMessages: vi.fn(), sendMessage: vi.fn() };
vi.mock("../src/api/threads", () => ({
  listThreads: (id: string) => threadsApi.listThreads(id), openChat: (id: string) => threadsApi.openChat(id),
  listMessages: (id: string) => threadsApi.listMessages(id), sendMessage: (id: string, t: string) => threadsApi.sendMessage(id, t),
}));
const working = makeBot({ id: "bot-1", name: "Scout", status: "on_it", activity: "reading your message" });
vi.mock("../src/api/bots", () => ({ getBot: () => Promise.resolve(working) }));
vi.mock("../src/api/stuck", () => ({ listStuck: () => Promise.resolve([]) }));
vi.mock("../src/api/approvals", () => ({ listApprovals: () => Promise.resolve([]) }));
vi.mock("../src/api/computer", () => ({ getControl: () => Promise.resolve({ held: false, since: null }) }));
vi.mock("../src/hooks/useLiveStore", () => ({
  useLiveState: () => ({
    cursor: 0, bots: { "bot-1": working }, messagesByThread: {}, streaming: {}, toolLines: {},
    boardVersion: { tasks: 0, money: 0, notes: 0, documents: 0 }, stuckCards: {}, approvalCards: {},
  }),
}));

const thread = { id: "t-1", bot_id: "bot-1", title: null, kind: "chat", created_at: "2026-10-22T10:00:00Z", updated_at: "2026-10-22T10:00:00Z" };

beforeEach(() => {
  threadsApi.listThreads.mockResolvedValue([thread]);
  threadsApi.openChat.mockResolvedValue(thread);
  threadsApi.listMessages.mockResolvedValue([makeMessage({ id: "m-1", thread_id: "t-1", role: "user", body: "hello", created_at: "2026-10-22T10:00:00Z", seq: 1 })]);
});
afterEach(() => { cleanup(); Object.values(threadsApi).forEach((m) => m.mockReset()); });

function renderChat() {
  return render(<MemoryRouter initialEntries={["/bots/bot-1"]}><Routes><Route path="/bots/:botId" element={<Chat />} /></Routes></MemoryRouter>);
}

describe("the chat composer while a bot is On it", () => {
  it("the composer stays usable while the bot is On it", async () => {
    renderChat();
    const box = await screen.findByPlaceholderText("Message Scout");
    expect(box).toBeEnabled();
    threadsApi.sendMessage.mockResolvedValue({ message_id: "u-2", queued: false });
    await userEvent.type(box, "one more thing{Enter}");
    expect(threadsApi.sendMessage).toHaveBeenCalledWith("t-1", "one more thing");
    expect(box).toBeEnabled();
  });

  it("a queued send shows \"Queued, I'll pick it up next\"", async () => {
    renderChat();
    const box = await screen.findByPlaceholderText("Message Scout");
    threadsApi.sendMessage.mockResolvedValue({ message_id: "u-2", queued: true });
    await userEvent.type(box, "after that{Enter}");
    expect(await screen.findByText("Queued, I'll pick it up next")).toBeInTheDocument();
  });
});
