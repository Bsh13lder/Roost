import { apiRequest } from "./client";

// Teach a task (docs/plans/2026-10-22-roost-teach.md): you show the bot a task on its Linux computer.
export interface TeachOut {
  teaching: boolean;
  steps: number;
  capped: boolean;
  started_at: string | null;
}

export interface TeachStopOut {
  proposal_id: string | null; // the skill proposal card posted in the bot's chat
  steps: number;
  discarded: boolean;
}

export interface TeachStopIn {
  description?: string;
  discard?: boolean;
}

export const getTeach = (botId: string) => apiRequest<TeachOut>("GET", `/api/bots/${botId}/teach`);
// Starts a fresh recording and takes control of the computer.
export const startTeach = (botId: string) => apiRequest<TeachOut>("POST", `/api/bots/${botId}/teach/start`);
// Ends teaching and gives the computer back: a skill proposal card, or the recording thrown away.
export const stopTeach = (botId: string, body: TeachStopIn) =>
  apiRequest<TeachStopOut>("POST", `/api/bots/${botId}/teach/stop`, body);
