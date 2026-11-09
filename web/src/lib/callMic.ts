// A call's ear (voice call mode): the microphone stays open for the whole call. The browser's small blocks of
// samples are gathered into 20 ms frames; each frame's loudness drives the orb and steps the endpointer once, which
// cuts what you say into turns, each handed over as a 16 kHz WAV. Three modes: listening; guarded (the bot speaks
// and the browser cancels its echo: only a clearly louder voice counts, and a start is a barge-in); off (the bot
// speaks with no echo cancellation, or you muted it: blocks are ignored and a half-heard turn is dropped). Nothing
// is stored.
import {
  ENDPOINT_DEFAULTS, ENDPOINT_GUARDED, ENDPOINT_IDLE, flushEndpoint, stepEndpoint, type EndpointOptions,
  type EndpointState,
} from "./endpointer";
import { openMic } from "./recorder";
import { recordingToWav } from "./wav";

export const FRAME_MS = 20;

export interface TurnCollector {
  readonly push: (chunk: Float32Array) => number | null; // the frame's loudness once a frame is complete
  readonly reset: () => void; // drop a half-heard turn
  readonly flush: () => void; // end the turn now
  readonly setOptions: (options: EndpointOptions) => void; // swap the thresholds, keeping the turn
}

interface Frame { readonly blocks: readonly Float32Array[]; readonly ms: number }

// Gathers blocks into frames of about FRAME_MS, with the frame's RMS from the running sum of squares.
function createFramer(sampleRate: number) {
  const frameSamples = Math.round((sampleRate * FRAME_MS) / 1000);
  let blocks: Float32Array[] = [];
  let count = 0;
  let sumSquares = 0;
  return (chunk: Float32Array): (Frame & { level: number }) | null => {
    for (let i = 0; i < chunk.length; i += 1) sumSquares += chunk[i] * chunk[i];
    blocks = [...blocks, chunk];
    count += chunk.length;
    if (count < frameSamples) return null;
    const frame = { blocks, ms: (count / sampleRate) * 1000, level: count > 0 ? Math.sqrt(sumSquares / count) : 0 };
    blocks = [];
    count = 0;
    sumSquares = 0;
    return frame;
  };
}

export function createTurnCollector(
  sampleRate: number, onTurn: (wav: Blob) => void, options: EndpointOptions = ENDPOINT_DEFAULTS,
  onStart?: () => void,
): TurnCollector {
  let current = options;
  let state: EndpointState = ENDPOINT_IDLE;
  let before: Frame[] = []; // the last prerollMs, kept while waiting
  let turn: Float32Array[] = [];
  const frameOf = createFramer(sampleRate);

  const keepBefore = (frame: Frame) => {
    before = [...before, frame];
    let kept = before.reduce((sum, f) => sum + f.ms, 0);
    while (before.length > 1 && kept - before[0].ms >= current.prerollMs) {
      kept -= before[0].ms;
      before = before.slice(1);
    }
  };

  const finish = (event: "end" | "cut" | "drop" | null) => {
    if (event === "end" || event === "cut") onTurn(recordingToWav(turn, sampleRate));
    if (event !== null) turn = [];
  };

  const push = (chunk: Float32Array) => {
    const frame = frameOf(chunk);
    if (frame === null) return null;
    const wasSpeaking = state.speaking;
    keepBefore(frame);
    const next = stepEndpoint(state, frame.level, frame.ms, current);
    state = next.state;
    if (next.event === "start") {
      turn = before.flatMap((f) => f.blocks);
      onStart?.();
    } else if (wasSpeaking) {
      turn = [...turn, ...frame.blocks];
    }
    if (next.event !== "start") finish(next.event);
    return frame.level;
  };

  const flush = () => {
    const next = flushEndpoint(state, current);
    state = next.state;
    finish(next.event);
  };

  const reset = () => {
    state = { ...ENDPOINT_IDLE, floor: state.floor, levels: state.levels };
    before = [];
    turn = [];
  };
  return { push, reset, flush, setOptions: (next) => { current = next; } };
}

export type CallMicMode = "listening" | "guarded" | "off";

export interface CallMic {
  readonly setMode: (mode: CallMicMode) => void;
  readonly flush: () => void; // send what was heard so far
  readonly resume: () => Promise<void>; // wake a suspended audio graph (a tap)
  readonly audioState: () => AudioContextState;
  readonly echoCancellation: boolean; // the track really cancels the speaker's echo
  readonly close: () => void;
}

export interface CallMicHandlers {
  readonly onLevel: (level: number) => void;
  readonly onTurn: (wav: Blob) => void;
  readonly onBargeIn?: () => void; // guarded mode heard you over the bot
  readonly onAudioState?: (state: AudioContextState) => void;
}

const MODE_OPTIONS: Record<Exclude<CallMicMode, "off">, EndpointOptions> = {
  listening: ENDPOINT_DEFAULTS, guarded: ENDPOINT_GUARDED,
};

// Opens the microphone for a call. Rejects with a sentence the call screen can show.
export async function openCallMic(handlers: CallMicHandlers, context?: AudioContext): Promise<CallMic> {
  let mode: CallMicMode = "listening";
  let turns: TurnCollector | null = null;
  const mic = await openMic((chunk) => {
    if (mode === "off" || turns === null) return;
    const level = turns.push(chunk);
    if (level !== null) handlers.onLevel(level);
  }, context);
  turns = createTurnCollector(mic.sampleRate, handlers.onTurn, ENDPOINT_DEFAULTS, () => {
    if (mode === "guarded") handlers.onBargeIn?.();
  });
  const onState = () => handlers.onAudioState?.(mic.context.state);
  mic.context.addEventListener("statechange", onState);
  return {
    setMode: (next) => {
      mode = next;
      if (next === "off") {
        turns?.reset();
        handlers.onLevel(0);
      } else {
        turns?.setOptions(MODE_OPTIONS[next]);
      }
    },
    flush: () => turns?.flush(),
    resume: async () => {
      await mic.context.resume();
      onState();
    },
    audioState: () => mic.context.state,
    echoCancellation: mic.echoCancellation,
    close: () => {
      mode = "off";
      mic.context.removeEventListener("statechange", onState);
      mic.close();
    },
  };
}
