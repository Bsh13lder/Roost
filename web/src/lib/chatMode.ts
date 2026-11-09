// The chat mode (owner decision 2026-10-25), shared by the composer's pill and the Info tab's Browsing actions row so
// the two always agree. It is read from the bot's approval, never stored apart: "browsing" in the Always ask topics is
// Ask me; otherwise `auto_review` is Full auto; otherwise Just browse. The approval mode itself never changes.
import type { ApprovalMode, ApprovalTopic, BotOut } from "../api/types";
import { CHAT_MODE_OPTIONS, type ChatMode } from "../components/approvals/constants";

export type { ChatMode };

const BROWSING: ApprovalTopic = "browsing";

export interface ChatModeApproval {
  mode: ApprovalMode;
  askTopics: readonly ApprovalTopic[];
  autoReview: boolean;
}

export function chatModeOf(bot: BotOut): ChatMode {
  if (bot.approval.ask_topics.includes(BROWSING)) return "ask";
  return bot.approval.auto_review === true ? "auto" : "browse";
}

// What to send to PUT /api/bots/{id}/approval for `mode`: a new value, the bot left as it was.
export function approvalFor(bot: BotOut, mode: ChatMode): ChatModeApproval {
  const others = bot.approval.ask_topics.filter((topic) => topic !== BROWSING);
  return {
    mode: bot.approval.mode,
    askTopics: mode === "ask" ? [...others, BROWSING] : others,
    autoReview: mode === "auto",
  };
}

export function chatModeOption(mode: ChatMode) {
  return CHAT_MODE_OPTIONS.find((option) => option.id === mode) ?? CHAT_MODE_OPTIONS[1];
}
