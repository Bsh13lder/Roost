import "@testing-library/jest-dom/vitest";
import { beforeEach } from "vitest";
import { setAppTimeZone } from "../src/lib/timeZone";

// The account's zone (owner, 2026-11-09) is the browser's until /api/auth/me says otherwise. Every test starts
// on Madrid's, whatever the machine's zone, so the expected times hold anywhere; a test may switch it.
setAppTimeZone("Europe/Madrid");
beforeEach(() => { setAppTimeZone("Europe/Madrid"); });

// jsdom has no matchMedia implementation at all — give every test a
// harmless default (matches: false) so a component that calls it
// doesn't throw; individual tests override this with their own
// vi.stubGlobal/direct assignment when they need matches: true. A suite
// in the node environment (the license gate) has no window at all.
if (typeof window !== "undefined" && !window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

// Radix primitives (Select, DropdownMenu, Popover, Tooltip) call these browser APIs, which jsdom
// does not have. Harmless stand-ins on Element, so a test may still replace one with its own spy.
if (typeof window !== "undefined") {
  const element = window.Element.prototype;
  element.hasPointerCapture ??= () => false;
  element.setPointerCapture ??= () => {};
  element.releasePointerCapture ??= () => {};
  element.scrollIntoView ??= () => {};
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
}

// Node 25 puts its own localStorage on the global, and it has no methods unless node runs with a valid
// --localstorage-file; it also hides jsdom's. Give every test a working, empty one (redesign P2's unread
// dots), as a getter so a test can still make it throw.
if (typeof window !== "undefined" && typeof window.localStorage?.getItem !== "function") {
  class MemoryStorage {
    private readonly items = new Map<string, string>();
    get length(): number { return this.items.size; }
    clear(): void { this.items.clear(); }
    getItem(key: string): string | null { return this.items.get(key) ?? null; }
    key(index: number): string | null { return [...this.items.keys()][index] ?? null; }
    removeItem(key: string): void { this.items.delete(key); }
    setItem(key: string, value: string): void { this.items.set(key, String(value)); }
  }
  const storage = new MemoryStorage() as unknown as Storage;
  Object.defineProperty(globalThis, "localStorage", { configurable: true, get: () => storage });
}
