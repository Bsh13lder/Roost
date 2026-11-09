import { afterEach, describe, expect, it, vi } from "vitest";
import { endCall, lineUrl, liveSpeechPartUrl, liveSpeechPlan, startCall, transcribe, warmVoice } from "../src/api/voice";
import { sendMessage } from "../src/api/threads";

interface Hit { url: string; init?: RequestInit }

function stub(status = 200, body: unknown = { ok: true }) {
  const hits: Hit[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    hits.push({ url, init });
    return new Response(JSON.stringify(body), { status });
  }));
  return hits;
}

const bodyOf = (hit: Hit) => JSON.parse(hit.init?.body as string) as unknown;

afterEach(() => vi.unstubAllGlobals());

describe("the call's API (contracts A–C)", () => {
  it("warm names the bot whose lines to pre-make, or sends an empty body", async () => {
    const hits = stub();
    await warmVoice("b1");
    expect(hits[0].url).toBe("/api/voice/warm");
    expect(bodyOf(hits[0])).toEqual({ bot_id: "b1" });
    await warmVoice();
    expect(bodyOf(hits[1])).toEqual({});
  });

  it("starts or beats a call, with the message it cut off", async () => {
    const hits = stub(200, { ok: true, expires_in: 60 });
    await expect(startCall("t-1")).resolves.toEqual({ ok: true, expires_in: 60 });
    expect(hits[0].url).toBe("/api/threads/t-1/call");
    expect(hits[0].init?.method).toBe("POST");
    expect(bodyOf(hits[0])).toEqual({});
    await startCall("t-1", "m-9");
    expect(bodyOf(hits[1])).toEqual({ interrupted: "m-9" });
  });

  it("ends a call", async () => {
    const hits = stub();
    await endCall("t-1");
    expect(hits[0]).toMatchObject({ url: "/api/threads/t-1/call", init: expect.objectContaining({ method: "DELETE" }) });
  });

  it("knows the live-speech and fixed-line addresses", async () => {
    const hits = stub(200, { parts: 2, done: false, speed: 1 });
    await expect(liveSpeechPlan("t-1", "m-1")).resolves.toEqual({ parts: 2, done: false, speed: 1 });
    expect(hits[0].url).toBe("/api/threads/t-1/live-speech/m-1");
    expect(liveSpeechPartUrl("t-1", "m-1", 3)).toBe("/api/threads/t-1/live-speech/m-1/3");
    expect(lineUrl("b1", "say_again")).toBe("/api/bots/b1/voice/line/say_again");
  });

  it("transcribe can be cut short with a signal", async () => {
    const hits = stub(200, { text: "hi" });
    const controller = new AbortController();
    await transcribe(new Blob(["x"], { type: "audio/wav" }), controller.signal);
    expect(hits[0].init?.signal).toBe(controller.signal);
  });
});

describe("sendMessage's call flag", () => {
  it("marks a call turn, and leaves an ordinary message as it was", async () => {
    const hits = stub(200, { message_id: "m", status: "started", queued: false, mentioned: [] });
    await sendMessage("t-1", "hello", null, { call: true });
    expect(bodyOf(hits[0])).toEqual({ text: "hello", call: true });
    await sendMessage("t-1", "hello");
    expect(bodyOf(hits[1])).toEqual({ text: "hello" });
    await sendMessage("t-1", "hello", "q-1", { call: false });
    expect(bodyOf(hits[2])).toEqual({ text: "hello", reply_to: "q-1" });
  });

  it("marks a message whose words came from the voice service as spoken (a call turn is both)", async () => {
    const hits = stub(200, { message_id: "m", status: "started", queued: false, mentioned: [] });
    await sendMessage("t-1", "hello", null, { spoken: true });
    expect(bodyOf(hits[0])).toEqual({ text: "hello", spoken: true });
    await sendMessage("t-1", "hello", null, { call: true, spoken: true });
    expect(bodyOf(hits[1])).toEqual({ text: "hello", call: true, spoken: true });
    await sendMessage("t-1", "hello", null, { spoken: false });
    expect(bodyOf(hits[2])).toEqual({ text: "hello" });
  });
});
