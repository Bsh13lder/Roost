import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { useLiveScreen } from "../src/hooks/useLiveScreen";
import type { RfbLike, RfbConstructor } from "../src/lib/novnc";

type Listener = (event: { code?: number }) => void;

class FakeSocket {
  closed = false;
  private listeners = new Map<string, Listener[]>();
  addEventListener(type: string, fn: Listener) { this.listeners.set(type, [...(this.listeners.get(type) ?? []), fn]); }
  removeEventListener() {}
  close() { this.closed = true; }
  emit(type: string, event: { code?: number } = {}) { (this.listeners.get(type) ?? []).forEach((fn) => fn(event)); }
}

class FakeRfb implements RfbLike {
  static last: FakeRfb | null = null;
  viewOnly = false;
  scaleViewport = false;
  disconnected = false;
  pasted: string[] = [];
  keys: [number, string | null, boolean | undefined][] = [];
  clipboardPasteFrom(text: string) { this.pasted.push(text); }
  sendKey(keysym: number, code: string | null, down?: boolean) { this.keys.push([keysym, code, down]); }
  private listeners = new Map<string, Listener[]>();
  constructor(public target: Element, public channel: unknown, public options: object) { FakeRfb.last = this; }
  addEventListener(type: string, fn: Listener) { this.listeners.set(type, [...(this.listeners.get(type) ?? []), fn]); }
  disconnect() { this.disconnected = true; }
  emit(type: string) { (this.listeners.get(type) ?? []).forEach((fn) => fn({})); }
}

function setup(mode: "view" | "control" = "view") {
  const socket = new FakeSocket();
  const target = document.createElement("div");
  const openSocket = vi.fn(() => socket as unknown as WebSocket);
  const loadRfb = vi.fn(async () => FakeRfb as unknown as RfbConstructor);
  const ref = { current: target };
  const view = renderHook(() => useLiveScreen({ botId: "bot-1", target: ref, mode, openSocket, loadRfb }));
  return { socket, target, openSocket, view };
}

afterEach(() => { cleanup(); FakeRfb.last = null; });

describe("useLiveScreen", () => {
  it("opens the view socket and hands it to noVNC view only", async () => {
    const { socket, target, openSocket, view } = setup();
    await waitFor(() => expect(FakeRfb.last).not.toBeNull());
    expect(openSocket).toHaveBeenCalledWith("bot-1");
    expect(FakeRfb.last?.channel).toBe(socket);
    expect(FakeRfb.last?.target).toBe(target);
    expect(FakeRfb.last?.viewOnly).toBe(true);
    expect(view.result.current.state).toBe("connecting");
    act(() => FakeRfb.last?.emit("connect"));
    expect(view.result.current.state).toBe("live");
  });

  it("maps 4410 to asleep and 4503 to unreachable", async () => {
    const first = setup();
    await waitFor(() => expect(FakeRfb.last).not.toBeNull());
    act(() => first.socket.emit("close", { code: 4410 }));
    expect(first.view.result.current.state).toBe("asleep");
    cleanup();
    const second = setup();
    await waitFor(() => expect(FakeRfb.last).not.toBeNull());
    act(() => second.socket.emit("close", { code: 4503 }));
    expect(second.view.result.current.state).toBe("unreachable");
  });

  it("closes the socket and disconnects on unmount", async () => {
    const { socket, view } = setup();
    await waitFor(() => expect(FakeRfb.last).not.toBeNull());
    const rfb = FakeRfb.last;
    view.unmount();
    expect(rfb?.disconnected).toBe(true);
    expect(socket.closed).toBe(true);
  });

  it("opens the socket only after noVNC has loaded, so the greeting is never lost", async () => {
    const socket = new FakeSocket();
    const openSocket = vi.fn(() => socket as unknown as WebSocket);
    let release: (rfb: RfbConstructor) => void = () => {};
    const loadRfb = vi.fn(() => new Promise<RfbConstructor>((resolve) => { release = resolve; }));
    renderHook(() => useLiveScreen({ botId: "bot-1", target: { current: document.createElement("div") }, openSocket, loadRfb }));
    expect(openSocket).not.toHaveBeenCalled();
    release(FakeRfb as unknown as RfbConstructor);
    await waitFor(() => expect(openSocket).toHaveBeenCalledWith("bot-1"));
    expect(FakeRfb.last?.channel).toBe(socket);
  });

  it("in control, typeText goes through the computer's clipboard and Ctrl+V; pressKey sends one key down and up", async () => {
    const { view } = setup("control");
    await waitFor(() => expect(FakeRfb.last).not.toBeNull());
    act(() => view.result.current.typeText("hello"));
    expect(FakeRfb.last?.pasted).toEqual(["hello"]);
    expect(FakeRfb.last?.keys).toEqual([
      [0xffe3, "ControlLeft", true], [0x76, "KeyV", true], [0x76, "KeyV", false], [0xffe3, "ControlLeft", false],
    ]);
    act(() => view.result.current.pressKey("Enter"));
    expect(FakeRfb.last?.keys.slice(-2)).toEqual([[0xff0d, "Enter", true], [0xff0d, "Enter", false]]);
  });

  it("in view mode, typeText and pressKey send nothing", async () => {
    const { view } = setup("view");
    await waitFor(() => expect(FakeRfb.last).not.toBeNull());
    act(() => { view.result.current.typeText("hello"); view.result.current.pressKey("Enter"); });
    expect(FakeRfb.last?.pasted).toEqual([]);
    expect(FakeRfb.last?.keys).toEqual([]);
  });
});
