// A tab left open across an update still runs the old build, which asks for chunk files the new build no
// longer has: the markdown renderer never loads, and bot replies stay as raw "**text**". The cure is one
// reload to pick up the new build, at most once per STALE_RELOAD_GAP_MS so a truly missing file can't loop.

const STALE_RELOAD_KEY = "roost:stale-build-reload-at";
const STALE_RELOAD_GAP_MS = 10 * 60_000;

function lastReload(store: Storage): number | null {
  try {
    const saved = store.getItem(STALE_RELOAD_KEY);
    return saved === null ? null : Number(saved) || null;
  } catch {
    return null;
  }
}

function markReload(store: Storage, now: number): void {
  try {
    store.setItem(STALE_RELOAD_KEY, String(now));
  } catch {
    // Storage blocked (private mode): reload anyway; the gap guard just can't hold across the reload.
  }
}

/** Reloads unless it already did so within the gap. Returns whether it reloaded. */
export function reloadForNewBuild(reload: () => void, store: Storage, now: number = Date.now()): boolean {
  const last = lastReload(store);
  if (last !== null && now - last < STALE_RELOAD_GAP_MS) return false;
  markReload(store, now);
  reload();
  return true;
}

/** Vite fires "vite:preloadError" when a lazy chunk can't load; that is the stale-build sign. */
export function installStaleBuildReload(target: EventTarget, reload: () => void, store: Storage): void {
  target.addEventListener("vite:preloadError", (event) => {
    event.preventDefault();
    reloadForNewBuild(reload, store);
  });
}
