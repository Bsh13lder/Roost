import { useEffect, useSyncExternalStore } from "react";
import { calmSetting, onCalmChange, setCalmSetting } from "../lib/calm";
import { usePrefersReducedMotion } from "./usePrefersReducedMotion";

const CALM_CLASS = "calm";

// The Calm robots setting (lib/calm.ts) as state: the account menu's switch reads and writes it.
export function useCalmSetting(): [boolean, (on: boolean) => void] {
  const on = useSyncExternalStore(onCalmChange, calmSetting);
  return [on, setCalmSetting];
}

// Mounted once, in Layout: `html.calm` for the setting or for prefers-reduced-motion. robot.css keeps
// every motion but the blink behind `html:not(.calm)`, and the pointer loop (robot/lookAt.ts) stops.
export function useApplyCalm(): void {
  const [on] = useCalmSetting();
  const reduced = usePrefersReducedMotion();
  useEffect(() => {
    document.documentElement.classList.toggle(CALM_CLASS, on || reduced);
    return () => document.documentElement.classList.remove(CALM_CLASS);
  }, [on, reduced]);
}
