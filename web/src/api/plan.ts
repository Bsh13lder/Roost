// web/src/api/plan.ts — a bot's Plan (routines plan, Task 14/17). Shapes match roost/gateway/routes/plan.py: the
// server is the only parser, so every answer is the whole Plan as text plus its items.
import { apiRequest } from "./client";

export type PlanStatus = "planned" | "on_it" | "done" | "dropped";

export interface PlanItemOut {
  id: string | null; // an item that has no id yet cannot be moved
  status: PlanStatus;
  text: string;
  tags: string[];
  date: string | null; // "YYYY-MM-DD"
  time: string | null; // "HH:MM"
  done_on: string | null;
  dropped_on: string | null;
  scheduled: string | null;
  indent: number;
  line_no: number;
  tainted: boolean; // the bot wrote it after reading outside content
}

export interface PlanOut {
  content: string;
  revision: number;
  unreadable: number; // lines the server could not read
  items: PlanItemOut[];
}

export interface PlanItemChanges {
  status?: PlanStatus;
  text?: string;
  date?: string | null;
  time?: string | null;
  tags?: string[];
}

const planPath = (botId: string) => `/api/bots/${encodeURIComponent(botId)}/plan`;

export const getPlan = (botId: string) => apiRequest<PlanOut>("GET", planPath(botId));
export const putPlan = (botId: string, content: string, baseRevision: number) =>
  apiRequest<PlanOut>("PUT", planPath(botId), { content, base_revision: baseRevision });
export const patchPlanItem = (botId: string, itemId: string, baseRevision: number, changes: PlanItemChanges) =>
  apiRequest<PlanOut>("PATCH", `${planPath(botId)}/items/${encodeURIComponent(itemId)}`, { base_revision: baseRevision, ...changes });
