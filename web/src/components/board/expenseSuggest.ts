import { accept, suggest, type SuggestOption, type Suggestion } from "../tasks/quickSuggest";

/** The expense line completes only `/Project` names: `#tag` stays in the note and `!` means nothing here. */
export function suggestProject(text: string, caret: number, projects: readonly string[]): Suggestion | null {
  const found = suggest(text, caret, { projects, tags: [], bots: [] });
  return found && found.trigger === "/" ? found : null;
}

export { accept };
export type { SuggestOption };
