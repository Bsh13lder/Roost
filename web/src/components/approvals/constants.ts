// The words and limits of the approval modes and cards, in one place (Amendment N: the third mode is shown as
// "Review first" and its card is called a Proposal). The wire values ("ask", "auto_edit", "plan") never change.
// roost/approvals/texts.py (MODE_LABELS, PLAN_CARD_NAME) says the same names; keep the two together.
import type { ApprovalMode, ApprovalTopic } from "../../api/types";

export const MODE_OPTIONS: ReadonlyArray<{ id: ApprovalMode; label: string; description: string }> = [
  { id: "ask", label: "Ask every time", description: "Every change waits for your OK on a card." },
  { id: "auto_edit", label: "Auto-edit", description: "Ordinary changes go straight through, each with Undo. Risky ones still ask." },
  { id: "plan", label: "Review first", description: "It shows you a proposal first. Accept runs it all." },
];

export const PROPOSAL_CARD_NAME = "Proposal";
export const ALWAYS_ASK_TITLE = "Always ask about";
export const LOCKED_TOPIC_LABEL = "Posting and sending";
export const LOCKED_TOPIC_NOTE = "always asks";

export const TOPIC_OPTIONS: ReadonlyArray<{ id: ApprovalTopic; label: string }> = [
  { id: "files", label: "Files" },
  { id: "tasks", label: "Tasks" },
  { id: "money", label: "Money" },
  { id: "notes", label: "Notes" },
  { id: "documents", label: "Documents" },
  { id: "projects", label: "Projects" },
  { id: "memory", label: "Memory" },
  { id: "team", label: "Team" },
  { id: "routines", label: "Routines" },
  // Programs: run_program and write_file in the bot's own workspace. Off, they just run in a clean run.
  { id: "programs", label: "Programs" },
];

// C3: Browsing actions, the bot's ordinary clicks and typing on its own computer, shown as the chat mode (owner
// decision 2026-10-25): the composer's pill and the Info tab's row offer the same three. Just browse is the default.
// Ask me is the "browsing" topic, Full auto is `auto_review` (lib/chatMode.ts). Buying, sending and submitting always ask.
export const TOPIC_LABELS = { browsing: "Browsing actions" } as const;
export type ChatMode = "ask" | "browse" | "auto";
export const CHAT_MODE_TITLE = "Chat mode";
export const CHAT_MODE_OPTIONS: ReadonlyArray<{ id: ChatMode; label: string; description: string }> = [
  { id: "ask", label: "Ask me", description: "Every click on its computer waits for your OK." },
  { id: "browse", label: "Just browse", description: "Ordinary clicks just happen. Buttons it can't read still ask." },
  {
    id: "auto", label: "Full auto",
    description: "A checker looks at buttons it can't read first. Paying, sending, deleting, typing and new sites still ask.",
  },
];
// The screen acts whose card shows a picture of the button (CU_ACT_TOOLS in roost/constants.py).
export const CU_ACT_TOOLS: ReadonlySet<string> = new Set(["click", "type", "press_key"]);
export const CROP_FAILED = "Couldn't load the picture of the button.";

export const FOLDERS_TITLE = "Folders it may use";
export const ACCESS_OPTIONS = [
  { id: "read", label: "Read only" },
  { id: "read_write", label: "Read and write" },
] as const;
export const READ_POLICY_OPTIONS = [
  { id: "ask_each", label: "Ask every time" },
  { id: "ask_session", label: "Ask once per session" },
] as const;
export const SCOPE_OPTIONS = [
  { id: "bot", label: "This bot" },
  { id: "all", label: "All bots" },
] as const;
export const FOLDER_HINT = "Keys, system folders and dot-folders inside it stay hidden.";

// The red line on a step that came from outside content (roost/approvals/texts.py OUTSIDE_CONTENT_MARK).
export const OUTSIDE_CONTENT_MARK = "Based on outside content";
export const FROM_WEB_CONTENT = "from web content";
export const HARD_FLOOR_BADGE = "Hard floor";

