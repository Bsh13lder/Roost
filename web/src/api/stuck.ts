// web/src/api/stuck.ts — the Stuck card's buttons and Home's My turn (stuck flow, Piece A).
import { apiRequest } from "./client";
import type { StuckCardOut } from "./types";

// Ids come from the server, but encoding keeps a stray "/" or "?" from ever reaching another route.
const cardPath = (cardId: string) => `/api/stuck/${encodeURIComponent(cardId)}`;

export const listStuck = () => apiRequest<StuckCardOut[]>("GET", "/api/stuck");
export interface ClearOptions {
  account?: string;
  keep?: boolean; // a Sign-in card's "Keep me signed in on this computer?"
  how?: "try_again" | "gave_back";
}

// Only the fields given go along; none at all sends no body (Give it back).
function clearBody(options?: ClearOptions): ClearOptions | undefined {
  if (!options) return undefined;
  const body: ClearOptions = {
    ...(options.account ? { account: options.account } : {}),
    ...(options.keep !== undefined ? { keep: options.keep } : {}),
    ...(options.how ? { how: options.how } : {}),
  };
  return Object.keys(body).length ? body : undefined;
}

export const clearStuck = (cardId: string, options?: ClearOptions) =>
  apiRequest<StuckCardOut>("POST", `${cardPath(cardId)}/clear`, clearBody(options));
// The Sign-in card: Take control (open-sign-in: its page on the bot's computer, then you hold control) and Later.
export const openSignIn = (cardId: string) => apiRequest<StuckCardOut>("POST", `${cardPath(cardId)}/open-sign-in`);
// B3: the masked field's value, typed into the box on the bot's computer. Sent once, never kept here.
// `save` (Save in Vault, 2026-11-08) has the server keep a password sealed in Vault: passwords for this site.
export const typeSecret = (cardId: string, value: string, save = false) =>
  apiRequest<StuckCardOut>("POST", `${cardPath(cardId)}/secret`, { value, save });
export const laterStuck = (cardId: string) => apiRequest<StuckCardOut>("POST", `${cardPath(cardId)}/later`);
export const giveUpStuck = (cardId: string) => apiRequest<StuckCardOut>("POST", `${cardPath(cardId)}/give-up`);
export const openInMainBrowser = (cardId: string) =>
  apiRequest<StuckCardOut>("POST", `${cardPath(cardId)}/open-in-main-browser`);
