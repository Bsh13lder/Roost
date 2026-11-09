// A bot's reply opens with one line of what it is starting on ("On it: checking your inbox.", roost/talk/chat_feel.py).
// Owner, 2026-10-27: that line is the working robot's words while the bot works, never a line of the answer. So a
// reply is split into that lead and the rest: while only the lead has streamed, it is the working line; once the
// answer follows, only the answer shows. A reply that is nothing but the lead keeps its words.
const LEAD = /^\s*On it\s*[:,—-]\s*([^\n]*)(?:\n+|$)/i;

export interface OnItSplit {
  readonly lead: string | null; // the words after "On it:", or null when the reply has no such line
  readonly rest: string; // the answer after it ("" while only the lead has come)
}

export function splitOnItLead(text: string): OnItSplit {
  const found = LEAD.exec(text);
  if (!found) return { lead: null, rest: text };
  return { lead: found[1].trim(), rest: text.slice(found[0].length).trimStart() };
}

// What a bot's text reply shows: the answer without its lead; the lead's words alone when there is no answer.
export function shownReply(text: string): string {
  const { lead, rest } = splitOnItLead(text);
  if (lead === null) return text;
  return rest || lead;
}
