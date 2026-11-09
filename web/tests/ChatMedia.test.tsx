import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { Chat } from "../src/pages/Chat";
import { MessageMedia } from "../src/components/chat/MessageMedia";
import { frameTimes } from "../src/lib/videoFrames";
import { ApiError } from "../src/api/client";
import { makeBot } from "./fixtures";

const threadsApi = vi.hoisted(() => ({ listThreads: vi.fn(), openChat: vi.fn(), listMessages: vi.fn(), sendMessage: vi.fn() }));
vi.mock("../src/api/threads", () => ({
  listThreads: (id: string) => threadsApi.listThreads(id), openChat: (id: string) => threadsApi.openChat(id),
  listMessages: (id: string) => threadsApi.listMessages(id), sendMessage: (...a: unknown[]) => threadsApi.sendMessage(...a),
}));
const mediaApi = vi.hoisted(() => ({ uploadMedia: vi.fn() }));
vi.mock("../src/api/media", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../src/api/media")>()),
  uploadMedia: (...a: unknown[]) => mediaApi.uploadMedia(...a),
}));
const frames = vi.hoisted(() => ({ grabFrames: vi.fn() }));
vi.mock("../src/lib/videoFrames", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../src/lib/videoFrames")>()),
  grabFrames: (...a: unknown[]) => frames.grabFrames(...a),
}));
vi.mock("../src/api/bots", () => ({ getBot: () => Promise.resolve(makeBot({ id: "bot-1", name: "Scout" })) }));
vi.mock("../src/api/stuck", () => ({ listStuck: () => Promise.resolve([]) }));
vi.mock("../src/api/approvals", () => ({ listApprovals: () => Promise.resolve([]) }));
vi.mock("../src/api/computer", () => ({ getControl: () => Promise.resolve({ held: false, since: null }) }));
vi.mock("../src/hooks/useLiveStore", () => ({
  useLiveState: () => ({
    cursor: 0, bots: {}, messagesByThread: {}, streaming: {}, boardVersion: { tasks: 0, money: 0, notes: 0, documents: 0 },
    stuckCards: {},
  }),
}));

const thread = { id: "t-1", bot_id: "bot-1", title: null, kind: "chat", created_at: "2026-11-05T10:00:00Z", updated_at: "2026-11-05T10:00:00Z" };
const photo = (name: string) => new File([new Uint8Array([0xff, 0xd8, 0xff])], name, { type: "image/jpeg" });

