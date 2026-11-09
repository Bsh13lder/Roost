import type { MediaOut } from "./media";
// Wire types mirroring the contract exactly (see
// .superpowers/sdd/2026-10-13-roost-night1-walking-skeleton/contract.md
// "HTTP API" and "Events" sections). Kept in one file so every consumer
// (REST calls, the live WS store, components) imports the same shapes.
import type { MemoriesChangedFrame } from "./memoryTypes";
import type { InstructionProposalsChangedFrame } from "./instructions";
import type { ExpenseOut, TaskOut } from "./taskMoneyTypes";

export type * from "./taskMoneyTypes";

// A bot's robot (avatars v7, the Lensbots): one of eighteen shapes. The ten ghosts (v5), the six Boxbot
// heads (V1) and the S1.6 bird shapes stay valid and draw as a Lensbot through one table
// (components/robot/look.ts LEGACY_SHAPE_TO_LENSBOT); nothing migrates.
export type LensbotShape =
  | "mochi" | "loaf" | "gumdrop" | "pebble" | "bun" | "acorn" | "marsh" | "dumpling" | "muffs" | "squish" | "cub"
  | "sprout" | "cheeky" | "tower" | "helmet" | "bell" | "puck" | "pod";
export type GhostShape = "dome" | "tall" | "wide" | "round" | "droopy" | "spire" | "comet" | "cape" | "puff" | "hooded";
export type LegacyAvatarShape = GhostShape | "classic" | "soft" | "cube" | "monitor" | "egg" | "pear" | "plump" | "crest";
export type AvatarShape = LensbotShape | LegacyAvatarShape;
// The job a bot's body shows as a small emblem (avatars v7 role looks). No role counts as general.
export type BotRole = "general" | "tasks" | "code" | "seo" | "money" | "social" | "research" | "writer";
// The Boxbot screen's signal style: still accepted and stored, no longer drawn (a Lensbot has no screen).
export type RobotScreen = "glow" | "pixel" | "signal";
export type AvatarBadge = "none" | "tasks" | "finance" | "notes" | "docs" | "inbox";

export interface AvatarOut {
  shape: AvatarShape;
  color: string; // "#RRGGBB"
  badge: AvatarBadge;
  screen?: RobotScreen;
  role?: BotRole | null; // on the wire only when set
  picture?: string | null; // a bot's own picture (GET /api/bots/{id}/picture?v=…), shown inside its body
}

export type BotStatus = "resting" | "on_it" | "asking_you" | "stuck" | "off_duty";

export type ApprovalMode = "ask" | "auto_edit" | "plan";
export type ApprovalTopic =
  | "files" | "tasks" | "money" | "notes" | "documents" | "projects" | "memory" | "team" | "routines" | "posting" | "browsing"
  | "programs";
