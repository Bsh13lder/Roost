// The quick add's manual pickers write the same words typing would, into the line (Amendment T), so the
// server reads them like any other words and draws the same chip. Pure.

export const PRIORITY_CHOICES = [
  { key: "urgent", label: "Urgent", words: "!urgent" },
  { key: "high", label: "High", words: "!high" },
  { key: "medium", label: "Medium", words: "!medium" },
  { key: "low", label: "Low", words: "!low" },
] as const;

export const REPEAT_CHOICES = [
  { key: "day", label: "Every day", words: "every day" },
  { key: "weekday", label: "Every weekday", words: "every weekday" },
  { key: "week", label: "Every week", words: "every week" },
  { key: "other-week", label: "Every other week", words: "every other week" },
  { key: "month", label: "Every month", words: "every month" },
  { key: "year", label: "Every year", words: "every year" },
] as const;

const ISO_DAY = /^(\d{4}-\d{2}-\d{2})(?: (\d{2}:\d{2}))?$/;

/** A DatePicker / DateTimePicker value as words the server reads: "2026-10-21 09:00" is
 * "2026-10-21 at 09:00"; words the user typed go in as they are; "" is no date. */
export function dateWords(value: string): string {
  const found = ISO_DAY.exec(value.trim());
  if (!found) return value.trim();
  return found[2] ? `${found[1]} at ${found[2]}` : found[1];
}

const escape = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** `text` without the earlier words of a chip (whole words, any case), single spaces. */
export function withoutWords(text: string, words: readonly string[]): string {
  const cut = [...words].sort((a, b) => b.length - a.length).reduce(
    (now, word) => now.replace(new RegExp(`(?<!\\w)${escape(word)}(?!\\w)`, "i"), " "), text);
  return cut.replace(/\s+/g, " ").trim();
}

/** The line with a picked chip's words: they replace the chip's earlier words (when it had some) or are
 * added at the end. Empty words only remove (No date). */
export function insertWords(text: string, words: string, replacing: readonly string[] = []): string {
  const base = withoutWords(text, replacing);
  return [base, words.trim()].filter(Boolean).join(" ");
}

/** A tag typed or picked as `#tag`; spaces and a leading # are dropped. null when nothing usable is left. */
export function tagWords(raw: string): string | null {
  const name = raw.trim().replace(/^#+/, "").replace(/\s+/g, "-");
  return /^[\p{L}][\p{L}\p{N}_-]*$/u.test(name) ? `#${name}` : null;
}

/** Names containing the query, best (those that start with it) first. */
export function filterNames(names: readonly string[], query: string): string[] {
  const q = query.trim().toLocaleLowerCase();
  if (!q) return [...names];
  const has = names.filter((name) => name.toLocaleLowerCase().includes(q));
  return [...has.filter((name) => name.toLocaleLowerCase().startsWith(q)), ...has.filter((name) => !name.toLocaleLowerCase().startsWith(q))];
}
