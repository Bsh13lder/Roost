import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render } from "@testing-library/react";
import { createRef } from "react";
import { applyFrame, initialLiveState, pointerFor, type LiveState } from "../src/store/live";
import { POINTER_RING_MS } from "../src/components/computer/constants";
import type { ServerFrame } from "../src/api/types";

let liveState: LiveState = initialLiveState();
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => liveState }));
let reduced = false;
vi.mock("../src/hooks/usePrefersReducedMotion", () => ({ usePrefersReducedMotion: () => reduced }));

const { PointerRing } = await import("../src/components/computer/PointerRing");

const pointer = (x: number, y: number, bot = "bot-1"): ServerFrame =>
  ({ type: "computer_pointer", seq: 5, bot_id: bot, x, y, kind: "click" }) as ServerFrame;

// The noVNC canvas is drawn at 640×400, 20px right of and 10px below its box's corner.
function screenBox(): HTMLDivElement {
  const host = document.createElement("div");
  const canvas = document.createElement("canvas");
  host.appendChild(canvas);
  host.getBoundingClientRect = () => ({ left: 100, top: 50, width: 680, height: 420 }) as DOMRect;
  canvas.getBoundingClientRect = () => ({ left: 120, top: 60, width: 640, height: 400 }) as DOMRect;
  document.body.appendChild(host);
  return host;
}

function renderRing() {
  const ref = createRef<HTMLDivElement>();
  (ref as { current: HTMLDivElement | null }).current = screenBox();
  const view = render(<PointerRing botId="bot-1" canvasRef={ref} />);
  return view;
}

beforeEach(() => { vi.useFakeTimers(); liveState = initialLiveState(); reduced = false; });
afterEach(() => { cleanup(); vi.useRealTimers(); document.body.innerHTML = ""; });

describe("the pointer ring (C3)", () => {
  it("keeps each bot's newest pointer from computer_pointer frames, with no text", () => {
    const state = applyFrame(applyFrame(initialLiveState(), pointer(10, 20)), pointer(30, 40));
    expect(pointerFor(state, "bot-1")).toMatchObject({ x: 30, y: 40, kind: "click", n: 2 });
    expect(pointerFor(state, "bot-2")).toBeNull();
    expect(state.cursor).toBe(5);
  });

  it("test_ring_appears_at_the_scaled_point_and_fades", () => {
    const view = renderRing();
    expect(view.container.querySelector(".pointer-ring")).toBeNull();
    liveState = applyFrame(liveState, pointer(640, 400));
    view.rerender(<PointerRing botId="bot-1" canvasRef={{ current: document.body.firstElementChild as HTMLDivElement }} />);
    const ring = view.container.querySelector<HTMLElement>(".pointer-ring");
    expect(ring).not.toBeNull();
    // (640 / 1280, 400 / 800) of the drawn canvas: 20 + 320 across, 10 + 200 down.
    expect(ring?.style.left).toBe("340px");
    expect(ring?.style.top).toBe("210px");
    expect(ring).not.toHaveClass("pointer-ring--still");
    expect(ring?.style.animationDuration).toBe(`${POINTER_RING_MS}ms`);
    act(() => { vi.advanceTimersByTime(POINTER_RING_MS); });
    expect(view.container.querySelector(".pointer-ring")).toBeNull();
  });

  it("test_ring_respects_reduced_motion", () => {
    reduced = true;
    const view = renderRing();
    liveState = applyFrame(liveState, pointer(0, 0));
    view.rerender(<PointerRing botId="bot-1" canvasRef={{ current: document.body.firstElementChild as HTMLDivElement }} />);
    const ring = view.container.querySelector<HTMLElement>(".pointer-ring");
    expect(ring).toHaveClass("pointer-ring--still");
    expect(ring?.style.left).toBe("20px");
    act(() => { vi.advanceTimersByTime(POINTER_RING_MS - 1); });
    expect(view.container.querySelector(".pointer-ring")).not.toBeNull();
    act(() => { vi.advanceTimersByTime(1); });
    expect(view.container.querySelector(".pointer-ring")).toBeNull();
  });

  it("ignores another bot's pointer and one that was there before the screen opened", () => {
    liveState = applyFrame(liveState, pointer(5, 5));
    const view = renderRing();
    expect(view.container.querySelector(".pointer-ring")).toBeNull();
    liveState = applyFrame(liveState, pointer(5, 5, "bot-2"));
    view.rerender(<PointerRing botId="bot-1" canvasRef={{ current: document.body.firstElementChild as HTMLDivElement }} />);
    expect(view.container.querySelector(".pointer-ring")).toBeNull();
  });
});
