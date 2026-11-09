import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { VoiceSection, speedLabel, voiceSummary } from "../src/components/profile/VoiceSection";
import { resetVoiceInfo } from "../src/lib/voiceInfo";
import { resetSpeech } from "../src/store/speech";
import type { BotOut } from "../src/api/types";
import { makeBot } from "./fixtures";

const INFO = {
  available: true,
  speakers: [{ id: "aiden", name: "Aiden", best_in: "English" }, { id: "ono_anna", name: "Ono Anna", best_in: "Japanese" }],
  tones: [{ id: "natural", name: "Natural" }, { id: "calm", name: "Calm" }],
  speeds: [0.75, 1, 1.25, 2],
  languages: [{ id: "auto", name: "Auto-detect" }, { id: "en", name: "English" }, { id: "es", name: "Spanish" }],
};
const BOT = makeBot({ voice: { speaker: "aiden", tone: "natural", speed: 1.25, read_aloud: false, correct_english: false } });
// What a save PUTs (voice tuning D2/D3): the whole object, the switch under both names and the language.
const whole = (over: Partial<BotOut["voice"]> = {}) => ({
  speaker: "aiden", tone: "natural", speed: 1.25, read_aloud: false, correct_speech: false, correct_english: false,
  language: "auto", ...over,
});

let puts: unknown[];
let fetched: string[];

function stubServer(available = true) {
  puts = [];
  fetched = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    fetched.push(url);
    if (url === "/api/voice") return new Response(JSON.stringify({ ...INFO, available }));
    if (init?.method === "PUT") {
      const body = JSON.parse(String(init.body)) as BotOut["voice"];
      puts.push(body);
      return new Response(JSON.stringify(makeBot({ voice: body })));
    }
    if (url.includes("/voice/sample")) return new Response(new Blob(["wav"], { type: "audio/wav" }));
    return new Response("{}", { status: 404 });
  }));
}

