import { apiRequest } from "./client";
import type { DeskStatusOut, ExecResult } from "./types";

export function getDeskStatus(botId: string): Promise<DeskStatusOut> {
  return apiRequest<DeskStatusOut>("GET", `/api/bots/${botId}/desk`);
}

export function startBrowser(botId: string): Promise<DeskStatusOut> {
  return apiRequest<DeskStatusOut>("POST", `/api/bots/${botId}/desk/browser/start`);
}

export function stopBrowser(botId: string): Promise<DeskStatusOut> {
  return apiRequest<DeskStatusOut>("POST", `/api/bots/${botId}/desk/browser/stop`);
}

export function execWorkspace(botId: string, command: string): Promise<ExecResult> {
  return apiRequest<ExecResult>("POST", `/api/bots/${botId}/desk/workspace/exec`, { command });
}