// Ask and Proposal cards (roost/approvals/models.py ApprovalCardOut). The wire says "plan"; the user's word is Proposal.
export type ApprovalCardKind = "ask" | "plan";
export type ApprovalCardState = "open" | "approved" | "declined" | "edited" | "failed" | "expired";
export type ApprovalAnswer = "yes" | "yes_session" | "no" | "accept" | "decline" | "edit" | "pick" | "own";
// What goes along with an answer: Proposal changes or your own words (`text`), or an option's index (`choice`).
export interface ApprovalAnswerExtra {
  text?: string;
  choice?: number;
}
// An options card (roost/approvals/models.py ChoiceOut).
export interface ChoiceOut {
  question: string;
  options: string[];
  safe: number;
  own: boolean;
  why: string;
}
export interface ApprovalDiffOut {
  text: string; // at most 400 lines unless ?full=1; "" on a live frame
  plus: number;
  minus: number;
  truncated: boolean;
}
export interface ApprovalRowOut {
  key: string;
  label: string;
  value: string; // cut at 300 characters unless ?full=1
  truncated: boolean;
}
export interface ApprovalStepOut {
  tool: string;
  topic: string | null;
  title: string;
  detail: string;
  floor: string | null; // a hard-floor kind: this step asks in every mode
  tainted_basis: boolean; // based on outside content
  session_offer: boolean;
  rows: ApprovalRowOut[]; // every stored argument, money first
  diff: ApprovalDiffOut | null;
  // C3: a base64 JPEG of the button, only in GET /api/approvals/{id}?full=1 (live frames and lists send null).
  crop?: string | null;
}
export interface ApprovalCardOut {
  id: string;
  bot_id: string;
  thread_id: string;
  kind: ApprovalCardKind;
  state: ApprovalCardState;
  tainted: boolean;
  session_offer: boolean;
  created_at: string;
  closed_at: string | null;
  steps: ApprovalStepOut[];
  choice?: ChoiceOut | null; // set on an options card
  send?: boolean; // a Send card (roost/approvals/send_card.py): Send · Don't send · Change it…
  from_web?: boolean; // the red "from web content" chip (a Send card: only when its text came from a page)
  pay?: boolean; // a Pay card (roost/payments/pay_card.py): card fields, then the same Pay click
}
// GET /api/approvals/{id}/pay: the card parts the page asks for, why Roost can't fill them, your saved cards.
export type CardPart = "number" | "exp" | "name" | "cvc";
export interface SavedCardOut {
  id: string;
  brand: string;
  last4: string;
  last_used_at: string | null;
}
export interface PayFieldsOut {
  parts: CardPart[];
  refusal: string;
  cards: SavedCardOut[];
}
// POST /api/approvals/{id}/pay: a saved card's id and its security code, or a new card (save keeps it in Vault: cards).
export interface PayIn {
  card_id?: string;
  number?: string;
  exp?: string;
  name?: string;
  cvc?: string;
  save?: boolean;
}
// An "approval" message's body: the card id and the step titles as they were when it opened.
export interface ApprovalMessageData {
  card_id: string;
  kind: ApprovalCardKind;
  steps: string[];
}
// A mac_activity message's body (roost/mac/activity.py activity_body).
export interface MacActivityData {
  op: "create" | "edit" | "rename" | "trash" | "undo";
  label: string;
  path: string;
  new_path?: string;
  plus: number;
  minus: number;
  tainted_basis: boolean;
  undid?: string;
  undo: Record<string, unknown> | null;
}

// A program_activity message's body (roost/programs/wrap.py): a program the bot ran, or a file it wrote.
export interface ProgramActivityData {
  op: "run" | "write";
  command?: string;
  path?: string;
  exit_code: number;
  timed_out: boolean;
  output: string;
  cut: boolean;
  tainted_basis: boolean;
}

// A shared Mac folder (roost/gateway/routes/mac.py GrantOut). bot_id null: every bot may use it.
export type GrantAccess = "read" | "read_write";
export type ReadPolicy = "ask_each" | "ask_session";
export interface GrantOut {
  id: string;
  bot_id: string | null;
  label: string;
  path: string;
  access: GrantAccess;
  read_policy: ReadPolicy;
  is_vault: boolean;
  created_at: string;
}
export interface GrantIn {
  path: string;
  label: string;
  access: GrantAccess;
  read_policy: ReadPolicy;
  bot_id: string | null;
}
export interface GrantPatch {
  label?: string;
  access?: GrantAccess;
  read_policy?: ReadPolicy;
}

// A bot's voice (voice plan V2, schema v37): fixed ids and a number. The server sends the defaults
// (aiden · natural · 1.0 · off) for a bot that never chose.
export interface BotVoice {
  speaker: string;
  tone: string;
  speed: number; // the player's rate; it keeps the pitch
  read_aloud: boolean; // a reply that arrives while its chat is open plays by itself
  // Correct what I say (voice tuning D3): a corrected copy of what you say, in any language, with the mistakes
  // marked (an english_fix line). The server sends both names; an older one only the old. Missing: off.
  correct_speech?: boolean;
  correct_english?: boolean;
  // The language you speak to this bot: "auto" (the ear listens) or one of GET /api/voice's languages (D2).
  language?: string;
}

export interface BotApproval {
  mode: ApprovalMode;
  ask_topics: ApprovalTopic[]; // "Always ask about" switches that are on (posting is never in here)
  locked_topics: ApprovalTopic[]; // always on, shown greyed: ["posting"]
  // Full auto (chat mode, 2026-10-25): a checker looks at buttons it can't read first. Missing on an older server: off.
  auto_review?: boolean;
}

