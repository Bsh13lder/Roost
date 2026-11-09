import { createContext, useContext } from "react";

// Where an overlay inside a Sheet draws (redesign P3): the Sheet's own panel. Each Radix package here
// carries its own copy of Radix's focus scope, so a Select or a calendar drawn on the page body would fight
// the Sheet's focus trap (each pulls focus back, without end). Drawn inside the Sheet, focus stays within
// it. Outside a Sheet there is no container, and overlays draw on the body as before.
export const PortalContainer = createContext<HTMLElement | null>(null);

export function usePortalContainer(): HTMLElement | undefined {
  return useContext(PortalContainer) ?? undefined;
}
