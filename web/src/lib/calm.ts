// Calm robots (avatars v5 §C): a switch in the account menu that keeps every bot still, like
// prefers-reduced-motion does: no eye following, no float, no events, only slow blinks. Kept in this
// browser only, and never an error when storage is refused.
export const CALM_STORAGE_KEY = "roost.calm-robots.v1";
export type CalmStorage = Pick<Storage, "getItem" | "setItem">;

function browserStorage(): CalmStorage | undefined {
  try {
    return window.localStorage;
  } catch (error) {
    console.warn("This browser keeps no site data here: Calm robots lasts until the page reloads.", error);
    return undefined;
  }
}

export function readCalm(storage: CalmStorage | undefined = browserStorage()): boolean {
  try {
    return storage?.getItem(CALM_STORAGE_KEY) === "true";
  } catch (error) {
    console.warn("Could not read the Calm robots setting; robots move.", error);
    return false;
  }
}

export function writeCalm(on: boolean, storage: CalmStorage | undefined = browserStorage()): void {
  try {
    storage?.setItem(CALM_STORAGE_KEY, String(on));
  } catch (error) {
    console.warn("Could not remember the Calm robots setting.", error);
  }
}

let setting: boolean | null = null; // read once, on first use
const listeners = new Set<() => void>();

export function calmSetting(): boolean {
  if (setting === null) setting = readCalm();
  return setting;
}

export function setCalmSetting(on: boolean): void {
  if (on === calmSetting()) return;
  setting = on;
  writeCalm(on);
  listeners.forEach((listener) => listener());
}

export function onCalmChange(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
