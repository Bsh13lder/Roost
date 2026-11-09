import { useEffect, useRef, useState, type RefObject } from "react";
import { useLiveState } from "../../hooks/useLiveStore";
import { usePrefersReducedMotion } from "../../hooks/usePrefersReducedMotion";
import { pointerFor, type PointerMark } from "../../store/live";
import { cx } from "../../ui/cx";
import { COMPUTER_SCREEN_H, COMPUTER_SCREEN_W, POINTER_RING_MS, POINTER_RING_SIZE_PX } from "./constants";

interface Place {
  readonly n: number;
  readonly left: number;
  readonly top: number;
}

// The point on the page: the frame's screen pixel as a share of the 1280×800 screen, laid on the box noVNC drew
// its canvas in (it letterboxes, so the canvas may sit inside its container), measured from the container's corner.
export function ringPlace(mark: PointerMark, host: HTMLElement | null): Place | null {
  if (host === null) return null;
  const canvas = host.querySelector("canvas") ?? host;
  const drawn = canvas.getBoundingClientRect();
  const box = host.getBoundingClientRect();
  if (drawn.width <= 0 || drawn.height <= 0) return null;
  return {
    n: mark.n,
    left: drawn.left - box.left + (mark.x / COMPUTER_SCREEN_W) * drawn.width,
    top: drawn.top - box.top + (mark.y / COMPUTER_SCREEN_H) * drawn.height,
  };
}

export interface PointerRingProps {
  botId: string;
  canvasRef: RefObject<HTMLElement | null>; // the live screen's box, which holds noVNC's canvas
}

// C3: a ring where the bot just clicked or typed on its computer, fading over POINTER_RING_MS. With reduced motion
// it is a still ring for the same time. Only pointers that arrive while the screen is open show.
export function PointerRing({ botId, canvasRef }: PointerRingProps) {
  const mark = pointerFor(useLiveState(), botId);
  const still = usePrefersReducedMotion();
  const seen = useRef(mark?.n ?? 0);
  const latest = useRef(mark);
  latest.current = mark;
  const [shown, setShown] = useState<Place | null>(null);
  const n = mark?.n ?? 0;
  useEffect(() => {
    const now = latest.current;
    if (now === null || n === seen.current) return undefined;
    seen.current = n;
    const place = ringPlace(now, canvasRef.current);
    if (place === null) return undefined;
    setShown(place);
    const timer = setTimeout(() => setShown(null), POINTER_RING_MS);
    return () => clearTimeout(timer);
    // Only a new pointer moves the ring; the box is read when it arrives.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [n]);
  if (shown === null) return null;
  return (
    <span key={shown.n} className={cx("pointer-ring", still && "pointer-ring--still")} aria-hidden="true"
      style={{
        left: `${shown.left}px`, top: `${shown.top}px`, width: POINTER_RING_SIZE_PX, height: POINTER_RING_SIZE_PX,
        animationDuration: `${POINTER_RING_MS}ms`,
      }} />
  );
}
