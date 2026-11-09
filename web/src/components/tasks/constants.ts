// The task drawer's and the quick add's numbers (redesign P3). The limits are the gateway's
// (roost/constants.py MAX_STEP_TITLE_LENGTH, MAX_COMMENT_LENGTH, QUICK_LINE_MAX_LENGTH): the inputs stop
// there, and the gateway checks again.
export const MAX_STEP_TITLE = 200;
export const MAX_COMMENT = 4000;
export const MAX_QUICK_LINE = 300;
export const QUICK_PARSE_DELAY_MS = 250; // the quick add asks the server this long after the last key
export const REPEAT_DEFAULT_TIME = "09:00"; // a repeat for a task due on a day with no time
export const TASK_PARAM = "task"; // the open drawer's task id in the address (?task=…)
export const COMMENT_ROWS = 6; // the comment box grows to this many lines, then scrolls
export const MAX_SUGGESTIONS = 6; // the quick add's autocomplete shows at most this many names
export const MAX_TOKEN_WORDS = 5; // a project or bot name of up to this many words completes across spaces
