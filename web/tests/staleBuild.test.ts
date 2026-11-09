import { describe, expect, it, vi } from "vitest";
import { installStaleBuildReload, reloadForNewBuild } from "../src/lib/staleBuild";

// A tab left open across an update asks for chunk files the new build no longer has, so bot replies stayed
// as raw markdown ("**What I can do**"). The page reloads once to pick up the new build.

function fakeStore(): Storage {
  const data = new Map<string, string>();
  return {
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => void data.set(key, value),
    removeItem: (key: string) => void data.delete(key),
    clear: () => data.clear(),
    key: () => null,
    get length() {
      return data.size;
    },
  };
}

describe("reloadForNewBuild", () => {
  it("reloads once, then not again in the same tab session", () => {
    const reload = vi.fn();
    const store = fakeStore();
    expect(reloadForNewBuild(reload, store, 1_000)).toBe(true);
    expect(reloadForNewBuild(reload, store, 2_000)).toBe(false);
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("may reload again after a while (a later update)", () => {
    const reload = vi.fn();
    const store = fakeStore();
    reloadForNewBuild(reload, store, 1_000);
    expect(reloadForNewBuild(reload, store, 1_000 + 11 * 60_000)).toBe(true);
    expect(reload).toHaveBeenCalledTimes(2);
  });

  it("still reloads when storage throws (private mode)", () => {
    const reload = vi.fn();
    const broken = { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); } };
    expect(reloadForNewBuild(reload, broken as unknown as Storage, 1_000)).toBe(true);
    expect(reload).toHaveBeenCalledTimes(1);
  });
});

describe("installStaleBuildReload", () => {
  it("reloads on Vite's preload error and stops the error from surfacing", () => {
    const reload = vi.fn();
    const target = new EventTarget();
    installStaleBuildReload(target, reload, fakeStore());
    const event = new Event("vite:preloadError", { cancelable: true });
    target.dispatchEvent(event);
    expect(reload).toHaveBeenCalledTimes(1);
    expect(event.defaultPrevented).toBe(true);
  });
});
