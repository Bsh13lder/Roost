import { apiRequest } from "./client";
import type { ControlOut } from "./types";

export type ScreenResult = { kind: "image"; blob: Blob } | { kind: "asleep" } | { kind: "unreachable" };

// Viewing never wakes the computer: the server answers 409 "asleep" instead (S1.8).
export async function fetchScreen(botId: string): Promise<ScreenResult> {
  let response: Response;
  try {
    response = await fetch(`/api/bots/${botId}/desk/screenshot`, { credentials: "include", cache: "no-store" });
  } catch {
    return { kind: "unreachable" }; // offline or the gateway is restarting: the tab offers Retry
  }
  if (response.status === 409) return { kind: "asleep" };
  if (!response.ok) return { kind: "unreachable" };
  return { kind: "image", blob: await response.blob() };
}

export const getControl = (botId: string) => apiRequest<ControlOut>("GET", `/api/bots/${botId}/control`);
export const takeControl = (botId: string) => apiRequest<ControlOut>("POST", `/api/bots/${botId}/control`);
// "Which account did you use?" goes along only when given; the server keeps it for the page's site (Vault).
export const giveBack = (botId: string, account?: string) =>
  apiRequest<ControlOut>("DELETE", `/api/bots/${botId}/control`, account ? { account } : undefined);
