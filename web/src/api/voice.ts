// Voice (docs/plans/2026-10-30-roost-voice.md V2/V3): what you say becomes text in the composer, and a bot's reply
// can be heard in its own voice. Recordings and audio are never stored here: they live in memory while they play.
import { apiRequest, apiUpload, errorFrom } from "./client";
import type { BotOut, BotVoice, EnglishFix } from "./types";

export interface VoiceSpeaker {
  id: string;
  name: string;
  best_in: string; // the language it was made for; every voice speaks the others too
}

export interface VoiceTone {
  id: string;
  name: string;
}

export interface VoiceLanguage {
  id: string; // "auto", or a short code such as "en" or "es"
  name: string;
}

export interface VoiceInfo {
  available: boolean; // the Mac's voice service answers
  speakers: VoiceSpeaker[];
  tones: VoiceTone[];
  speeds: number[];
  languages?: VoiceLanguage[]; // Auto-detect first, then what the ear supports (missing on an older server)
}

// What POST /api/voice/correct gives back (voice tuning D3): the cleaned words and each fix, or the words unchanged.
export interface SpeechCorrection {
  corrected: string;
  fixes: EnglishFix[];
  changed: boolean;
}

export interface SpeechPlan {
  parts: number;
  speed: number;
}

export const WAV_TYPE = "audio/wav";

export function getVoiceInfo(): Promise<VoiceInfo> {
  return apiRequest<VoiceInfo>("GET", "/api/voice");
}

// The whole object every time (the server checks each field against its list: 422 otherwise).
export function setBotVoice(botId: string, voice: BotVoice): Promise<BotOut> {
  return apiRequest<BotOut>("PUT", `/api/bots/${encodeURIComponent(botId)}/voice`, voice);
}

const hearPath = (route: string, botId?: string) =>
  botId ? `${route}?bot_id=${encodeURIComponent(botId)}` : route;

// A WAV recording → its words. It sends nothing: the text goes into the composer. A call passes a signal to cut a
// slow hearing short. With the bot (voice tuning D1/D2) the ear reads that bot's names and language first.
export function transcribe(wav: Blob, signal?: AbortSignal, botId?: string): Promise<{ text: string }> {
  return apiUpload<{ text: string }>(hearPath("/api/voice/transcribe", botId), wav, WAV_TYPE, signal);
}

// The recording so far, while the mic is still open → the live words (voice tuning D4).
export function partialTranscribe(wav: Blob, botId?: string, signal?: AbortSignal): Promise<{ text: string }> {
  return apiUpload<{ text: string }>(hearPath("/api/voice/partial", botId), wav, WAV_TYPE, signal);
}

// What you said, cleaned up before the send (voice tuning D3): names, numbers, sites and grammar, any language.
export function correctSpeech(text: string, botId: string): Promise<SpeechCorrection> {
  return apiRequest<SpeechCorrection>("POST", "/api/voice/correct", { text, bot_id: botId });
}

function speechPath(threadId: string, messageId: string): string {
  return `/api/threads/${encodeURIComponent(threadId)}/messages/${encodeURIComponent(messageId)}/speech`;
}

export function getSpeechPlan(threadId: string, messageId: string): Promise<SpeechPlan> {
  return apiRequest<SpeechPlan>("GET", speechPath(threadId, messageId));
}

export function speechPartUrl(threadId: string, messageId: string, part: number): string {
  return `${speechPath(threadId, messageId)}/${part}`;
}

export function sampleUrl(botId: string, speaker: string, tone: string): string {
  const query = new URLSearchParams({ speaker, tone });
  return `/api/bots/${encodeURIComponent(botId)}/voice/sample?${query.toString()}`;
}

// One piece of audio (a reply's part, a sample) as a Blob; a failure carries the server's words.
export async function fetchAudio(url: string): Promise<Blob> {
  const response = await fetch(url, { credentials: "include" });
  if (!response.ok) throw await errorFrom(response);
  return response.blob();
}

// A call is opening: the Mac loads its ear and voice now, so the first answer doesn't wait for them; with a bot it
// also pre-makes that bot's fixed lines (contract C).
export function warmVoice(botId?: string): Promise<{ ok: boolean }> {
  return apiRequest<{ ok: boolean }>("POST", "/api/voice/warm", botId ? { bot_id: botId } : {});
}

// ---- The call (contract A) -------------------------------------------------------------------------------------

export interface CallStarted {
  ok: boolean;
  expires_in: number; // seconds until the call lapses without another beat
}

const callPath = (threadId: string) => `/api/threads/${encodeURIComponent(threadId)}/call`;

// Starts the call on a thread or beats it; `interrupted` names the reply you cut off.
export function startCall(threadId: string, interrupted?: string): Promise<CallStarted> {
  return apiRequest<CallStarted>("POST", callPath(threadId), interrupted ? { interrupted } : {});
}

export function endCall(threadId: string): Promise<{ ok: boolean }> {
  return apiRequest<{ ok: boolean }>("DELETE", callPath(threadId));
}

// ---- Fixed lines (contract C) ----------------------------------------------------------------------------------

export type VoiceLineKey = "greeting" | "bye" | "not_caught" | "still_on_it" | "asking" | "say_again";

export function lineUrl(botId: string, key: VoiceLineKey): string {
  return `/api/bots/${encodeURIComponent(botId)}/voice/line/${key}`;
}

// ---- Live speech (contract B): a call's reply, spoken sentence by sentence as it streams -----------------------

export interface LiveSpeechPlan {
  parts: number; // how many parts can be fetched now
  done: boolean; // the last part is among them
  speed: number;
}

function liveSpeechPath(threadId: string, messageId: string): string {
  return `/api/threads/${encodeURIComponent(threadId)}/live-speech/${encodeURIComponent(messageId)}`;
}

export function liveSpeechPlan(threadId: string, messageId: string): Promise<LiveSpeechPlan> {
  return apiRequest<LiveSpeechPlan>("GET", liveSpeechPath(threadId, messageId));
}

export function liveSpeechPartUrl(threadId: string, messageId: string, part: number): string {
  return `${liveSpeechPath(threadId, messageId)}/${part}`;
}