export interface BotOut {
  id: string;
  name: string;
  job: string;
  instructions: string;
  avatar: AvatarOut;
  template_id: string | null;
  status: BotStatus;
  activity: string | null;
  model_override: string | null;
  model: string; // what it runs on: its choice, or the default
  model_label: string;
  effort: "low" | "medium" | "high" | "max" | null; // null: the model's default
  off_duty: boolean;
  is_primary: boolean;
  group: string | null; // the sidebar label; null: none (polish R1)
  pinned: boolean; // in the sidebar's robot row; the main bot always is
  pinned_at: string | null; // when it was pinned: the row's order
  computer: ComputerKind; // which computer it works on: its own Linux computer (the default) or a Brave window on your Mac (optional)
  full_limit_until: string | null; // the full-limit switch is on until then (routines plan, Task 12)
  workspace_internet: boolean; // Internet in the workspace (A4): off by default, only its owner's switch turns it on
  notify: boolean; // a browser notification when it replies or asks while Roost is hidden (S1.10)
  approval: BotApproval; // what it may just do, and what needs your OK (approval modes)
  voice: BotVoice; // how it sounds when a reply is read aloud (voice plan)
  roles: string[]; // always [] since roles stopped gating anything (S1); kept for one release
  created_at: string;
  updated_at: string;
}

// Projects is first in the row (projects hub H14); the Board opens on Tasks (lead task 04).
export type BoardTab = "tasks" | "money" | "notes" | "documents";

// A "Start from" template (S1.7): it only fills the New bot form.
export interface TemplateOut {
  id: string;
  label: string;
  name: string;
  job: string;
  instructions: string;
  avatar: AvatarOut;
}

// What "From a file" puts in the form, once the server has checked the file.
export interface TemplateFormOut {
  name: string;
  job: string;
  instructions: string;
  avatar: AvatarOut;
  skills?: TemplateSkillCheck[]; // Skills: the file's skills; `have` when you already have that name
}

export interface TemplateSkillCheck {
  name: string;
  use_when: string;
  body: string;
  have: boolean;
}

export interface ThreadOut {
  id: string;
  bot_id: string;
  title: string | null;
  kind: string;
  created_at: string;
  updated_at: string;
}

// A group chat (plan Task 6): 2–6 member bots and a coordinator who
// answers a post that mentions nobody. Its messages live in `thread_id`.
export interface RoomOut {
  id: string;
  name: string;
  coordinator_id: string | null;
  member_ids: string[];
  thread_id: string;
  created_at: string;
  updated_at: string;
}

export type MessageRole = "user" | "bot" | "activity" | "system";

export type MessageKind =
  | "text" | "handoff" | "suggestion" | "notice" | "dropped" | "interrupted" | "daily_limit" | "bot_created"
  | "stuck" | "card_answer" | "memory_note" | "memory_offer" | "model_suggestion" | "approval" | "approval_result" | "mac_activity" | "reaction"
  | "program_activity"
  | "routine" | "report" | "routine_note" | "routine_proposal" | "question_note" | "skill_proposal"
  | "instructions_proposal" | "instruction_change" | "fresh_start" | "task_cards" | "english_fix";

export interface MessageOut {
  id: string;
  thread_id: string;
  role: MessageRole;
  body: string;
  tainted: boolean;
  seq: number;
  created_at: string;
  kind: MessageKind;
  author_bot_id: string | null;
  // Replies: the message this one answers (same thread) and the server's quote of it; its web-content mark.
  reply_to?: string | null;
  reply_quote?: string | null;
  reply_tainted?: boolean;
  // Its pictures: yours, a video's frames, or the bot's screenshots (owner, 2026-11-05).
  media?: MediaOut[];
}

// One fix in an english_fix line: the words you said and the words that are right.
export interface EnglishFix {
  wrong: string;
  right: string;
}

// An english_fix line's body (roost/voice/correct.py; role "activity"): the server's corrected copy of a spoken
// message of yours, shown under that message. Never sent to a model, never read aloud, never a preview.
export interface EnglishFixBody {
  message_id: string; // your message it corrects
  said: string;
  corrected: string;
  fixes: EnglishFix[];
}

