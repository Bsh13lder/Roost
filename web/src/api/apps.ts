// Install an app: the Debian packages the owner said Yes to on a bot's Linux computer. Remove is the owner's own click.
import { apiRequest } from "./client";
import type { BotAppOut } from "./types";

const base = (botId: string) => `/api/bots/${encodeURIComponent(botId)}/apps`;

export const listApps = (botId: string) => apiRequest<BotAppOut[]>("GET", base(botId));
export const removeApp = (botId: string, appId: string) =>
  apiRequest<void>("DELETE", `${base(botId)}/${encodeURIComponent(appId)}`);
