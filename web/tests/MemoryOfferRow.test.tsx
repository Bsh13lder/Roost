import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError } from "../src/api/client";
import type { MessageOut } from "../src/api/types";
import { MemoryOfferRow } from "../src/components/chat/MemoryOfferRow";
import { parseMemoryOffer } from "../src/lib/memoryOffer";
import { makeMessage } from "./fixtures";

// Plain functions, not spies: a spy that returns a rejected promise makes vitest report an unhandled rejection.
const api = vi.hoisted(() => ({
  remembered: [] as string[][],
  forgotten: [] as string[],
  remember: (_t: string, _m: string): Promise<unknown> => Promise.resolve({}),
  forget: (_id: string): Promise<void> => Promise.resolve(),
}));
vi.mock("../src/api/threads", () => ({
  rememberOffer: (t: string, m: string) => { api.remembered.push([t, m]); return api.remember(t, m); },
}));
vi.mock("../src/api/memories", () => ({ forgetMemory: (id: string) => { api.forgotten.push(id); return api.forget(id); } }));

const TEXT = "send me task alerts only, no budget alerts";
const body = (memoryId: string | null = null) => JSON.stringify({ text: TEXT, kind: "preference", importance: 5, memory_id: memoryId });
const offer = (raw = body()) => makeMessage({ id: "msg-9", thread_id: "th-1", role: "activity", kind: "memory_offer", tainted: true, author_bot_id: "bot-1", body: raw });
const accepted = (): { message: MessageOut; memory: { id: string } } => ({ message: offer(body("mem-7")), memory: { id: "mem-7" } });
const renderOffer = (message = offer()) => render(<ul><MemoryOfferRow message={message} /></ul>);

beforeEach(() => {
  api.remembered.length = 0;
  api.forgotten.length = 0;
  api.remember = () => Promise.resolve(accepted());
  api.forget = () => Promise.resolve();
});
afterEach(() => cleanup());

describe("parseMemoryOffer", () => {
  it("reads the offer's JSON and refuses anything else", () => {
    expect(parseMemoryOffer(body())).toEqual({ text: TEXT, kind: "preference", memory_id: null });
    expect(parseMemoryOffer(body("mem-1"))?.memory_id).toBe("mem-1");
    expect(parseMemoryOffer("nope")).toBeNull();
    expect(parseMemoryOffer(JSON.stringify({ text: "", kind: "fact" }))).toBeNull();
  });
});

describe("MemoryOfferRow", () => {
  it("says what was not remembered and why, with the from-web mark and Remember it", () => {
    renderOffer();
    expect(screen.getByText(`Not remembered: ${TEXT}. I read a web page in this run, so I can't save memories myself.`)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "From web content" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: `Remember it: ${TEXT}` })).toHaveTextContent("Remember it");
  });

  it("Remember it saves it and the line becomes Remembered with Undo", async () => {
    renderOffer();
    await userEvent.click(screen.getByRole("button", { name: /Remember it/ }));
    expect(api.remembered).toEqual([["th-1", "msg-9"]]);
    expect(await screen.findByText(`Remembered: ${TEXT}.`)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Undo/ }));
    expect(api.forgotten).toEqual(["mem-7"]);
    expect(await screen.findByText(`Forgot: ${TEXT}.`)).toBeInTheDocument();
  });

  it("a line already remembered shows Remembered and Undo after a reload", () => {
    renderOffer(offer(body("mem-3")));
    expect(screen.getByText(`Remembered: ${TEXT}.`)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: `Undo: forget ${TEXT}` })).toBeInTheDocument();
  });

  it("a refusal shows its sentence and keeps the button", async () => {
    api.remember = () => Promise.reject(new ApiError(422, "That looks like a password."));
    renderOffer();
    await userEvent.click(screen.getByRole("button", { name: /Remember it/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("That looks like a password.");
    expect(screen.getByRole("button", { name: /Remember it/ })).toBeInTheDocument();
  });

  it("a body that isn't an offer shows as a plain line with no button", () => {
    renderOffer(offer("not json"));
    expect(screen.getByText("Not remembered")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
