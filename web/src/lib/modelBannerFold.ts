// The new-model note in the sidebar starts folded to one row; this browser remembers when you open it.
// Kept in this browser only, and never an error when storage is refused.
export const MODEL_BANNER_STORAGE_KEY = "roost.model-banner-open.v1";
export type FoldStorage = Pick<Storage, "getItem" | "setItem">;

function browserStorage(): FoldStorage | undefined {
  try {
    return window.localStorage;
  } catch (error) {
    console.warn("This browser keeps no site data here: the new-model note stays folded after a reload.", error);
    return undefined;
  }
}

export function readBannerOpen(storage: FoldStorage | undefined = browserStorage()): boolean {
  try {
    return storage?.getItem(MODEL_BANNER_STORAGE_KEY) === "true";
  } catch (error) {
    console.warn("Could not read whether the new-model note was open; it starts folded.", error);
    return false;
  }
}

export function writeBannerOpen(open: boolean, storage: FoldStorage | undefined = browserStorage()): void {
  try {
    storage?.setItem(MODEL_BANNER_STORAGE_KEY, String(open));
  } catch (error) {
    console.warn("Could not remember whether the new-model note is open.", error);
  }
}
