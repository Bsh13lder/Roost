import type { QuickLineRichOut } from "../src/api/tasks";
import { makeQuickLine } from "./taskFixtures";

// The rich quick line's wire shape (Tasks & Money polish): the redesign P3 reading plus the new keys.
export function makeRichLine(overrides: Partial<QuickLineRichOut> = {}): QuickLineRichOut {
  return {
    ...makeQuickLine(), tags: [], due_text: null, reminder_text: null, budget_math: null, budget_currency: null, starred: false, estimate_minutes: null, reminder_at: null, reminder_words: null,
    recurring: null, recur_until: null, repeat_text: null, repeat_words: null, repeat_problem: null, assignee: null,
    assignee_words: null, assignee_question: null, warnings: [], ...overrides,
  };
}
