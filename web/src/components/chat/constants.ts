// The chat's numbers (redesign P2), in one place.
export const LONG_REPLY_CHARS = 280; // a bot reply this long is a full-width card, not a bubble
export const LONG_REPLY_LINES = 4; // so is one with more lines than this
export const TOOL_LINES_SHOWN = 5; // a reply lists at most this many of its bot's latest steps
export const COMPOSER_MAX_ROWS = 8; // the message box grows to this many lines, then scrolls
export const FIRST_LINE_DEFAULT_ACTIVITY = "reading your message";
export const WORKING_BOT_PX = 36; // a working bot's robot in its chat: just over 32 px, so its eyes move
export const QUEUED_LINE = "Queued, I'll pick it up next";
// Tapbacks: the server's REACTION_KEYS, each with a glyph and the words a screen reader hears.
export const REACTION_GLYPHS = {
  thumbs_up: { glyph: "👍", label: "Thumbs up" },
  heart: { glyph: "❤️", label: "Heart" },
  laugh: { glyph: "😂", label: "Laughing" },
  check: { glyph: "✅", label: "Done" },
  question: { glyph: "❓", label: "Question" },
} as const;
export type ReactionKey = keyof typeof REACTION_GLYPHS;
export const REACTION_KEYS = Object.keys(REACTION_GLYPHS) as readonly ReactionKey[];
export const COMPUTER_CARD_FOLD_MS = 220; // the computer card shrinks away this long when its run ends
// The steps sheet's way to the screen (owner, 2026-10-26: the chat never shows it; the Computer tab does).
export const OPEN_COMPUTER_LABEL = "Open computer";
// The web-content mark (2026-10-26): a quiet "Web" chip; its name and what a tap explains.
export const WEB_MARK_LABEL = "Web";
export const WEB_MARK_NAME = "From web content";
export const WEB_MARK_EXPLAINED =
  "Part of this came from a web page. Roost limits what the bot can do after reading it, so check it before you act on it.";
// Task cards (2026-10-26): what a task_cards line and a reminder card say.
export const TASK_CARDS_ADDED = "Added";
export const TASK_CARDS_LISTED = "Your tasks";
export const TASK_CARDS_GONE = "These tasks are gone.";
export const TASK_GONE = "This task is gone.";
export const TASK_CARDS_MORE = "and {count} more on the Board";
// A long task card shows this many rows and folds the rest (owner, 2026-10-29: "show first 4-5 and after toggle").
export const TASK_CARDS_SHOWN = 5;
export const TASK_CARDS_SHOW_MORE = "Show {count} more";
export const TASK_CARDS_SHOW_LESS = "Show less";
export const REMINDER_SKIPPED = "Skipped";
export const REMINDER_DONE = "✓ Done";
export const REMINDER_FAILED = "Marked failed";
export const REMINDER_NO_DATE = "Now has no date";
export const REMINDER_MOVED = "Moved to {when}";
