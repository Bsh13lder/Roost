import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { followShrink, useKeepBottom } from "../src/hooks/useKeepBottom";

let resized: (() => void) | null = null;
class FakeResizeObserver {
  constructor(callback: () => void) {
    resized = callback;
  }
  observe() {}
  disconnect() {
    resized = null;
  }
}

function Scroller() {
  return <div ref={useKeepBottom()} data-testid="scroller" />;
}

afterEach(() => { cleanup(); vi.unstubAllGlobals(); resized = null; });

describe("followShrink (redesign P2)", () => {
  it("scrolls down by as much as the box got shorter, and never up when it grew", () => {
    const box = { clientHeight: 480, scrollTop: 1000 };
    expect(followShrink(box, 500)).toBe(480);
    expect(box.scrollTop).toBe(1020);
    box.clientHeight = 520;
    expect(followShrink(box, 480)).toBe(520);
    expect(box.scrollTop).toBe(1020);
  });
});

describe("useKeepBottom (redesign P2)", () => {
  it("follows the scroll box's height while it is on screen, and lets go once it leaves", () => {
    vi.stubGlobal("ResizeObserver", FakeResizeObserver);
    let height = 500;
    vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockImplementation(() => height);
    const view = render(<Scroller />);
    const scroller = screen.getByTestId("scroller");
    scroller.scrollTop = 1000;
    height = 470; // the composer grew by a line and a half
    resized?.();
    expect(scroller.scrollTop).toBe(1030);
    view.unmount();
    expect(resized).toBeNull();
  });
});