// Ask card (Task 14).
export const YES = "Yes";
export const OPEN_SITE = "Open";   // an Open card: a site the bot wants to open (roost/talk/new_site.py)
export const YES_SESSION = "Yes for this session";
export const NO = "No";
export const ACCEPT = "Accept";
export const EDIT = "Edit";
export const DECLINE = "Decline";
export const SEND = "Send";
// The Send card (owner, 2026-11-03; roost/approvals/send_card.py): the bot's own text waits for one of these.
export const SEND_CARD_NAME = "Ready to send";
export const SEND_IT = "Send";
export const DONT_SEND = "Don't send";
export const CHANGE_IT = "Change it…";
export const CHANGE_IT_LABEL = "What should it say instead?";
export const SEND_CHANGE = "Send change";
export const CHANGE_MAX_CHARS = 4000; // the server's limit on an edit (APPROVAL_EDIT_TEXT_MAX)
export const SENT_LEAD = "You said send:";
export const NOT_SENT_LEAD = "Not sent:";
export const CHANGED_LEAD = "You asked for a change:";
// A row the Send card shows whole, in a box that scrolls when it is long (rows.py DRAFT_ROW_KEY).
export const DRAFT_ROW_KEY = "draft";

// A diff shows this many lines before "Open full diff" (the server cuts at the same number).
export const DIFF_SHOWN_LINES = 400;
export const OPEN_FULL_DIFF = "Open full diff";
export const OPEN_FULL_ROWS = "Open full";
export const UNDO = "Undo";

// A closed card, as the quiet line that replaces its buttons (roost/approvals/texts.py says the same lines to the bot).
export const EXPIRED_LINE = "Replaced by a newer question.";
export const ACCEPTED_PROPOSAL_LINE = "You accepted the proposal.";
export const DECLINED_PROPOSAL_LINE = "You declined the proposal.";
export const EDITED_PROPOSAL_LINE = "You asked for changes to the proposal.";
export const FAILED_LINE = "It didn't run.";
export const EDIT_LABEL = "What should change?";
export const FULL_DIFF_FAILED = "Couldn't open the full diff. Try again.";
// Options cards (roost/choices/texts.py says the same to the bot).
export const TYPE_YOUR_OWN = "Type your own";
export const DISMISS = "Dismiss";
export const SAFE_MARK = "Safe choice";
export const CHOICE_SEND = "Send";
export const CHOICE_OWN_MAX = 1000;
export const CHOICE_ANSWERED_LINE = "You answered.";
export const CHOICE_DISMISSED_LINE = "Dismissed: counts as No.";

export const ALREADY_ANSWERED = "Already answered.";
// An answered options card, shrunk to one line (lead task 07): "✓ You answered: Tuesday", the options behind a toggle.
export const CHOICE_DONE_LEAD = "You answered:";
export const CHOICE_SHOW_OPTIONS = "Show options";
export const CHOICE_YOUR_ANSWER = " (your answer)";

// The Pay card (owner, 2026-11-05, roost/payments/): the card parts the page asks for, then Pay · Don't pay.
export const PAY_CARD_NAME = "Ready to pay";
export const PAY_IT = "Pay";
export const DONT_PAY = "Don't pay";
export const PAID_LEAD = "You paid:";
export const NOT_PAID_LEAD = "Not paid:";
export const PAY_NEW_CARD = "Another card";
export const PAY_SAVE_CARD = "Save this card in Vault: cards (never the security code)";
export const PAY_LOADING = "Reading the payment page…";
export const PAY_FIELDS_FAILED = "Couldn't read the payment page. You can still pay or take control.";
export const PAY_NO_FIELDS = "The page asks for no card details here. Pay clicks the button.";
export const PAY_NOTE = "Roost types your card into the page; the bot never sees it.";
export const CARD_PART_LABELS = {
  number: "Card number", exp: "Expiry (MM/YY)", name: "Name on card", cvc: "Security code (CVC)",
} as const;
export const CARD_PART_AUTOCOMPLETE = {
  number: "cc-number", exp: "cc-exp", name: "cc-name", cvc: "cc-csc",
} as const;
export const CARD_PART_MAX = { number: 23, exp: 7, name: 80, cvc: 4 } as const;
export const savedCardLabel = (brand: string, last4: string) =>
  `${brand.charAt(0).toUpperCase()}${brand.slice(1)} ending ${last4}`;
