import { useEffect, useRef, useState } from "react";
import { blendGeometry, type LensGeometry } from "./lensbot";

export const MORPH_MS = 450;

interface Tween {
  readonly from: LensGeometry;
  readonly to: LensGeometry;
  readonly t: number;
}

const easeOut = (u: number) => 1 - (1 - u) ** 3;

// The geometry a Lensbot draws. When its shape changes and motion is on, the 48 body points tween from
// the old shape to the new one over 450 ms (the picker's drag morph); a change part way starts from where
// the tween is. The face is the new one at once. `morphing` is true while it runs.
export function useMorph(target: LensGeometry, animate: boolean): { geometry: LensGeometry; morphing: boolean } {
  const [tween, setTween] = useState<Tween | null>(null);
  const shown = useRef<LensGeometry>(target); // what the last render drew
  const settled = useRef(target); // the geometry the drawing has reached (or is tweening toward)
  const canTween = animate && typeof requestAnimationFrame === "function";
  useEffect(() => {
    if (settled.current === target) return undefined;
    const from = shown.current;
    settled.current = target;
    if (!canTween || from.d === target.d) {
      setTween(null);
      return undefined;
    }
    let start: number | null = null;
    let raf = requestAnimationFrame(function run(now: number) {
      if (start === null) start = now;
      const u = Math.min(1, (now - start) / MORPH_MS);
      if (u < 1) {
        setTween({ from, to: target, t: easeOut(u) });
        raf = requestAnimationFrame(run);
      } else {
        setTween(null);
      }
    });
    return () => cancelAnimationFrame(raf);
  }, [target, canTween]);
  // A body change the effect has not started tweening yet keeps the last body one more render.
  const holding = canTween && settled.current !== target && shown.current.d !== target.d;
  const geometry = tween ? blendGeometry(tween.from, tween.to, tween.t) : holding ? { ...target, ...bodyOf(shown.current) } : target;
  shown.current = geometry;
  return { geometry, morphing: tween !== null || holding };
}

const bodyOf = (geometry: LensGeometry) => ({ pts: geometry.pts, d: geometry.d, box: geometry.box, cy: geometry.cy, rot: geometry.rot });
