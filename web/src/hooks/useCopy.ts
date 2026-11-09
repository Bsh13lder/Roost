import { useCallback, useEffect, useRef, useState } from "react";
import { COPY_RESET_MS } from "../ui/constants";

export type CopyState = "idle" | "copied" | "failed";

// Copies text to the clipboard and says how it went for a moment (redesign P2): "copied", or "failed"
// when the browser has no clipboard here or refuses it. Never throws. A copy that settles after its
// component is gone sets no state and starts no timer; unmounting clears a running one.
export function useCopy(resetMs: number = COPY_RESET_MS): { state: CopyState; copy: (text: string) => void } {
  const [state, setState] = useState<CopyState>("idle");
  const timer = useRef<number | undefined>(undefined);
  const mounted = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      window.clearTimeout(timer.current);
    };
  }, []);
  const settle = useCallback((next: CopyState) => {
    if (!mounted.current) return;
    setState(next);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setState("idle"), resetMs);
  }, [resetMs]);
  const copy = useCallback((text: string) => {
    const clipboard = typeof navigator === "undefined" ? undefined : navigator.clipboard;
    if (!clipboard?.writeText) {
      settle("failed");
      return;
    }
    clipboard.writeText(text).then(() => settle("copied"), (error: unknown) => {
      console.warn("Copy to the clipboard failed.", error);
      settle("failed");
    });
  }, [settle]);
  return { state, copy };
}
