import { afterEach, describe, expect, it, vi } from "vitest";
import { openMic } from "../src/lib/recorder";

class FakeAudioContext {
  static made = 0;
  readonly sampleRate = 48_000;
  readonly destination = {};
  state: AudioContextState = "running";
  readonly close = vi.fn(async () => undefined);
  constructor() { FakeAudioContext.made += 1; }
  createMediaStreamSource() { return { connect: () => undefined }; }
  createScriptProcessor() { return { onaudioprocess: null, connect: () => undefined, disconnect: () => undefined }; }
}

let getUserMedia: ReturnType<typeof vi.fn>;

function stubMic(settings: MediaTrackSettings | null = { echoCancellation: true }) {
  const track = { stop: vi.fn(), getSettings: settings === null ? undefined : () => settings };
  getUserMedia = vi.fn(async () => ({ getTracks: () => [track] }));
  Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia } });
  vi.stubGlobal("AudioContext", FakeAudioContext);
  FakeAudioContext.made = 0;
}

afterEach(() => vi.unstubAllGlobals());

describe("openMic (call mode)", () => {
  it("asks for auto gain, echo cancellation and noise suppression", async () => {
    stubMic();
    const mic = await openMic(() => undefined);
    expect(getUserMedia).toHaveBeenCalledWith({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    expect(mic.echoCancellation).toBe(true);
    mic.close();
  });

  it("reports whether the track really cancels echo", async () => {
    stubMic({ echoCancellation: false });
    expect((await openMic(() => undefined)).echoCancellation).toBe(false);
    stubMic(null);
    expect((await openMic(() => undefined)).echoCancellation).toBe(false);
  });

  it("uses the AudioContext it is given (unlocked by the Call tap) instead of making one", async () => {
    stubMic();
    const given = new FakeAudioContext() as unknown as AudioContext;
    FakeAudioContext.made = 0;
    const mic = await openMic(() => undefined, given);
    expect(FakeAudioContext.made).toBe(0);
    expect(mic.context).toBe(given);
    mic.close();
    expect(given.close).toHaveBeenCalled();
  });
});
