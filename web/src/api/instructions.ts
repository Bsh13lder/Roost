// web/src/api/instructions.ts — the "Update my instructions?" card. Shapes match
// roost/gateway/routes/instruction_proposals.py.
import { apiRequest } from "./client";
import type { MessageOut } from "./types";

export type InstructionProposalState = "open" | "accepted" | "declined";

export interface InstructionDiffLine {
  op: "same" | "add" | "del";
  text: string;
}

export interface InstructionProposalOut {
  id: string;
  bot_id: string;
  before: string;
  after: string;
  why: string;
  diff: InstructionDiffLine[];
  stale: boolean; // your bot's instructions changed since the card was made: Accept would be refused
  tainted: boolean; // from web content
  from_routine: boolean;
  state: InstructionProposalState;
  created_at: string;
  decided_at: string | null;
}

export interface InstructionProposalsChangedFrame { type: "instruction_proposals_changed"; seq: number; bot_id: string }

const proposalPath = (id: string) => `/api/instruction-proposals/${encodeURIComponent(id)}`;

export const getInstructionProposal = (id: string) => apiRequest<InstructionProposalOut>("GET", proposalPath(id));
// `text`: your own edit of the new instructions; without it the card's text is saved.
export const acceptInstructionProposal = (id: string, text?: string) =>
  apiRequest<InstructionProposalOut>("POST", `${proposalPath(id)}/accept`, text === undefined ? {} : { text });
export const declineInstructionProposal = (id: string) =>
  apiRequest<InstructionProposalOut>("POST", `${proposalPath(id)}/decline`);

// update_my_instructions' line: Undo restores the text it replaced (roost/gateway/routes/instruction_changes.py).
export const undoInstructionChange = (messageId: string) =>
  apiRequest<{ message: MessageOut }>("POST", `/api/instruction-changes/${encodeURIComponent(messageId)}/undo`, {});
