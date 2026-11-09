// Connectors (web): the words the Connectors fold, its editor and the Add a key card share.
import type { AuthStyle } from "../../api/connectors";

export const CONNECTORS_TITLE = "Connectors";
export const CONNECTORS_EMPTY = "No connectors yet. Add one to let your bots use a service's API with your key.";
export const NEW_CONNECTOR = "Add connector";
export const SAVE = "Save";
export const KEY_LABEL = "Key";
export const KEY_HINT_NEW = "Write-only: Roost never shows it again, and bots never see it.";
export const KEY_HINT_KEEP = "Leave empty to keep the saved key.";
export const DELETE_QUESTION = "Delete this connector for every bot?";
export const EVERY_BOT = "Every bot";
export const ONLY_THIS_BOT = "Only this bot";
export const WHO_LABEL = "Who can use it";
export const PREFIXES_LABEL = "Allowed paths";
export const PREFIXES_HINT = "Optional, one per line, such as /v3/site-explorer. Empty: any path under the address.";
export const ADD_A_KEY = "Add a key";
export const NOT_NOW = "Not now";
export const KEY_ADDED = "Key added";
export const SAID_NOT_NOW = "Not now";
export const REQUEST_GONE = "This request is gone.";
export const MARK = "from web content";

export const STYLE_OPTIONS: ReadonlyArray<{ id: AuthStyle; label: string }> = [
  { id: "bearer", label: "Bearer token" },
  { id: "header", label: "Header" },
  { id: "query", label: "Query parameter" },
];

export const AUTH_NAME_LABEL: Record<AuthStyle, string> = {
  bearer: "Header name",
  header: "Header name",
  query: "Parameter name",
};

export const LIMITS = { name: 40, purpose: 300, url: 300, secret: 4096 } as const;
