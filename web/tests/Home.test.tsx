import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { Home } from "../src/pages/Home";
import { ApiError } from "../src/api/client";
import type { ChatRowOut, MessageFrame } from "../src/api/types";
import { applyFrame, initialLiveState, type LiveState } from "../src/store/live";
import { makeBot, makeMessage, makeStuckCard } from "./fixtures";

const listBotsMock = vi.fn();
const listChatsMock = vi.fn();
const logoutMock = vi.fn();
const listStuckMock = vi.fn();
vi.mock("../src/api/bots", () => ({ listBots: () => listBotsMock() }));
vi.mock("../src/api/chats", () => ({ listChats: () => listChatsMock() }));
vi.mock("../src/api/rooms", () => ({ createRoom: vi.fn() }));
const listQuestionsMock = vi.fn();
const listProposalsMock = vi.fn();
vi.mock("../src/api/stuck", () => ({ listStuck: () => listStuckMock() }));
vi.mock("../src/api/questions", () => ({ listQuestions: () => listQuestionsMock() }));
vi.mock("../src/api/proposals", () => ({ listProposals: () => listProposalsMock() }));
vi.mock("../src/api/skills", () => ({ listSkillProposals: () => Promise.resolve([]) }));
vi.mock("../src/api/connectors", () => ({ listKeyRequests: () => Promise.resolve([]), listConnectors: () => Promise.resolve([]) }));
vi.mock("../src/api/mac", () => ({ listGrants: () => Promise.resolve([]) }));
vi.mock("../src/api/usage", () => ({ getUsage: () => Promise.resolve({ readable: false, remaining_fraction: null, resets_at: null }) }));
vi.mock("../src/hooks/useAuth", () => ({ useAuth: () => ({ user: { id: "u", username: "blck it" }, logout: logoutMock }) }));
let liveState: LiveState = initialLiveState();
vi.mock("../src/hooks/useLiveStore", () => ({
  useLiveState: () => liveState,
  onLiveFrame: () => () => undefined,
}));

const CHIEF = makeBot({ id: "bot-9", name: "Chief", is_primary: true });
const SCOUT = makeBot({ id: "bot-1", name: "Scout" });
const ROWS: ChatRowOut[] = [
  { kind: "bot", id: "bot-1", name: "Scout", thread_id: "t-1", preview: "Market opens at 9", preview_kind: "text",
    from_you: false, last_at: "2026-10-14T12:19:00Z", tainted: false },
  { kind: "bot", id: "bot-9", name: "Chief", thread_id: null, preview: null, preview_kind: null, from_you: false,
    last_at: "2026-10-01T10:00:00Z", tainted: false },
];

function renderHome() {
  return render(<MemoryRouter><Home /></MemoryRouter>);
}

// The live store's own frames: your message, the bot's empty placeholder
// (seq 0), then its stored reply under the same id.
const frame = (seq: number, overrides: Parameters<typeof makeMessage>[0]): MessageFrame =>
  ({ type: "message", seq, thread_id: "t-1", message: makeMessage(overrides) });
const YOURS = frame(1, { id: "m-1", role: "user", body: "When does it open?", seq: 1 });
const PLACEHOLDER = frame(2, { id: "m-2", body: "", seq: 0, author_bot_id: "bot-1" });
const REPLY = frame(3, { id: "m-2", body: "Market opens at 9", seq: 2, author_bot_id: "bot-1" });
const rowsSaying = (preview: string, fromYou: boolean): ChatRowOut[] => [{ ...ROWS[0], preview, from_you: fromYou }];

