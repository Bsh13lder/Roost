// Talk's loading, sending and new-conversation regressions, kept for Chat
// (Task 7 moved that logic over unchanged; the controls moved into menus).
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { Chat } from "../src/pages/Chat";
import { ApiError } from "../src/api/client";
import type { MessageOut, ThreadOut } from "../src/api/types";
import { onThreadsChanged } from "../src/lib/threadsChanged";
import { makeBot } from "./fixtures";

const getBotMock = vi.fn();
const stopBotMock = vi.fn();
vi.mock("../src/api/bots", () => ({
  getBot: (...args: unknown[]) => getBotMock(...args),
  stopBot: (...a: unknown[]) => stopBotMock(...a),
}));

const listThreadsMock = vi.fn();
const openChatMock = vi.fn();
const listMessagesMock = vi.fn();
const sendMessageMock = vi.fn();
vi.mock("../src/api/threads", () => ({
  listThreads: (...args: unknown[]) => listThreadsMock(...args),
  openChat: (...args: unknown[]) => openChatMock(...args),
  listMessages: (...args: unknown[]) => listMessagesMock(...args),
  sendMessage: (...args: unknown[]) => sendMessageMock(...args),
}));

const BOARD = { tasks: 0, money: 0, notes: 0, documents: 0 };
const liveOf = (cursor = 0, messagesByThread: Record<string, MessageOut[]> = {}) =>
  ({ cursor, bots: {}, messagesByThread, streaming: {}, boardVersion: BOARD, stuckCards: {} });
let liveState = liveOf();
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => liveState }));
// Chat loads your open Stuck cards on mount; none are open in these tests.
vi.mock("../src/api/stuck", () => ({ listStuck: () => Promise.resolve([]) }));

const BOT = makeBot({ id: "bot-1", name: "Scout" });
const threadOf = (id: string, created_at: string): ThreadOut =>
  ({ id, bot_id: "bot-1", title: null, kind: "chat", created_at, updated_at: created_at });
const OLD_THREAD = threadOf("old-thread", "2026-10-13T00:00:00Z");
const NEW_THREAD = threadOf("new-thread", "2026-10-13T01:00:00Z");
const stored = (id: string, threadId: string, body: string, extra: Partial<MessageOut> = {}): MessageOut =>
  ({ id, thread_id: threadId, role: "bot", body, tainted: false, seq: 1, created_at: "x", kind: "text", author_bot_id: null, ...extra });

const view = (path = "/bots/bot-1") => (
  <MemoryRouter initialEntries={[path]}>
    <Routes><Route path="/bots/:botId" element={<Chat />} /></Routes>
  </MemoryRouter>
);
const renderChat = (path?: string) => render(view(path));

async function pick(menu: string, item: string) {
  await userEvent.click(await screen.findByRole("button", { name: menu }));
  await userEvent.click(screen.getByRole("menuitem", { name: item }));
}

beforeEach(() => {
  liveState = liveOf();
  getBotMock.mockReset().mockResolvedValue(BOT);
  stopBotMock.mockReset();
  listThreadsMock.mockReset();
  openChatMock.mockReset().mockResolvedValue(NEW_THREAD);
  listMessagesMock.mockReset().mockResolvedValue([]);
  sendMessageMock.mockReset();
});
afterEach(() => cleanup());

describe("Chat — thread selection", () => {
  it("tells the chat list about the chat it made for a new bot (M2 D6)", async () => {
    listThreadsMock.mockResolvedValue([]);
    const heard: string[] = [];
    const stop = onThreadsChanged((botId) => heard.push(botId));
    renderChat();
    await waitFor(() => expect(heard).toEqual(["bot-1"]));
    expect(listMessagesMock).toHaveBeenCalledWith("new-thread");
    stop();
  });

  it("shows the bot's one chat, not the last thread returned", async () => {
    listThreadsMock.mockResolvedValue([OLD_THREAD, NEW_THREAD]);
    openChatMock.mockResolvedValue(OLD_THREAD);
    listMessagesMock.mockImplementation((threadId: string) => Promise.resolve(
      threadId === "new-thread" ? [stored("m-new", "new-thread", "from the new thread")] : [stored("m-old", "old-thread", "from the old thread")],
    ));
    renderChat();
    expect(await screen.findByText("from the old thread")).toBeInTheDocument();
    expect(screen.queryByText("from the new thread")).toBeNull();
  });

  it("Earlier conversations lists every thread but the main chat, newest first", async () => {
    const third = threadOf("third-thread", "2026-10-13T02:00:00Z");
    listThreadsMock.mockResolvedValue([OLD_THREAD, NEW_THREAD, third]);
    openChatMock.mockResolvedValue(NEW_THREAD);
    renderChat();
    await pick("Scout menu", "Earlier conversations");
    const rows = screen.getByRole("dialog", { name: "Earlier conversations" }).querySelectorAll("button.sheet__row");
    expect(rows).toHaveLength(2);
    await userEvent.click(rows[0] as HTMLElement);
    await waitFor(() => expect(listMessagesMock).toHaveBeenCalledWith("third-thread"));
  });

  it("says so when there are no earlier conversations", async () => {
    listThreadsMock.mockResolvedValue([NEW_THREAD]);
    renderChat();
    await pick("Scout menu", "Earlier conversations");
    expect(screen.getByText("No earlier conversations.")).toBeInTheDocument();
  });

  it("opens the thread named in ?thread=", async () => {
    listThreadsMock.mockResolvedValue([OLD_THREAD, NEW_THREAD]);
    renderChat("/bots/bot-1?thread=old-thread");
    await waitFor(() => expect(listMessagesMock).toHaveBeenCalledWith("old-thread"));
  });
});

