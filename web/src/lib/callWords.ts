// Goodbye words on a call (call mode, contract D; the phone's call_words.dart holds the same set): the whole
// utterance, lower-cased, trimmed and stripped of punctuation, must be one of these. Never a substring, so
// "bye the way" is just words for the bot. A goodbye is never sent as a message.

export const GOODBYE_WORDS: ReadonlySet<string> = new Set([
  "bye", "goodbye", "bye bye", "hang up", "end call", "end the call", "that's all", "that is all",
  "adiós", "adios", "hasta luego", "cuelga", "chao",
]);

// Punctuation and symbols go; letters (any script), digits, spaces and the apostrophe stay.
const NOT_WORDS = /[^\p{L}\p{N}\s']/gu;
const CURLY_APOSTROPHES = /[‘’ʼ]/g;

export function isGoodbye(text: string): boolean {
  const words = text
    .toLowerCase()
    .replace(CURLY_APOSTROPHES, "'")
    .replace(NOT_WORDS, " ")
    .replace(/\s+/g, " ")
    .trim();
  return words.length > 0 && GOODBYE_WORDS.has(words);
}
