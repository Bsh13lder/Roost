import { BOT_LIMITS, NAME_PATTERN, fitsOnOneLine } from "./botProfile";

export const characterCount = (text: string) => [...text].length; // code points, like the server

// The counter shows only near the limit (S1.6): from 90% of it.
export const INSTRUCTIONS_COUNTER_FROM = Math.floor(BOT_LIMITS.instructions * 0.9);

/** How many characters a draft is over the instructions limit (0 when it fits). */
export const instructionsOver = (text: string) => Math.max(0, characterCount(text) - BOT_LIMITS.instructions);

export function checkName(name: string): string | null {
  return fitsOnOneLine(name) && NAME_PATTERN.test(name) ? null : "Use letters, numbers, spaces, . or - (up to 40).";
}

export function checkJob(job: string): string | null {
  if (!job.trim()) return "Say in one line what this bot does.";
  return fitsOnOneLine(job) && characterCount(job) <= BOT_LIMITS.job
    ? null : "Keep the job to one line of up to 200 characters.";
}

/** A sidebar label: one line, at most BOT_LIMITS.group characters; blank is fine (it clears). */
export function checkGroup(value: string): string | null {
  if (!fitsOnOneLine(value)) return "A label fits on one line.";
  return characterCount(value.trim()) <= BOT_LIMITS.group ? null : `A label is at most ${BOT_LIMITS.group} characters.`;
}
