// web/src/lib/myTurn.ts — the rows My turn adds for what bots ask outside a chat: open questions in the question
// book, routine proposals that wait for Approve or Decline, and skill proposals that wait for Save skill.
import type { ProposalOut } from "../api/proposals";
import type { QuestionOut } from "../api/questions";
import type { KeyRequestOut } from "../api/connectors";
import type { SkillProposalOut } from "../api/skills";
import type { BotOut } from "../api/types";

export interface AskRow {
  key: string;
  to: string;
  text: string;
}

const PROPOSAL_WORDS = { create: "New routine", change: "Change routine", pause: "Pause routine" } as const;
const SKILL_WORDS = { create: "New skill", change: "Change skill" } as const;

// Rows for bots still on the team, proposals first (they block a decision), each opening the bot's chat or its Info tab.
// Skill proposals come after routine proposals and before questions.
export function askRows(
  questions: readonly QuestionOut[], proposals: readonly ProposalOut[], bots: Readonly<Record<string, BotOut>>,
  skillProposals: readonly SkillProposalOut[] = [], keyRequests: readonly KeyRequestOut[] = [],
): AskRow[] {
  const proposalRows = proposals.filter((p) => bots[p.bot_id]).map((p) => ({
    key: `proposal-${p.id}`, to: `/bots/${p.bot_id}`,
    text: `${bots[p.bot_id].name} · ${PROPOSAL_WORDS[p.action]} · ${p.payload?.name ?? p.routine_name ?? ""}`.replace(/ · $/, ""),
  }));
  const questionRows = questions.filter((q) => bots[q.bot_id]).map((q) => ({
    key: `question-${q.id}`, to: `/bots/${q.bot_id}?panel=settings`, text: `${bots[q.bot_id].name} · ${q.question}`,
  }));
  const skillRows = skillProposals.filter((p) => bots[p.bot_id]).map((p) => ({
    key: `skill-proposal-${p.id}`, to: `/bots/${p.bot_id}`,
    text: `${bots[p.bot_id].name} · ${SKILL_WORDS[p.action]} · ${(p.action === "create" ? p.payload.name : p.skill_name) ?? ""}`
      .replace(/ · $/, ""),
  }));
  const keyRows = keyRequests.filter((r) => bots[r.bot_id]).map((r) => ({
    key: `key-request-${r.id}`, to: `/bots/${r.bot_id}`, text: `${bots[r.bot_id].name} · Add a key · ${r.service}`,
  }));
  return [...proposalRows, ...skillRows, ...keyRows, ...questionRows];
}
