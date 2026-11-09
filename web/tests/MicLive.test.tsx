// Voice tuning D3/D4 in the composer: the words show as you speak (live partials), the final transcript takes their
// place, the check swaps in the cleaned words with the fixes marked above the box, Keep my words puts the raw ones
// back, and the send carries heard + fixes once the check came back.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Composer } from "../src/components/Composer";
import { KEEP_MY_WORDS_LABEL } from "../src/components/chat/SpokenFixStrip";
import { resetVoiceInfo } from "../src/lib/voiceInfo";

const INFO = { available: true, speakers: [], tones: [], speeds: [1] };
const SAID = "tell maka eremadse on what's up";
const CORRECTED = "tell Maka Eremadze on WhatsApp";
const FIXES = [{ wrong: "maka eremadse", right: "Maka Eremadze" }, { wrong: "what's up", right: "WhatsApp" }];

interface FakeProcessor { onaudioprocess: ((event: { inputBuffer: { getChannelData: () => Float32Array } }) => void) | null; connect: () => void; disconnect: () => void }

class FakeAudioContext {
  static last: FakeAudioContext | null = null;
  readonly sampleRate = 16_000;
  readonly destination = {};
  processor: FakeProcessor | null = null;
  readonly close = vi.fn(async () => undefined);
  constructor() { FakeAudioContext.last = this; }
  createMediaStreamSource() { return { connect: () => undefined }; }
  createScriptProcessor() {
    this.processor = { onaudioprocess: null, connect: () => undefined, disconnect: vi.fn() };
    return this.processor;
  }
}

const say = (samples: number) =>
  FakeAudioContext.last?.processor?.onaudioprocess?.({ inputBuffer: { getChannelData: () => new Float32Array(samples) } });

interface Served { partial: string; correct?: { corrected: string; fixes: typeof FIXES; changed: boolean }; hold?: boolean }

// `hold` keeps the correction's answer until `release()` is called, so "Checking…" can be seen.
function stubServer(served: Served) {
  const hits: { url: string; init?: RequestInit }[] = [];
  let release: () => void = () => undefined;
  const held = new Promise<void>((resolve) => { release = resolve; });
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    hits.push({ url, init });
    if (url === "/api/voice") return new Response(JSON.stringify(INFO));
    if (url.startsWith("/api/voice/partial")) return new Response(JSON.stringify({ text: served.partial }));
    if (url.startsWith("/api/voice/transcribe")) return new Response(JSON.stringify({ text: SAID }));
    if (url === "/api/voice/correct") {
      if (served.hold) await held;
      return new Response(JSON.stringify(served.correct ?? { corrected: SAID, fixes: [], changed: false }));
    }
    return new Response("{}", { status: 404 });
  }));
  return { hits, release: () => release() };
}

async function record(withSpeech = true) {
  await userEvent.click(await screen.findByRole("button", { name: "Speak a message" }));
  await screen.findByRole("button", { name: "Stop recording" });
  if (withSpeech) { say(16_000); say(16_000); } // two seconds at 16 kHz
}

beforeEach(() => {
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true, value: { getUserMedia: vi.fn(async () => ({ getTracks: () => [{ stop: vi.fn() }] })) },
  });
  vi.stubGlobal("AudioContext", FakeAudioContext);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  resetVoiceInfo();
  FakeAudioContext.last = null;
  Reflect.deleteProperty(navigator, "mediaDevices");
});

describe("live words while recording (D4)", () => {
  it("shows the partial's words in the box as the ear hears them, then the final words take their place", async () => {
    const { hits } = stubServer({ partial: "tell maka" });
    const onSend = vi.fn();
    render(<Composer onSend={onSend} voice={{ onError: vi.fn(), botId: "b1" }} />);
    const box = screen.getByRole("textbox");
    await userEvent.type(box, "Please");
    await record();
    await waitFor(() => expect(box).toHaveValue("Please tell maka"), { timeout: 3000 });
    expect(box).toHaveAttribute("readonly");
    const partials = hits.filter((hit) => hit.url.startsWith("/api/voice/partial"));
    expect(partials[0].url).toBe("/api/voice/partial?bot_id=b1");
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();   // not yours to send yet
    await userEvent.click(screen.getByRole("button", { name: "Stop recording" }));
    await waitFor(() => expect(box).toHaveValue(`Please ${SAID}`));
    expect(box).not.toHaveAttribute("readonly");
    expect(hits.find((hit) => hit.url.startsWith("/api/voice/transcribe"))?.url).toBe("/api/voice/transcribe?bot_id=b1");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(onSend).toHaveBeenCalledWith(`Please ${SAID}`, { spoken: true });   // no check asked: the server's turn
  });

  it("Cancel drops the live words too", async () => {
    stubServer({ partial: "tell maka" });
    render(<Composer onSend={vi.fn()} voice={{ onError: vi.fn(), botId: "b1" }} />);
    await record();
    await waitFor(() => expect(screen.getByRole("textbox")).toHaveValue("tell maka"), { timeout: 3000 });
    await userEvent.click(screen.getByRole("button", { name: "Cancel recording" }));
    expect(screen.getByRole("textbox")).toHaveValue("");
  });
});

