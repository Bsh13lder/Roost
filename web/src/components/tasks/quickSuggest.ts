import { MAX_SUGGESTIONS, MAX_TOKEN_WORDS } from "./constants";

// The quick line's autocomplete (Tasks & Money polish), pure: which token is being typed at the caret,
// and what could finish it. It only suggests names from lists the web already loads; the server then
// reads the accepted text, so the line means exactly what the server says it means.
export type Trigger = "/" | "#" | "@" | "!";

export interface SuggestOption {
  key: string; // a stable id for the list
  label: string; // what the list shows
  insert: string; // the whole token, trigger included: "/Casa Nueva"
  hint?: string;
}

export interface Suggestion {
  trigger: Trigger;
  start: number; // where the token's trigger is
  end: number; // the caret
  options: readonly SuggestOption[];
}

export interface SuggestSources {
  projects: readonly string[]; // after "/"
  tags: readonly string[]; // after "#"
  bots: readonly string[];
}

export interface TokenAtCaret {
  trigger: Trigger;
  start: number;
  query: string; // the text after the trigger, up to the caret
}

interface Level extends SuggestOption {
  aliases: readonly string[]; // other words, without the "!", that start this one
}

const LEVELS: readonly Level[] = [
  { key: "urgent", label: "Urgent", insert: "!urgent", hint: "!!!", aliases: ["!!", "urgente"] },
  { key: "high", label: "High", insert: "!high", hint: "!!", aliases: ["!", "alta"] },
  { key: "medium", label: "Medium", insert: "!medium", hint: "!", aliases: ["media"] },
  { key: "low", label: "Low", insert: "!low", hint: "!-", aliases: ["-", "baja"] },
  { key: "star", label: "Star it", insert: "!star", hint: "*", aliases: ["fav"] },
];
const TRIGGERS: readonly string[] = ["/", "#", "@", "!"];
const NAMES_OF: Record<"/" | "#" | "@", (sources: SuggestSources) => readonly string[]> = {
  "/": (sources) => sources.projects, "#": (sources) => sources.tags, "@": (sources) => sources.bots,
};
const SHORTHAND = /^(?:!{2,}|!-)$/;
const SPACE = /\s/;

const same = (a: string, b: string) => a.toLocaleLowerCase() === b.toLocaleLowerCase();
const startsLike = (name: string, query: string) => name.toLocaleLowerCase().startsWith(query.toLocaleLowerCase());

/** The token being typed at `caret`: the nearest / # @ or ! that starts a word before it, and what follows. */
export function tokenAt(text: string, caret: number): TokenAtCaret | null {
  const before = text.slice(0, caret);
  for (let index = before.length - 1; index >= 0; index -= 1) {
    const char = before[index];
    if (!TRIGGERS.includes(char) || (index > 0 && !SPACE.test(before[index - 1]))) continue;
    const query = before.slice(index + 1);
    if ((char === "!" || char === "#") && SPACE.test(query)) return null; // levels and tags are one word
    if (query.trim().split(/\s+/).filter(Boolean).length > MAX_TOKEN_WORDS) return null;
    return { trigger: char as Trigger, start: index, query };
  }
  return null;
}

function levelOptions(query: string): readonly SuggestOption[] {
  return LEVELS.filter((level) => [level.key, ...level.aliases].some((word) => startsLike(word, query)))
    .map(({ key, label, insert, hint }) => ({ key, label, insert, hint }));
}

function nameOptions(names: readonly string[], trigger: "/" | "#" | "@", query: string): readonly SuggestOption[] {
  return names.filter((name) => startsLike(name, query))
    .map((name) => ({ key: name, label: name, insert: `${trigger}${name}` }));
}

/** What could finish the token at the caret, or null when nothing is being typed or nothing fits. */
export function suggest(text: string, caret: number, sources: SuggestSources): Suggestion | null {
  const token = tokenAt(text, caret);
  if (!token) return null;
  const typed = text.slice(token.start, caret);
  if (token.trigger === "!" && SHORTHAND.test(typed)) return null; // "!!!" is already whole
  const found = token.trigger === "!" ? levelOptions(token.query)
    : nameOptions(NAMES_OF[token.trigger](sources), token.trigger, token.query);
  const options = found.slice(0, MAX_SUGGESTIONS);
  if (options.length === 0) return null;
  if (options.length === 1 && same(options[0].insert, typed)) return null; // nothing left to complete
  return { trigger: token.trigger, start: token.start, end: caret, options };
}

/** The text with the typed token replaced by the option, a space after it, and where the caret goes. */
export function accept(text: string, suggestion: Suggestion, option: SuggestOption): { text: string; caret: number } {
  const after = text.slice(suggestion.end);
  const head = `${text.slice(0, suggestion.start)}${option.insert}`;
  return { text: `${head}${after.startsWith(" ") ? "" : " "}${after}`, caret: head.length + 1 };
}
