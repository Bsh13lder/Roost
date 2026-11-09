import { useLayoutEffect, useRef, useState, type KeyboardEvent, type RefObject } from "react";
import {
  handleListKey, insertMention, matchingOptions, mentionQuery, type MentionOption, type MentionTrigger,
} from "../../lib/mentions";

export interface MentionPicker {
  shown: MentionOption[];
  trigger: MentionTrigger; // what the open list inserts: "@" a bot, "#" a project
  highlighted: number;
  pick: (option: MentionOption) => void;
  onEdit: (caret: number) => void;
  onSelect: (caret: number) => void;
  // True when the open list used the key (the composer then does nothing else with it).
  onKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => boolean;
}

// The word at the caret and the list it opens: "#word" your projects, "@word" your other bots.
function openList(
  beforeCaret: string, bots: readonly MentionOption[] | undefined, projects: readonly MentionOption[] | undefined,
): { trigger: MentionTrigger; options: MentionOption[] } {
  const projectQuery = projects ? mentionQuery(beforeCaret, "#") : null;
  if (projectQuery !== null && projects) return { trigger: "#", options: matchingOptions(projectQuery, projects) };
  return { trigger: "@", options: bots ? matchingOptions(mentionQuery(beforeCaret, "@"), bots) : [] };
}

// Typing "@" in a bot's chat lists your other bots, and "#" your projects; picking one writes "@Name " or
// "#Name " in place of the partial word. With no options of a kind its list never opens.
// ArrowUp/ArrowDown move, Enter or Tab picks, Escape closes.
export function useMentionPicker(
  boxRef: RefObject<HTMLTextAreaElement | null>, text: string, setText: (text: string) => void,
  options: readonly MentionOption[] | undefined, projects?: readonly MentionOption[],
): MentionPicker {
  const [caret, setCaret] = useState(0);
  const [active, setActive] = useState(0);
  const [dismissed, setDismissed] = useState(false);
  const pending = useRef<number | null>(null);
  // React puts the caret at the end when it rewrites the value; put it back right after the picked name.
  useLayoutEffect(() => {
    const at = pending.current;
    if (at === null) return;
    pending.current = null;
    boxRef.current?.setSelectionRange(at, at);
  });

  const list = openList(text.slice(0, caret), options, projects);
  const shown = dismissed ? [] : list.options;
  const highlighted = Math.min(active, shown.length - 1);
  const pick = (option: MentionOption) => {
    const next = insertMention(text, caret, option.name, list.trigger);
    pending.current = next.caret;
    setCaret(next.caret);
    setText(next.text);
  };
  const onEdit = (at: number) => {
    setCaret(at);
    setDismissed(false);
    setActive(0);
  };
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) =>
    shown.length > 0 && handleListKey(event, {
      count: shown.length, setActive, pick: () => pick(shown[highlighted]), dismiss: () => setDismissed(true),
    });
  return { shown, trigger: list.trigger, highlighted, pick, onEdit, onSelect: setCaret, onKeyDown };
}