describe("the check before the send (D3)", () => {
  it("swaps in the cleaned words with the fixes marked, and the send carries heard and fixes", async () => {
    const { hits, release } = stubServer({ partial: "", correct: { corrected: CORRECTED, fixes: FIXES, changed: true }, hold: true });
    const onSend = vi.fn();
    render(<Composer onSend={onSend} voice={{ onError: vi.fn(), botId: "b1", correct: true }} />);
    await record(false);
    await userEvent.click(screen.getByRole("button", { name: "Stop recording" }));
    await waitFor(() => expect(screen.getByRole("textbox")).toHaveValue(SAID));   // the raw words land first
    expect(await screen.findByText("Checking…")).toBeInTheDocument();
    release();
    await waitFor(() => expect(screen.getByRole("textbox")).toHaveValue(CORRECTED));
    expect(screen.queryByText("Checking…")).not.toBeInTheDocument();
    const strip = screen.getByRole("status", { name: "Corrected what you said" });
    expect(within(strip).getByText("maka eremadse")).toHaveClass("english-fix__wrong");
    expect(within(strip).getByText("WhatsApp")).toHaveClass("english-fix__right");
    expect(within(strip).getByText(`You said: ${SAID}`)).toBeInTheDocument();
    const correct = hits.find((hit) => hit.url === "/api/voice/correct");
    expect(JSON.parse(String(correct?.init?.body))).toEqual({ text: SAID, bot_id: "b1" });
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(onSend).toHaveBeenCalledWith(CORRECTED, { spoken: true, heard: SAID, fixes: FIXES });
    expect(screen.queryByRole("status", { name: "Corrected what you said" })).not.toBeInTheDocument();
  });

  it("Keep my words puts the raw transcript back, and the send says it was checked", async () => {
    stubServer({ partial: "", correct: { corrected: CORRECTED, fixes: FIXES, changed: true } });
    const onSend = vi.fn();
    render(<Composer onSend={onSend} voice={{ onError: vi.fn(), botId: "b1", correct: true }} />);
    await record(false);
    await userEvent.click(screen.getByRole("button", { name: "Stop recording" }));
    await waitFor(() => expect(screen.getByRole("textbox")).toHaveValue(CORRECTED));
    await userEvent.click(screen.getByRole("button", { name: KEEP_MY_WORDS_LABEL }));
    expect(screen.getByRole("textbox")).toHaveValue(SAID);
    expect(screen.queryByRole("status", { name: "Corrected what you said" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(onSend).toHaveBeenCalledWith(SAID, { spoken: true, heard: SAID, fixes: [] });
  });

  it("a fine sentence stays, the send still says it was checked, and an edit makes it typed", async () => {
    stubServer({ partial: "" });
    const onSend = vi.fn();
    render(<Composer onSend={onSend} voice={{ onError: vi.fn(), botId: "b1", correct: true }} />);
    await record(false);
    await userEvent.click(screen.getByRole("button", { name: "Stop recording" }));
    await waitFor(() => expect(screen.getByRole("textbox")).toHaveValue(SAID));
    await waitFor(() => expect(screen.queryByText("Checking…")).not.toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(onSend).toHaveBeenCalledWith(SAID, { spoken: true, heard: SAID, fixes: [] });
    await record(false);
    await userEvent.click(screen.getByRole("button", { name: "Stop recording" }));
    await waitFor(() => expect(screen.getByRole("textbox")).toHaveValue(SAID));
    await userEvent.type(screen.getByRole("textbox"), " now{Enter}");
    expect(onSend).toHaveBeenLastCalledWith(`${SAID} now`, { spoken: false });
  });

  it("with the switch off nothing is checked", async () => {
    const { hits } = stubServer({ partial: "" });
    render(<Composer onSend={vi.fn()} voice={{ onError: vi.fn(), botId: "b1", correct: false }} />);
    await record(false);
    await userEvent.click(screen.getByRole("button", { name: "Stop recording" }));
    await waitFor(() => expect(screen.getByRole("textbox")).toHaveValue(SAID));
    expect(hits.some((hit) => hit.url === "/api/voice/correct")).toBe(false);
  });
});
