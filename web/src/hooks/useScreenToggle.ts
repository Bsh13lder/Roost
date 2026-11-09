// web/src/hooks/useScreenToggle.ts: a show / hide switch remembered per screen in this browser (board toggles,
// 2026-10-26): Routines on a calendar, Tasks a bot made, a Plan's done items. Each (screen, toggle) pair has its own
// key, so the Board's List and its Calendar keep their own choices. Every reader of the same pair hears a change at
// once (the toolbar and the lazy calendar agree), and a change in another tab too. A browser that refuses storage
// keeps the choice for this visit only.
import { useCallback, useSyncExternalStore } from "react";

export type ToggleName = "routines" | "botMade" | "done";

export const SCREEN_TOGGLE_PREFIX = "roost.show.v1";

export const screenToggleKey = (screen: string, toggle: ToggleName): string => `${SCREEN_TOGGLE_PREFIX}.${screen}.${toggle}`;

const ON = "1";
const OFF = "0";
const listeners = new Set<() => void>();
const unsaved = new Map<string, boolean>(); // choices storage refused, for this visit

function read(key: string, fallback: boolean): boolean {
  const kept = unsaved.get(key);
  if (kept !== undefined) return kept;
  try {
    const raw = window.localStorage.getItem(key);
    return raw === ON ? true : raw === OFF ? false : fallback;
  } catch {
    return fallback;
  }
}

function write(key: string, show: boolean): void {
  try {
    window.localStorage.setItem(key, show ? ON : OFF);
    unsaved.delete(key);
  } catch (error) {
    console.warn("Could not remember this show / hide choice; it lasts until the page reloads.", error);
    unsaved.set(key, show);
  }
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  const onStorage = (event: StorageEvent) => {
    if (event.key === null || event.key.startsWith(SCREEN_TOGGLE_PREFIX)) listener();
  };
  window.addEventListener("storage", onStorage);
  return () => { listeners.delete(listener); window.removeEventListener("storage", onStorage); };
}

/** One screen's show / hide choice: `fallback` until the user flips it. */
export function useScreenToggle(screen: string, toggle: ToggleName, fallback = true): [boolean, (show: boolean) => void] {
  const key = screenToggleKey(screen, toggle);
  const show = useSyncExternalStore(subscribe, () => read(key, fallback), () => fallback);
  return [show, useCallback((next: boolean) => write(key, next), [key])];
}
