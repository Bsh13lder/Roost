import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { SpeakButton } from "../src/components/chat/SpeakButton";
import { MessageRow } from "../src/components/MessageRow";
import { resetVoiceInfo } from "../src/lib/voiceInfo";
import { resetSpeech } from "../src/store/speech";
import { ToastProvider } from "../src/ui/Toast";
import { makeMessage } from "./fixtures";

const INFO = { available: true, speakers: [], tones: [], speeds: [1] };
const PLAN_URL = "/api/threads/t-1/messages/m-1/speech";

let played: HTMLMediaElement[];
let fetched: string[];

function stubServer({ available = true, parts = 2, speed = 1.25, planStatus = 200 } = {}) {
  fetched = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    fetched.push(url);
    if (url === "/api/voice") return new Response(JSON.stringify({ ...INFO, available }));
    if (url === PLAN_URL) {
      return planStatus === 200 ? new Response(JSON.stringify({ parts, speed }))
        : new Response(JSON.stringify({ detail: "This message has nothing to read aloud." }), { status: planStatus });
    }
    if (url.startsWith(`${PLAN_URL}/`)) return new Response(new Blob([url], { type: "audio/wav" }));
    return new Response("{}", { status: 404 });
  }));
}

beforeEach(() => {
  played = [];
  vi.spyOn(window.HTMLMediaElement.prototype, "play").mockImplementation(function play(this: HTMLMediaElement) {
    played.push(this);
    return Promise.resolve();
  });
  vi.spyOn(window.HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
  let n = 0;
  URL.createObjectURL = vi.fn(() => `blob:part-${n++}`);
  URL.revokeObjectURL = vi.fn();
});

afterEach(() => {
  cleanup();
  resetSpeech();
  resetVoiceInfo();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const renderButton = () => render(<ToastProvider><SpeakButton threadId="t-1" messageId="m-1" /></ToastProvider>);

describe("the speaker on a bot's reply (voice V3)", () => {
  it("plays the parts in order at the bot's speed, fetching the next while one plays", async () => {
    stubServer();
    renderButton();
    await userEvent.click(await screen.findByRole("button", { name: "Read aloud" }));
    await waitFor(() => expect(played).toHaveLength(1));
    const element = played[0];
    expect(element.playbackRate).toBe(1.25);
    expect(element.preservesPitch).toBe(true);
    expect(element.src).toBe("blob:part-0");
    await waitFor(() => expect(fetched).toContain(`${PLAN_URL}/1`)); // part 2 is fetched while part 1 plays
    expect(fetched.filter((url) => url.startsWith(PLAN_URL))).toEqual([PLAN_URL, `${PLAN_URL}/0`, `${PLAN_URL}/1`]);
    expect(await screen.findByRole("button", { name: "Stop reading" })).toBeInTheDocument();
    act(() => { element.dispatchEvent(new Event("ended")); });
    await waitFor(() => expect(played).toHaveLength(2));
    expect(played[1].src).toBe("blob:part-1");
    expect(played[1].playbackRate).toBe(1.25);
    act(() => { played[1].dispatchEvent(new Event("ended")); });
    expect(await screen.findByRole("button", { name: "Read aloud" })).toBeInTheDocument();
  });

  it("tapping again stops it, and nothing more plays", async () => {
    stubServer();
    renderButton();
    await userEvent.click(await screen.findByRole("button", { name: "Read aloud" }));
    await waitFor(() => expect(played).toHaveLength(1));
    await userEvent.click(await screen.findByRole("button", { name: "Stop reading" }));
    expect(window.HTMLMediaElement.prototype.pause).toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Read aloud" })).toBeInTheDocument();
    act(() => { played[0].dispatchEvent(new Event("ended")); });
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(played).toHaveLength(1);
  });

  it("shows the server's words when it can't be read", async () => {
    stubServer({ planStatus: 404 });
    renderButton();
    await userEvent.click(await screen.findByRole("button", { name: "Read aloud" }));
    expect(await screen.findByText("This message has nothing to read aloud.")).toBeInTheDocument();
    expect(played).toHaveLength(0);
  });

  it("is hidden while voice is off on the Mac", async () => {
    stubServer({ available: false });
    renderButton();
    await waitFor(() => expect(fetched).toContain("/api/voice"));
    expect(screen.queryByRole("button", { name: "Read aloud" })).not.toBeInTheDocument();
  });

  it("only one plays at a time: starting another stops the first", async () => {
    stubServer({ parts: 1 });
    render(<ToastProvider><SpeakButton threadId="t-1" messageId="m-1" /><SpeakButton threadId="t-1" messageId="m-2" /></ToastProvider>);
    const [first] = await screen.findAllByRole("button", { name: "Read aloud" });
    await userEvent.click(first);
    expect(await screen.findByRole("button", { name: "Stop reading" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Read aloud" }));
    await waitFor(() => expect(screen.queryAllByRole("button", { name: "Stop reading" })).toHaveLength(0));
    expect(window.HTMLMediaElement.prototype.pause).toHaveBeenCalled();
  });
});

describe("where the speaker shows", () => {
  const row = (overrides: Parameters<typeof makeMessage>[0]) => render(
    <MemoryRouter><ToastProvider><ul>
      <MessageRow message={makeMessage(overrides)} runStart fallbackName="Scout" team={[]} />
    </ul></ToastProvider></MemoryRouter>,
  );

  it("on a bot's reply", async () => {
    stubServer();
    row({ role: "bot", body: "Done, I added it." });
    expect(await screen.findByRole("button", { name: "Read aloud" })).toBeInTheDocument();
  });

  it("on a Report", async () => {
    stubServer();
    row({ role: "bot", kind: "report", body: JSON.stringify({ headline: "Daily", text: "All good.", source: "routine" }) });
    expect(await screen.findByRole("button", { name: "Read aloud" })).toBeInTheDocument();
  });

  it("never on your own message", async () => {
    stubServer();
    row({ role: "user", body: "Hi" });
    expect(await screen.findByRole("button", { name: "Copy message" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Read aloud" })).not.toBeInTheDocument();
  });
});
