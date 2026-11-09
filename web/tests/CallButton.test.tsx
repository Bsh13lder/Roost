import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Composer } from "../src/components/Composer";
import { takeUnlockedContext } from "../src/lib/audioUnlock";
import { resetVoiceInfo } from "../src/lib/voiceInfo";
import { resetSpeech } from "../src/store/speech";

const INFO = { available: true, speakers: [], tones: [], speeds: [1] };

class FakeAudioContext {
  static made: FakeAudioContext[] = [];
  state: AudioContextState = "suspended";
  readonly resume = vi.fn(async () => { this.state = "running"; });
  constructor() { FakeAudioContext.made.push(this); }
}

let probes: number;

function stub({ available = true, mic = true, status = 200 } = {}) {
  probes = 0;
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    if (url !== "/api/voice") return new Response("{}", { status: 404 });
    probes += 1;
    return status === 200 ? new Response(JSON.stringify({ ...INFO, available })) : new Response("{}", { status });
  }));
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true, value: mic ? { getUserMedia: vi.fn() } : undefined,
  });
  vi.stubGlobal("AudioContext", FakeAudioContext);
}

let played: number;
beforeEach(() => {
  resetVoiceInfo();
  FakeAudioContext.made = [];
  played = 0;
  vi.spyOn(window.HTMLMediaElement.prototype, "play").mockImplementation(() => { played += 1; return Promise.resolve(); });
  vi.spyOn(window.HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); resetVoiceInfo(); resetSpeech(); takeUnlockedContext(); });

describe("the composer's Call button", () => {
  it("takes Send's place while the box is empty; typing brings Send back", async () => {
    stub();
    const onCall = vi.fn();
    render(<Composer onSend={vi.fn()} voice={{ onError: vi.fn() }} call={{ name: "Gigs", onCall }} />);
    const call = await screen.findByRole("button", { name: "Call Gigs" });
    expect(call.getAttribute("data-testid")).toBe("call");
    fireEvent.click(call);
    await waitFor(() => expect(onCall).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "hi" } });
    expect(screen.queryByRole("button", { name: "Call Gigs" })).toBeNull();
    expect(screen.getByRole("button", { name: "Send" })).toBeTruthy();
  });

  it("the tap unlocks the browser's audio and the speaker before the call opens", async () => {
    stub();
    const onCall = vi.fn();
    render(<Composer onSend={vi.fn()} call={{ name: "Gigs", onCall }} />);
    fireEvent.click(await screen.findByRole("button", { name: "Call Gigs" }));
    await waitFor(() => expect(onCall).toHaveBeenCalledTimes(1));
    expect(FakeAudioContext.made).toHaveLength(1);
    expect(FakeAudioContext.made[0].resume).toHaveBeenCalled();
    expect(played).toBe(1); // the silent unlock
    expect(takeUnlockedContext()).toBe(FakeAudioContext.made[0] as unknown as AudioContext);
    expect(takeUnlockedContext()).toBeNull(); // taken once
  });

  it("never silently becomes Send: without https it is a disabled Call that says so", async () => {
    stub({ mic: false });
    render(<Composer onSend={vi.fn()} call={{ name: "Gigs", onCall: vi.fn() }} />);
    const call = await screen.findByRole("button", { name: "Voice needs https" });
    expect(call.hasAttribute("disabled")).toBe(true);
    expect(call.getAttribute("title")).toBe("Voice needs https");
    expect(screen.queryByRole("button", { name: "Send" })).toBeNull();
  });

  it("says when the Mac's voice isn't running, and still shows Call while it doesn't know", async () => {
    stub({ available: false });
    render(<Composer onSend={vi.fn()} call={{ name: "Gigs", onCall: vi.fn() }} />);
    const off = await screen.findByRole("button", { name: "Voice isn't running on your Mac yet" });
    expect(off.hasAttribute("disabled")).toBe(true);
    cleanup();
    resetVoiceInfo();
    stub({ status: 500 });
    const onCall = vi.fn();
    render(<Composer onSend={vi.fn()} call={{ name: "Gigs", onCall }} />);
    await waitFor(() => expect(probes).toBe(1));
    const call = await screen.findByRole("button", { name: "Call Gigs" });
    expect(call.hasAttribute("disabled")).toBe(false);
    fireEvent.click(call);
    await waitFor(() => expect(onCall).toHaveBeenCalled());
  });

  it("asks the server again when the composer gains focus, so a voice that came up is found", async () => {
    stub({ available: false });
    render(<Composer onSend={vi.fn()} call={{ name: "Gigs", onCall: vi.fn() }} />);
    await screen.findByRole("button", { name: "Voice isn't running on your Mac yet" });
    expect(probes).toBe(1);
    stub({ available: true });
    fireEvent.focus(screen.getByRole("textbox"));
    await screen.findByRole("button", { name: "Call Gigs" });
    expect(probes).toBe(1); // this stub counts its own
  });

  it("isn't there without a call to make", () => {
    stub();
    render(<Composer onSend={vi.fn()} />);
    expect(screen.queryByTestId("call")).toBeNull();
  });
});
