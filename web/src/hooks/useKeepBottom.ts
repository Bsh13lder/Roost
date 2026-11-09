import { useCallback } from "react";

interface ScrollBox {
  readonly clientHeight: number;
  scrollTop: number;
}

// A scroll box that just changed height: if it got shorter (the composer grew a line, a notice appeared),
// it scrolls down by as much, so what sat at its bottom edge, the last message, stays in view. Returns
// the height to compare with next time.
export function followShrink(box: ScrollBox, before: number): number {
  const shrunk = before - box.clientHeight;
  if (shrunk > 0) box.scrollTop += shrunk;
  return box.clientHeight;
}

// The chat's scroll box keeps its last message in view while the dock below it grows (redesign P2).
// A callback ref, so it follows the box from whenever it appears (after Loading…) until it goes.
export function useKeepBottom(): (element: HTMLElement | null) => void | (() => void) {
  return useCallback((element: HTMLElement | null) => {
    if (!element || typeof ResizeObserver === "undefined") return undefined;
    let height = element.clientHeight;
    const observer = new ResizeObserver(() => {
      height = followShrink(element, height);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
}
