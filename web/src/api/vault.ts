// Vault: site logins (Computers 2.0, C2): the accounts you said a bot is signed in with. Only labels, never passwords.
import { apiRequest } from "./client";
import type { SiteLoginOut } from "./types";

const base = (botId: string) => `/api/bots/${encodeURIComponent(botId)}/site-logins`;

export const listSiteLogins = (botId: string) => apiRequest<SiteLoginOut[]>("GET", base(botId));
export const forgetSiteLogin = (botId: string, loginId: string) =>
  apiRequest<void>("DELETE", `${base(botId)}/${encodeURIComponent(loginId)}`);
// Sign out: the bot's Linux computer forgets the site (cookies and storage), and the login goes.
export const signOutSiteLogin = (botId: string, loginId: string) =>
  apiRequest<void>("POST", `${base(botId)}/${encodeURIComponent(loginId)}/sign-out`);
