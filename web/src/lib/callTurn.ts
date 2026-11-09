// What a call does after you spoke (voice call mode): it waits for the bot, then speaks its reply, or says the bot is
// asking you something, or goes back to listening when the bot worked and said nothing. Pure: the call screen feeds it
// the chat's messages and the bot's status as they change.
import type { ApprovalCardOut, BotStatus, MessageOut, StuckCardOut } from "../api/types";
import { isSpokenReply } from "../hooks/useReadAloud";

export type TurnOutcome =
  | { readonly kind: "reply"; readonly messageId: string }
  | { readonly kind: "asking" }
  | { readonly kind: "done" };

const WAITING_ON_YOU: ReadonlySet<BotStatus> = new Set(["asking_you", "stuck"]);

// `sentId` is your message; `sawOnIt` is true once the bot has been On it since you sent it.
export function turnOutcome(
  messages: readonly MessageOut[], sentId: string, status: BotStatus, sawOnIt: boolean,
): TurnOutcome | null {
  const at = messages.findIndex((message) => message.id === sentId);
  if (at < 0 || status === "on_it") return null;
  const reply = messages.slice(at + 1).find(isSpokenReply);
  if (reply) return { kind: "reply", messageId: reply.id };
  if (WAITING_ON_YOU.has(status)) return { kind: "asking" };
  return sawOnIt ? { kind: "done" } : null;
}

// What the bot is waiting on: its newest open Ask, Proposal or options card, else its open Stuck card.
export function askingTitle(
  approvals: readonly ApprovalCardOut[], stuck: readonly StuckCardOut[], botId: string,
): string | null {
  const card = approvals.filter((c) => c.bot_id === botId && c.state === "open").at(-1);
  if (card) return card.choice?.question ?? card.steps[0]?.title ?? null;
  const blocked = stuck.filter((c) => c.bot_id === botId && c.state === "open").at(-1);
  return blocked ? `Help on ${blocked.host}` : null;
}

export function askingLine(botName: string, title: string | null): string {
  const what = title ? `is asking: ${title.replace(/[.?!]+$/, "")}${/\?$/.test(title) ? "?" : "."}` : "is asking you something.";
  return `${botName} ${what} Say yes or no, or answer in the chat.`;
}

// The bot's reply as it is being written: the live placeholder (seq 0) after your message. Its id stays the stored
// reply's id, and is what the server's live speech (contract B) is keyed by.
export function replyPlaceholder(messages: readonly MessageOut[], sentId: string): MessageOut | null {
  const at = messages.findIndex((message) => message.id === sentId);
  if (at < 0) return null;
  return messages.slice(at + 1).find((message) => message.role === "bot" && message.seq === 0) ?? null;
}
