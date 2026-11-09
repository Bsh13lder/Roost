import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, renderHook } from "@testing-library/react";
import type { BotOut, MessageOut } from "../src/api/types";
import { makeBot, makeMessage } from "./fixtures";

const speakMessage = vi.fn(async (_thread: string, _message: string) => undefined);
vi.mock("../src/store/speech", () => ({ speakMessage: (t: string, m: string) => speakMessage(t, m) }));

const { isSpokenReply, useReadAloud } = await import("../src/hooks/useReadAloud");

const READER = makeBot({ id: "bot-1", voice: { speaker: "aiden", tone: "calm", speed: 1.25, read_aloud: true } });
const QUIET = makeBot({ id: "bot-1" });

const reply = (overrides: Partial<MessageOut> = {}) =>
  makeMessage({ id: "m-9", thread_id: "t-1", seq: 7, author_bot_id: "bot-1", ...overrides });

interface Props { thread: string; messages: readonly MessageOut[]; bots: Record<string, BotOut>; bot: BotOut | null }

function mount(initial: Partial<Props> = {}) {
  const props: Props = { thread: "t-1", messages: [], bots: {}, bot: READER, ...initial };
  return renderHook((p: Props) => useReadAloud(p.thread, p.messages, p.bots, p.bot), { initialProps: props });
}

let visibility: DocumentVisibilityState = "visible";
beforeEach(() => {
  visibility = "visible";
  vi.spyOn(document, "visibilityState", "get").mockImplementation(() => visibility);
});
afterEach(() => {
  cleanup();
  speakMessage.mockReset();
  vi.restoreAllMocks();
});

describe("Read replies aloud (voice V3)", () => {
  it("plays a reply that arrives in the open chat from a bot with read aloud on, once", () => {
    const view = mount();
    const placeholder = reply({ seq: 0, body: "" });
    view.rerender({ thread: "t-1", messages: [placeholder], bots: {}, bot: READER });
    expect(speakMessage).not.toHaveBeenCalled(); // still being written
    const stored = [reply()];
    view.rerender({ thread: "t-1", messages: stored, bots: {}, bot: READER });
    view.rerender({ thread: "t-1", messages: [...stored], bots: {}, bot: READER });
    expect(speakMessage).toHaveBeenCalledTimes(1);
    expect(speakMessage).toHaveBeenCalledWith("t-1", "m-9");
  });

  it("never plays what the chat already held when it opened", () => {
    const view = mount({ messages: [reply({ id: "old" })] });
    view.rerender({ thread: "t-1", messages: [reply({ id: "old" })], bots: {}, bot: READER });
    expect(speakMessage).not.toHaveBeenCalled();
  });

  it("plays a Report too", () => {
    const view = mount();
    view.rerender({ thread: "t-1", messages: [reply({ kind: "report", body: "{}" })], bots: {}, bot: READER });
    expect(speakMessage).toHaveBeenCalledWith("t-1", "m-9");
  });

  it("never for your own message, a card, or while the page is hidden", () => {
    const view = mount();
    view.rerender({ thread: "t-1", messages: [reply({ id: "u", role: "user", author_bot_id: null })], bots: {}, bot: READER });
    view.rerender({ thread: "t-1", messages: [reply({ id: "s", kind: "stuck" })], bots: {}, bot: READER });
    visibility = "hidden";
    view.rerender({ thread: "t-1", messages: [reply({ id: "h" })], bots: {}, bot: READER });
    expect(speakMessage).not.toHaveBeenCalled();
  });

  it("not when the bot's switch is off; the live copy of the author decides", () => {
    const view = mount({ bot: QUIET });
    view.rerender({ thread: "t-1", messages: [reply({ id: "a" })], bots: {}, bot: QUIET });
    expect(speakMessage).not.toHaveBeenCalled();
    view.rerender({ thread: "t-1", messages: [reply({ id: "b" })], bots: { "bot-1": READER }, bot: QUIET });
    expect(speakMessage).toHaveBeenCalledWith("t-1", "b");
    view.rerender({ thread: "t-1", messages: [reply({ id: "c" })], bots: { "bot-1": QUIET }, bot: READER });
    expect(speakMessage).toHaveBeenCalledTimes(1);
  });

  it("another chat starts fresh: what it held is never played", () => {
    const view = mount();
    view.rerender({ thread: "t-2", messages: [reply({ id: "x", thread_id: "t-2" })], bots: {}, bot: READER });
    expect(speakMessage).not.toHaveBeenCalled();
    view.rerender({ thread: "t-2", messages: [reply({ id: "x", thread_id: "t-2" }), reply({ id: "y", thread_id: "t-2" })], bots: {}, bot: READER });
    expect(speakMessage).toHaveBeenCalledWith("t-2", "y");
  });

  it("a blocked autoplay is left alone: no retry", async () => {
    speakMessage.mockRejectedValueOnce(new DOMException("blocked", "NotAllowedError"));
    vi.spyOn(console, "info").mockImplementation(() => undefined);
    const view = mount();
    view.rerender({ thread: "t-1", messages: [reply()], bots: {}, bot: READER });
    await Promise.resolve();
    view.rerender({ thread: "t-1", messages: [reply()], bots: {}, bot: READER });
    expect(speakMessage).toHaveBeenCalledTimes(1);
  });

  it("isSpokenReply picks only a stored bot reply or Report", () => {
    expect(isSpokenReply(reply())).toBe(true);
    expect(isSpokenReply(reply({ seq: 0 }))).toBe(false);
    expect(isSpokenReply(reply({ kind: "approval" }))).toBe(false);
  });
});

describe("Read replies aloud during a call", () => {
  it("is paused while the call speaks the reply itself, and that reply never plays later", () => {
    const view = renderHook((p: Props & { paused: boolean }) => useReadAloud(p.thread, p.messages, p.bots, p.bot, p.paused),
      { initialProps: { thread: "t-1", messages: [], bots: {}, bot: READER, paused: true } });
    view.rerender({ thread: "t-1", messages: [reply({ id: "in-call" })], bots: {}, bot: READER, paused: true });
    expect(speakMessage).not.toHaveBeenCalled();
    view.rerender({ thread: "t-1", messages: [reply({ id: "in-call" })], bots: {}, bot: READER, paused: false });
    expect(speakMessage).not.toHaveBeenCalled();
    view.rerender({ thread: "t-1", messages: [reply({ id: "in-call" }), reply({ id: "after" })], bots: {}, bot: READER, paused: false });
    expect(speakMessage).toHaveBeenCalledWith("t-1", "after");
  });
});
