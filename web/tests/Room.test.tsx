import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { Room } from "../src/pages/Room";
import { makeBot, makeMessage } from "./fixtures";

const getRoomMock = vi.fn();
const listRoomMessagesMock = vi.fn();
const postRoomMessageMock = vi.fn();
vi.mock("../src/api/rooms", () => ({
  getRoom: (...a: unknown[]) => getRoomMock(...a),
  listRoomMessages: (...a: unknown[]) => listRoomMessagesMock(...a),
  postRoomMessage: (...a: unknown[]) => postRoomMessageMock(...a),
}));
const listBotsMock = vi.fn();
vi.mock("../src/api/bots", () => ({ listBots: (...a: unknown[]) => listBotsMock(...a) }));
vi.mock("../src/hooks/useLiveStore", () => ({
  useLiveState: () => ({ cursor: 0, bots: {}, messagesByThread: {}, streaming: {} }),
}));
// Final-review fix: opening a room preloads the markdown renderer. The rest of RichText stays real.
const preloadMarkdown = vi.hoisted(() => vi.fn(() => Promise.resolve()));
vi.mock("../src/components/chat/RichText", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../src/components/chat/RichText")>()), preloadMarkdown,
}));

const CHIEF = makeBot({ id: "c", name: "Chief" });
const SCOUT = makeBot({ id: "s", name: "Scout", avatar: { shape: "wide", color: "#3b82f6", badge: "none" } });
const ROOM = { id: "r1", name: "Saturday", coordinator_id: "c", member_ids: ["c", "s"], thread_id: "rt", created_at: "x", updated_at: "x" };

beforeEach(() => {
  getRoomMock.mockReset().mockResolvedValue(ROOM);
  listBotsMock.mockReset().mockResolvedValue([CHIEF, SCOUT]);
  listRoomMessagesMock.mockReset().mockResolvedValue([
    makeMessage({ id: "u", thread_id: "rt", role: "user", body: "plan Saturday" }),
    makeMessage({ id: "h", thread_id: "rt", role: "activity", kind: "handoff", body: "Chief → Scout: price it" }),
    makeMessage({ id: "a", thread_id: "rt", author_bot_id: "c", body: "Plan: 52 EUR" }),
  ]);
  postRoomMessageMock.mockReset().mockResolvedValue({ message_id: "m2", routed_to: ["s"] });
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(() => cleanup());

function renderRoom() {
  render(
    <MemoryRouter initialEntries={["/rooms/r1"]}>
      <Routes>
        <Route path="/rooms/:roomId" element={<Room />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Room", () => {
  it("shows the room, its members with the coordinator, and who said what", async () => {
    renderRoom();
    expect(await screen.findByRole("heading", { name: "Saturday" })).toBeInTheDocument();
    const members = screen.getByRole("list", { name: "Members" });
    expect(members).toHaveTextContent("Chief");
    expect(members).toHaveTextContent("coordinator");
    expect(screen.getByText("Chief → Scout: price it").closest("li")).toHaveClass("message--handoff");
    expect(screen.getByText("Plan: 52 EUR").closest("li")).toHaveTextContent("Chief");
  });

  it("preloads the markdown renderer as soon as it opens, before any message is loaded", () => {
    preloadMarkdown.mockClear();
    getRoomMock.mockReturnValue(new Promise(() => undefined));
    renderRoom();
    expect(screen.getByText("Loading…")).toBeInTheDocument();
    expect(preloadMarkdown).toHaveBeenCalledTimes(1);
  });

  it("leads back to the chat list, the only way home on a phone (S1.4)", async () => {
    renderRoom();
    await screen.findByRole("heading", { name: "Saturday" });
    expect(screen.getByRole("link", { name: "Back to chats" })).toHaveAttribute("href", "/");
  });

  it("posts to the room", async () => {
    renderRoom();
    const box = await screen.findByPlaceholderText("Message the room… (@ to mention)");
    await userEvent.type(box, "thanks{Enter}");
    expect(postRoomMessageMock).toHaveBeenCalledWith("r1", "thanks");
    expect(await screen.findByText("thanks")).toBeInTheDocument();
  });

  it("Reply on a bot's message sends the follow-up to that bot", async () => {
    renderRoom();
    await userEvent.click(await screen.findByRole("button", { name: "Reply to Chief" }));
    const box = screen.getByPlaceholderText("Message the room… (@ to mention)");
    expect(box).toHaveFocus();
    await userEvent.type(box, "and the drinks?{Enter}");
    expect(postRoomMessageMock).toHaveBeenCalledWith("r1", "@Chief and the drinks?");
    expect(screen.getAllByRole("button", { name: /^Reply to/ })).toHaveLength(1); // bot messages only
  });
});
