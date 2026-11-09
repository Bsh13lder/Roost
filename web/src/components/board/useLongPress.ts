import { useCallback, useEffect, useRef, type PointerEvent } from "react";
import { LONG_PRESS_MS, LONG_PRESS_SLOP_PX } from "./constants";

const CONTROLS = "button, a, input, [role='checkbox'], [role='menuitem']";

export interface LongPress {
  handlers: {
    onPointerDown: (event: PointerEvent<HTMLElement>) => void;
    onPointerMove: (event: PointerEvent<HTMLElement>) => void;
    onPointerUp: () => void;
    onPointerCancel: () => void;
    onPointerLeave: () => void;
  };
  /** True once, right after a long press fired: the click that follows it should be ignored. */
  consumed: () => boolean;
}

// A press held for LONG_PRESS_MS on a touch or pen (not a mouse, not on a control) calls `onLongPress`.
// Moving more than the slop (scrolling), lifting early or leaving cancels it.
export function useLongPress(onLongPress: () => void): LongPress {
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const start = useRef<{ x: number; y: number } | null>(null);
  const fired = useRef(false);
  const cancel = useCallback(() => {
    if (timer.current !== null) clearTimeout(timer.current);
    timer.current = null;
    start.current = null;
  }, []);
  useEffect(() => cancel, [cancel]);

  const onPointerDown = (event: PointerEvent<HTMLElement>) => {
    if (event.pointerType === "mouse" || (event.target as HTMLElement).closest?.(CONTROLS)) return;
    cancel();
    fired.current = false;
    start.current = { x: event.clientX, y: event.clientY };
    timer.current = setTimeout(() => {
      timer.current = null;
      fired.current = true;
      onLongPress();
    }, LONG_PRESS_MS);
  };
  const onPointerMove = (event: PointerEvent<HTMLElement>) => {
    const from = start.current;
    if (from && Math.hypot(event.clientX - from.x, event.clientY - from.y) > LONG_PRESS_SLOP_PX) cancel();
  };
  const consumed = () => {
    const was = fired.current;
    fired.current = false;
    return was;
  };
  return { handlers: { onPointerDown, onPointerMove, onPointerUp: cancel, onPointerCancel: cancel, onPointerLeave: cancel }, consumed };
}
