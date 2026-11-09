import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Composer, withSpokenText } from "../src/components/Composer";
import { MIC_DENIED_TEXT } from "../src/lib/recorder";
import { resetVoiceInfo } from "../src/lib/voiceInfo";

const INFO = {
  available: true,
  speakers: [{ id: "aiden", name: "Aiden", best_in: "English" }],
  tones: [{ id: "natural", name: "Natural" }],
  speeds: [1],
};

interface FakeProcessor {
  onaudioprocess: ((event: { inputBuffer: { getChannelData: () => Float32Array } }) => void) | null;
  connect: () => void;
  disconnect: ReturnType<typeof vi.fn>;
}

// The browser's audio graph, with no AudioWorklet: the recorder takes the ScriptProcessor way.
class FakeAudioContext {
  static last: FakeAudioContext | null = null;
  readonly sampleRate = 48_000;
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

function say(samples: number) {
  FakeAudioContext.last?.processor?.onaudioprocess?.({ inputBuffer: { getChannelData: () => new Float32Array(samples) } });
}

let track: { stop: ReturnType<typeof vi.fn> };
let getUserMedia: ReturnType<typeof vi.fn>;

function stubMic(fail?: unknown) {
  track = { stop: vi.fn() };
  getUserMedia = fail === undefined
    ? vi.fn(async () => ({ getTracks: () => [track] }))
    : vi.fn(async () => { throw fail; });
  Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia } });
  vi.stubGlobal("AudioContext", FakeAudioContext);
}

function stubServer({ info = INFO, transcribe = () => new Response(JSON.stringify({ text: "Add milk to my list" })) } = {}) {
  const posts: RequestInit[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/voice") return new Response(JSON.stringify(info));
    if (url === "/api/voice/transcribe" && init?.method === "POST") { posts.push(init); return transcribe(); }
    return new Response("{}", { status: 404 });
  }));
  return posts;
}

function renderComposer(onError = vi.fn()) {
  render(<Composer onSend={vi.fn()} voice={{ onError }} />);
  return onError;
}

beforeEach(() => { stubMic(); });
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  resetVoiceInfo();
  FakeAudioContext.last = null;
  Reflect.deleteProperty(navigator, "mediaDevices");
});

