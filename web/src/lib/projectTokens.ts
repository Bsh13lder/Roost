// "#Project Name" in your own chat messages (2026-10-26): the same reading as the server's
// roost/projects/chat_refs.py — exact names, any case, longest first, never inside a word — so a chip in your bubble
// is exactly the project the bot was told about.
import type { MentionOption } from "./mentions";

export type ProjectSegment = { text: string } | { text: string; project: MentionOption };

const escapeRegExp = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

function tokenPattern(projects: readonly MentionOption[]): RegExp {
  const names = [...projects].map((p) => p.name).sort((a, b) => b.length - a.length).map(escapeRegExp);
  return new RegExp(`(?<![\\p{L}\\p{N}_#])#(${names.join("|")})(?![\\p{L}\\p{N}_-])`, "giu");
}

/** `text` cut into plain runs and "#Name" tokens of known projects (the token keeps the letters as typed). */
export function splitProjectTokens(text: string, projects: readonly MentionOption[]): ProjectSegment[] {
  if (projects.length === 0 || !text.includes("#")) return [{ text }];
  const byName = new Map(projects.map((p) => [p.name.toLocaleLowerCase(), p]));
  const segments: ProjectSegment[] = [];
  let last = 0;
  for (const match of text.matchAll(tokenPattern(projects))) {
    const start = match.index ?? 0;
    const project = byName.get(match[1].toLocaleLowerCase());
    if (!project) continue;
    if (start > last) segments.push({ text: text.slice(last, start) });
    segments.push({ text: match[0], project });
    last = start + match[0].length;
  }
  if (last < text.length) segments.push({ text: text.slice(last) });
  return segments.length > 0 ? segments : [{ text }];
}