// A suggestion card's body (role "bot", kind "suggestion"): JSON written
// by the model, so lib/team.ts parseSuggestion checks every field.
export interface SuggestionCardData {
  name: string;
  job: string;
  avatar: AvatarOut;
}

// A "Created <name>" card's body (message kind "bot_created", S1.3).
export interface CreatedCardData {
  bot_id: string;
  name: string;
  job: string;
  instructions: string;
  avatar: AvatarOut;
  checked?: boolean;   // made after the chat read web content, once the create check (or your Yes) passed
}

// The stuck flow (Piece A): why a bot stopped, and where its card stands.
export type StuckReason = "challenge" | "login" | "code" | "refused" | "asked";
// "replied": you answered the card in the chat (your message, or a Reply on the card).
export type StuckState = "open" | "cleared" | "given_up" | "blocked" | "replied";

// A Stuck card (roost/stuck/models.py StuckCardOut): GET /api/stuck, every button's answer and
// the stuck_card frame. `host` is "" when the bot asked for help with no web address.
export interface StuckCardOut {
  id: string;
  bot_id: string;
  thread_id: string;
  reason: StuckReason;
  host: string;
  url: string;
  note: string;
  suggest_main_browser: boolean;
  tainted: boolean;
  main_opened: boolean;
  state: StuckState;
  created_at: string;
  closed_at: string | null;
  sign_in?: boolean; // a Sign-in card: a sign-in page on the bot's Linux computer (Take control · Later, Check again as a quiet text button)
  secret_field?: SecretFieldKind | null; // B3: the card shows a masked field for this kind
}

// B3: what a Sign-in card's masked field asks you to type (it goes straight into the box on the bot's computer).
export type SecretFieldKind = "password" | "code";

// A Stuck card's chat message body (message kind "stuck", roost/stuck/texts.py
// stuck_message_body): the card as it opened, plus the bot's line. Its live state is a StuckCardOut.
export interface StuckMessageData {
  card_id: string;
  bot_id: string;
  reason: StuckReason;
  host: string;
  url: string;
  note: string;
  suggest_main_browser: boolean;
  line: string;
  sign_in?: boolean;
  secret_field?: SecretFieldKind;
}

export interface StopResult {
  dropped: number;
  interrupted: number;
  done?: string[]; // steer: what the stopped run did ("Added a task")
}

export interface ExecResult {
  exit_code: number;
  stdout: string;
  stderr: string;
  timed_out: boolean;
  truncated: boolean;
}

export type ComputerKind = "linux" | "mac_brave";

export interface DeskStatusOut {
  browser: "running" | "stopped";
  workspace: "running" | "stopped" | "absent";
  computer?: ComputerKind;
}

// The user's notes (M2 D1/D4).
export interface NoteLinkOut {
  target: string; // the folded [[target]]
  title: string; // as written
  note_id: string | null; // null: no note has that title yet
}

export interface NoteSummaryOut {
  id: string;
  title: string;
  tags: string[];
  snippet: string;
  pinned: boolean;
  revision: number;
  created_at: string;
  updated_at: string;
  created_by_bot: string | null;
  tainted: boolean;
  project_id: string | null;
}

export interface NoteOut extends NoteSummaryOut {
  content: string;
  links: NoteLinkOut[];
}

// The user's documents (M2 D2/D4): one record per doc, sheet or PDF.
export type DocumentKind = "doc" | "sheet" | "pdf";

export interface DocumentOut {
  id: string;
  kind: DocumentKind;
  title: string;
  pages: number | null;
  revision: number;
  created_at: string;
  updated_at: string;
  created_by_bot: string | null;
  tainted: boolean;
  project_id: string | null;
}

export interface DocumentDetailOut extends DocumentOut {
  payload: Record<string, unknown> | null; // the Univer snapshot; null for a PDF
}

// Home's chat list (S1.4): one row per bot and per room, newest first.
export interface ChatRowOut {
  kind: "bot" | "room";
  id: string;
  name: string;
  thread_id: string | null;
  preview: string | null;
  preview_kind: "text" | "handoff" | "card" | "notice" | null;
  from_you: boolean;
  last_at: string;
  tainted: boolean;
}

// A link seen in this bot's chats (S1.9). Roost never fetches it.
export interface LinkOut { url: string; host: string; message_id: string; thread_id: string; created_at: string }

