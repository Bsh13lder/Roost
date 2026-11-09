// web/src/api/mac.ts: the Mac folders a bot may use, the folder picker and Undo on a Mac activity line.
import { apiRequest } from "./client";
import type { GrantAccess, GrantIn, GrantOut, GrantPatch, MessageOut } from "./types";

const enc = encodeURIComponent;

export type { GrantAccess };

export const listGrants = (botId?: string) =>
  apiRequest<GrantOut[]>("GET", botId ? `/api/mac/grants?bot_id=${enc(botId)}` : "/api/mac/grants");
export const addGrant = (body: GrantIn) => apiRequest<GrantOut>("POST", "/api/mac/grants", body);
export const updateGrant = (id: string, patch: GrantPatch) =>
  apiRequest<GrantOut>("PATCH", `/api/mac/grants/${enc(id)}`, patch);
export const revokeGrant = (id: string) => apiRequest<void>("DELETE", `/api/mac/grants/${enc(id)}`);
// The Mac's own folder window: the picked path, or null when the window was cancelled.
export const pickFolder = () => apiRequest<{ path: string | null }>("POST", "/api/mac/pick-folder", {});
// Undo of a Mac activity line, at once: answers the "Undid ..." line, or 409 with a plain reason.
export const undoActivity = (messageId: string) =>
  apiRequest<{ message: MessageOut }>("POST", `/api/mac/activity/${enc(messageId)}/undo`, {});
