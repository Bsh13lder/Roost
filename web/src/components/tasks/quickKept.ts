import type { QuickChip } from "./quickChips";

// Cancelling a chip (user ruling 2026-10-20): its typed words go back into the title as plain text and are
// not read again while the user keeps typing. The server does the keeping (`keep` on POST /api/tasks/parse);
// this is the web's side: which words are kept, which chips that hides at once, and when a word is let go.

const same = (a: string, b: string) => a.toLocaleLowerCase() === b.toLocaleLowerCase();

/** The words still in the text, so deleting a cancelled word and typing a new one reads again. */
export function stillTyped(kept: readonly string[], text: string): string[] {
  const lower = text.toLocaleLowerCase();
  return kept.filter((word) => lower.includes(word.toLocaleLowerCase()));
}

/** Adds a chip's words to those kept, once each. */
export function keepWords(kept: readonly string[], words: readonly string[]): string[] {
  return [...kept, ...words.filter((word) => !kept.some((have) => same(have, word)))];
}

/** A chip whose words were all cancelled is hidden at once, before the server answers. */
export function isCancelled(chip: QuickChip, kept: readonly string[]): boolean {
  return Boolean(chip.words?.length) && (chip.words ?? []).every((word) => kept.some((have) => same(have, word)));
}
