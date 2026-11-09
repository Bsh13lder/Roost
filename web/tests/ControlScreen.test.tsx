import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ControlScreen } from "../src/components/computer/ControlScreen";
import { ToastProvider } from "../src/ui/Toast";
import { makeBot, makeStuckCard } from "./fixtures";
import type { RfbConstructor } from "../src/lib/novnc";

const computer = { giveBack: vi.fn() };
const stuck = { clearStuck: vi.fn() };
vi.mock("../src/api/computer", () => ({ giveBack: (...a: unknown[]) => computer.giveBack(...a) }));
vi.mock("../src/api/stuck", () => ({ clearStuck: (...a: unknown[]) => stuck.clearStuck(...a) }));
const teach = { stopTeach: vi.fn() };
vi.mock("../src/api/teach", () => ({ stopTeach: (...a: unknown[]) => teach.stopTeach(...a) }));

type Listener = (event: { code?: number }) => void;
class FakeSocket {
  private listeners: Listener[] = [];
  addEventListener(type: string, fn: Listener) { if (type === "close") this.listeners.push(fn); }
  removeEventListener() {}
  close() {}
  emitClose(code: number) { this.listeners.forEach((fn) => fn({ code })); }
}
class FakeRfb {
  static last: FakeRfb | null = null;
  viewOnly = true;
  scaleViewport = false;
  focused = false;
  pasted: string[] = [];
  keys: [number, string | null, boolean | undefined][] = [];
  constructor() { FakeRfb.last = this; }
  clipboardPasteFrom(text: string) { this.pasted.push(text); }
  sendKey(keysym: number, code: string | null, down?: boolean) { this.keys.push([keysym, code, down]); }
  addEventListener() {}
  disconnect() {}
  focus() { this.focused = true; }
}

let socket: FakeSocket;
const openSocket = vi.fn((_id: string, _mode?: string) => socket as unknown as WebSocket);
const loadRfb = async () => FakeRfb as unknown as RfbConstructor;
const onClosed = vi.fn();
const bot = makeBot({ name: "Scout", computer: "linux" });
const view = (card?: ReturnType<typeof makeStuckCard>, teaching = false) => render(
  <ToastProvider><ControlScreen bot={bot} card={card} teaching={teaching} onClosed={onClosed} openSocket={openSocket} loadRfb={loadRfb} /></ToastProvider>,
);

beforeEach(() => {
  socket = new FakeSocket();
  computer.giveBack.mockResolvedValue({ held: false, since: null });
  stuck.clearStuck.mockResolvedValue({});
});
afterEach(() => { cleanup(); FakeRfb.last = null; openSocket.mockClear(); onClosed.mockReset(); computer.giveBack.mockReset(); stuck.clearStuck.mockReset(); teach.stopTeach.mockReset(); });

