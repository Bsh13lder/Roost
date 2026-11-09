// web/src/api/proposals.ts — the small card a bot raises instead of writing a routine itself (routines plan).
import { apiRequest } from "./client";
import type { ScheduleIn, WatchIn } from "./routines";
import type { PermissionIn } from "./standing";

export type ProposalAction = "create" | "change" | "pause";
export type ProposalState = "open" | "approved" | "declined" | "expired";

export interface ProposalOut {
  id: string;
  bot_id: string;
  action: ProposalAction;
  routine_id: string | null;
  routine_name: string | null;
  state: ProposalState;
  // permission: a standing permission the bot asks for with a new routine; stored only on Approve
  // watch: "Only run when the page changes"; then words says so and next is empty
  payload: { name: string; instructions: string; schedule: ScheduleIn; permission?: PermissionIn | null; watch?: WatchIn | null } | null;
  words: string;
  next: string[]; // the next fires, account-zone ISO
  diff: Array<{ field: "name" | "instructions" | "schedule" | "watch"; before: string; after: string }>;
  tainted: boolean; // the run that raised it read outside content
  from_routine: boolean; // a routine's own run raised it
  created_at: string;
}

const path = (id: string) => `/api/routine-proposals/${encodeURIComponent(id)}`;

export const listProposals = () =>
  apiRequest<{ proposals: ProposalOut[] }>("GET", "/api/routine-proposals?state=open").then((r) => r.proposals);
// Left out, Approve stores the proposed standing permission as it is; { permission: null } stores none.
export const approveProposal = (id: string, body?: { permission: PermissionIn | null }) =>
  body === undefined ? apiRequest<ProposalOut>("POST", `${path(id)}/approve`) : apiRequest<ProposalOut>("POST", `${path(id)}/approve`, body);
export const declineProposal = (id: string) => apiRequest<ProposalOut>("POST", `${path(id)}/decline`);
