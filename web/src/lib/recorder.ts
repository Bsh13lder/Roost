// The composer's microphone (voice plan V3): the browser's own audio graph collects float samples (an AudioWorklet, or
// the older ScriptProcessor where there is none), and stop() turns them into a 16 kHz mono WAV. The microphone is
// released as soon as recording stops or is cancelled. Nothing is stored: the samples live in memory until sent.
import { recordingToWav } from "./wav";

export interface Recording {
  stop: () => Blob; // ends the recording and returns its WAV
  cancel: () => void; // ends it and drops what was said
  snapshot: () => Blob; // the WAV of what was said so far, the recording going on (live words, voice tuning D4)
  seconds: () => number; // how much sound is collected so far
}

const WORKLET_NAME = "roost-mic";
const SCRIPT_BUFFER = 4096;
// Copies each block of the first channel to the page. Loaded from a Blob, so it needs no file of its own.
const WORKLET_SOURCE = `
class RoostMic extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel) this.port.postMessage(channel.slice(0));
    return true;
  }
}
registerProcessor("${WORKLET_NAME}", RoostMic);
`;

export const MIC_UNSUPPORTED_TEXT = "This browser can't record here.";
export const MIC_DENIED_TEXT = "Roost can't use the microphone. Allow it in the browser's site settings.";

export function canRecord(): boolean {
  return typeof navigator !== "undefined" && typeof navigator.mediaDevices?.getUserMedia === "function"
    && typeof window !== "undefined" && typeof window.AudioContext === "function";
}

type Collect = (chunk: Float32Array) => void;

async function workletTap(context: AudioContext, source: MediaStreamAudioSourceNode, collect: Collect): Promise<AudioNode> {
  const url = URL.createObjectURL(new Blob([WORKLET_SOURCE], { type: "text/javascript" }));
  try {
    await context.audioWorklet.addModule(url);
  } finally {
    URL.revokeObjectURL(url);
  }
  const node = new AudioWorkletNode(context, WORKLET_NAME);
  node.port.onmessage = (event: MessageEvent<Float32Array>) => collect(event.data);
  source.connect(node);
  return node;
}

function scriptTap(context: AudioContext, source: MediaStreamAudioSourceNode, collect: Collect): AudioNode {
  const node = context.createScriptProcessor(SCRIPT_BUFFER, 1, 1);
  node.onaudioprocess = (event) => collect(event.inputBuffer.getChannelData(0).slice(0));
  source.connect(node);
  node.connect(context.destination); // a ScriptProcessor only runs while connected; its output stays silent
  return node;
}

async function tap(context: AudioContext, source: MediaStreamAudioSourceNode, collect: Collect): Promise<AudioNode> {
  if (context.audioWorklet && typeof AudioWorkletNode === "function") {
    try {
      return await workletTap(context, source, collect);
    } catch (err) {
      console.warn("The audio worklet didn't load; recording the older way.", err);
    }
  }
  return scriptTap(context, source, collect);
}

function micError(err: unknown): Error {
  const name = err instanceof DOMException || err instanceof Error ? err.name : "";
  if (name === "NotAllowedError" || name === "SecurityError") return new Error(MIC_DENIED_TEXT);
  if (name === "NotFoundError") return new Error("No microphone was found.");
  return new Error(MIC_UNSUPPORTED_TEXT);
}

export interface OpenMic {
  readonly sampleRate: number; // the microphone's own rate; recordingToWav brings it down to 16 kHz
  readonly echoCancellation: boolean; // the track really cancels the speaker's echo (a call may then hear you over the bot)
  readonly context: AudioContext; // the graph, for its state (a browser may suspend it until a tap)
  readonly close: () => void; // releases the microphone and the audio graph
}

// What the microphone was asked for: mono, the browser's echo cancellation, noise suppression and automatic gain
// (so quiet speech on a laptop or a phone still reaches the endpointer's start level).
export const MIC_CONSTRAINTS: MediaTrackConstraints = {
  channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true,
};

function cancelsEcho(stream: MediaStream): boolean {
  const track = stream.getTracks()[0] as (MediaStreamTrack & { getSettings?: () => MediaTrackSettings }) | undefined;
  return track?.getSettings?.().echoCancellation === true;
}

// Asks for the microphone and hands every block of float samples to `collect` until close(). Rejects with a sentence
// the screen can show. Shared by the composer's mic and a call; a call hands over the AudioContext it unlocked in the
// Call tap, so the graph is allowed to run.
export async function openMic(collect: Collect, given?: AudioContext): Promise<OpenMic> {
  if (!canRecord()) throw new Error(MIC_UNSUPPORTED_TEXT);
  let stream: MediaStream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: MIC_CONSTRAINTS });
  } catch (err) {
    throw micError(err);
  }
  const context = given ?? new AudioContext();
  let node: AudioNode | null = null;
  let done = false;
  const close = () => {
    if (done) return;
    done = true;
    stream.getTracks().forEach((track) => track.stop());
    node?.disconnect();
    context.close().catch((err: unknown) => console.warn("The audio graph didn't close cleanly.", err));
  };
  try {
    const source = context.createMediaStreamSource(stream);
    node = await tap(context, source, (chunk) => { if (!done) collect(chunk); });
  } catch (err) {
    close();
    throw micError(err);
  }
  return { sampleRate: context.sampleRate, echoCancellation: cancelsEcho(stream), context, close };
}

// Asks for the microphone and starts collecting. Rejects with a sentence the composer can show.
export async function startRecording(): Promise<Recording> {
  const chunks: Float32Array[] = [];
  const mic = await openMic((chunk) => chunks.push(chunk));
  return {
    stop: () => {
      mic.close();
      return recordingToWav(chunks, mic.sampleRate);
    },
    cancel: () => {
      mic.close();
      chunks.length = 0;
    },
    snapshot: () => recordingToWav([...chunks], mic.sampleRate),
    seconds: () => chunks.reduce((sum, chunk) => sum + chunk.length, 0) / mic.sampleRate,
  };
}
