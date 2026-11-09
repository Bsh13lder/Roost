// Vault: passwords (owner, 2026-11-08; docs/plans/2026-11-08-roost-vault-passwords.md): the words in one place.
import { decidedAt } from "../../lib/decisions";

export const VAULT_PASSWORDS_TITLE = "Vault: passwords";
export const VAULT_PASSWORDS_NOTE =
  "Roost keeps these sealed. Your bots never see them; Roost types one only after your Yes, or at once on a site you set to Always.";
export const VAULT_PASSWORDS_EMPTY = "No saved passwords yet.";
export const ADD_LOGIN = "Add a login";
export const SAVE_PASSWORD_TITLE = "Save a password";
export const SAVE_PASSWORD_MENU_ITEM = "Save a password";
export const SAVE_PASSWORD_DESCRIPTION = "It goes into Vault: passwords, not into the chat. The bot isn't told.";
export const SAVED_TOAST = "Saved in Vault: passwords";
export const ALWAYS_LABEL = "Always for this site";
export const SAVE_IN_VAULT = "Save in Vault";
export const SITE_LABEL = "Site";
export const SITE_PLACEHOLDER = "upwork.com";
export const USERNAME_LABEL = "User name";
export const PASSWORD_LABEL = "Password";
export const NEVER_USED = "Not used yet";

// The server's limits (roost/constants.py VAULT_*_MAX_CHARS).
export const VAULT_HOST_MAX = 253;
export const VAULT_USERNAME_MAX = 254;
export const VAULT_PASSWORD_MAX = 256;

export const deleteQuestion = (host: string, username: string): string =>
  `Delete the saved login${username ? ` ${username}` : ""} for ${host}? Roost forgets its password.`;

// "me@x.com · Last used 22 Oct, 14:19": the user name and when Roost last typed it, on the account's clock.
export function loginDetail(username: string, lastUsedAt: string | null): string {
  const used = lastUsedAt ? decidedAt(lastUsedAt) : "";
  const when = used ? `Last used ${used}` : NEVER_USED;
  return username ? `${username} · ${when}` : when;
}
