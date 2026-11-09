// The app's accent colour (restructure slice 3): the phone's six choices, remembered in this browser. Violet is the
// tokens' own; any other sets data-accent on the page root, and tokens.css swaps the accent variables for it.
export const ACCENTS = [
  { id: "violet", label: "Violet" }, { id: "blue", label: "Blue" }, { id: "teal", label: "Teal" },
  { id: "green", label: "Green" }, { id: "orange", label: "Orange" }, { id: "pink", label: "Pink" },
] as const;

export type AccentId = (typeof ACCENTS)[number]["id"];

export const DEFAULT_ACCENT: AccentId = "violet";
export const ACCENT_KEY = "roost.accent";

const isAccent = (value: string | null): value is AccentId => ACCENTS.some((accent) => accent.id === value);

export function readAccent(): AccentId {
  try {
    const saved = window.localStorage.getItem(ACCENT_KEY);
    return isAccent(saved) ? saved : DEFAULT_ACCENT;
  } catch (error) {
    console.warn("This browser keeps no site data here: the accent stays violet.", error);
    return DEFAULT_ACCENT;
  }
}

export function saveAccent(id: AccentId): void {
  try {
    window.localStorage.setItem(ACCENT_KEY, id);
  } catch (error) {
    console.warn("Could not remember the accent colour in this browser.", error);
  }
}

export function applyAccent(id: AccentId): void {
  const root = document.documentElement;
  if (id === DEFAULT_ACCENT) delete root.dataset.accent;
  else root.dataset.accent = id;
}
