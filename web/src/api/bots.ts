import { apiRequest, apiUpload } from "./client";
import type { ApprovalMode, ApprovalTopic, AvatarOut, BotOut, ComputerKind, StopResult } from "./types";

export interface BotDraftIn {
  name: string;
  job: string;
  instructions: string;
  avatar: AvatarOut;
  template_id?: string | null;
}

export interface BotPatchIn {
  name?: string;
  job?: string;
  instructions?: string;
  avatar?: AvatarOut;
  group?: string | null; // text sets it, "" or null clears it, absent keeps it
}

export function listBots(): Promise<BotOut[]> {
  return apiRequest<BotOut[]>("GET", "/api/bots");
}

export function createBot(draft: BotDraftIn): Promise<BotOut> {
  return apiRequest<BotOut>("POST", "/api/bots", draft);
}

export function getBot(botId: string): Promise<BotOut> {
  return apiRequest<BotOut>("GET", `/api/bots/${botId}`);
}

export function updateBot(botId: string, patch: BotPatchIn): Promise<BotOut> {
  return apiRequest<BotOut>("PATCH", `/api/bots/${botId}`, patch);
}

export function deleteBot(botId: string): Promise<void> {
  return apiRequest<void>("DELETE", `/api/bots/${botId}`);
}

export function starBot(botId: string): Promise<BotOut> {
  return apiRequest<BotOut>("POST", `/api/bots/${botId}/star`);
}

export function stopBot(botId: string): Promise<StopResult> {
  return apiRequest<StopResult>("POST", `/api/bots/${botId}/stop`);
}

export function setOffDuty(botId: string, offDuty: boolean): Promise<BotOut> {
  return apiRequest<BotOut>("PUT", `/api/bots/${botId}/duty`, { off_duty: offDuty });
}

// A picture on the bot's screen (redesign P1): the raw image, like a PDF upload.
export function uploadPicture(botId: string, picture: Blob): Promise<BotOut> {
  return apiUpload<BotOut>(`/api/bots/${botId}/picture`, picture, picture.type);
}

export function removePicture(botId: string): Promise<BotOut> {
  return apiRequest<BotOut>("DELETE", `/api/bots/${botId}/picture`);
}

// The profile's Notifications switch (S1.10).
export function setNotify(botId: string, notify: boolean): Promise<BotOut> {
  return apiRequest<BotOut>("PUT", `/api/bots/${botId}/notify`, { notify });
}

// Pin a bot to the sidebar's robot row, or take it off (the main bot is always there).
export function setPinned(botId: string, pinned: boolean): Promise<BotOut> {
  return apiRequest<BotOut>("PUT", `/api/bots/${botId}/pin`, { pinned });
}

// The profile's approval mode and its "Always ask about" topics (approval modes). Posting is locked on by the server.
// `autoReview` (the chat mode's Full auto) is sent only when given; left out, the server keeps the stored value.
export function setApproval(
  botId: string, mode: ApprovalMode, askTopics: readonly ApprovalTopic[], autoReview?: boolean,
): Promise<BotOut> {
  const body = autoReview === undefined
    ? { mode, ask_topics: askTopics }
    : { mode, ask_topics: askTopics, auto_review: autoReview };
  return apiRequest<BotOut>("PUT", `/api/bots/${botId}/approval`, body);
}

// Which computer the bot works in. The server stops the old kind.
export function setComputer(botId: string, computer: ComputerKind): Promise<BotOut> {
  return apiRequest<BotOut>("PATCH", `/api/bots/${botId}`, { computer });
}
