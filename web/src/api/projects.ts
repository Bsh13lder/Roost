import { apiRequest } from "./client";
import type { RecurringOut, UpcomingChargeOut } from "./money";
import type { ProjectDetailOut, ProjectOut, ProjectProgressOut, TopupOut } from "./types";

// The user's projects (projects hub): the same records every bot works on with its project tools.
// Amounts go as decimal strings ("1200.00"), already read by parseAmountInput.

export interface ProjectIn {
  name: string;
  currency: string;
  budget: string | null; // the total budget; top-ups raise it later
  monthly_budget: string | null;
  color: string;
  start_date: string | null; // "YYYY-MM-DD"
  due_date: string | null;
  lead_bot_id: string | null;
}

// Only the fields that change; null clears a date, the monthly limit or the lead bot.
// The total budget is not here: it has its own call, setProjectBudget.
export type ProjectPatchIn = Partial<{
  name: string;
  color: string;
  start_date: string | null;
  due_date: string | null;
  monthly_budget: string | null;
  lead_bot_id: string | null;
  status: ProjectOut["status"];
  currency: string;
}>;

export interface TopupIn {
  amount: string;
  source?: string; // where the money came from
}

// Board G13: the project page's progress; since lead task 20 the list carries the same fields.
export type ProjectProgressBoardOut = ProjectProgressOut;

export interface ProjectCountsOut {
  tasks_open: number;
  expenses: number;
  notes: number;
  documents: number;
}

export type ProjectDetailBoardOut = Omit<ProjectDetailOut, "progress"> & {
  progress: ProjectProgressBoardOut;
  counts: ProjectCountsOut;
  repeating: RecurringOut[]; // the project's active repeating charges
  upcoming_charges: UpcomingChargeOut[]; // the next 31 days
};

const path = (projectId: string) => `/api/projects/${encodeURIComponent(projectId)}`;
const topupPath = (topupId: string) => `/api/topups/${encodeURIComponent(topupId)}`;

// A project as Board G7 sends it: pinned to the top of the Money tab, and when.
export type PinnedProjectOut = ProjectOut & { pinned: boolean; pinned_at: string | null };

// Pin a project to the top of the Money tab, or unpin it (General can't be pinned).
export function pinProject(projectId: string, pinned: boolean): Promise<PinnedProjectOut> {
  return apiRequest<PinnedProjectOut>("PUT", `${path(projectId)}/pin`, { pinned });
}

// General is never listed (H2); archived projects only when asked.
export function listProjects(includeArchived = false): Promise<ProjectOut[]> {
  return apiRequest<ProjectOut[]>("GET", includeArchived ? "/api/projects?include_archived=true" : "/api/projects");
}

export function getProject(projectId: string): Promise<ProjectDetailBoardOut> {
  return apiRequest<ProjectDetailBoardOut>("GET", path(projectId));
}

export function createProject(input: ProjectIn): Promise<ProjectOut> {
  return apiRequest<ProjectOut>("POST", "/api/projects", input);
}

export function updateProject(projectId: string, patch: ProjectPatchIn): Promise<ProjectOut> {
  return apiRequest<ProjectOut>("PATCH", path(projectId), patch);
}

// The total budget (P3): set it, or clear it with null (H5). The history gets a "Budget set" row.
export function setProjectBudget(projectId: string, amount: string | null): Promise<ProjectOut> {
  return apiRequest<ProjectOut>("PUT", `${path(projectId)}/budget`, { amount });
}

// Keep: the user vouches for a project a bot made from web content, so its "from web content" mark goes.
export function keepProject(projectId: string): Promise<ProjectOut> {
  return apiRequest<ProjectOut>("POST", `${path(projectId)}/keep`);
}

// Its expenses move to General; its tasks, notes and documents stay, unlinked (H9).
export function deleteProject(projectId: string): Promise<void> {
  return apiRequest<void>("DELETE", path(projectId));
}

export function listTopups(projectId: string): Promise<TopupOut[]> {
  return apiRequest<TopupOut[]>("GET", `${path(projectId)}/topups`);
}

export function addTopup(projectId: string, input: TopupIn): Promise<TopupOut> {
  return apiRequest<TopupOut>("POST", `${path(projectId)}/topups`, input);
}

// `amount` is the top-up's new amount; the server writes the difference as a "Top-up changed" row (H4).
export function editTopup(topupId: string, amount: string): Promise<TopupOut> {
  return apiRequest<TopupOut>("PATCH", topupPath(topupId), { amount });
}

// Undo takes the top-up and its changes out of the budget together; 409 when it is already undone.
export function undoTopup(topupId: string): Promise<TopupOut> {
  return apiRequest<TopupOut>("POST", `${topupPath(topupId)}/undo`);
}
