// web/src/api/standing.ts — a routine's standing permissions (docs/plans/2026-10-23-roost-full-computer.md Step 2).
// Shapes match roost/gateway/routes/standing.py.
import { apiRequest } from "./client";

export type StandingAction = "post" | "send" | "submit";

export interface PermissionIn {
  host: string;
  action: StandingAction;
  max_per_day: number;
  until: string; // "YYYY-MM-DD", a day on the account's calendar (the last day it holds)
}

export interface PermissionOut extends PermissionIn {
  id: string;
  routine_id: string;
  used_today: number;
  created_at: string;
}

const path = (routineId: string) => `/api/routines/${encodeURIComponent(routineId)}/permissions`;

export const listPermissions = (routineId: string) =>
  apiRequest<{ permissions: PermissionOut[] }>("GET", path(routineId)).then((r) => r.permissions);
export const addPermission = (routineId: string, permission: PermissionIn) =>
  apiRequest<PermissionOut>("POST", path(routineId), permission);
export const revokePermission = (routineId: string, permissionId: string) =>
  apiRequest<void>("DELETE", `${path(routineId)}/${encodeURIComponent(permissionId)}`);
