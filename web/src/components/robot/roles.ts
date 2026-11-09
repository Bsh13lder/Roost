// Role looks (avatars v7): what each role does to a Lensbot besides its emblem (emblem.tsx), and the
// role a bot's job text suggests. A suggestion is only shown; the user confirms it with one click.
import type { BotRole } from "../../api/types";
import type { LookNudge } from "./lensbot";

// A role may nudge the eye style and the visor; the body stays the shape the user picked.
export const ROLE_LOOKS: Readonly<Record<BotRole, LookNudge>> = {
  general: {},
  tasks: {},
  code: { eyes: "square", visor: "screen" },
  seo: { eyes: "ring" },
  money: {},
  social: {},
  research: {},
  writer: { eyes: "almond", visor: "brow" },
};

// Keyword rules, the most specific first: "SEO writer" is SEO, "writes code" is code. Whole words only,
// so "device" is not "dev" and "codenames" is not "code".
const RULES: ReadonlyArray<readonly [BotRole, RegExp]> = [
  ["seo", /\bseo\b/i],
  ["code", /\b(code|coding|coder|dev|devs|developer|developers|develops|programmer|programming)\b/i],
  ["money", /\b(money|budgets?|finances?|financial|expenses?|spending)\b/i],
  ["social", /\b(social|instagram|tiktok|twitter|linkedin|facebook)\b/i],
  ["research", /\b(research|researcher|researches|researching)\b/i],
  ["writer", /\b(write|writes|writer|writing|blog|blogs|copywriting)\b/i],
  ["tasks", /\b(tasks?|to-?dos?)\b/i],
];

/** The role a job's words point to, or null when none does. */
export function suggestRole(job: string): BotRole | null {
  return RULES.find(([, words]) => words.test(job))?.[0] ?? null;
}
