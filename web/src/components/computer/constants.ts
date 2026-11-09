// The live screen's numbers (mirrors LIVE_CLOSE_* in roost/constants.py) and its words.
export const LIVE_CLOSE_ASLEEP = 4410;
export const LIVE_CLOSE_UNAVAILABLE = 4503;
export const LIVE_CLOSE_GIVEN_BACK = 4000;
export const LIVE_CLOSE_NOT_HELD = 4409;
export const ACCOUNT_MAX_CHARS = 100; // mirrors SITE_LOGIN_LABEL_MAX_CHARS

// Teach a task: mirrors TEACH_DESCRIPTION_MAX in roost/constants.py.
export const TEACH_DESCRIPTION_MAX = 200;
export const TEACH_PROPOSED_TEXT = "The skill is in the chat. Press Save skill to keep it.";
export const TEACH_DISCARDED_TEXT = "The recording was thrown away.";

export const CONTROL_GIVEN_BACK_TEXT = "Control was given back.";

// Wipe workspace (Workspace files): the confirm, and the quiet line after it.
export const WIPE_LABEL = "Wipe workspace";
export const wipeConfirmText = (botName: string) => `Delete every file in ${botName}'s workspace? This can't be undone.`;
export const wipeForGoodLabel = (botName: string) => `Wipe ${botName}'s workspace for good`;
export const WIPED_TEXT = "Workspace wiped.";

// Internet in the workspace (A4): off by default; roost/programs/texts.py tells the bot the same.
export const INTERNET_LABEL = "Internet in the workspace";
export const INTERNET_OFF_LINE = "Off: programs in the workspace have no internet.";
export const INTERNET_ON_LINE =
  "On: programs can reach public sites through Roost's proxy, never your Mac or local network. Your keys never go in.";
export const COMPUTERS_BUSY_TEXT ="All computers are busy right now. Try again in a few minutes.";

// Linux is the usual choice (DEFAULT_COMPUTER = "linux"); Mac Brave is the optional one.
export const KIND_LABELS = { linux: "Linux computer", mac_brave: "Mac Brave (optional)" } as const;
export const MAC_BRAVE_RISK_LINE = "Mac Brave runs as your macOS user. The Linux computer is sealed off.";
export const KIND_LINES = {
  linux: "The usual choice: a sealed Linux computer on this Mac. Sign in once with Take control.",
  mac_brave: "Optional: its own Brave window on your Mac.",
} as const;

// C3: the ring that shows where the bot clicks (computer_pointer frames carry screen pixels of the 1280×800 Xvnc
// screen, mirroring CU_VIEW_MAX_W / CU_VIEW_MAX_H). Its size lives in tokens.css (--pointer-ring-size).
export const COMPUTER_SCREEN_W = 1280;
export const COMPUTER_SCREEN_H = 800;
export const POINTER_RING_MS = 900;
export const POINTER_RING_SIZE_PX = "var(--pointer-ring-size)";

// Take control on a touch screen: noVNC turns a tap into a click, two fingers into a right click or a scroll, and
// this row stands in for the keyboard. Each key is its X11 keysym and its KeyboardEvent code.
export const TOUCH_POINTER_QUERY = "(pointer: coarse)";
export const TOUCH_KEYS = {
  Enter: [0xff0d, "Enter"],
  Backspace: [0xff08, "Backspace"],
  Tab: [0xff09, "Tab"],
  Escape: [0xff1b, "Escape"],
} as const satisfies Record<string, readonly [number, string]>;
export type TouchKey = keyof typeof TOUCH_KEYS;
export const TOUCH_KEY_ORDER: readonly TouchKey[] = ["Enter", "Backspace", "Tab", "Escape"];
export const TOUCH_TYPE_LABEL = "Type on the computer";
export const TOUCH_SEND_LABEL = "Send text";
export const TOUCH_TYPE_MAX_CHARS = 2000; // mirrors LIVE_PASTE_MAX_CHARS: the server drops a longer paste
