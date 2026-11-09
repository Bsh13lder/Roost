import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { Chat } from "../src/pages/Chat";
import { ApiError } from "../src/api/client";
import type { ThreadOut } from "../src/api/types";
import { resetVoiceInfo } from "../src/lib/voiceInfo";
import { makeBot, makeMessage, makeStuckCard, stuckBody, STUCK_LINE } from "./fixtures";

const threadsApi = { listThreads: vi.fn(), openChat: vi.fn(), listMessages: vi.fn(), sendMessage: vi.fn() };
vi.mock("../src/api/threads", () => ({
  listThreads: (id: string) => threadsApi.listThreads(id), openChat: (id: string) => threadsApi.openChat(id),
  listMessages: (id: string) => threadsApi.listMessages(id), sendMessage: (...a: unknown[]) => threadsApi.sendMessage(...a),
}));
vi.mock("../src/api/bots", () => ({ getBot: () => Promise.resolve(makeBot({ id: "bot-1", name: "Scout" })) }));
const documentsApi = vi.hoisted(() => ({ uploadPdf: vi.fn() }));
vi.mock("../src/api/documents", () => ({ uploadPdf: (file: File) => documentsApi.uploadPdf(file) }));
const stuckApi = { listStuck: vi.fn() };
vi.mock("../src/api/stuck", () => ({ listStuck: () => stuckApi.listStuck() }));
// An open Stuck card asks who holds the bot's computer when it mounts; nobody does here.
vi.mock("../src/api/approvals", () => ({ listApprovals: () => Promise.resolve([]) }));
vi.mock("../src/api/computer", () => ({ getControl: () => Promise.resolve({ held: false, since: null }) }));
vi.mock("../src/hooks/useLiveStore", () => ({
  useLiveState: () => ({
    cursor: 0, bots: {}, messagesByThread: {}, streaming: {}, boardVersion: { tasks: 0, money: 0, notes: 0, documents: 0 },
    stuckCards: {},
  }),
}));
// The composer's mic, stubbed: one tap puts fixed words in the box, the way a transcription does.
vi.mock("../src/components/chat/MicButton", () => ({
  MicButton: ({ onText }: { onText: (text: string) => void }) => (
    <button type="button" onClick={() => onText("I goed home")}>Speak</button>
  ),
}));
// Final-review fix: opening a chat preloads the markdown renderer. The rest of RichText stays real.
const preloadMarkdown = vi.hoisted(() => vi.fn(() => Promise.resolve()));
vi.mock("../src/components/chat/RichText", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../src/components/chat/RichText")>()), preloadMarkdown,
}));

// The call screen, stubbed: it shows its dialog, sends one turn through the chat's own send path and can end.
vi.mock("../src/components/call/CallScreen", () => ({
  default: ({ onSend, onClose, bot }: { onSend: (t: string) => Promise<string>; onClose: () => void; bot: { name: string } }) => (
    <div role="dialog" aria-label={`Call with ${bot.name}`}>
      <button type="button" onClick={() => { void onSend("Add milk").then((id) => { document.title = `sent ${id}`; }); }}>Say</button>
      <button type="button" onClick={onClose}>End call</button>
    </div>
  ),
}));

const thread = (id: string, created_at: string, kind = "chat"): ThreadOut =>
  ({ id, bot_id: "bot-1", title: null, kind, created_at, updated_at: created_at });

function Where() {
  const { pathname, search } = useLocation();
  return <p data-testid="where">{pathname + search}</p>;
}

function renderChat(path = "/bots/bot-1") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes><Route path="/bots/:botId" element={<><Chat /><Where /></>} /></Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  threadsApi.listThreads.mockResolvedValue([thread("t-1", "2026-10-13T10:00:00Z"), thread("t-2", "2026-10-14T10:00:00Z")]);
  threadsApi.listMessages.mockResolvedValue([
    makeMessage({ id: "m-1", thread_id: "t-2", role: "user", body: "hello", created_at: "2026-10-14T10:00:00Z" }),
    makeMessage({ id: "m-2", thread_id: "t-2", kind: "bot_created", author_bot_id: "bot-1", created_at: "2026-10-14T10:01:00Z",
      body: JSON.stringify({ bot_id: "bot-7", name: "HiMap SEO", job: "SEO", instructions: "Audit.", avatar: { shape: "egg", color: "#14b8a6", badge: "none" } }) }),
  ]);
  threadsApi.openChat.mockResolvedValue(thread("t-2", "2026-10-14T10:00:00Z"));
  stuckApi.listStuck.mockResolvedValue([]);
});
afterEach(() => { cleanup(); [...Object.values(threadsApi), stuckApi.listStuck].forEach((m) => m.mockReset()); });

