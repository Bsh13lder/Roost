// A stand-in for IntersectionObserver (jsdom has none): the look-at engine's tests see what it observes
// and can tell it that an avatar came on or off screen.
export interface ObserverStub {
  observed: Element[];
  enter(target: Element, visible: boolean): void;
  restore(): void;
}

type Callback = (entries: Array<{ target: Element; isIntersecting: boolean }>) => void;

export function installObserverStub(): ObserverStub {
  const observed: Element[] = [];
  const callbacks = new Set<Callback>();
  const previous = globalThis.IntersectionObserver;
  class FakeObserver {
    private readonly callback: Callback;
    constructor(callback: Callback) { this.callback = callback; callbacks.add(callback); }
    observe(target: Element) { observed.push(target); }
    unobserve(target: Element) { const at = observed.indexOf(target); if (at !== -1) observed.splice(at, 1); }
    disconnect() { callbacks.delete(this.callback); }
  }
  globalThis.IntersectionObserver = FakeObserver as unknown as typeof IntersectionObserver;
  return {
    observed,
    enter: (target, visible) => { for (const callback of callbacks) callback([{ target, isIntersecting: visible }]); },
    restore: () => { globalThis.IntersectionObserver = previous; },
  };
}
