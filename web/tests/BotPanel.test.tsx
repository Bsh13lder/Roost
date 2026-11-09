import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { Chat } from "../src/pages/Chat";
import { LazyBotPanel } from "../src/components/panel/lazyBotPanel";
import { PHONE_QUERY } from "../src/components/panel/panelTabs";
import { ToastProvider } from "../src/ui/Toast";
import { makeBot, makeMessage } from "./fixtures";

const updateBotMock = vi.fn();
const setNotifyMock = vi.fn();
const deskStatus = vi.fn();
const threadsApi = { listThreads: vi.fn(), openChat: vi.fn(), listMessages: vi.fn(), sendMessage: vi.fn() };
vi.mock("../src/api/threads", () => ({
  listThreads: (id: string) => threadsApi.listThreads(id), openChat: (id: string) => threadsApi.openChat(id),
  listMessages: (id: string) => threadsApi.listMessages(id), sendMessage: (id: string, t: string) => threadsApi.sendMessage(id, t),
}));
vi.mock("../src/api/bots", () => ({
  getBot: () => Promise.resolve(makeBot({ id: "bot-1", name: "Chief", job: "Leads", is_primary: true })),
  updateBot: (id: string, patch: unknown) => updateBotMock(id, patch),
  setNotify: (id: string, on: boolean) => setNotifyMock(id, on),
  deleteBot: () => Promise.resolve(),
}));
vi.mock("../src/api/stuck", () => ({ listStuck: () => Promise.resolve([]) }));
vi.mock("../src/api/computer", () => ({
  getControl: () => Promise.resolve({ held: false, since: null }),
  fetchScreen: () => new Promise(() => undefined),
}));
vi.mock("../src/api/desk", () => ({ getDeskStatus: (id: string) => deskStatus(id) }));
vi.mock("../src/api/routines", () => ({
  listRoutines: () => Promise.resolve([{ id: "r1", enabled: true }, { id: "r2", enabled: true }, { id: "r3", enabled: false }]),
}));
vi.mock("../src/api/profile", () => ({
  getMade: () => Promise.resolve({
    tasks: [], expenses: [], notes: [],
    documents: [{ id: "d1", title: "Weekly report", tainted: false, created_at: new Date().toISOString(), updated_at: "x" }],
  }),
  getLinks: () => Promise.resolve([{ url: "https://shop.example/deal", host: "shop.example", message_id: "m", thread_id: "t", created_at: "2026-01-02T10:00:00Z" }]),
}));
vi.mock("../src/api/mac", () => ({ listGrants: () => Promise.resolve([]) }));
vi.mock("../src/api/memories", () => ({ listMemories: () => Promise.resolve([]) }));
vi.mock("../src/hooks/useTemplates", () => ({ useTemplates: () => ({ templates: [], error: null }) }));
vi.mock("../src/hooks/useLiveStore", () => ({
  useLiveState: () => ({
    cursor: 0, bots: {}, messagesByThread: {}, streaming: {}, stuckCards: {}, toolLines: {},
    boardVersion: { tasks: 0, money: 0, notes: 0, documents: 0, memories: 0 },
  }),
}));

function Where() {
  const { pathname, search } = useLocation();
  return <p data-testid="where">{pathname + search}</p>;
}

function renderChat(path = "/bots/bot-1") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <ToastProvider>
        <Routes><Route path="/bots/:botId" element={<><Chat /><Where /></>} /></Routes>
      </ToastProvider>
    </MemoryRouter>,
  );
}

