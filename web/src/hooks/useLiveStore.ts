import { useEffect, useState } from "react";
import type { ServerFrame } from "../api/types";
import { createLiveStore, type LiveState, type LiveStore } from "../store/live";

// One WS connection for the whole app, created lazily on first use (so
// it never opens before login) and never recreated across route
// changes — Layout and Talk/Desk pages all read the same store through
// this hook rather than each owning a socket.
//
// `resetLiveStore` closes and drops it: `useAuth`'s `AuthProvider` calls
// this on logout and on a fresh login/register, so a second user who
// signs in on the same browser tab never has their UI briefly render
// the previous user's cached bots/messages over a connection that was
// never actually torn down.
let singleton: LiveStore | null = null;

function getLiveStore(): LiveStore {
  if (singleton === null) {
    singleton = createLiveStore();
    singleton.connect();
  }
  return singleton;
}

export function resetLiveStore(): void {
  if (singleton !== null) {
    singleton.close();
    singleton = null;
  }
}

export function useLiveState(): LiveState {
  const store = getLiveStore();
  const [state, setState] = useState<LiveState>(store.getState());

  useEffect(() => store.subscribe(setState), [store]);

  return state;
}

// Every state after a frame is applied (the ghosts' Thinking state, avatars v5).
export function subscribeLive(listener: (state: LiveState) => void): () => void {
  return getLiveStore().subscribe(listener);
}

// Every incoming frame, before it is applied (the attention notifier, S1.10).
export function onLiveFrame(listener: (frame: ServerFrame, state: LiveState) => void): () => void {
  return getLiveStore().onFrame(listener);
}
