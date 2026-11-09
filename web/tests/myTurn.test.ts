import { describe, expect, it } from "vitest";
import { askRows } from "../src/lib/myTurn";
import type { ProposalOut } from "../src/api/proposals";
import type { QuestionOut } from "../src/api/questions";
import type { SkillProposalOut } from "../src/api/skills";
import { makeBot } from "./fixtures";

const bots = { "bot-1": makeBot(), "bot-2": makeBot({ id: "bot-2", name: "Ledger" }) };

const routineProposal = { id: "rp-1", bot_id: "bot-1", action: "create", routine_id: null, routine_name: null,
  state: "open", payload: { name: "Morning digest", instructions: "x", schedule: { kind: "times", days: [1], times: ["10:00"] } },
  words: "", next: [], diff: [], tainted: false, from_routine: false, created_at: "x" } as unknown as ProposalOut;
const question = { id: "q-1", bot_id: "bot-2", question: "Which bank?" } as unknown as QuestionOut;

function skillProposal(overrides: Partial<SkillProposalOut> = {}): SkillProposalOut {
  return { id: "sp-1", bot_id: "bot-1", skill_id: null, action: "create",
    payload: { name: "Post on X", use_when: "posting", body: "1. Open X" }, skill_name: "Post on X", diff: [],
    tainted: false, from_routine: false, state: "open", created_at: "x", ...overrides };
}

describe("My turn rows", () => {
  it("My turn lists skill proposals after routine proposals", () => {
    const change = skillProposal({ id: "sp-2", action: "change", skill_id: "s-1", skill_name: "Weekly SEO",
      payload: { name: null, use_when: null, body: "new" } });
    const rows = askRows([question], [routineProposal], bots, [skillProposal(), change]);
    expect(rows.map((row) => row.text)).toEqual([
      "Scout · New routine · Morning digest",
      "Scout · New skill · Post on X",
      "Scout · Change skill · Weekly SEO",
      "Ledger · Which bank?",
    ]);
    expect(rows[1]).toEqual({ key: "skill-proposal-sp-1", to: "/bots/bot-1", text: "Scout · New skill · Post on X" });
  });

  it("leaves out proposals of bots no longer on the team, and works without skills", () => {
    expect(askRows([], [], bots, [skillProposal({ bot_id: "gone" })])).toEqual([]);
    expect(askRows([question], [], bots).map((row) => row.key)).toEqual(["question-q-1"]);
  });
});
