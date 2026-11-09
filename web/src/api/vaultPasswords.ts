// web/src/api/vaultPasswords.ts: Vault: passwords (roost/gateway/routes/vault_passwords.py,
// docs/plans/2026-11-08-roost-vault-passwords.md). A password only ever goes out in a request body; no reply holds one.
import { apiRequest } from "./client";

export interface VaultPasswordOut {
  id: string;
  host: string;
  username: string;
  always: boolean; // Always for this site: Roost types it with no card
  created_at: string;
  updated_at: string;
  last_used_at: string | null;
}

export interface VaultPasswordIn {
  host: string;
  username: string;
  password: string;
  always?: boolean;
}

export interface VaultPasswordPatch {
  password?: string;
  always?: boolean;
}

const BASE = "/api/vault/passwords";
const loginPath = (id: string) => `${BASE}/${encodeURIComponent(id)}`;

export const listVaultPasswords = () => apiRequest<VaultPasswordOut[]>("GET", BASE);
export const saveVaultPassword = (body: VaultPasswordIn) => apiRequest<VaultPasswordOut>("POST", BASE, body);
export const patchVaultPassword = (id: string, body: VaultPasswordPatch) =>
  apiRequest<VaultPasswordOut>("PATCH", loginPath(id), body);
export const deleteVaultPassword = (id: string) => apiRequest<void>("DELETE", loginPath(id));
