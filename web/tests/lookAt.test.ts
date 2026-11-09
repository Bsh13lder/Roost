import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LIVE_OVER_PX, isCalm, registerLookAt, resetLookAtForTests } from "../src/components/robot/lookAt";
import { installObserverStub, type ObserverStub } from "./lookAtStub";

// One shared frame loop moves every live ghost's eyes toward the pointer (avatars v5 §C). It runs only
// while the tab is shown, touches only the ghosts on screen, and stops when robots are calm.
let observer: ObserverStub;
let frames: FrameRequestCallback[];
let hidden = false;

function makeSvg(face = "open"): SVGSVGElement {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "robot robot--live");
  svg.dataset.face = face;
  svg.dataset.ey = "20";
  svg.getBoundingClientRect = () => ({ left: 100, top: 100, width: 64, height: 64, right: 164, bottom: 164 } as DOMRect);
  document.body.appendChild(svg);
  return svg;
}

function runFrame(now = 1000): void {
  const due = frames.splice(0);
  for (const frame of due) frame(now);
}

function movePointer(x: number, y: number): void {
  window.dispatchEvent(new MouseEvent("pointermove", { clientX: x, clientY: y }));
}

beforeEach(() => {
  observer = installObserverStub();
  frames = [];
  hidden = false;
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => { frames.push(callback); return frames.length; });
  vi.stubGlobal("cancelAnimationFrame", () => {});
  Object.defineProperty(document, "hidden", { configurable: true, get: () => hidden });
  document.documentElement.classList.remove("calm");
  resetLookAtForTests();
});

afterEach(() => {
  observer.restore();
  vi.unstubAllGlobals();
  document.body.innerHTML = "";
  document.documentElement.classList.remove("calm");
});

describe("the look-at engine", () => {
  it("is for ghosts drawn larger than 32 px", () => {
    expect(LIVE_OVER_PX).toBe(32);
  });

  it("watches a registered ghost and forgets it when told", () => {
    const svg = makeSvg();
    const unregister = registerLookAt(svg);
    expect(observer.observed).toEqual([svg]);
    unregister();
    expect(observer.observed).toEqual([]);
  });

  it("moves the eyes of a ghost on screen toward the pointer, a little each frame", () => {
    const svg = makeSvg();
    registerLookAt(svg);
    observer.enter(svg, true);
    movePointer(400, 132); // to the right of the ghost, on its eye line
    runFrame(1000);
    const ex = Number(svg.style.getPropertyValue("--ex"));
    expect(ex).toBeGreaterThan(0);
    expect(ex).toBeLessThanOrEqual(1.5);
    expect(Math.abs(Number(svg.style.getPropertyValue("--ey")))).toBeLessThan(0.2);
    runFrame(1016);
    expect(Number(svg.style.getPropertyValue("--ex"))).toBeGreaterThan(ex);
  });

  it("leans toward a pointer over the ghost", () => {
    const svg = makeSvg();
    registerLookAt(svg);
    observer.enter(svg, true);
    movePointer(150, 130); // over the ghost, right of centre
    runFrame(1000);
    expect(Number(svg.style.getPropertyValue("--lx"))).toBeGreaterThan(0);
    expect(Number(svg.style.getPropertyValue("--lr"))).toBeGreaterThan(0);
  });

  it("leaves a ghost off screen alone, and pauses its animations", () => {
    const svg = makeSvg();
    registerLookAt(svg);
    observer.enter(svg, false);
    expect(svg).toHaveClass("robot--offscreen");
    movePointer(400, 132);
    runFrame(1000);
    expect(svg.style.getPropertyValue("--ex")).toBe("");
    observer.enter(svg, true);
    expect(svg).not.toHaveClass("robot--offscreen");
  });

  it("does not run while the tab is hidden, and picks up again when it shows", () => {
    const svg = makeSvg();
    registerLookAt(svg);
    observer.enter(svg, true);
    runFrame(1000); // the frame registration asked for
    hidden = true;
    movePointer(400, 132);
    expect(frames).toHaveLength(0);
    hidden = false;
    document.dispatchEvent(new Event("visibilitychange"));
    expect(frames.length).toBeGreaterThan(0);
  });

  it("does nothing when robots are calm", () => {
    document.documentElement.classList.add("calm");
    expect(isCalm()).toBe(true);
    const svg = makeSvg();
    registerLookAt(svg);
    observer.enter(svg, true);
    movePointer(400, 132);
    expect(frames).toHaveLength(0);
  });

  it("does not move eyes that are lines or closed (Stuck, Off duty)", () => {
    const svg = makeSvg("lines");
    registerLookAt(svg);
    observer.enter(svg, true);
    movePointer(400, 132);
    runFrame(1000);
    expect(svg.style.getPropertyValue("--ex")).toBe("");
  });

  it("a fast pass makes the nearest ghost do a double-take", () => {
    const svg = makeSvg();
    registerLookAt(svg);
    observer.enter(svg, true);
    vi.spyOn(performance, "now").mockReturnValueOnce(1000).mockReturnValueOnce(1010);
    movePointer(100, 132);
    movePointer(300, 132); // 200 px in 10 ms
    runFrame(1020);
    expect(svg).toHaveClass("robot--ev-dbl");
    expect(svg.style.getPropertyValue("--dtx")).toBe("1.5");
  });
});
