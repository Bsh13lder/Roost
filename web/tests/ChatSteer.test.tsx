import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { Chat } from "../src/pages/Chat";
import type { BotOut } from "../src/api/types";
import { makeBot, makeMessage } from "./fixtures";

// Steer (docs/plans/2026-10-22-roost-steer.md): a message the bot's run reads mid-work shows no Queued line,
// and a Stop button sits by the composer while the bot is On it.

const threadsApi = { listThreads: vi.fn(), openChat: vi.fn(), listMessages: vi.fn(), sendMessage: vi.fn() };
vi.mock("../src/api/threads", () => ({
  listThreads: (id: string) => threadsApi.listThreads(id), openChat: (id: string) => threadsApi.openChat(id),
  listMessages: (id: string) => threadsApi.listMessages(id), sendMessage: (id: string, t: string) => threadsApi.sendMessage(id, t),
}));
const state: { bot: BotOut } = { bot: makeBot({ id: "bot-1", name: "Scout", status: "on_it", activity: "reading your message" }) };
const stopBot = vi.fn();
vi.mock("../src/api/bots", () => ({ getBot: () => Promise.resolve(state.bot), stopBot: (id: string) => stopBot(id) }));
vi.mock("../src/api/stuck", () => ({ listStuck: () => Promise.resolve([]) }));
vi.mock("../src/api/approvals", () => ({ listApprovals: () => Promise.resolve([]) }));
vi.mock("../src/api/computer", () => ({ getControl: () => Promise.resolve({ held: false, since: null }) }));
vi.mock("../src/hooks/useLiveStore", () => ({
  useLiveState: () => ({
    cursor: 0, bots: { "bot-1": state.bot }, messagesByThread: {}, streaming: {}, toolLines: {},
    boardVersion: { tasks: 0, money: 0, notes: 0, documents: 0 }, stuckCards: {}, approvalCards: {},
  }),
}));

const thread = { id: "t-1", bot_id: "bot-1", title: null, kind: "chat", created_at: "2026-10-22T10:00:00Z", updated_at: "2026-10-22T10:00:00Z" };

beforeEach(() => {
  threadsApi.listThreads.mockResolvedValue([thread]);
  threadsApi.openChat.mockResolvedValue(thread);
  threadsApi.listMessages.mockResolvedValue([makeMessage({ id: "m-1", thread_id: "t-1", role: "user", body: "hello", created_at: "2026-10-22T10:00:00Z", seq: 1 })]);
});
afterEach(() => {
  cleanup();
  Object.values(threadsApi).forEach((m) => m.mockReset());
  stopBot.mockReset();
  state.bot = makeBot({ id: "bot-1", name: "Scout", status: "on_it", activity: "reading your message" });
});

function renderChat() {
  return render(<MemoryRouter initialEntries={["/bots/bot-1"]}><Routes><Route path="/bots/:botId" element={<Chat />} /></Routes></MemoryRouter>);
}

describe("steer in the chat", () => {
  it("a steered send shows no Queued line", async () => {
    renderChat();
    const box = await screen.findByPlaceholderText("Message Scout");
    threadsApi.sendMessage.mockResolvedValue({ message_id: "u-2", status: "steered", queued: false });
    await userEvent.type(box, "and Tuesday{Enter}");
    expect(await screen.findByText("and Tuesday")).toBeInTheDocument();
    expect(screen.queryByText("Queued, I'll pick it up next")).not.toBeInTheDocument();
  });

  it("Stop sits by the composer while the bot is On it and stops it", async () => {
    stopBot.mockResolvedValue({ dropped: 0, interrupted: 0, done: [] });
    renderChat();
    await userEvent.click(await screen.findByRole("button", { name: "Stop Scout" }));
    expect(stopBot).toHaveBeenCalledWith("bot-1");
  });

  it("a failed Stop says why", async () => {
    stopBot.mockRejectedValue(new Error("network down"));
    renderChat();
    await userEvent.click(await screen.findByRole("button", { name: "Stop Scout" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  it("no Stop while the bot is Resting", async () => {
    state.bot = makeBot({ id: "bot-1", name: "Scout", status: "resting", activity: null });
    renderChat();
    await screen.findByPlaceholderText("Message Scout");
    expect(screen.queryByRole("button", { name: "Stop Scout" })).not.toBeInTheDocument();
  });
});
