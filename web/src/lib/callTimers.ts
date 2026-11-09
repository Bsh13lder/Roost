// One timer at a time: setting it again replaces the one that waits, so a call's clocks (the hearing cut-off, the
// thinking watchdog, "Still on it", the speaker's tail) never fire twice or after they were cleared.

export interface TimerSlot {
  readonly set: (fn: () => void, ms: number) => void;
  readonly clear: () => void;
  readonly pending: () => boolean;
}

export function createTimerSlot(): TimerSlot {
  let handle: ReturnType<typeof setTimeout> | null = null;
  const clear = () => {
    if (handle !== null) clearTimeout(handle);
    handle = null;
  };
  return {
    set: (fn, ms) => {
      clear();
      handle = setTimeout(() => { handle = null; fn(); }, ms);
    },
    clear,
    pending: () => handle !== null,
  };
}

// A beat: `fn` now and then every `ms` until stopped.
export function createBeat(fn: () => void, ms: number): { readonly stop: () => void } {
  fn();
  const handle = setInterval(fn, ms);
  return { stop: () => clearInterval(handle) };
}
