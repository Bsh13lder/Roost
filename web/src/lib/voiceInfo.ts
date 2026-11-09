// GET /api/voice, fetched once and shared by the composer's mic, every speaker button and the Voice fold.
// A failed fetch is forgotten (so the next mount tries again) and reads as "not available".
import { useEffect, useSyncExternalStore } from "react";
import { describeError } from "../api/client";
import { getVoiceInfo, type VoiceInfo } from "../api/voice";

export type VoiceInfoState =
  | { readonly status: "loading" }
  | { readonly status: "ready"; readonly info: VoiceInfo }
  | { readonly status: "failed"; readonly error: string };

const LOADING: VoiceInfoState = { status: "loading" };

const REPROBE_MIN_MS = 10_000; // a voice that answers is asked again at most this often

let state: VoiceInfoState = LOADING;
let pending: Promise<void> | null = null;
let probedAt = 0;
const listeners = new Set<() => void>();

function publish(next: VoiceInfoState): void {
  state = next;
  listeners.forEach((listener) => listener());
}

function probe(): Promise<void> {
  if (pending === null) {
    probedAt = Date.now();
    pending = getVoiceInfo()
      .then((info) => publish({ status: "ready", info }))
      .catch((err: unknown) => {
        console.warn("Roost couldn't read the voice settings.", err);
        publish({ status: "failed", error: describeError(err) });
      })
      .finally(() => { pending = null; });
  }
  return pending;
}

export function loadVoiceInfo(): Promise<void> {
  if (state.status === "ready") return Promise.resolve();
  return probe();
}

// The composer gained focus: a voice that was off or unreachable is asked again (the Mac's service may have come
// up since the page loaded); one that answers is asked again only now and then.
export function reprobeVoiceInfo(): void {
  if (voiceAvailable(state) && Date.now() - probedAt < REPROBE_MIN_MS) return;
  void probe();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

const snapshot = (): VoiceInfoState => state;

export function useVoiceInfo(): VoiceInfoState {
  const current = useSyncExternalStore(subscribe, snapshot, snapshot);
  // Once per mount: a failed load is tried again only by the next mount, never in a loop.
  useEffect(() => {
    if (snapshot().status !== "ready") void loadVoiceInfo();
  }, []);
  return current;
}

// True only once the server said the Mac's voice service answers.
export function voiceAvailable(current: VoiceInfoState): boolean {
  return current.status === "ready" && current.info.available;
}

// Tests only: forget the shared answer.
export function resetVoiceInfo(): void {
  state = LOADING;
  pending = null;
  probedAt = 0;
  listeners.forEach((listener) => listener());
}
