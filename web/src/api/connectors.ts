// web/src/api/connectors.ts — the user's connectors (a service's web API with their key) and the bots' Add a key
// cards. Shapes match roost/gateway/routes/connectors.py. The key is write-only: no response ever holds it.
import { apiRequest } from "./client";

export type AuthStyle = "bearer" | "header" | "query";

export interface ConnectorOut {
  id: string;
  name: string;
  purpose: string;
  base_url: string;
  host: string;
  auth_style: AuthStyle;
  auth_name: string;
  key_hint: string; // "key set ••••abcd" or "key set"
  allowed_prefixes: string[];
  bot_ids: string[] | null; // null: every bot
  created_at: string;
  updated_at: string;
}

export interface ConnectorFields {
  name: string;
  purpose: string;
  base_url: string;
  auth_style: AuthStyle;
  auth_name: string;
  allowed_prefixes: string[];
  secret?: string; // only when the user typed one
  bot_ids?: string[] | null;
  all_bots?: boolean;
}

export interface KeyRequestOut {
  id: string;
  bot_id: string;
  thread_id: string;
  service: string;
  base_url: string;
  host: string;
  why: string;
  auth_style: AuthStyle;
  auth_name: string;
  tainted: boolean;
  state: "open" | "saved" | "declined";
  connector_id: string | null;
  created_at: string;
}

const path = (id: string) => `/api/connectors/${encodeURIComponent(id)}`;
const requestPath = (id: string) => `/api/connector-requests/${encodeURIComponent(id)}`;

export const listConnectors = () => apiRequest<ConnectorOut[]>("GET", "/api/connectors");
export const addConnector = (fields: ConnectorFields) => apiRequest<ConnectorOut>("POST", "/api/connectors", fields);
export const changeConnector = (id: string, fields: Partial<ConnectorFields>) =>
  apiRequest<ConnectorOut>("PATCH", path(id), fields);
export const deleteConnector = (id: string) => apiRequest<void>("DELETE", path(id));

export const listKeyRequests = () => apiRequest<KeyRequestOut[]>("GET", "/api/connector-requests?state=open");
export const getKeyRequest = (id: string) => apiRequest<KeyRequestOut>("GET", requestPath(id));
export const saveKeyRequest = (id: string, secret: string) =>
  apiRequest<KeyRequestOut>("POST", `${requestPath(id)}/save`, { secret });
export const declineKeyRequest = (id: string) => apiRequest<KeyRequestOut>("POST", `${requestPath(id)}/decline`);
