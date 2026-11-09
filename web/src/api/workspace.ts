// web/src/api/workspace.ts: a bot's own workspace (Programs): its files, read-only, and Wipe workspace.
import { apiRequest } from "./client";
import type { BotOut } from "./types";

export interface WorkspaceEntry {
  name: string;
  kind: "file" | "dir" | "link" | "other";
  size: number | null;
}

export interface WorkspaceListing {
  path: string;
  entries: WorkspaceEntry[];
  more: boolean;
}

export const listWorkspaceFiles = (botId: string, path = "") =>
  apiRequest<WorkspaceListing>(
    "GET", `/api/bots/${encodeURIComponent(botId)}/workspace/files?path=${encodeURIComponent(path)}`);

export interface WipeResult {
  removed: number;
}

// Empties the workspace (and its scratch folders) and clears its "from web content" mark.
export const wipeWorkspace = (botId: string) =>
  apiRequest<WipeResult>("POST", `/api/bots/${encodeURIComponent(botId)}/workspace/wipe`);

// Internet in the workspace (A4): the keeper recreates the workspace (files kept); answers the updated bot.
export const setWorkspaceInternet = (botId: string, on: boolean) =>
  apiRequest<BotOut>("PUT", `/api/bots/${encodeURIComponent(botId)}/workspace-internet`, { on });