// What a bot added to the user's shared records ("Made by <bot>", D1).
export interface MadeOut { tasks: TaskOut[]; expenses: ExpenseOut[]; notes: NoteSummaryOut[]; documents: DocumentOut[] }

// Who holds the bot's computer (S1.8): `since` is the UTC ISO time the hold began.
export interface ControlOut { held: boolean; since: string | null }

// Vault: site logins (roost/vault/models.py): the account you said a bot is signed in with, for one site.
// `kept` false: "No, this time" — Roost signs the computer out of the site after the task.
export interface SiteLoginOut { id: string; bot_id: string; host: string; label: string; updated_at: string; kept?: boolean }

// Install an app (roost/apps/models.py BotAppOut): one package the owner said Yes to.
export interface BotAppOut { id: string; package: string; installed_at: string }

export interface CurrentUser {
  id: string;
  username: string;
  // The account's IANA time zone (GET /api/auth/me); null until one is saved, absent where a route leaves it out.
  timezone?: string | null;
}

// ---------------------------------------------------------------------------
// WS frames (roost/events/hub.py)
// ---------------------------------------------------------------------------

export interface SnapshotFrame {
  type: "snapshot";
  cursor: number;
  bots: BotOut[];
  // The computer card: each working bot's current run's steps (live only on the server, so a reload gets them here).
  computer_steps?: Record<string, ComputerStepOut[]>;
  // The activity pill: each working bot's current run's steps in plain words (live only on the server too).
  run_steps?: Record<string, RunStepOut[]>;
}

export type ComputerStepKind = "look" | "wait" | "scroll" | "click" | "type" | "key" | "open_page" | "open_app" | "tab";

// The computer card (docs/plans/2026-10-23-roost-computer-card.md): one screen step of a bot's run, in words.
// Never typed text (a line says how many characters), never a picture; the host name alone, or null off the web.
export interface ComputerStepOut {
  bot_id: string;
  thread_id: string | null;
  run_id: string;
  step: number;
  kind: ComputerStepKind;
  line: string;
  host: string | null;
  at: string;
}

export interface ComputerStepFrame extends ComputerStepOut {
  type: "computer_step";
  seq: number;
}

export type RunStepKind =
  | "think" | "search" | "read" | "computer" | "program" | "file" | "tasks" | "notes" | "money" | "calendar"
  | "bots" | "memory" | "message" | "other"
  | "note"; // the bot's own words between steps (owner, 2026-11-04), never a tool step

// The activity pill (docs/plans/2026-10-23-roost-activity-pill.md): one step of a bot's run in plain words, never
// code. A step starts and then ends (done or failed) under the same number.
export interface RunStepOut {
  bot_id: string;
  thread_id: string | null;
  run_id: string;
  step: number;
  kind: RunStepKind;
  line: string;
  host: string | null;
  at: string;
  state: "start" | "done" | "failed";
  tainted?: boolean; // a note only: the run had read outside content when the bot wrote it (the Web mark)
}

export interface RunStepFrame extends RunStepOut {
  type: "run_step";
  seq: number;
}

export interface BotStatusFrame {
  type: "bot_status";
  seq: number;
  bot_id: string;
  status: BotStatus;
  activity: string | null;
}

export interface MessageFrame {
  type: "message";
  seq: number;
  thread_id: string;
  message: MessageOut;
}

export interface TextDeltaFrame {
  type: "text_delta";
  seq: number;
  thread_id: string;
  message_id: string;
  delta: string;
}

export interface MessageDoneFrame {
  type: "message_done";
  seq: number;
  thread_id: string;
  message_id: string;
}

// Call mode (contract B): one more part of a reply's speech can be fetched from live-speech; `done` once the last is.
export interface SpeechReadyFrame {
  type: "speech_ready";
  seq: number;
  thread_id: string;
  message_id: string;
  part: number;
  done: boolean;
}

export interface BotRemovedFrame {
  type: "bot_removed";
  seq: number;
  bot_id: string;
}

export interface BotUpdatedFrame {
  type: "bot_updated";
  seq: number;
  bot: BotOut;
}

