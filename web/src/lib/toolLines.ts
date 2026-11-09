// A bot's step, as the gateway announces it while the bot works ("adding a task", "opening elpais.com"),
// written as a compact line in its reply (redesign P2): "Adding a task…" while it is the current step,
// "Added a task" once done. P4 turns these lines into live record cards.
//
// Every verb the gateway announces has its past tense here: tests/test_tool_lines.py checks it.
const PAST: Readonly<Record<string, string>> = {
  adding: "added", asking: "asked", changing: "changed", checking: "checked", completing: "completed",
  correcting: "corrected", creating: "created", deleting: "deleted", editing: "edited", filing: "filed", forgetting: "forgot", logging: "logged",
  looking: "looked", making: "made", moving: "moved", opening: "opened", reading: "read", renaming: "renamed", saving: "saved", searching: "searched",
  sending: "sent", setting: "set", switching: "switched", undoing: "undid", updating: "updated", waiting: "waited", writing: "wrote",
};

const capitalised = (text: string): string => text.charAt(0).toUpperCase() + text.slice(1);

export function toolLineText(activity: string, done: boolean): string {
  const text = activity.trim();
  if (!done) return `${capitalised(text)}…`;
  const [verb, ...rest] = text.split(" ");
  const past = PAST[verb.toLowerCase()];
  return capitalised(past ? [past, ...rest].join(" ") : text);
}
