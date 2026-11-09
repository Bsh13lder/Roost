// The one voice player (voice plan V3): a bot's reply, a Report, a voice sample, a call's fixed line or a call's
// reply as it streams, played part by part through one HTMLAudioElement at the bot's speed (pitch kept). Only one
// thing plays at a time, app-wide: starting another stops the first, and tapping the same one again stops it. Audio
// lives in memory (object URLs) only while it plays.
import { useSyncExternalStore } from "react";
import { ApiError, describeError } from "../api/client";
import {
  fetchAudio, getSpeechPlan, lineUrl, liveSpeechPartUrl, liveSpeechPlan, sampleUrl, speechPartUrl, type VoiceLineKey,
} from "../api/voice";
import { encodeWav } from "../lib/wav";

export type SpeechPhase = "idle" | "loading" | "playing";

export interface SpeechState {
  readonly key: string | null; // what plays: "message:<id>", "sample:<bot id>", "line:<key>" or "live:<id>"
  readonly phase: SpeechPhase;
}

// What to play: the rate, and the next part by index (null: nothing more). The next part is fetched while one plays.
export interface SpeechSource {
  readonly rate: number;
  readonly next: (index: number) => Promise<Blob | null>;
  readonly onPart?: (index: number) => void; // a part starts
}

export const PLAY_FAILED_TEXT = "That couldn't be played. Try again.";
export const LIVE_POLL_MS = 400; // live speech with no frame: how often the plan is asked (contract B)
const LIVE_PART_RETRIES_MAX = 50; // a part that stays 404 this many ticks is given up (~20 s)
const SILENT_SAMPLES = 160; // 10 ms at 16 kHz: the unlock's silent moment

const IDLE: SpeechState = { key: null, phase: "idle" };

let state: SpeechState = IDLE;
let audio: HTMLAudioElement | null = null;
let objectUrl: string | null = null;
let token = 0; // bumped by every start and stop: an older run sees it changed and ends quietly
let endPart: (() => void) | null = null; // ends the part that plays now (a stop)
const listeners = new Set<() => void>();

function publish(next: SpeechState): void {
  state = next;
  listeners.forEach((listener) => listener());
}

function forgetUrl(): void {
  if (objectUrl !== null) URL.revokeObjectURL(objectUrl);
  objectUrl = null;
}

function player(): HTMLAudioElement {
  if (audio === null) audio = new Audio();
  return audio;
}

// Plays one part to its end. Resolves at its end or when stopped; rejects when the browser refuses or fails.
function playPart(blob: Blob, rate: number, run: number, key: string): Promise<void> {
  const element = player();
  forgetUrl();
  objectUrl = URL.createObjectURL(blob);
  element.src = objectUrl;
  element.preservesPitch = true;
  element.defaultPlaybackRate = rate; // a new src resets playbackRate to this
  element.playbackRate = rate;
  return new Promise<void>((resolve, reject) => {
    const settle = (fail?: unknown) => {
      element.removeEventListener("ended", onEnded);
      element.removeEventListener("error", onError);
      endPart = null;
      if (fail === undefined) resolve();
      else reject(fail);
    };
    const onEnded = () => settle();
    const onError = () => settle(new Error(PLAY_FAILED_TEXT));
    element.addEventListener("ended", onEnded);
    element.addEventListener("error", onError);
    endPart = () => settle();
    Promise.resolve(element.play())
      .then(() => { if (run === token) publish({ key, phase: "playing" }); })
      .catch((err: unknown) => settle(err ?? new Error(PLAY_FAILED_TEXT)));
  });
}

async function playAll(source: SpeechSource, run: number, key: string): Promise<void> {
  let pending = source.next(0);
  for (let index = 0; ; index += 1) {
    const blob = await pending;
    if (run !== token || blob === null) return;
    pending = source.next(index + 1); // fetched (or awaited) while this part plays
    pending.catch(() => undefined); // a stop before it is awaited must not leave an unhandled rejection
    source.onPart?.(index);
    await playPart(blob, source.rate, run, key);
    if (run !== token) return;
  }
}