describe("ControlScreen", () => {
  it("covers the screen with You're in control and I'm done", async () => {
    view();
    expect(screen.getByText("You're in control")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "I'm done" })).toBeInTheDocument();
    expect(screen.getByLabelText("Scout’s screen, live")).toBeInTheDocument();
    await waitFor(() => expect(FakeRfb.last).not.toBeNull());
    expect(openSocket).toHaveBeenCalledWith("bot-1", "control");
    expect(FakeRfb.last?.viewOnly).toBe(false);
    expect(FakeRfb.last?.focused).toBe(true);
  });

  it("Escape goes to the page, not the sheet", async () => {
    view();
    await userEvent.keyboard("{Escape}");
    expect(screen.getByText("You're in control")).toBeInTheDocument();
    expect(onClosed).not.toHaveBeenCalled();
  });

  it("closes when the server says Given back", async () => {
    view();
    await waitFor(() => expect(FakeRfb.last).not.toBeNull());
    act(() => socket.emitClose(4000));
    expect(onClosed).toHaveBeenCalled();
    expect(await screen.findByText("Control was given back.")).toBeInTheDocument();
  });

  it("I'm done asks for the account, gives it back with it, and closes", async () => {
    view();
    await userEvent.click(screen.getByRole("button", { name: "I'm done" }));
    await userEvent.type(screen.getByLabelText(/Which account did you use\?/), "work email");
    await userEvent.click(screen.getByRole("button", { name: "Give it back" }));
    expect(computer.giveBack).toHaveBeenCalledWith("bot-1", "work email");
    await waitFor(() => expect(onClosed).toHaveBeenCalled());
  });

  it("with a Stuck card, I'm done clears the card with the account", async () => {
    const card = makeStuckCard();
    view(card);
    await userEvent.click(screen.getByRole("button", { name: "I'm done" }));
    await userEvent.type(screen.getByLabelText(/Which account did you use\?/), "me");
    await userEvent.click(screen.getByRole("button", { name: "Give it back" }));
    expect(stuck.clearStuck).toHaveBeenCalledWith(card.id, { account: "me" });
    await waitFor(() => expect(onClosed).toHaveBeenCalled());
  });

  it("with a Sign-in card, I'm done asks Keep me signed in and sends the answer", async () => {
    const card = makeStuckCard({ sign_in: true });
    view(card);
    await userEvent.click(screen.getByRole("button", { name: "I'm done" }));
    expect(screen.getByText(/Roost never sees your password\./)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "No, this time" }));
    expect(stuck.clearStuck).toHaveBeenCalledWith(card.id, { keep: false });
    await waitFor(() => expect(onClosed).toHaveBeenCalled());
  });

  it("a failed give-back says why and stays in control", async () => {
    computer.giveBack.mockRejectedValue(new Error("x"));
    view();
    await userEvent.click(screen.getByRole("button", { name: "I'm done" }));
    await userEvent.click(screen.getByRole("button", { name: "Give it back" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(onClosed).not.toHaveBeenCalled();
  });
});

describe("ControlScreen on a touch screen", () => {
  const original = window.matchMedia;
  const touch = (coarse: boolean) => {
    window.matchMedia = ((query: string) => ({
      matches: coarse && query === "(pointer: coarse)", media: query,
      addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
    })) as unknown as typeof window.matchMedia;
  };
  afterEach(() => { window.matchMedia = original; });

  it("a keyboard row types text into the computer and sends Enter and Backspace", async () => {
    touch(true);
    view();
    await waitFor(() => expect(FakeRfb.last).not.toBeNull());
    const field = screen.getByLabelText("Type on the computer");
    await userEvent.type(field, "blue mug");
    await userEvent.click(screen.getByRole("button", { name: "Send text" }));
    expect(FakeRfb.last?.pasted).toEqual(["blue mug"]);
    expect(field).toHaveValue("");
    await userEvent.click(screen.getByRole("button", { name: "Enter" }));
    await userEvent.click(screen.getByRole("button", { name: "Backspace" }));
    expect(FakeRfb.last?.keys.slice(-4).map(([, code, down]) => [code, down])).toEqual([
      ["Enter", true], ["Enter", false], ["Backspace", true], ["Backspace", false],
    ]);
  });

  it("an empty field sends nothing", async () => {
    touch(true);
    view();
    await waitFor(() => expect(FakeRfb.last).not.toBeNull());
    expect(screen.getByRole("button", { name: "Send text" })).toBeDisabled();
  });

  it("a mouse and keyboard screen has no keyboard row", () => {
    touch(false);
    view();
    expect(screen.queryByLabelText("Type on the computer")).not.toBeInTheDocument();
  });
});

describe("ControlScreen while teaching", () => {
  it("says what is recorded and I'm done teaching sends the description", async () => {
    teach.stopTeach.mockResolvedValue({ proposal_id: "p1", steps: 3, discarded: false });
    view(undefined, true);
    expect(screen.getByText(/You're teaching Scout\. Clicks and field names are recorded, never what you type\./))
      .toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "I'm done" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "I'm done teaching" }));
    await userEvent.type(screen.getByLabelText(/What is this task\?/), "  Reorder an item  ");
    await userEvent.click(screen.getByRole("button", { name: "Make the skill" }));
    expect(teach.stopTeach).toHaveBeenCalledWith("bot-1", { description: "Reorder an item" });
    await waitFor(() => expect(onClosed).toHaveBeenCalled());
    expect(await screen.findByText("The skill is in the chat. Press Save skill to keep it.")).toBeInTheDocument();
  });

  it("no description sends an empty body, and Discard throws the recording away", async () => {
    teach.stopTeach.mockResolvedValue({ proposal_id: null, steps: 1, discarded: true });
    view(undefined, true);
    await userEvent.click(screen.getByRole("button", { name: "I'm done teaching" }));
    await userEvent.click(screen.getByRole("button", { name: "Discard" }));
    expect(teach.stopTeach).toHaveBeenCalledWith("bot-1", { discard: true });
    expect(await screen.findByText("The recording was thrown away.")).toBeInTheDocument();
    cleanup();
    teach.stopTeach.mockResolvedValue({ proposal_id: "p", steps: 1, discarded: false });
    view(undefined, true);
    await userEvent.click(screen.getByRole("button", { name: "I'm done teaching" }));
    await userEvent.click(screen.getByRole("button", { name: "Make the skill" }));
    expect(teach.stopTeach).toHaveBeenLastCalledWith("bot-1", {});
  });

  it("a refused stop says why and stays teaching; Back returns to the bar", async () => {
    teach.stopTeach.mockRejectedValue(new Error("Nothing was recorded yet."));
    view(undefined, true);
    await userEvent.click(screen.getByRole("button", { name: "I'm done teaching" }));
    await userEvent.click(screen.getByRole("button", { name: "Make the skill" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(onClosed).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(screen.getByRole("button", { name: "I'm done teaching" })).toBeInTheDocument();
  });

  it("a description that is too long is refused before it is sent", async () => {
    view(undefined, true);
    await userEvent.click(screen.getByRole("button", { name: "I'm done teaching" }));
    const field = screen.getByLabelText(/What is this task\?/);
    await userEvent.click(field);
    await userEvent.paste("x".repeat(201));
    await userEvent.click(screen.getByRole("button", { name: "Make the skill" }));
    expect(await screen.findByText("Keep it to 200 characters or fewer.")).toBeInTheDocument();
    expect(teach.stopTeach).not.toHaveBeenCalled();
  });
});