beforeEach(() => {
  threadsApi.listThreads.mockResolvedValue([thread]);
  threadsApi.openChat.mockResolvedValue(thread);
  threadsApi.listMessages.mockResolvedValue([]);
  threadsApi.sendMessage.mockResolvedValue({ message_id: "u-9", queued: false });
  let n = 0;
  mediaApi.uploadMedia.mockImplementation(() => { n += 1; return Promise.resolve({ id: `p${n}`, width: 10, height: 10 }); });
  URL.createObjectURL = vi.fn(() => "blob:local");
  URL.revokeObjectURL = vi.fn();
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

async function openChat() {
  render(<MemoryRouter initialEntries={["/bots/bot-1"]}><Routes><Route path="/bots/:botId" element={<Chat />} /></Routes></MemoryRouter>);
  await screen.findByRole("heading", { name: "Scout" });
}

describe("pictures in the chat", () => {
  it("+ offers pictures and a video beside Choose file", async () => {
    await openChat();
    await userEvent.click(screen.getByRole("button", { name: "Add to the chat" }));
    expect(screen.getAllByRole("menuitem").map((item) => item.textContent))
      .toEqual(["Attach pictures", "Attach a video", "Choose file", "Save a password"]);
  });

  it("pictures wait above the composer, one can be removed, and Send uploads them then sends", async () => {
    await openChat();
    await userEvent.upload(screen.getByLabelText("Attach pictures"), [photo("a.jpg"), photo("b.jpg")]);
    expect(screen.getAllByRole("img", { name: /to send$/ })).toHaveLength(2);
    await userEvent.click(screen.getByRole("button", { name: "Remove picture 1" }));
    expect(screen.getAllByRole("img", { name: /to send$/ })).toHaveLength(1);
    await userEvent.type(screen.getByPlaceholderText("Message Scout"), "What is this?{Enter}");
    expect(mediaApi.uploadMedia).toHaveBeenCalledTimes(1);
    expect(mediaApi.uploadMedia.mock.calls[0][0]).toBe("t-1");
    expect(mediaApi.uploadMedia.mock.calls[0][2]).toBe(false);
    expect(threadsApi.sendMessage).toHaveBeenCalledWith("t-1", "What is this?", undefined, { mediaIds: ["p1"] });
    expect(screen.queryByRole("img", { name: /to send$/ })).not.toBeInTheDocument();
  });

  it("pictures alone can be sent with no words", async () => {
    await openChat();
    await userEvent.upload(screen.getByLabelText("Attach pictures"), photo("a.jpg"));
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(threadsApi.sendMessage).toHaveBeenCalledWith("t-1", "", undefined, { mediaIds: ["p1"] });
  });

  it("a video sends its frames in order, each marked as video", async () => {
    frames.grabFrames.mockResolvedValue([1, 2, 3, 4, 5, 6, 7, 8].map((i) => new Blob([String(i)], { type: "image/jpeg" })));
    await openChat();
    await userEvent.upload(screen.getByLabelText("Attach a video"), new File(["v"], "clip.mp4", { type: "video/mp4" }));
    expect(await screen.findByText("Video · 8 frames")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(mediaApi.uploadMedia).toHaveBeenCalledTimes(8);
    expect(mediaApi.uploadMedia.mock.calls.every((call) => call[2] === true)).toBe(true);
    expect(threadsApi.sendMessage).toHaveBeenCalledWith("t-1", "", undefined,
      { mediaIds: ["p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8"] });
  });

  it("a failed upload keeps the pictures and the words and says why", async () => {
    mediaApi.uploadMedia.mockRejectedValueOnce(new ApiError(413, "That picture is too big."));
    await openChat();
    await userEvent.upload(screen.getByLabelText("Attach pictures"), photo("a.jpg"));
    const box = screen.getByPlaceholderText("Message Scout");
    await userEvent.type(box, "Read it{Enter}");
    expect(await screen.findByText("That picture is too big.")).toBeInTheDocument();
    expect(threadsApi.sendMessage).not.toHaveBeenCalled();
    expect(box).toHaveValue("Read it");
    expect(screen.getAllByRole("img", { name: /to send$/ })).toHaveLength(1);
  });
});

describe("a message's pictures", () => {
  const ref = (id: string, group: "video" | null = null, source: "you" | "bot" = "you") =>
    ({ id, width: 640, height: 480, source, group });

  it("photos load lazily from the gateway and open full size", async () => {
    render(<MessageMedia media={[ref("a"), ref("b")]} />);
    const first = screen.getByRole("img", { name: "Picture 1" });
    expect(first).toHaveAttribute("src", "/api/media/a");
    expect(first).toHaveAttribute("loading", "lazy");
    await userEvent.click(screen.getByRole("button", { name: "Open picture 2" }));
    const viewer = screen.getByRole("dialog", { name: "Pictures" });
    expect(within(viewer).getByRole("img", { name: "Picture 2 of 2" })).toHaveAttribute("src", "/api/media/b");
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("a video shows as one strip with its frame count", () => {
    render(<MessageMedia media={[1, 2, 3, 4, 5, 6, 7, 8].map((i) => ref(`v${i}`, "video"))} />);
    expect(screen.getByText("Video · 8 frames")).toBeInTheDocument();
  });

  it("frames are taken evenly across the clip", () => {
    expect(frameTimes(16, 8)).toEqual([1, 3, 5, 7, 9, 11, 13, 15]);
    expect(frameTimes(0, 8)).toEqual([]);
  });
});