// Stops whatever plays (or loads). Safe to call when nothing does.
export function stopSpeech(): void {
  token += 1;
  audio?.pause();
  endPart?.();
  forgetUrl();
  if (state.phase !== "idle") publish(IDLE);
}

// Plays `key` from `load`, stopping anything else first. Rejects (with the server's words when it has some) only for
// the run that is still current; a run that was stopped ends quietly. `alive` tells a slow source it was stopped.
export async function playSpeech(key: string, load: (alive: () => boolean) => Promise<SpeechSource>): Promise<void> {
  stopSpeech();
  const run = token;
  const alive = () => run === token;
  publish({ key, phase: "loading" });
  try {
    const source = await load(alive);
    if (!alive()) return;
    await playAll(source, run, key);
  } catch (err) {
    if (!alive()) return;
    stopSpeech();
    throw err;
  }
  if (alive()) {
    forgetUrl();
    publish(IDLE);
  }
}

// A fixed number of parts, each fetched from its address.
function countedSource(parts: number, rate: number, part: (index: number) => Promise<Blob>): SpeechSource {
  return { rate, next: (index) => (index < parts ? part(index) : Promise.resolve(null)) };
}

export const messageKey = (messageId: string) => `message:${messageId}`;
export const sampleKey = (botId: string) => `sample:${botId}`;
export const liveKey = (messageId: string) => `live:${messageId}`;
export const lineKey = (key: VoiceLineKey) => `line:${key}`;

export function speakMessage(threadId: string, messageId: string): Promise<void> {
  return playSpeech(messageKey(messageId), async () => {
    const plan = await getSpeechPlan(threadId, messageId);
    return countedSource(plan.parts, plan.speed, (i) => fetchAudio(speechPartUrl(threadId, messageId, i)));
  });
}

export function playSample(botId: string, speaker: string, tone: string, speed: number): Promise<void> {
  const url = sampleUrl(botId, speaker, tone);
  return playSpeech(sampleKey(botId), async () => countedSource(1, speed, () => fetchAudio(url)));
}

const isNotFound = (err: unknown) => err instanceof ApiError && err.status === 404;

// A call's fixed line in the bot's voice (contract C). An old server has none (404): nothing plays, nothing fails.
export async function speakLine(botId: string, key: VoiceLineKey): Promise<void> {
  try {
    await playSpeech(lineKey(key), async () => countedSource(1, 1, () => fetchAudio(lineUrl(botId, key))));
  } catch (err) {
    if (!isNotFound(err)) throw err;
  }
}

// ---- Live speech (contract B) ----------------------------------------------------------------------------------

export interface LiveReady {
  readonly parts: number; // parts that can be fetched
  readonly done: boolean; // the last part is among them
}

// What the call knows about a reply's speech: the live store's speech_ready frames, and a wake-up when they change.
export interface LiveSource {
  readonly ready: () => LiveReady;
  readonly onChange: (listener: () => void) => () => void;
  readonly settled?: () => boolean; // the reply is stored: with no new part in a poll, nothing more is coming
  readonly onPart?: (index: number) => void;
}

// The server has no live speech for this reply (an old server, or no call on the thread): speak it stored instead.
export class LiveSpeechUnavailable extends Error {
  constructor() {
    super("Live speech isn't available for this reply.");
    this.name = "LiveSpeechUnavailable";
  }
}

// Resolves true when a frame wakes it, false after LIVE_POLL_MS.
function waitTick(source: LiveSource): Promise<boolean> {
  return new Promise<boolean>((resolve) => {
    let off: (() => void) | null = null;
    const timer = setTimeout(() => { off?.(); resolve(false); }, LIVE_POLL_MS);
    off = source.onChange(() => { clearTimeout(timer); off?.(); resolve(true); });
  });
}

const atLeast = (a: LiveReady, b: LiveReady): LiveReady => ({ parts: Math.max(a.parts, b.parts), done: a.done || b.done });