describe("Chat — errors stay in place", () => {
  it("shows a retryable error instead of hanging on Loading… when getBot fails", async () => {
    getBotMock.mockRejectedValue(new ApiError(404, "Bot not found."));
    listThreadsMock.mockResolvedValue([NEW_THREAD]);
    renderChat();
    expect(await screen.findByRole("alert")).toHaveTextContent("Bot not found.");
    getBotMock.mockResolvedValue(BOT);
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("heading", { name: "Scout" })).toBeInTheDocument();
  });

  it("a failed send shows an inline error without blanking the page, and keeps the typed text", async () => {
    listThreadsMock.mockResolvedValue([NEW_THREAD]);
    sendMessageMock.mockRejectedValue(new ApiError(500, "Something went wrong."));
    renderChat();
    await screen.findByRole("heading", { name: "Scout" });
    await userEvent.type(screen.getByRole("textbox"), "hello{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong.");
    expect(screen.getByRole("heading", { name: "Scout" })).toBeInTheDocument();
    expect(screen.getByRole("textbox")).toHaveValue("hello");
  });

  it("says why when Stop fails, without leaving the conversation", async () => {
    getBotMock.mockResolvedValue({ ...BOT, status: "on_it" });
    listThreadsMock.mockResolvedValue([OLD_THREAD]);
    stopBotMock.mockRejectedValue(new ApiError(500, "Could not stop Scout."));
    renderChat();
    await pick("Scout menu", "Stop");
    expect(stopBotMock).toHaveBeenCalledWith("bot-1");
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not stop Scout.");
    expect(screen.getByRole("textbox")).toBeInTheDocument();
  });
});

describe("Chat — sending", () => {
  it("uses the server message_id, so the live echo of the same message doesn't show twice", async () => {
    listThreadsMock.mockResolvedValue([NEW_THREAD]);
    sendMessageMock.mockResolvedValue({ message_id: "msg-99" });
    const { rerender } = renderChat();
    await screen.findByRole("heading", { name: "Scout" });
    await userEvent.type(screen.getByRole("textbox"), "hello{Enter}");
    await waitFor(() => expect(screen.getAllByText("hello")).toHaveLength(1));
    liveState = liveOf(2, { "new-thread": [stored("msg-99", "new-thread", "hello", { role: "user", seq: 2 })] });
    rerender(view());
    expect(screen.getAllByText("hello")).toHaveLength(1);
  });

  it("keeps each reply under the message it answers across two rounds", async () => {
    listThreadsMock.mockResolvedValue([NEW_THREAD]);
    sendMessageMock.mockResolvedValueOnce({ message_id: "u1" }).mockResolvedValueOnce({ message_id: "u2" });
    const reply = (id: string, seq: number) => stored(id, "new-thread", `reply ${id}`, { seq, author_bot_id: "bot-1" });
    const { rerender } = renderChat();
    await screen.findByRole("heading", { name: "Scout" });
    await userEvent.type(screen.getByRole("textbox"), "first{Enter}");
    await screen.findByText("first");
    liveState = liveOf(2, { "new-thread": [reply("b1", 2)] });
    rerender(view());
    await userEvent.type(screen.getByRole("textbox"), "second{Enter}");
    await screen.findByText("second");
    liveState = liveOf(4, { "new-thread": [reply("b1", 2), reply("b2", 4)] });
    rerender(view());
    const rows = within(screen.getByRole("list", { name: "Messages" })).getAllByRole("listitem");
    expect(rows.map((row) => row.querySelector(".message__body")?.textContent)).toEqual(["first", "reply b1", "second", "reply b2"]);
  });
});
