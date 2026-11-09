import { apiRequest } from "./client";
import type { EnglishFix, MessageOut, RememberedOffer, ThreadOut } from "./types";

export function listThreads(botId: string): Promise<ThreadOut[]> {
  return apiRequest<ThreadOut[]>("GET", `/api/bots/${botId}/threads`);
}

export function createThread(botId: string, title?: string | null): Promise<ThreadOut> {
  return apiRequest<ThreadOut>("POST", `/api/bots/${botId}/threads`, { title: title ?? null });
}

// The bot's one chat (the thread last talked in), made when it has none.
export function openChat(botId: string): Promise<ThreadOut> {
  return apiRequest<ThreadOut>("POST", `/api/bots/${botId}/chat`);
}

export function listMessages(threadId: string, after = 0): Promise<MessageOut[]> {
  return apiRequest<MessageOut[]>("GET", `/api/threads/${threadId}/messages?after=${after}`);
}

export interface SentMessage {
  message_id: string;
  // steered: the bot's run for this chat reads it mid-work; queued: a busy bot picks it up after; started: a free bot.
  status?: "steered" | "queued" | "started";
  queued: boolean; // status === "queued"
  mentioned?: string[]; // the other bots named with "@" that were handed this message
}

// `replyTo`: the message of this thread you answer; the server makes its quote.
export interface SendOptions {
  readonly call?: boolean; // a call's turn (contract A): the server beats the call before it queues the message
  // The words came from the voice service (a call turn, or a dictation sent as it landed): with Correct my English
  // on, the server adds an english_fix line under the message. The bot reads your original words either way.
  readonly spoken?: boolean;
  // Voice tuning D3: the composer already showed the correction; `heard` is the raw transcript and `fixes` what it
  // marked, so the server posts the english_fix line at once (no second model call).
  readonly heard?: string;
  readonly fixes?: readonly EnglishFix[];
  readonly mediaIds?: readonly string[]; // pictures uploaded to this thread first (POST …/media)
}

export function sendMessage(
  threadId: string, text: string, replyTo?: string | null, options: SendOptions = {},
): Promise<SentMessage> {
  const body = {
    text,
    ...(replyTo ? { reply_to: replyTo } : {}),
    ...(options.call ? { call: true } : {}),
    ...(options.spoken ? { spoken: true } : {}),
    ...(options.spoken && options.heard !== undefined ? { heard: options.heard, fixes: options.fixes ?? [] } : {}),
    ...(options.mediaIds && options.mediaIds.length > 0 ? { media_ids: options.mediaIds } : {}),
  };
  return apiRequest<SentMessage>("POST", `/api/threads/${threadId}/messages`, body);
}

// A tapback on a message; null clears it. The reply is the stored reaction row.
export function reactTo(threadId: string, messageId: string, key: string | null): Promise<MessageOut> {
  return apiRequest<MessageOut>("PUT", `/api/threads/${threadId}/messages/${messageId}/reaction`, { key });
}

export type ReminderAnswer = "done" | "failed" | "rescheduled" | "skipped";

// A task reminder card's answer, kept on its Report so the web and the phone show it folded. `due` is a
// Reschedule's new due (null: no date); every other answer sends null.
export function answerReminder(threadId: string, messageId: string, answer: ReminderAnswer,
  due: string | null): Promise<MessageOut> {
  return apiRequest<MessageOut>("PUT", `/api/threads/${threadId}/messages/${messageId}/reminder-answer`, { answer, due });
}

// Remember it on a "Not remembered" line: saves it as your own memory. Pressing it twice saves once.
export function rememberOffer(threadId: string, messageId: string): Promise<RememberedOffer> {
  return apiRequest<RememberedOffer>("POST", `/api/threads/${threadId}/messages/${messageId}/remember`, {});
}

// Fresh start: a chat line that hides earlier web replies from the bot's next runs.
export function freshStart(threadId: string): Promise<MessageOut> {
  return apiRequest<MessageOut>("POST", `/api/threads/${threadId}/fresh-start`, {});
}
