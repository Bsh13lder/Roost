// web/src/api/vaultExport.ts — the one-way Obsidian export (obsidian track). Shapes match
// roost/gateway/routes/vault_export.py.
import { apiRequest } from "./client";

export type ExportCode = "ok" | "partial" | "no_grant" | "away" | "failed" | "off";

export interface ExportFolder {
  id: string;
  label: string;
  bot_id: string | null;
  is_vault: boolean;
}

export interface VaultExportOut {
  grant_id: string | null;
  journals: boolean;
  grants: ExportFolder[]; // only folders Roost may write to
  projects: string[]; // the projects switched on
  last: { result: ExportCode | null; written: number; conflicts: number; at: string | null };
}

export interface ExportRunOut {
  result: ExportCode;
  written: number;
  conflicts: number;
  failed: number;
}

export const getVaultExport = () => apiRequest<VaultExportOut>("GET", "/api/vault-export");

export const putVaultExport = (grantId: string | null, journals: boolean) =>
  apiRequest<VaultExportOut>("PUT", "/api/vault-export", { grant_id: grantId, journals });

export const runVaultExport = () => apiRequest<ExportRunOut>("POST", "/api/vault-export/run");

export const setProjectExport = (projectId: string, on: boolean) =>
  apiRequest<{ project_id: string; on: boolean }>(
    "PUT", `/api/projects/${encodeURIComponent(projectId)}/vault-export`, { on },
  );
