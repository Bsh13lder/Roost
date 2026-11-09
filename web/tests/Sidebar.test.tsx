import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { Home } from "../src/pages/Home";
import type { ChatRowOut } from "../src/api/types";
import { initialLiveState } from "../src/store/live";
import { makeBot } from "./fixtures";

const listBotsMock = vi.fn();
const listChatsMock = vi.fn();
vi.mock("../src/api/bots", () => ({ listBots: () => listBotsMock() }));
vi.mock("../src/api/chats", () => ({ listChats: () => listChatsMock() }));
vi.mock("../src/api/rooms", () => ({ createRoom: vi.fn() }));
vi.mock("../src/api/stuck", () => ({ listStuck: () => Promise.resolve([]) }));
vi.mock("../src/hooks/useAuth", () => ({ useAuth: () => ({ user: { id: "u", username: "blck it" }, logout: vi.fn() }) }));
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => initialLiveState(), onLiveFrame: () => () => undefined }));

const CHIEF = makeBot({ id: "bot-9", name: "Chief", is_primary: true });
const SCOUT = makeBot({ id: "bot-1", name: "Scout", group: "Work" });
const MOLE = makeBot({ id: "bot-2", name: "Mole" });
const row = (id: string, name: string, preview: string | null, lastAt: string): ChatRowOut => ({
  kind: "bot", id, name, thread_id: null, preview, preview_kind: preview ? "text" : null, from_you: false,
  last_at: lastAt, tainted: false,
});
const ROWS = [
  row("bot-1", "Scout", "Market opens at 9", "2026-10-14T12:19:00Z"),
  row("bot-2", "Mole", "Dug a **hole**", "2026-10-14T11:00:00Z"),
  row("bot-9", "Chief", null, "2026-10-01T10:00:00Z"),
];

const renderHome = () => render(<MemoryRouter><Home /></MemoryRouter>);

beforeEach(() => {
  localStorage.clear();
  listBotsMock.mockResolvedValue([CHIEF, SCOUT, MOLE]);
  listChatsMock.mockResolvedValue(ROWS);
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe("Sidebar", () => {
  it("search and + sit at the top, the initials menu and Board at the bottom", async () => {
    renderHome();
    const chats = await screen.findByRole("navigation", { name: "Chats" });
    const before = (a: Node, b: Node) => Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
    const search = screen.getByRole("searchbox", { name: "Search chats" });
    expect(search).toHaveAttribute("placeholder", "Search");
    expect(before(search, chats)).toBe(true);
    expect(before(screen.getByRole("button", { name: "New" }), chats)).toBe(true);
    expect(before(chats, screen.getByRole("button", { name: "Settings" }))).toBe(true);
    const board = screen.getByRole("link", { name: "Workspace" });
    expect(before(chats, board)).toBe(true);
    expect(board).toHaveAttribute("href", "/board");
  });

  it("the avatar row shows the main bot first with its star, then the pinned bots, and each robot opens its chat", async () => {
    listBotsMock.mockResolvedValue([CHIEF, SCOUT, makeBot({ ...MOLE, pinned: true, pinned_at: "2026-10-14T10:00:00Z" })]);
    const { container } = renderHome();
    const bots = await screen.findByRole("list", { name: "Your bots" });
    const links = within(bots).getAllByRole("link");
    expect(links.map((link) => link.getAttribute("href"))).toEqual(["/bots/bot-9", "/bots/bot-2"]);
    expect(links[0]).toHaveAccessibleName("Chief");
    expect(links[1]).toHaveAccessibleName("Mole");
    expect(links[0].querySelector(".robot__star")).not.toBeNull();
    expect(container.querySelector(".home-header")).toBeNull();
  });

  it("pinned tiles show the bot's name under a large avatar, and the open chat's tile is selected", async () => {
    listBotsMock.mockResolvedValue([CHIEF, SCOUT, makeBot({ ...MOLE, pinned: true, pinned_at: "x" })]);
    const { container } = render(<MemoryRouter initialEntries={["/bots/bot-2"]}><Home /></MemoryRouter>);
    const bots = await screen.findByRole("list", { name: "Your bots" });
    const [chief, mole] = within(bots).getAllByRole("link");
    expect(within(chief).getByText("Chief")).toBeVisible();
    expect(within(mole).getByText("Mole")).toBeVisible();
    expect(chief.querySelector(".avatar-row__job")).not.toBeNull();
    expect(mole.querySelector(".avatar-row__job")).toBeNull();
    expect(mole).toHaveClass("avatar-row__link", "active");
    expect(chief).not.toHaveClass("active");
    expect(Number(container.querySelector(".avatar-row .robot")?.getAttribute("width"))).toBeGreaterThanOrEqual(56);
  });

  it("the avatar row holds only the main bot while nothing is pinned", async () => {
    renderHome();
    const bots = await screen.findByRole("list", { name: "Your bots" });
    expect(within(bots).getAllByRole("link")).toHaveLength(1);
  });

  it("pinned bots leave the chat list, and the main bot is pinned", async () => {
    listBotsMock.mockResolvedValue([CHIEF, SCOUT, makeBot({ ...MOLE, pinned: true, pinned_at: "x" })]);
    renderHome();
    const chats = await screen.findByRole("navigation", { name: "Chats" });
    expect(within(chats).getAllByRole("link").map((link) => link.getAttribute("href"))).toEqual(["/bots/bot-1"]);
  });

  it("chats sit under their group headings, ungrouped first", async () => {
    renderHome();
    const chats = await screen.findByRole("navigation", { name: "Chats" });
    expect(within(chats).getAllByRole("heading")).toHaveLength(1);
    expect(within(chats).getByRole("heading", { name: "Work" })).toBeInTheDocument();
    const hrefs = within(chats).getAllByRole("link").map((link) => link.getAttribute("href"));
    expect(hrefs).toEqual(["/bots/bot-2", "/bots/bot-1"]);
  });

  it("each row shows the avatar, name, a plain one-line preview and the unread dot", async () => {
    localStorage.setItem("roost.chat-seen.v1", JSON.stringify({ "bot-1": "2026-10-14T10:00:00Z" }));
    renderHome();
    const chats = await screen.findByRole("navigation", { name: "Chats" });
    const mole = within(chats).getByRole("link", { name: /^Mole\b/ });
    expect(within(mole).getByText("Dug a hole")).toBeInTheDocument();
    expect(mole.querySelector(".robot")).not.toBeNull();
    const scout = within(chats).getByRole("link", { name: /^Scout\b/ });
    expect(within(scout).getByText("Unread")).toBeInTheDocument();
  });

  it("search filters every section and hides the avatar row", async () => {
    renderHome();
    await screen.findByRole("navigation", { name: "Chats" });
    await userEvent.type(screen.getByRole("searchbox", { name: "Search chats" }), "market");
    expect(screen.queryByRole("list", { name: "Your bots" })).not.toBeInTheDocument();
    const chats = screen.getByRole("navigation", { name: "Chats" });
    expect(within(chats).getAllByRole("link")).toHaveLength(1);
    expect(within(chats).getByRole("heading", { name: "Work" })).toBeInTheDocument();
    await userEvent.clear(screen.getByRole("searchbox", { name: "Search chats" }));
    await userEvent.type(screen.getByRole("searchbox", { name: "Search chats" }), "dug");
    expect(within(chats).queryByRole("heading", { name: "Work" })).not.toBeInTheDocument();
  });
});
