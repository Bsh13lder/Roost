// "@Name" while typing: shared by the room composer and a bot's chat composer. The server reads the names when
// the message arrives (rooms: roost/rooms/mentions.py; a bot's chat: roost/talk/mentions.py).
import type { Dispatch, KeyboardEvent, SetStateAction } from "react";

export interface MentionOption {
  id: string;
  name: string;
}

// "@" names one of your other bots; "#" one of your projects (2026-10-26: the server reads "#Name" against your
// projects and tells the bot which one you mean).
export type MentionTrigger = "@" | "#";

// "@word" (or "#word") right before the caret, at the start or after whitespace — so an e-mail address
// (me@scout) or an issue number (a#1) never opens the list.
const WORD = "[\\p{L}\\p{N}_.-]*";
const beforeCaret = (trigger: MentionTrigger) => new RegExp(`(?:^|\\s)${trigger}(${WORD})$`, "u");
const partial = (trigger: MentionTrigger) => new RegExp(`${trigger}(${WORD})$`, "u");

export function mentionQuery(textBeforeCaret: string, trigger: MentionTrigger = "@"): string | null {
  const match = beforeCaret(trigger).exec(textBeforeCaret);
  return match ? match[1] : null;
}

export function insertMention(
  text: string, caret: number, name: string, trigger: MentionTrigger = "@",
): { text: string; caret: number } {
  const before = text.slice(0, caret).replace(partial(trigger), `${trigger}${name} `);
  return { text: before + text.slice(caret), caret: before.length };
}

export function withReplyMention(draft: string, name: string): string {
  const mention = `@${name} `;
  return draft.startsWith(mention) ? draft : mention + draft;
}

// The options whose name starts with what is typed after "@" (none while no "@word" is being typed).
export function matchingOptions(query: string | null, options: readonly MentionOption[]): MentionOption[] {
  if (query === null) return [];
  const wanted = query.toLowerCase();
  return options.filter((option) => option.name.toLowerCase().startsWith(wanted));
}

export interface ListKeys {
  count: number;
  setActive: Dispatch<SetStateAction<number>>;
  pick: () => void;
  dismiss: () => void;
}

// The keys the open list owns. Returns false for any other key.
export function handleListKey(event: KeyboardEvent<HTMLTextAreaElement>, keys: ListKeys): boolean {
  if (event.key === "ArrowDown" || event.key === "ArrowUp") {
    const step = event.key === "ArrowDown" ? 1 : keys.count - 1;
    keys.setActive((index) => (index + step) % keys.count);
  } else if (event.key === "Enter" || event.key === "Tab") {
    keys.pick();
  } else if (event.key === "Escape") {
    keys.dismiss();
  } else {
    return false;
  }
  event.preventDefault();
  return true;
}
