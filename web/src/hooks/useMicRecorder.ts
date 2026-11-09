import { useCallback, useEffect, useRef, useState } from "react";
import { describeError } from "../api/client";
import { correctSpeech, partialTranscribe, transcribe } from "../api/voice";
import type { EnglishFix } from "../api/types";
import { startRecording, type Recording } from "../lib/recorder";
import { VOICE_MAX_SECONDS, VOICE_PARTIAL_EVERY_MS, VOICE_PARTIAL_MAX_S } from "../lib/wav";

export const MIC_TICK_MS = 250;
export const NOTHING_HEARD_TEXT = "I didn't catch anything. Try again.";

// idle → starting → recording (the live words come) → listening (the final transcript) → checking (the correction)
export type MicPhase = "idle" | "starting" | "recording" | "listening" | "checking";

// A correction of what you said (voice tuning D3): the raw words, the cleaned words and each fix.
export interface SpokenCorrection {
  readonly said: string;
  readonly corrected: string;
  readonly fixes: readonly EnglishFix[];
}

export interface MicOptions {
  readonly botId?: string; // the bot you speak to: its names and language guide the ear
  readonly correct?: boolean; // the bot's Correct what I say switch: ask for the correction after the transcript
  readonly onLive?: (text: string) => void; // the words so far while recording ("" when it ends)
  readonly onChecked?: () => void; // the check came back (changed or fine): the send need not ask again
  readonly onCorrected?: (correction: SpokenCorrection) => void; // the cleaned words, once they come
}

export interface MicRecorder {
  phase: MicPhase;
  seconds: number; // how long this recording has run
  toggle: () => void; // idle → recording → listening
  cancel: () => void; // drop the recording, send nothing
}

const errorText = (err: unknown) => (err instanceof Error && !("status" in err) ? err.message : describeError(err));
const isAbort = (err: unknown) => err instanceof DOMException && err.name === "AbortError";

// The composer's mic (voice plan V3, voice tuning D3/D4): tap to record, tap again (or reach two minutes) to stop.
// While it records, the buffer so far goes for a partial transcript every second (one in flight at a time, up to
// VOICE_PARTIAL_MAX_S) and the words show through onLive; the final WAV goes to the voice service and its words
// come back through onText; with the bot's switch on, the correction follows through onCorrected. Nothing is sent
// as a message. The microphone is released as soon as recording stops, is cancelled or the composer goes away.
export function useMicRecorder(onText: (text: string) => void, onError: (message: string) => void,
  options: MicOptions = {}): MicRecorder {
  const [phase, setPhase] = useState<MicPhase>("idle");
  const [seconds, setSeconds] = useState(0);
  const recording = useRef<Recording | null>(null);
  const started = useRef(0);
  const mounted = useRef(true);
  const partial = useRef<{ at: number; abort: AbortController | null }>({ at: 0, abort: null });
  const callbacks = useRef({ onText, onError, options });
  callbacks.current = { onText, onError, options };

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      recording.current?.cancel();
      recording.current = null;
      partial.current.abort?.abort();
    };
  }, []);

  const stopPartials = useCallback(() => {
    partial.current.abort?.abort();
    partial.current = { at: 0, abort: null };
    callbacks.current.options.onLive?.("");
  }, []);

  const check = useCallback(async (text: string) => {
    const { botId, correct, onCorrected, onChecked } = callbacks.current.options;
    if (!correct || !botId || !onCorrected) return;
    setPhase("checking");
    try {
      const found = await correctSpeech(text, botId);
      if (!mounted.current) return;
      onChecked?.();
      if (found.changed) onCorrected({ said: text, corrected: found.corrected, fixes: found.fixes });
    } catch (err) {
      console.warn("The correction didn't come; your words stay as heard.", err);
    }
  }, []);

  const finish = useCallback(() => {
    const current = recording.current;
    if (!current) return;
    recording.current = null;
    const wav = current.stop();
    stopPartials();
    setPhase("listening");
    transcribe(wav, undefined, callbacks.current.options.botId)
      .then(async ({ text }) => {
        if (!mounted.current) return;
        if (!text.trim()) { callbacks.current.onError(NOTHING_HEARD_TEXT); return; }
        callbacks.current.onText(text.trim());
        await check(text.trim());
      })
      .catch((err: unknown) => { if (mounted.current) callbacks.current.onError(describeError(err)); })
      .finally(() => { if (mounted.current) setPhase("idle"); });
  }, [stopPartials, check]);

  // One partial at a time, every VOICE_PARTIAL_EVERY_MS, while the buffer is short enough to be cheap.
  const livePartial = useCallback((current: Recording, now: number) => {
    if (partial.current.abort || now - partial.current.at < VOICE_PARTIAL_EVERY_MS) return;
    if (current.seconds() > VOICE_PARTIAL_MAX_S || current.seconds() < 0.5) return;
    const abort = new AbortController();
    partial.current = { at: now, abort };
    partialTranscribe(current.snapshot(), callbacks.current.options.botId, abort.signal)
      .then(({ text }) => {
        if (mounted.current && recording.current === current && text.trim()) callbacks.current.options.onLive?.(text.trim());
      })
      .catch((err: unknown) => { if (!isAbort(err)) console.warn("A live transcript didn't come.", err); })
      .finally(() => { if (partial.current.abort === abort) partial.current = { at: partial.current.at, abort: null }; });
  }, []);

  const begin = useCallback(() => {
    setPhase("starting");
    setSeconds(0);
    startRecording()
      .then((made) => {
        if (!mounted.current) { made.cancel(); return; }
        recording.current = made;
        started.current = Date.now();
        partial.current = { at: Date.now(), abort: null };
        setPhase("recording");
      })
      .catch((err: unknown) => {
        if (!mounted.current) return;
        setPhase("idle");
        callbacks.current.onError(errorText(err));
      });
  }, []);

  useEffect(() => {
    if (phase !== "recording") return undefined;
    const timer = window.setInterval(() => {
      const now = Date.now();
      const elapsed = Math.floor((now - started.current) / 1000);
      setSeconds(elapsed);
      if (elapsed >= VOICE_MAX_SECONDS) { finish(); return; }
      if (recording.current && callbacks.current.options.onLive) livePartial(recording.current, now);
    }, MIC_TICK_MS);
    return () => window.clearInterval(timer);
  }, [phase, finish, livePartial]);

  const toggle = useCallback(() => {
    if (phase === "idle") begin();
    else if (phase === "recording") finish();
  }, [phase, begin, finish]);

  const cancel = useCallback(() => {
    recording.current?.cancel();
    recording.current = null;
    stopPartials();
    setPhase("idle");
    setSeconds(0);
  }, [stopPartials]);

  return { phase, seconds, toggle, cancel };
}
