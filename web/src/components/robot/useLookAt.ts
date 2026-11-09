import { useEffect, type RefObject } from "react";
import { registerLookAt } from "./lookAt";

// A robot joins the shared pointer loop (lookAt.ts) while it is live: drawn larger than 32 px, with its
// eyes showing, and not still. The loop reads its eye line from `data-ey`, so a morph never re-registers it.
export function useLookAt(ref: RefObject<SVGSVGElement | null>, enabled: boolean): void {
  useEffect(() => {
    const svg = ref.current;
    if (!enabled || !svg) return undefined;
    return registerLookAt(svg);
  }, [ref, enabled]);
}