// Pulls the reply's parts as they become ready: a frame or a poll says one more is in, a 404 means not quite yet.
function livePuller(threadId: string, messageId: string, source: LiveSource, alive: () => boolean, first: LiveReady) {
  let polled = first;
  const known = () => atLeast(source.ready(), polled);
  const poll = async () => {
    try {
      const plan = await liveSpeechPlan(threadId, messageId);
      polled = atLeast(polled, plan);
    } catch (err) {
      console.warn("The live speech plan couldn't be read; waiting for the next frame.", err);
    }
  };
  return async (index: number): Promise<Blob | null> => {
    let retries = 0;
    let stale = false;
    for (;;) {
      if (!alive()) return null;
      const ready = known();
      if (index < ready.parts) {
        try {
          return await fetchAudio(liveSpeechPartUrl(threadId, messageId, index));
        } catch (err) {
          if (!isNotFound(err) || ++retries > LIVE_PART_RETRIES_MAX) throw err;
        }
      } else if (ready.done || (stale && source.settled?.())) {
        return null;
      }
      const woke = await waitTick(source);
      if (!woke) {
        await poll();
        stale = known().parts === ready.parts;
      }
    }
  };
}

// Speaks a call's reply as the server makes its parts (contract B). Rejects with LiveSpeechUnavailable when the
// server has no live speech for it, so the call speaks the stored reply instead.
export function speakLive(threadId: string, messageId: string, source: LiveSource): Promise<void> {
  return playSpeech(liveKey(messageId), async (alive) => {
    let plan;
    try {
      plan = await liveSpeechPlan(threadId, messageId);
    } catch (err) {
      if (isNotFound(err)) throw new LiveSpeechUnavailable();
      throw err;
    }
    return { rate: plan.speed, next: livePuller(threadId, messageId, source, alive, plan), onPart: source.onPart };
  });
}

// ---- Unlocking ---------------------------------------------------------------------------------------------------

let silentUrl: string | null = null;

function silentWav(): string {
  if (silentUrl === null) {
    const bytes = new Uint8Array(encodeWav(new Float32Array(SILENT_SAMPLES)));
    let text = "";
    bytes.forEach((byte) => { text += String.fromCharCode(byte); });
    silentUrl = `data:audio/wav;base64,${btoa(text)}`;
  }
  return silentUrl;
}

// In the Call tap: a silent moment through the shared element, so the browser lets the call's sound play later
// without another tap. Never throws; a browser that still refuses is met by "Tap to hear" on the orb.
export async function unlockSpeech(): Promise<void> {
  if (state.phase !== "idle") return;
  const element = player();
  element.src = silentWav();
  try {
    await element.play();
  } catch (err) {
    console.info("The sound wasn't unlocked by the tap; the call will ask for one.", err);
  }
  element.pause();
}

// Tap once to play, again to stop.
export function toggleSpeech(key: string, start: () => Promise<void>): Promise<void> {
  if (state.key === key && state.phase !== "idle") {
    stopSpeech();
    return Promise.resolve();
  }
  return start();
}

// The words for a failed play: a browser that blocked sound, or the server's own words.
export function speechErrorText(err: unknown): string {
  if (err instanceof DOMException && err.name === "NotAllowedError") return "Your browser blocked the sound. Tap the speaker again.";
  if (err instanceof Error && err.message === PLAY_FAILED_TEXT) return PLAY_FAILED_TEXT;
  return describeError(err);
}

export const isSoundBlocked = (err: unknown) => err instanceof DOMException && err.name === "NotAllowedError";

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

const snapshot = (): SpeechState => state;

export function useSpeechState(): SpeechState {
  return useSyncExternalStore(subscribe, snapshot, snapshot);
}

// This key's phase: "idle" whenever something else plays.
export function useSpeechPhase(key: string): SpeechPhase {
  const current = useSpeechState();
  return current.key === key ? current.phase : "idle";
}

// Tests only: stop and drop the element so the next test makes its own.
export function resetSpeech(): void {
  stopSpeech();
  audio = null;
}
