import type { MemoryKind, MemorySource } from "../../api/types";

// The server's text limit (MEMORY_TEXT_MAX_CHARS in roost/constants.py).
export const MEMORY_TEXT_MAX = 500;

export const KIND_LABELS: Readonly<Record<MemoryKind, string>> = {
  about_you: "About you",
  preference: "Preference",
  fact: "Fact",
  project: "Project",
  lesson: "Lesson",
  decision: "Decision",
};

// The kinds a bot's own memory can have; About you is the only kind that is shared.
export const BOT_KINDS: readonly MemoryKind[] = ["preference", "fact", "project", "lesson"];
export const ABOUT_YOU_KINDS: readonly MemoryKind[] = ["about_you"];

export const SOURCE_LABELS: Readonly<Record<MemorySource, string>> = { user: "You", bot: "A bot" };
