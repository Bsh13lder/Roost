// Voice tuning (docs/plans/2026-11-06-roost-voice-tuning.md): the ear is told which bot you speak to, the live partial
// goes to its own route, the correction asks the worker before the send, and a checked send carries heard + fixes.
import { afterEach, describe, expect, it, vi } from "vitest";
import { correctSpeech, partialTranscribe, transcribe } from "../src/api/voice";
import { sendMessage } from "../src/api/threads";

interface Hit { url: string; init?: RequestInit }

function stub(body: unknown = { text: "hi" }) {
  const hits: Hit[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    hits.push({ url, init });
    return new Response(JSON.stringify(body), { status: 200 });
  }));
  return hits;
}

const wav = new Blob([new Uint8Array(44)], { type: "audio/wav" });
const bodyOf = (hit: Hit) => JSON.parse(hit.init?.body as string) as unknown;

afterEach(() => vi.unstubAllGlobals());

describe("hearing with a bot (D1/D2/D4)", () => {
  it("transcribe names the bot in the query, or nothing", async () => {
    const hits = stub();
    await transcribe(wav, undefined, "b 1");
    expect(hits[0].url).toBe("/api/voice/transcribe?bot_id=b%201");
    await transcribe(wav);
    expect(hits[1].url).toBe("/api/voice/transcribe");
    expect(hits[0].init?.method).toBe("POST");
    expect((hits[0].init?.headers as Record<string, string>)["Content-Type"]).toBe("audio/wav");
  });

  it("a partial goes to the live route with the bot and an abort signal", async () => {
    const hits = stub({ text: "Tell Maka" });
    const abort = new AbortController();
    await expect(partialTranscribe(wav, "b1", abort.signal)).resolves.toEqual({ text: "Tell Maka" });
    expect(hits[0].url).toBe("/api/voice/partial?bot_id=b1");
    expect(hits[0].init?.signal).toBe(abort.signal);
  });
});

describe("the correction before the send (D3)", () => {
  it("asks for the cleaned words with the bot", async () => {
    const hits = stub({ corrected: "On WhatsApp", fixes: [{ wrong: "what's up", right: "WhatsApp" }], changed: true });
    await expect(correctSpeech("On what's up", "b1")).resolves.toEqual({
      corrected: "On WhatsApp", fixes: [{ wrong: "what's up", right: "WhatsApp" }], changed: true,
    });
    expect(hits[0].url).toBe("/api/voice/correct");
    expect(bodyOf(hits[0])).toEqual({ text: "On what's up", bot_id: "b1" });
  });

  it("a checked send carries heard and fixes; a plain spoken one only spoken; a typed one neither", async () => {
    const hits = stub({ message_id: "m1", status: "started" });
    await sendMessage("t1", "On WhatsApp", null, { spoken: true, heard: "On what's up", fixes: [{ wrong: "what's up", right: "WhatsApp" }] });
    expect(bodyOf(hits[0])).toEqual({ text: "On WhatsApp", spoken: true, heard: "On what's up", fixes: [{ wrong: "what's up", right: "WhatsApp" }] });
    await sendMessage("t1", "On WhatsApp", null, { spoken: true });
    expect(bodyOf(hits[1])).toEqual({ text: "On WhatsApp", spoken: true });
    await sendMessage("t1", "On WhatsApp", null, { heard: "x", fixes: [] });   // not spoken: heard means nothing
    expect(bodyOf(hits[2])).toEqual({ text: "On WhatsApp" });
  });
});