beforeEach(() => {
  localStorage.clear();
  liveState = initialLiveState();
  listBotsMock.mockResolvedValue([CHIEF, SCOUT]);
  listChatsMock.mockResolvedValue(ROWS);
  listStuckMock.mockResolvedValue([]);
  listQuestionsMock.mockResolvedValue([]);
  listProposalsMock.mockResolvedValue([]);
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe("Home", () => {
  it("shows the main bot first in the robot row, wearing its star, with no hero above it", async () => {
    const { container } = renderHome();
    const row = await screen.findByRole("list", { name: "Your bots" });
    const first = within(row).getAllByRole("link")[0];
    expect(first).toHaveAttribute("href", "/bots/bot-9");
    expect(first).toHaveAccessibleName(/^Chief\b/);
    expect(first.querySelector(".robot__star")).not.toBeNull();
    expect(container.querySelector(".main-bot")).toBeNull();
    expect(within(screen.getByRole("navigation", { name: "Chats" })).queryByRole("link", { name: /^Chief/ })).toBeNull();
  });

  it("+ offers New bot and New room, and Board opens the shared Board", async () => {
    renderHome();
    await screen.findByRole("navigation", { name: "Chats" });
    expect(screen.getByRole("link", { name: "Workspace" })).toHaveAttribute("href", "/board");
    await userEvent.click(screen.getByRole("button", { name: "New" }));
    expect(screen.getByRole("menuitem", { name: "New bot" })).toHaveAttribute("href", "/bots/new");
    await userEvent.click(screen.getByRole("menuitem", { name: "New room" }));
    expect(await screen.findByRole("dialog", { name: "New room" })).toBeInTheDocument();
  });

  it("search filters the chats", async () => {
    renderHome();
    await screen.findByRole("navigation", { name: "Chats" });
    await userEvent.type(screen.getByRole("searchbox", { name: "Search chats" }), "market");
    expect(screen.getAllByRole("link", { name: /Scout/ })).toHaveLength(1);
    expect(screen.queryByRole("link", { name: /^Chief\b.*Oct/ })).not.toBeInTheDocument();
  });

  it("search finds the main bot like any other chat", async () => {
    renderHome();
    const chats = await screen.findByRole("navigation", { name: "Chats" });
    await userEvent.type(screen.getByRole("searchbox", { name: "Search chats" }), "chief");
    expect(within(chats).getAllByRole("link").map((link) => link.getAttribute("href"))).toEqual(["/bots/bot-9"]);
  });

  it("dots a chat with a message you have not seen, and clears it once you open that chat", async () => {
    localStorage.setItem("roost.chat-seen.v1", JSON.stringify({ "bot-1": "2026-10-14T10:00:00Z", "bot-9": "2026-10-01T10:00:00Z" }));
    renderHome();
    const chats = await screen.findByRole("navigation", { name: "Chats" });
    expect(within(within(chats).getByRole("link", { name: /^Scout\b/ })).getByText("Unread")).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "Your bots" })).queryByText("Unread")).toBeNull();
    cleanup();
    render(<MemoryRouter initialEntries={["/bots/bot-1"]}><Home /></MemoryRouter>);
    const open = within(await screen.findByRole("navigation", { name: "Chats" })).getByRole("link", { name: /^Scout\b/ });
    expect(within(open).queryByText("Unread")).toBeNull();
    await waitFor(() => expect(JSON.parse(localStorage.getItem("roost.chat-seen.v1") ?? "{}")["bot-1"]).toBe("2026-10-14T12:19:00Z"));
  });

  it("your initials open Settings, where Sign out logs you out", async () => {
    renderHome();
    const initials = await screen.findByRole("button", { name: "Settings" });
    expect(initials).toHaveTextContent("BI");
    await userEvent.click(initials);
    const sheet = await screen.findByRole("dialog", { name: "Settings" });
    await userEvent.click(within(sheet).getByRole("button", { name: "Sign out" }));
    expect(logoutMock).toHaveBeenCalled();
  });

  it("the grid at the bottom opens the Board", async () => {
    renderHome();
    expect(await screen.findByRole("link", { name: "Workspace" })).toHaveAttribute("href", "/board");
  });

  it("with no browser answer yet, Settings asks for notifications in one tap", async () => {
    const requestPermission = vi.fn().mockResolvedValue("granted");
    vi.stubGlobal("Notification", Object.assign(function () {}, { permission: "default", requestPermission }));
    listBotsMock.mockResolvedValue([{ ...CHIEF, notify: true }, SCOUT]);
    renderHome();
    await userEvent.click(await screen.findByRole("button", { name: "Settings" }));
    const sheet = await screen.findByRole("dialog", { name: "Settings" });
    await userEvent.click(within(sheet).getByRole("button", { name: "Allow browser notifications" }));
    expect(requestPermission).toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it("a failed load says why and offers Retry", async () => {
    listChatsMock.mockRejectedValueOnce(new ApiError(500, "Could not load your chats."));
    renderHome();
    expect(await screen.findByText("Could not load your chats.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /retry/i }));
    await waitFor(() => expect(listChatsMock).toHaveBeenCalledTimes(2));
  });

  it("a bot's reply refreshes its row, though it replaces the placeholder in place", async () => {
    liveState = [YOURS, PLACEHOLDER].reduce(applyFrame, initialLiveState());
    listChatsMock.mockResolvedValue(rowsSaying("When does it open?", true));
    const view = renderHome();
    expect(await screen.findByText("You: When does it open?")).toBeInTheDocument();
    liveState = applyFrame(liveState, REPLY);
    listChatsMock.mockResolvedValue(rowsSaying("Market opens at 9", false));
    view.rerender(<MemoryRouter><Home /></MemoryRouter>);
    expect(await screen.findByText("Market opens at 9")).toBeInTheDocument();
  });

  it("a bot moves under its label when a bot_updated frame says so", async () => {
    const view = renderHome();
    await screen.findByRole("navigation", { name: "Chats" });
    expect(screen.queryByRole("heading", { name: "Work" })).not.toBeInTheDocument();
    liveState = applyFrame(liveState, { type: "bot_updated", seq: 7, bot: { ...SCOUT, group: "Work" } });
    view.rerender(<MemoryRouter><Home /></MemoryRouter>);
    const heading = await screen.findByRole("heading", { name: "Work" });
    const section = heading.closest("section") as HTMLElement;
    expect(within(section).getByRole("link", { name: /Scout/ })).toHaveAttribute("href", "/bots/bot-1");
  });

  it("an older load that answers last never replaces a newer one", async () => {
    let answerOld: (rows: ChatRowOut[]) => void = () => undefined;
    listChatsMock.mockReturnValueOnce(new Promise<ChatRowOut[]>((resolve) => { answerOld = resolve; }));
    listChatsMock.mockResolvedValueOnce(rowsSaying("Market opens at 9", false));
    const view = renderHome();
    liveState = applyFrame(liveState, YOURS);
    view.rerender(<MemoryRouter><Home /></MemoryRouter>);
    expect(await screen.findByText("Market opens at 9")).toBeInTheDocument();
    await act(async () => answerOld(rowsSaying("an old preview", false)));
    expect(screen.queryByText("an old preview")).not.toBeInTheDocument();
    expect(screen.getByText("Market opens at 9")).toBeInTheDocument();
  });
});

describe("Home — My turn", () => {
  const CARD = makeStuckCard({ bot_id: "bot-1", thread_id: "t-1" });

  it("lists each open Stuck card, linking to that bot's chat", async () => {
    listStuckMock.mockResolvedValue([CARD]);
    renderHome();
    const turn = await screen.findByRole("region", { name: "My turn" });
    expect(within(turn).getByRole("link", { name: "Scout · Stuck on shop.example" }))
      .toHaveAttribute("href", "/bots/bot-1?thread=t-1");
  });

  it("a Sign-in card's row says the bot needs you to sign in", async () => {
    listStuckMock.mockResolvedValue([{ ...CARD, sign_in: true }]);
    renderHome();
    const turn = await screen.findByRole("region", { name: "My turn" });
    expect(within(turn).getByRole("link", { name: "Scout needs you to sign in to shop.example" }))
      .toHaveAttribute("href", "/bots/bot-1?thread=t-1");
  });

  it("is hidden while nothing waits on you", async () => {
    renderHome();
    await screen.findByRole("navigation", { name: "Chats" });
    expect(screen.queryByRole("region", { name: "My turn" })).not.toBeInTheDocument();
  });

  it("follows live stuck_card frames without reloading", async () => {
    const view = renderHome();
    await screen.findByRole("navigation", { name: "Chats" });
    liveState = applyFrame(liveState, { type: "stuck_card", seq: 4, card: CARD });
    view.rerender(<MemoryRouter><Home /></MemoryRouter>);
    expect(await screen.findByRole("region", { name: "My turn" })).toBeInTheDocument();
    liveState = applyFrame(liveState, {
      type: "stuck_card", seq: 5, card: { ...CARD, state: "cleared", closed_at: "2026-10-14T10:05:00Z" },
    });
    view.rerender(<MemoryRouter><Home /></MemoryRouter>);
    expect(screen.queryByRole("region", { name: "My turn" })).not.toBeInTheDocument();
    expect(listStuckMock).toHaveBeenCalledTimes(1);
  });

  it("steps aside while you search", async () => {
    listStuckMock.mockResolvedValue([CARD]);
    renderHome();
    await screen.findByRole("region", { name: "My turn" });
    await userEvent.type(screen.getByRole("searchbox", { name: "Search chats" }), "scout");
    expect(screen.queryByRole("region", { name: "My turn" })).not.toBeInTheDocument();
  });

  it("still shows the chats when the Stuck list fails", async () => {
    listStuckMock.mockRejectedValueOnce(new ApiError(500, "Could not load your Stuck cards."));
    renderHome();
    expect(await screen.findByRole("navigation", { name: "Chats" })).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "Your bots" })).getByRole("link", { name: /^Chief\b/ })).toBeInTheDocument();
    const turn = await screen.findByRole("region", { name: "My turn" });
    expect(within(turn).getByRole("alert")).toHaveTextContent("Could not load your Stuck cards.");
    expect(screen.getAllByRole("alert")).toHaveLength(1);           // only My turn says so, never Home as a whole
    await userEvent.click(within(turn).getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(listStuckMock).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByRole("region", { name: "My turn" })).not.toBeInTheDocument());
    expect(listChatsMock).toHaveBeenCalledTimes(1);                 // Retry reloads the Stuck list only
  });

  it("my turn lists questions and proposals and survives a failed load", async () => {
    listQuestionsMock.mockResolvedValue([{ id: "q-1", bot_id: "bot-1", question: "Weekly or daily?", default_choice: "weekly" }]);
    listProposalsMock.mockResolvedValueOnce([{ id: "p-1", bot_id: "bot-1", action: "create", routine_name: null,
      payload: { name: "Morning digest" } }]);
    renderHome();
    const turn = await screen.findByRole("region", { name: "My turn" });
    expect(within(turn).getByRole("link", { name: "Scout · New routine · Morning digest" })).toHaveAttribute("href", "/bots/bot-1");
    expect(within(turn).getByRole("link", { name: "Scout · Weekly or daily?" })).toHaveAttribute("href", "/bots/bot-1?panel=settings");
  });

  it("a failed question load says so in My turn only, with Retry", async () => {
    listQuestionsMock.mockRejectedValueOnce(new ApiError(500, "Could not load your questions."));
    renderHome();
    expect(await screen.findByRole("navigation", { name: "Chats" })).toBeInTheDocument();
    const turn = await screen.findByRole("region", { name: "My turn" });
    expect(within(turn).getByRole("alert")).toHaveTextContent("Could not load your questions.");
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    listQuestionsMock.mockResolvedValue([{ id: "q-1", bot_id: "bot-1", question: "Weekly or daily?", default_choice: "weekly" }]);
    await userEvent.click(within(turn).getByRole("button", { name: "Retry" }));
    expect(await within(screen.getByRole("region", { name: "My turn" })).findByRole("link", { name: /Weekly or daily/ })).toBeInTheDocument();
  });
});