describe("Chat", () => {
  it("has a back button, a pill that opens the profile and a composer named for the bot", async () => {
    renderChat();
    expect(await screen.findByRole("heading", { name: "Scout" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to chats" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: "Open Scout's profile" })).toHaveAttribute("href", "/bots/bot-1?panel=profile");
    expect(screen.getByPlaceholderText("Message Scout")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Desk" })).not.toBeInTheDocument();
  });

  it("takes the bot's colour on the chat container only", async () => {
    const { container } = renderChat();
    await screen.findByRole("heading", { name: "Scout" });
    const page = container.querySelector<HTMLElement>(".chat-page");
    expect(page?.style.getPropertyValue("--chat-accent")).toBe("#10b981");
    expect(page?.style.getPropertyValue("--chat-on-accent")).not.toBe("");
    expect(document.documentElement.style.getPropertyValue("--chat-accent")).toBe("");
  });

  it("preloads the markdown renderer as soon as it opens, before any reply is loaded", () => {
    preloadMarkdown.mockClear();
    threadsApi.listThreads.mockReturnValue(new Promise(() => undefined));
    renderChat();
    expect(screen.getByText("Loading…")).toBeInTheDocument();
    expect(preloadMarkdown).toHaveBeenCalledTimes(1);
  });

  it("shows the Created card inline", async () => {
    renderChat();
    expect(await screen.findByRole("group", { name: "Created HiMap SEO" })).toBeInTheDocument();
  });

  it("opens the bot's one chat", async () => {
    renderChat();
    await screen.findByRole("heading", { name: "Scout" });
    expect(threadsApi.openChat).toHaveBeenCalledWith("bot-1");
    expect(threadsApi.listMessages).toHaveBeenCalledWith("t-2");
    expect(screen.getByPlaceholderText("Message Scout")).toBeInTheDocument();
  });

  it("the header's ⋯ menu has Earlier conversations and no New conversation", async () => {
    renderChat();
    await screen.findByRole("heading", { name: "Scout" });
    await userEvent.click(screen.getByRole("button", { name: "Scout menu" }));
    expect(screen.getByRole("menuitem", { name: "Earlier conversations" })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "New conversation" })).not.toBeInTheDocument();
  });

  it("the composer's + offers pictures, a video and Choose file, and a PDF lands in your documents", async () => {
    documentsApi.uploadPdf.mockResolvedValue({ id: "d-9", title: "Lease" });
    renderChat();
    await screen.findByRole("heading", { name: "Scout" });
    await userEvent.click(screen.getByRole("button", { name: "Add to the chat" }));
    expect(screen.getAllByRole("menuitem").map((item) => item.textContent))
      .toEqual(["Attach pictures", "Attach a video", "Choose file", "Save a password"]);
    await userEvent.keyboard("{Escape}");
    const file = new File(["%PDF-1.4"], "Lease.pdf", { type: "application/pdf" });
    await userEvent.upload(screen.getByLabelText("Choose a PDF"), file);
    expect(documentsApi.uploadPdf).toHaveBeenCalledWith(file);
    expect(await screen.findByRole("status")).toHaveTextContent("Added “Lease” to your documents. Ask Scout to read it.");
  });

  it("View profile in the ⋯ menu opens the profile beside the chat", async () => {
    renderChat();
    await screen.findByRole("heading", { name: "Scout" });
    await userEvent.click(screen.getByRole("button", { name: "Scout menu" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "View profile" }));
    expect(screen.getByTestId("where")).toHaveTextContent("/bots/bot-1?panel=profile");
  });

  it("Find in chat shows only the messages with the words, says how many, and Close brings all back", async () => {
    threadsApi.listMessages.mockResolvedValue([
      makeMessage({ id: "m-1", thread_id: "t-2", role: "user", body: "find me a flight", created_at: "2026-10-14T10:00:00Z" }),
      makeMessage({ id: "m-2", thread_id: "t-2", role: "bot", body: "Here are three hotels", created_at: "2026-10-14T10:01:00Z" }),
    ]);
    renderChat();
    await screen.findByText("Here are three hotels");
    await userEvent.click(screen.getByRole("button", { name: "Scout menu" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Find in chat" }));
    const box = screen.getByRole("searchbox", { name: "Find in chat" });
    expect(box).toHaveFocus();
    await userEvent.type(box, "FLIGHT");
    expect(screen.getByText("1 found")).toBeInTheDocument();
    expect(screen.queryByText("Here are three hotels")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Close find" }));
    expect(await screen.findByText("Here are three hotels")).toBeInTheDocument();
    expect(screen.queryByRole("searchbox", { name: "Find in chat" })).not.toBeInTheDocument();
  });

  it("the ⋯ menu lists the earlier conversations and opens the one you pick", async () => {
    renderChat();
    await screen.findByRole("heading", { name: "Scout" });
    await userEvent.click(screen.getByRole("button", { name: "Scout menu" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Earlier conversations" }));
    const sheet = screen.getByRole("dialog", { name: "Earlier conversations" });
    const rows = sheet.querySelectorAll("button.sheet__row");
    expect(rows).toHaveLength(1);
    await userEvent.click(rows[0] as HTMLElement);
    expect(screen.getByTestId("where")).toHaveTextContent("/bots/bot-1?thread=t-1");
  });

  it("an earlier conversation is read-only, with a way back to the chat", async () => {
    renderChat("/bots/bot-1?thread=t-1");
    expect(await screen.findByText("An earlier conversation, read-only.")).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to the chat" })).toHaveAttribute("href", "/bots/bot-1");
    expect(threadsApi.listMessages).toHaveBeenCalledWith("t-1");
  });

  it("a handoff thread keeps its composer", async () => {
    threadsApi.listThreads.mockResolvedValue([thread("t-1", "2026-10-13T10:00:00Z"), thread("t-2", "2026-10-14T10:00:00Z"),
      thread("h-1", "2026-10-14T12:00:00Z", "handoff")]);
    renderChat("/bots/bot-1?thread=h-1");
    await screen.findByRole("heading", { name: "Scout" });
    expect(screen.getByPlaceholderText("Message Scout")).toBeInTheDocument();
    expect(screen.queryByText("An earlier conversation, read-only.")).not.toBeInTheDocument();
  });
});

describe("Chat — Stuck cards", () => {
  const CARD = makeStuckCard({ thread_id: "t-2" });
  const STUCK = makeMessage({
    id: "m-9", thread_id: "t-2", kind: "stuck", author_bot_id: "bot-1", created_at: "2026-10-14T10:02:00Z",
    body: stuckBody(CARD),
  });

  it("loads your open cards once and shows this chat's card with its buttons", async () => {
    stuckApi.listStuck.mockResolvedValue([CARD]);
    threadsApi.listMessages.mockResolvedValue([STUCK]);
    renderChat();
    const card = await screen.findByRole("group", { name: "Stuck on shop.example" });
    expect(within(card).getByRole("button", { name: "Take control" })).toBeInTheDocument();
    expect(stuckApi.listStuck).toHaveBeenCalledTimes(1);
  });

  it("a card that is no longer open shows only the bot's line", async () => {
    threadsApi.listMessages.mockResolvedValue([STUCK]);
    renderChat();
    expect(await screen.findByText(STUCK_LINE)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Take control" })).not.toBeInTheDocument();
  });

  it("a failed card list says why in the dock, and the chat still shows", async () => {
    stuckApi.listStuck.mockRejectedValue(new ApiError(500, "Could not load your Stuck cards."));
    threadsApi.listMessages.mockResolvedValue([STUCK]);
    renderChat();
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load your Stuck cards.");
    expect(screen.getByText(STUCK_LINE)).toBeInTheDocument();
  });

  it("shows New above the first unseen reply in the main chat, and none in an earlier conversation", async () => {
    localStorage.setItem("roost.chat-seen.v1", JSON.stringify({ "bot-1": "2026-10-14T10:00:30Z" }));
    threadsApi.listMessages.mockResolvedValue([
      makeMessage({ id: "m-1", thread_id: "t-2", role: "user", body: "hello", created_at: "2026-10-14T10:00:00Z" }),
      makeMessage({ id: "m-2", thread_id: "t-2", role: "bot", body: "fresh reply", seq: 2, created_at: "2026-10-14T10:05:00Z" }),
    ]);
    const first = renderChat();
    expect(await screen.findByRole("separator", { name: "New messages" })).toBeInTheDocument();
    first.unmount();
    renderChat("/bots/bot-1?thread=t-1");
    await screen.findByText("fresh reply");
    expect(screen.queryByRole("separator", { name: "New messages" })).not.toBeInTheDocument();
    localStorage.clear();
  });

  it("the composer is one pill with its + inside, and no later-update note", async () => {
    renderChat();
    const input = await screen.findByPlaceholderText("Message Scout");
    expect(screen.queryByRole("button", { name: "More for this chat" })).not.toBeInTheDocument();
    const leading = input.closest(".composer")?.querySelector(".composer__leading");
    expect(leading?.querySelector("button[aria-label='Add to the chat']")).not.toBeNull();
    expect(screen.queryByText(/later update/)).not.toBeInTheDocument();
  });

  it("Reply puts the message's quote over the composer and sends it as reply_to", async () => {
    threadsApi.sendMessage.mockResolvedValue({ message_id: "m-9", queued: false });
    renderChat();
    expect(await screen.findByText("hello")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Reply" }));
    expect(screen.getByText("Replying to")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Cancel reply" }));
    expect(screen.queryByText("Replying to")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Reply" }));
    await userEvent.type(screen.getByPlaceholderText("Message Scout"), "why?{Enter}");
    expect(threadsApi.sendMessage).toHaveBeenCalledWith("t-2", "why?", "m-1", {});
    expect(await screen.findByLabelText("Replying to")).toHaveTextContent("hello");
    expect(screen.queryByText("Replying to")).not.toBeInTheDocument();
  });

  it("a dictated message sent as it landed goes out as spoken; one you edited does not", async () => {
    threadsApi.sendMessage.mockResolvedValue({ message_id: "m-9", queued: false });
    renderChat();
    await screen.findByPlaceholderText("Message Scout");
    await userEvent.click(screen.getByRole("button", { name: "Speak" }));
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(threadsApi.sendMessage).toHaveBeenLastCalledWith("t-2", "I goed home", undefined, { spoken: true });
    await userEvent.click(screen.getByRole("button", { name: "Speak" }));
    await userEvent.type(screen.getByPlaceholderText("Message Scout"), " now{Enter}");
    expect(threadsApi.sendMessage).toHaveBeenLastCalledWith("t-2", "I goed home now", undefined, {});
  });

  it("Call opens the call screen, whose turns go out as your own messages", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => (url === "/api/voice"
      ? new Response(JSON.stringify({ available: true, speakers: [], tones: [], speeds: [1] }))
      : new Response("{}", { status: 404 }))));
    Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia: vi.fn() } });
    vi.stubGlobal("AudioContext", class { resume = async () => undefined; });
    threadsApi.sendMessage.mockResolvedValue({ message_id: "m-9", queued: false });
    const user = userEvent.setup();
    renderChat();
    await user.click(await screen.findByRole("button", { name: "Call Scout" }));
    const dialog = await screen.findByRole("dialog", { name: "Call with Scout" });
    await user.click(within(dialog).getByRole("button", { name: "Say" }));
    expect(threadsApi.sendMessage).toHaveBeenCalledWith("t-2", "Add milk", undefined, {});
    await vi.waitFor(() => expect(document.title).toBe("sent m-9"));
    expect(await screen.findByText("Add milk")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "End call" }));
    expect(screen.queryByRole("dialog", { name: "Call with Scout" })).not.toBeInTheDocument();
    vi.unstubAllGlobals();
    resetVoiceInfo();
  });
});
