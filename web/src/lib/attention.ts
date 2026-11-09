// Bots that finished, asked for you or got Stuck while Roost's tab was hidden (S1.10, stuck flow):
// a highlighted Home row, plus a browser notification when the user allowed them.
import type { BotOut, ServerFrame } from "../api/types";
import { plainText } from "./plainText";
import { signInWaitHost } from "./stuck";

export interface AttentionSignal {
  botId: string;
  title: string;
  body: string;
}

const BODY_CHARS = 120;
const oneLine = (text: string) => {
  const flat = text.split(/\s+/).join(" ").trim();
  return flat.length <= BODY_CHARS ? flat : `${flat.slice(0, BODY_CHARS - 1)}…`;
};

export function attentionFor(frame: ServerFrame, bots: Readonly<Record<string, BotOut>>): AttentionSignal | null {
  if (frame.type === "message") {
    const message = frame.message;
    const bot = message.author_bot_id ? bots[message.author_bot_id] : undefined;
    if (!bot?.notify || message.role !== "bot" || message.kind !== "text" || !message.body.trim()) return null;
    return { botId: bot.id, title: `${bot.name} replied`, body: oneLine(plainText(message.body)) };
  }
  if (frame.type === "bot_status" && (frame.status === "asking_you" || frame.status === "stuck")) {
    const bot = bots[frame.bot_id];
    if (!bot?.notify) return null;
    const signIn = signInWaitHost(frame.status, frame.activity) !== null;
    const title = signIn ? `${bot.name} needs you to sign in`
      : frame.status === "stuck" ? `${bot.name} is stuck` : `${bot.name} needs you`;
    return { botId: bot.id, title, body: frame.activity ?? "" };
  }
  return null;
}

let marked: ReadonlySet<string> = new Set();
const listeners = new Set<() => void>();
const changed = () => listeners.forEach((listener) => listener());

export function markAttention(botId: string): void {
  if (marked.has(botId)) return;
  marked = new Set([...marked, botId]);
  changed();
}

export function clearAttention(botId: string): void {
  if (!marked.has(botId)) return;
  marked = new Set([...marked].filter((id) => id !== botId));
  changed();
}

export const attentionSnapshot = (): ReadonlySet<string> => marked;

export function onAttentionChange(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function showNotification(signal: AttentionSignal): void {
  if (typeof Notification === "undefined" || Notification.permission !== "granted") return;
  new Notification(signal.title, { body: signal.body, tag: signal.botId });
}

export type BrowserPermission = NotificationPermission | "unsupported";

export const notificationPermission = (): BrowserPermission =>
  typeof Notification === "undefined" ? "unsupported" : Notification.permission;

// Call it from a click: browsers show the prompt only for a user gesture. Every bot's
// switch starts on (bots.notify defaults to 1), so without this tap nothing would ever show.
export async function askNotificationPermission(): Promise<BrowserPermission> {
  if (typeof Notification === "undefined") return "unsupported";
  return Notification.requestPermission();
}