// The Board's reload signals (M1 D8): additive, an old client ignores them.
export interface TasksChangedFrame {
  type: "tasks_changed";
  seq: number;
  change: "created" | "updated" | "completed" | "deleted" | "failed" | "commented";
  task_id: string;
}

// A day note was added or deleted (Board G11); it carries only the id and the day.
export interface DayNotesChangedFrame {
  type: "day_notes_changed";
  seq: number;
  change: "created" | "deleted";
  id: string;
  day: string;
}

export interface MoneyChangedFrame {
  type: "money_changed";
  seq: number;
  change:
    | "expense_created" | "expense_updated" | "expense_deleted" | "budget_set"
    // Projects and their top-ups ride on money_changed too (H10); `id` is the project's or the top-up's.
    | "project_created" | "project_updated" | "project_deleted" | "topup_added" | "topup_edited" | "topup_undone";
  id: string;
}

export interface NotesChangedFrame {
  type: "notes_changed";
  seq: number;
  change: "created" | "updated" | "deleted";
  note_id: string;
}

export interface DocumentsChangedFrame {
  type: "documents_changed";
  seq: number;
  change: "created" | "updated" | "deleted";
  document_id: string;
  kind: DocumentKind;
}

// What I remember (memory plan): its shapes live in memoryTypes.ts, re-exported here.
export type {
  MemoriesChangedFrame, MemoryIn, MemoryKind, MemoryNoteBody, MemoryOfferBody, MemoryOut, MemoryPatchIn, MemorySource,
  RememberedOffer,
} from "./memoryTypes";
// A Stuck card changed: it opened, was cleared, given up, blocked, or opened in the main Brave.
export interface StuckCardFrame {
  type: "stuck_card";
  seq: number;
  card: StuckCardOut;
}

// An approval card changed: it opened, or was answered, declined or replaced. Its diffs carry counts only (text
// is ""); GET /api/approvals/{id}?full=1 serves the text.
export interface ApprovalCardFrame {
  type: "approval_card";
  seq: number;
  card: ApprovalCardOut;
}

// Routines plan: a bot's routines, proposals, questions or Plan changed. The Plan frame carries the new revision.
export interface RoutinesChangedFrame { type: "routines_changed"; seq: number; bot_id: string }
export interface ProposalsChangedFrame { type: "proposals_changed"; seq: number; bot_id: string }
export interface QuestionsChangedFrame { type: "questions_changed"; seq: number; bot_id: string }
export interface PlanChangedFrame { type: "plan_changed"; seq: number; bot_id: string; revision: number }
// Skills: the user's skills (or one bot's switch) or the open skill proposals changed.
export interface SkillsChangedFrame { type: "skills_changed"; seq: number; bot_id?: string }
export interface SkillProposalsChangedFrame { type: "skill_proposals_changed"; seq: number; bot_id: string }
// Connectors: an Add a key card opened or was answered.
export interface ConnectorRequestsChangedFrame { type: "connector_requests_changed"; seq: number; bot_id: string }

// C3: where the bot just clicked, typed, pressed or scrolled on its computer, in screen pixels. Never any text.
export interface ComputerPointerFrame {
  type: "computer_pointer";
  seq: number;
  bot_id: string;
  x: number;
  y: number;
  kind: "click" | "type" | "key" | "scroll";
}

export type ServerFrame =
  | SnapshotFrame
  | BotStatusFrame
  | MessageFrame
  | TextDeltaFrame
  | MessageDoneFrame
  | SpeechReadyFrame
  | BotRemovedFrame
  | BotUpdatedFrame
  | TasksChangedFrame
  | MoneyChangedFrame
  | DayNotesChangedFrame
  | NotesChangedFrame
  | DocumentsChangedFrame
  | MemoriesChangedFrame
  | StuckCardFrame
  | ApprovalCardFrame
  | RoutinesChangedFrame
  | ProposalsChangedFrame
  | QuestionsChangedFrame
  | PlanChangedFrame
  | ComputerPointerFrame
  | ComputerStepFrame
  | RunStepFrame
  | SkillsChangedFrame
  | SkillProposalsChangedFrame
  | InstructionProposalsChangedFrame
  | ConnectorRequestsChangedFrame;

export interface ResumeFrame {
  type: "resume";
  cursor: number;
}