beforeEach(() => {
  vi.spyOn(window.HTMLMediaElement.prototype, "play").mockImplementation(() => Promise.resolve());
  vi.spyOn(window.HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
  URL.createObjectURL = vi.fn(() => "blob:sample");
  URL.revokeObjectURL = vi.fn();
});
afterEach(() => {
  cleanup();
  resetSpeech();
  resetVoiceInfo();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("the Voice fold (voice V3)", () => {
  it("shows the bot's voice, tone and speed", async () => {
    stubServer();
    render(<VoiceSection bot={BOT} onChange={vi.fn()} />);
    expect(await screen.findByRole("combobox", { name: "Voice" })).toHaveTextContent("Aiden");
    expect(screen.getByRole("combobox", { name: "Tone" })).toHaveTextContent("Natural");
    expect(screen.getByRole("combobox", { name: "Speed" })).toHaveTextContent("1.25×");
    expect(screen.getByRole("switch", { name: "Read replies aloud" })).toHaveAttribute("aria-checked", "false");
  });

  it('lists each voice with "best in" its language', async () => {
    stubServer();
    render(<VoiceSection bot={BOT} onChange={vi.fn()} />);
    await userEvent.click(await screen.findByRole("combobox", { name: "Voice" }));
    expect(await screen.findByRole("option", { name: /Ono Anna/ })).toHaveTextContent("Ono Annabest in Japanese");
  });

  it("each change PUTs the whole object and hands back the saved bot", async () => {
    stubServer();
    const onChange = vi.fn();
    render(<VoiceSection bot={BOT} onChange={onChange} />);
    await userEvent.click(await screen.findByRole("combobox", { name: "Tone" }));
    await userEvent.click(await screen.findByRole("option", { name: "Calm" }));
    await waitFor(() => expect(puts).toEqual([whole({ tone: "calm" })]));
    await userEvent.click(screen.getByRole("switch", { name: "Read replies aloud" }));
    await waitFor(() => expect(puts[1]).toEqual(whole({ read_aloud: true })));
    await userEvent.click(screen.getByRole("combobox", { name: "Speed" }));
    await userEvent.click(await screen.findByRole("option", { name: "2.0×" }));
    await waitFor(() => expect(puts[2]).toEqual(whole({ speed: 2 })));
    expect(onChange).toHaveBeenCalledTimes(3);
    expect(fetched.filter((url) => url === "/api/bots/bot-1/voice")).toHaveLength(3);
  });

  it('has a "Correct what I say" switch with its hint, saved with the rest; an older server\'s bot reads as off', async () => {
    stubServer();
    const onChange = vi.fn();
    const { speaker, tone, speed, read_aloud } = BOT.voice;
    render(<VoiceSection bot={makeBot({ voice: { speaker, tone, speed, read_aloud } })} onChange={onChange} />);
    const correct = await screen.findByRole("switch", { name: "Correct what I say" });
    expect(correct).toHaveAttribute("aria-checked", "false");
    expect(screen.getByText(/corrected copy of what you say, in any language/)).toHaveClass("info-row__hint");
    await userEvent.click(correct);
    await waitFor(() => expect(puts).toEqual([whole({ correct_speech: true, correct_english: true })]));
    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it("shows the switch on when the bot's voice has it on, under either name", async () => {
    stubServer();
    render(<VoiceSection bot={makeBot({ voice: { ...BOT.voice, correct_english: true } })} onChange={vi.fn()} />);
    expect(await screen.findByRole("switch", { name: "Correct what I say" })).toHaveAttribute("aria-checked", "true");
    cleanup();
    render(<VoiceSection bot={makeBot({ voice: { ...BOT.voice, correct_speech: true } })} onChange={vi.fn()} />);
    expect(await screen.findByRole("switch", { name: "Correct what I say" })).toHaveAttribute("aria-checked", "true");
  });

  it('has an "I speak" pick: Auto-detect, or a language the ear supports (voice tuning D2)', async () => {
    stubServer();
    render(<VoiceSection bot={BOT} onChange={vi.fn()} />);
    const pick = await screen.findByRole("combobox", { name: "I speak" });
    expect(pick).toHaveTextContent("Auto-detect");
    await userEvent.click(pick);
    expect(screen.queryByRole("option", { name: "Georgian" })).not.toBeInTheDocument();
    await userEvent.click(await screen.findByRole("option", { name: "Spanish" }));
    await waitFor(() => expect(puts).toEqual([whole({ language: "es" })]));
  });

  it("shows the bot's language, and no pick at all on a server without languages", async () => {
    stubServer();
    render(<VoiceSection bot={makeBot({ voice: { ...BOT.voice, language: "es" } })} onChange={vi.fn()} />);
    expect(await screen.findByRole("combobox", { name: "I speak" })).toHaveTextContent("Spanish");
    cleanup();
    resetVoiceInfo();
    const { languages: _languages, ...older } = INFO;
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(older))));
    render(<VoiceSection bot={BOT} onChange={vi.fn()} />);
    await screen.findByRole("combobox", { name: "Voice" });
    expect(screen.queryByRole("combobox", { name: "I speak" })).not.toBeInTheDocument();
  });

  it("Try it plays the sample for the chosen voice and tone at the chosen speed", async () => {
    stubServer();
    render(<VoiceSection bot={makeBot({ voice: { speaker: "ono_anna", tone: "calm", speed: 0.75, read_aloud: false } })} onChange={vi.fn()} />);
    await userEvent.click(await screen.findByRole("button", { name: "Try it" }));
    await waitFor(() => expect(fetched).toContain("/api/bots/bot-1/voice/sample?speaker=ono_anna&tone=calm"));
    await waitFor(() => expect(window.HTMLMediaElement.prototype.play).toHaveBeenCalled());
    const element = vi.mocked(window.HTMLMediaElement.prototype.play).mock.contexts[0] as HTMLMediaElement;
    expect(element.playbackRate).toBe(0.75);
    expect(await screen.findByRole("button", { name: "Stop" })).toBeInTheDocument();
  });

  it("with voice off on the Mac: one quiet line, the controls readable but disabled", async () => {
    stubServer(false);
    render(<VoiceSection bot={BOT} onChange={vi.fn()} />);
    expect(await screen.findByText("Voice isn't running on your Mac yet.")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Voice" })).toBeDisabled();
    expect(screen.getByRole("combobox", { name: "Voice" })).toHaveTextContent("Aiden");
    expect(screen.getByRole("combobox", { name: "Tone" })).toBeDisabled();
    expect(screen.getByRole("combobox", { name: "Speed" })).toBeDisabled();
    expect(screen.getByRole("switch", { name: "Read replies aloud" })).toBeDisabled();
    expect(screen.getByRole("switch", { name: "Correct what I say" })).toBeDisabled();
    expect(screen.getByRole("combobox", { name: "I speak" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Try it" })).toBeDisabled();
  });

  it("names speeds and sums up the voice while folded", () => {
    expect([0.75, 1, 1.25, 2].map(speedLabel)).toEqual(["0.75×", "1.0×", "1.25×", "2.0×"]);
    expect(voiceSummary(INFO, BOT.voice)).toBe("Aiden");
    expect(voiceSummary(null, BOT.voice)).toBeUndefined();
  });
});
