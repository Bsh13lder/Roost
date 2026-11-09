// web/src/api/skills.ts — the user's Skills (saved how-tos every bot can reuse) and the bots' skill proposals.
// Shapes match roost/gateway/routes/skills.py and skill_proposals.py.
import { apiRequest } from "./client";
import { withConflict } from "./conflict";

export type SkillOrigin = "user" | "bot" | "file";

export interface SkillOut {
  id: string;
  name: string;
  use_when: string;
  body: string; // the steps, Markdown
  origin: SkillOrigin;
  tainted: boolean; // from web content: reading it marks a bot's run, until you save it yourself
  created_by_bot: string | null;
  revision: number;
  created_at: string;
  updated_at: string;
  on?: boolean; // with ?bot_id=: whether it is on for that bot
}

export interface SkillFields {
  name: string;
  use_when: string;
  body: string;
}

export interface TemplateSkill {
  name: string;
  use_when: string;
  steps: string;
}

export type SkillProposalAction = "create" | "change";
export type SkillProposalState = "open" | "saved" | "declined";
export type SkillField = "name" | "use_when" | "body";

export interface SkillProposalOut {
  id: string;
  bot_id: string;
  skill_id: string | null;
  action: SkillProposalAction;
  payload: { name: string | null; use_when: string | null; body: string | null };
  skill_name: string | null;
  diff: Array<{ field: SkillField; before: string; after: string }>;
  tainted: boolean;
  from_routine: boolean;
  state: SkillProposalState;
  created_at: string;
}

const skillPath = (id: string) => `/api/skills/${encodeURIComponent(id)}`;
const proposalPath = (id: string) => `/api/skill-proposals/${encodeURIComponent(id)}`;

export const listSkills = (botId?: string) =>
  apiRequest<SkillOut[]>("GET", botId ? `/api/skills?bot_id=${encodeURIComponent(botId)}` : "/api/skills");
export const getSkill = (id: string) => apiRequest<SkillOut>("GET", skillPath(id));
export const addSkill = (fields: SkillFields) => apiRequest<SkillOut>("POST", "/api/skills", fields);
// A stale revision throws RevisionConflictError carrying the stored copy (Load the latest · Keep mine).
export const saveSkill = (id: string, fields: Partial<SkillFields>, baseRevision: number) =>
  withConflict<SkillOut, SkillOut>(apiRequest<SkillOut>("PUT", skillPath(id), { ...fields, base_revision: baseRevision }));
export const deleteSkill = (id: string) => apiRequest<void>("DELETE", skillPath(id));
export const setSkillOn = (botId: string, skillId: string, on: boolean) =>
  apiRequest<{ on: boolean }>("PUT", `/api/bots/${encodeURIComponent(botId)}/skills/${encodeURIComponent(skillId)}`, { on });
export const importSkills = (skills: TemplateSkill[], botId?: string) =>
  apiRequest<{ added: SkillOut[]; have: string[] }>("POST", "/api/skills/import", botId ? { skills, bot_id: botId } : { skills });

export const listSkillProposals = () => apiRequest<SkillProposalOut[]>("GET", "/api/skill-proposals?state=open");
export const getSkillProposal = (id: string) => apiRequest<SkillProposalOut>("GET", proposalPath(id));
export const saveSkillProposal = (id: string) => apiRequest<SkillProposalOut>("POST", `${proposalPath(id)}/save`);
export const declineSkillProposal = (id: string) => apiRequest<SkillProposalOut>("POST", `${proposalPath(id)}/decline`);