function stubPhone(phone: boolean) {
  window.matchMedia = ((query: string) => ({
    matches: phone && query === PHONE_QUERY, media: query, onchange: null,
    addListener: () => {}, removeListener: () => {}, addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

const panel = () => screen.getByRole("complementary", { name: "Chief's profile" });
const where = () => screen.getByTestId("where").textContent;
const rows = () => within(panel()).getByRole("list", { name: "Chief's pages" });

beforeEach(() => {
  stubPhone(false);
  const thread = { id: "t-1", bot_id: "bot-1", title: null, kind: "chat", created_at: "2026-10-14T10:00:00Z", updated_at: "2026-10-14T10:00:00Z" };
  threadsApi.listThreads.mockResolvedValue([thread]);
  threadsApi.openChat.mockResolvedValue(thread);
  threadsApi.listMessages.mockResolvedValue([makeMessage({ id: "m-1", thread_id: "t-1", role: "user", body: "hello" })]);
  threadsApi.sendMessage.mockResolvedValue({ message_id: "m-9" });
  deskStatus.mockResolvedValue({ browser: "running", workspace: "running" });
});
afterEach(() => {
  cleanup(); updateBotMock.mockReset(); setNotifyMock.mockReset(); deskStatus.mockReset();
  Object.values(threadsApi).forEach((m) => m.mockReset());
});

describe("the profile panel's own chunk", () => {
  it("shows a quiet loading panel while the chunk arrives, then the profile", async () => {
    render(
      <MemoryRouter><ToastProvider>
        <LazyBotPanel bot={makeBot({ id: "bot-1", name: "Chief" })} page="profile" onPage={vi.fn()} onClose={vi.fn()} onChange={vi.fn()} />
      </ToastProvider></MemoryRouter>,
    );
    const waiting = screen.queryByRole("complementary", { name: "Loading the profile" });
    if (waiting) expect(waiting).toHaveAttribute("aria-busy", "true"); // a cached chunk may skip it
    const aside = await screen.findByRole("complementary", { name: "Chief's profile" });
    expect(await within(aside).findByRole("button", { name: /Plan & routines/ })).toBeInTheDocument();
    expect(screen.queryByRole("complementary", { name: "Loading the profile" })).not.toBeInTheDocument();
  });

  it("on a phone the wait shows nothing (the sheet opens with the profile)", () => {
    stubPhone(true);
    render(
      <MemoryRouter><ToastProvider>
        <LazyBotPanel bot={makeBot({ id: "bot-1", name: "Chief" })} page="profile" onPage={vi.fn()} onClose={vi.fn()} onChange={vi.fn()} />
      </ToastProvider></MemoryRouter>,
    );
    expect(screen.queryByRole("complementary", { name: "Loading the profile" })).not.toBeInTheDocument();
  });
});

describe("the profile as rows", () => {
  it("the pill opens the profile and the URL says ?panel=profile", async () => {
    renderChat();
    await userEvent.click(await screen.findByRole("link", { name: "Open Chief's profile" }));
    expect(where()).toBe("/bots/bot-1?panel=profile");
    expect(screen.getByRole("link", { name: "Close Chief's profile" })).toHaveAttribute("href", "/bots/bot-1");
    expect(within(panel()).queryAllByRole("tab")).toHaveLength(0);
  });

  it("one card of rows: Plan & routines, Computer, Library, Settings, with their values", async () => {
    renderChat("/bots/bot-1?panel=profile");
    await screen.findByRole("complementary", { name: "Chief's profile" });
    const list = rows();
    const names = within(list).getAllByRole("button").map((row) => row.querySelector(".profile-row__label")?.textContent);
    expect(names).toEqual(["Plan & routines", "Computer", "Library", "Settings"]);
    expect(await within(list).findByText("2 on")).toBeInTheDocument();
    expect(await within(list).findByText("Idle")).toBeInTheDocument();
  });

  it("the Computer row says Asleep when the computer is asleep", async () => {
    deskStatus.mockResolvedValue({ browser: "stopped", workspace: "absent" });
    renderChat("/bots/bot-1?panel=profile");
    await screen.findByRole("complementary", { name: "Chief's profile" });
    expect(await within(rows()).findByText("Asleep")).toBeInTheDocument();
  });

  it("each row opens its page, in the URL, and the back arrow comes home", async () => {
    renderChat("/bots/bot-1?panel=profile");
    await screen.findByRole("complementary", { name: "Chief's profile" });
    for (const [name, id] of [["Plan & routines", "plan"], ["Computer", "computer"], ["Library", "library"], ["Settings", "settings"]]) {
      await userEvent.click(within(rows()).getByRole("button", { name: new RegExp(`^${name}`) }));
      expect(where()).toBe(`/bots/bot-1?panel=${id}`);
      expect(within(panel()).getByRole("heading", { level: 2, name })).toBeInTheDocument();
      await userEvent.click(within(panel()).getByRole("button", { name: "Back to the profile" }));
      expect(where()).toBe("/bots/bot-1?panel=profile");
    }
  });

  it("an old ?panel=info opens Settings, and ?panel=links the Library", async () => {
    renderChat("/bots/bot-1?panel=info");
    expect(await within(await screen.findByRole("complementary", { name: "Chief's profile" }))
      .findByRole("heading", { level: 2, name: "Settings" })).toBeInTheDocument();
    cleanup();
    renderChat("/bots/bot-1?panel=links");
    expect(await within(await screen.findByRole("complementary", { name: "Chief's profile" }))
      .findByRole("heading", { level: 2, name: "Library" })).toBeInTheDocument();
  });

  it("the hero shows the robot with its star, the name, the job and Edit", async () => {
    renderChat("/bots/bot-1?panel=profile");
    const aside = await screen.findByRole("complementary", { name: "Chief's profile" });
    expect(within(aside).getByRole("img", { name: "Main bot" })).toBeInTheDocument();
    expect(within(aside).getByRole("heading", { level: 2, name: "Chief" })).toBeInTheDocument();
    expect(within(aside).getByText("Leads")).toBeInTheDocument();
    expect(within(aside).getByRole("button", { name: "Edit" })).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 1, name: "Chief" })).toHaveLength(1);
  });

  it("the Notifications card is a switch with its caption", async () => {
    setNotifyMock.mockResolvedValue(makeBot({ id: "bot-1", name: "Chief", notify: false, is_primary: true }));
    renderChat("/bots/bot-1?panel=profile");
    const aside = await screen.findByRole("complementary", { name: "Chief's profile" });
    const toggle = within(aside).getByRole("switch", { name: /Notifications/ });
    expect(toggle).toHaveAttribute("aria-checked", "true");
    expect(within(aside).getByText("Get told when this bot finishes or is waiting for you.")).toBeInTheDocument();
    await userEvent.click(toggle);
    expect(setNotifyMock).toHaveBeenCalledWith("bot-1", false);
  });

  it("the Library groups documents and links by Today and Earlier", async () => {
    renderChat("/bots/bot-1?panel=library");
    const aside = await screen.findByRole("complementary", { name: "Chief's profile" });
    expect(await within(aside).findByRole("heading", { level: 3, name: "Today" })).toBeInTheDocument();
    expect(within(aside).getByRole("heading", { level: 3, name: "Earlier" })).toBeInTheDocument();
    expect(within(aside).getByRole("link", { name: /Weekly report/ })).toHaveAttribute("href", expect.stringContaining("d1"));
    expect(within(aside).getByRole("link", { name: /shop\.example/ })).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("Settings holds What I remember and ends with Retire this bot", async () => {
    renderChat("/bots/bot-1?panel=settings");
    const aside = await screen.findByRole("complementary", { name: "Chief's profile" });
    expect(await within(aside).findByText(/What I remember/)).toBeInTheDocument();
    const buttons = within(aside).getAllByRole("button");
    expect(buttons[buttons.length - 1]).toHaveTextContent("Retire this bot");
  });

  it("Close and Escape close the panel and focus goes back to the pill", async () => {
    renderChat("/bots/bot-1?panel=profile");
    const aside = await screen.findByRole("complementary", { name: "Chief's profile" });
    await userEvent.click(within(aside).getByRole("button", { name: "Close profile" }));
    expect(where()).toBe("/bots/bot-1");
    expect(screen.queryByRole("complementary")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Chief's profile" })).toHaveFocus();

    await userEvent.click(screen.getByRole("link", { name: "Open Chief's profile" }));
    await userEvent.keyboard("{Escape}");
    expect(where()).toBe("/bots/bot-1");
    expect(screen.getByRole("link", { name: "Open Chief's profile" })).toHaveFocus();
  });

  it("on a phone the panel is a full-screen sheet", async () => {
    stubPhone(true);
    renderChat("/bots/bot-1?panel=library");
    const sheet = await screen.findByRole("dialog", { name: "Chief's profile" });
    expect(sheet).toHaveClass("ui-sheet--full");
    expect(screen.queryByRole("complementary")).not.toBeInTheDocument();
    expect(within(sheet).getByRole("heading", { level: 2, name: "Library" })).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(where()).toBe("/bots/bot-1");
  });

  it("the chat stays usable while the panel is open", async () => {
    renderChat("/bots/bot-1?panel=profile");
    await screen.findByRole("complementary", { name: "Chief's profile" });
    await userEvent.type(screen.getByPlaceholderText("Message Chief"), "hi there{Enter}");
    expect(threadsApi.sendMessage).toHaveBeenCalledWith("t-1", "hi there");
  });

  it("Edit opens the name in place, and a new name saves", async () => {
    updateBotMock.mockResolvedValue(makeBot({ id: "bot-1", name: "Boss", is_primary: true }));
    renderChat("/bots/bot-1?panel=profile");
    const aside = await screen.findByRole("complementary", { name: "Chief's profile" });
    await userEvent.click(within(aside).getByRole("button", { name: "Edit" }));
    await userEvent.click(within(aside).getByRole("button", { name: "Edit name" }));
    const field = within(aside).getByRole("textbox", { name: "Name" });
    await userEvent.clear(field);
    await userEvent.type(field, "Boss{Enter}");
    expect(updateBotMock).toHaveBeenCalledWith("bot-1", { name: "Boss" });
    expect(await within(screen.getByRole("complementary")).findByRole("heading", { name: "Boss" })).toBeInTheDocument();
  });

  it("refuses a name that breaks the line without asking the server", async () => {
    renderChat("/bots/bot-1?panel=profile");
    const aside = await screen.findByRole("complementary", { name: "Chief's profile" });
    await userEvent.click(within(aside).getByRole("button", { name: "Edit" }));
    await userEvent.click(within(aside).getByRole("button", { name: "Edit name" }));
    const field = within(aside).getByRole("textbox", { name: "Name" });
    await userEvent.clear(field);
    await userEvent.type(field, " bad{Enter}");
    expect(screen.getByText("Use letters, numbers, spaces, . or - (up to 40).")).toBeInTheDocument();
    expect(updateBotMock).not.toHaveBeenCalled();
  });
});