describe("the composer's mic (voice V3)", () => {
  it("records, shows the time, sends a 16 kHz WAV and puts the words after what you typed", async () => {
    const posts = stubServer();
    renderComposer();
    const box = screen.getByRole("textbox");
    await userEvent.type(box, "Please");
    await userEvent.click(await screen.findByRole("button", { name: "Speak a message" }));
    await screen.findByRole("button", { name: "Stop recording" });
    expect(screen.getByRole("timer", { name: "Recording" })).toHaveTextContent("0:00");
    say(4_800);
    say(4_800); // 0.2 s at 48 kHz
    await userEvent.click(screen.getByRole("button", { name: "Stop recording" }));
    expect(track.stop).toHaveBeenCalled(); // the microphone is released at once
    await waitFor(() => expect(box).toHaveValue("Please Add milk to my list"));
    expect(posts).toHaveLength(1);
    const headers = posts[0].headers as Record<string, string>;
    expect(headers["Content-Type"]).toBe("audio/wav");
    const body = posts[0].body as Blob;
    expect(body.size).toBe(44 + 2 * 3_200);
    expect(getUserMedia).toHaveBeenCalledWith({ audio: expect.objectContaining({ channelCount: 1 }) });
  });

  it('says "Listening…" while the words come back', async () => {
    let answer: (response: Response) => void = () => undefined;
    stubServer({ transcribe: () => new Promise<Response>((resolve) => { answer = resolve; }) as unknown as Response });
    renderComposer();
    await userEvent.click(await screen.findByRole("button", { name: "Speak a message" }));
    await userEvent.click(await screen.findByRole("button", { name: "Stop recording" }));
    expect(await screen.findByText("Listening…")).toBeInTheDocument();
    answer(new Response(JSON.stringify({ text: "Hi" })));
    await waitFor(() => expect(screen.getByRole("textbox")).toHaveValue("Hi"));
    expect(screen.queryByText("Listening…")).not.toBeInTheDocument();
  });

  it("shows the server's words when voice is off, and keeps the box as it was", async () => {
    stubServer({ transcribe: () => new Response(JSON.stringify({ detail: "Voice isn't running on your Mac yet." }), { status: 503 }) });
    const onError = renderComposer();
    await userEvent.click(await screen.findByRole("button", { name: "Speak a message" }));
    await userEvent.click(await screen.findByRole("button", { name: "Stop recording" }));
    await waitFor(() => expect(onError).toHaveBeenCalledWith("Voice isn't running on your Mac yet."));
    expect(screen.getByRole("textbox")).toHaveValue("");
    expect(screen.getByRole("button", { name: "Speak a message" })).toBeEnabled();
  });

  it("says so when the browser is not allowed to use the microphone", async () => {
    stubMic(new DOMException("denied", "NotAllowedError"));
    stubServer();
    const onError = renderComposer();
    await userEvent.click(await screen.findByRole("button", { name: "Speak a message" }));
    await waitFor(() => expect(onError).toHaveBeenCalledWith(MIC_DENIED_TEXT));
  });

  it("Cancel drops the recording: nothing is sent and the microphone is released", async () => {
    const posts = stubServer();
    renderComposer();
    await userEvent.click(await screen.findByRole("button", { name: "Speak a message" }));
    say(4_800);
    await userEvent.click(await screen.findByRole("button", { name: "Cancel recording" }));
    expect(track.stop).toHaveBeenCalled();
    expect(posts).toHaveLength(0);
    expect(screen.getByRole("button", { name: "Speak a message" })).toBeInTheDocument();
  });

  it("stops by itself at two minutes", async () => {
    const posts = stubServer();
    renderComposer();
    await userEvent.click(await screen.findByRole("button", { name: "Speak a message" }));
    await screen.findByRole("button", { name: "Stop recording" });
    const now = Date.now();
    vi.spyOn(Date, "now").mockReturnValue(now + 121_000);
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(track.stop).toHaveBeenCalled();
  });

  it("is hidden while voice is off on the Mac", async () => {
    stubServer({ info: { ...INFO, available: false } });
    renderComposer();
    await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/voice", expect.anything()));
    expect(screen.queryByRole("button", { name: "Speak a message" })).not.toBeInTheDocument();
  });

  it("is hidden in a browser that can't record", async () => {
    Reflect.deleteProperty(navigator, "mediaDevices");
    stubServer();
    renderComposer();
    await waitFor(() => expect(fetch).toHaveBeenCalled());
    fireEvent.focus(screen.getByRole("textbox"));
    expect(screen.queryByRole("button", { name: "Speak a message" })).not.toBeInTheDocument();
  });
});

describe("withSpokenText", () => {
  it("adds what you said after a space, or alone in an empty box", () => {
    expect(withSpokenText("", "Hi")).toBe("Hi");
    expect(withSpokenText("Please  ", "add milk")).toBe("Please add milk");
  });
});

describe("startRecording with an AudioWorklet", () => {
  it("collects the worklet's blocks and releases the microphone on stop", async () => {
    const { startRecording } = await import("../src/lib/recorder");
    const nodes: { port: { onmessage: ((event: { data: Float32Array }) => void) | null }; disconnect: () => void }[] = [];
    class FakeWorkletNode {
      port = { onmessage: null as ((event: { data: Float32Array }) => void) | null };
      disconnect = vi.fn();
      constructor() { nodes.push(this); }
    }
    class WorkletContext extends FakeAudioContext {
      readonly audioWorklet = { addModule: vi.fn(async () => undefined) };
    }
    vi.stubGlobal("AudioContext", WorkletContext);
    vi.stubGlobal("AudioWorkletNode", FakeWorkletNode);
    URL.createObjectURL = vi.fn(() => "blob:worklet");
    URL.revokeObjectURL = vi.fn();
    const recording = await startRecording();
    expect(nodes).toHaveLength(1);
    nodes[0].port.onmessage?.({ data: new Float32Array(480) });
    nodes[0].port.onmessage?.({ data: new Float32Array(480) });
    const wav = recording.stop();
    expect(wav.size).toBe(44 + 2 * 320);
    expect(track.stop).toHaveBeenCalled();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:worklet");
  });
});
