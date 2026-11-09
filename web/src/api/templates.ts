import { apiRequest, errorFrom } from "./client";
import type { TemplateFormOut, TemplateOut } from "./types";

export function listTemplates(): Promise<TemplateOut[]> {
  return apiRequest<TemplateOut[]>("GET", "/api/templates");
}

// From a file (S1.7): the server checks it and answers the form's values; it creates nothing.
export function checkTemplateFile(file: unknown): Promise<TemplateFormOut> {
  return apiRequest<TemplateFormOut>("POST", "/api/templates/check", { file });
}

// The server's template_filename, for a message before the download answers.
export const templateFileName = (name: string) =>
  `${name.replace(/[^A-Za-z0-9 _-]/g, "").trim() || "bot"}.roost-bot.json`;

// Share as Template: the file as the server wrote it (422 when a field looks like a secret).
export async function downloadTemplate(botId: string): Promise<{ blob: Blob; filename: string }> {
  const response = await fetch(`/api/bots/${botId}/template`, { credentials: "include" });
  if (!response.ok) throw await errorFrom(response);
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const filename = /filename="([^"]+)"/.exec(disposition)?.[1] ?? "bot.roost-bot.json";
  return { blob: await response.blob(), filename };
}
