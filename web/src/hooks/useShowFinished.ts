// web/src/hooks/useShowFinished.ts: the Show finished switch (lead task 14), off by default and kept in this browser
// under one key for every view that lists tasks, so the List, Kanban, Calendar, a project's page and a bot's Made by
// agree. Every reader hears a change at once, and a change in another tab too. A browser that refuses storage keeps
// the choice for this visit only.
import { useCallback, useSyncExternalStore } from "react";

export const SHOW_FINISHED_STORAGE_KEY = "roost.show-finished.v1";

const listeners = new Set<() => void>();
let unsaved: boolean | null = null; // the choice storage refused, for this visit

function read(): boolean {
  if (unsaved !== null) return unsaved;
  try {
    return window.localStorage.getItem(SHOW_FINISHED_STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

function write(show: boolean): void {
  try {
    if (show) window.localStorage.setItem(SHOW_FINISHED_STORAGE_KEY, "1");
    else window.localStorage.removeItem(SHOW_FINISHED_STORAGE_KEY);
    unsaved = null;
  } catch (error) {
    console.warn("Could not remember Show finished; it lasts until the page reloads.", error);
    unsaved = show;
  }
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  const onStorage = (event: StorageEvent) => { if (event.key === SHOW_FINISHED_STORAGE_KEY || event.key === null) listener(); };
  window.addEventListener("storage", onStorage);
  return () => { listeners.delete(listener); window.removeEventListener("storage", onStorage); };
}

export function useShowFinished(): [boolean, (show: boolean) => void] {
  const show = useSyncExternalStore(subscribe, read, () => false);
  return [show, useCallback((next: boolean) => write(next), [])];
}
