// One row of a conversation: a message (you on the right in an accent bubble, a bot on the left, a long
// reply as a full-width card), a quiet line (activity, a handoff between bots, a notice), a suggestion
// card, a "Created <name>" card or a Stuck card. Split out of MessageList so the list stays a loop.
import { Suspense, lazy } from "react";
import { Avatar } from "./Avatar";
import { CreatedBotCard } from "./CreatedBotCard";
import { StuckCard } from "./StuckCard";
import { SuggestionCard } from "./SuggestionCard";
import { ModelSuggestionCard } from "./ModelSuggestionCard";
import { ApprovalMessage } from "./approvals/ApprovalMessage";
import { InstructionChangeRow } from "./chat/InstructionChangeRow";
import { MacActivityRow } from "./chat/MacActivityRow";
import { ProgramActivityRow } from "./chat/ProgramActivityRow";
import { MemoryNoteRow } from "./chat/MemoryNoteRow";
import { EnglishFixRow } from "./chat/EnglishFixRow";
import { MemoryOfferRow } from "./chat/MemoryOfferRow";
import { ReportMessage } from "./chat/ReportMessage";
import { ProjectText } from "./chat/ProjectText";
import { TaskCards } from "./chat/TaskCards";
import { WebMark } from "./chat/WebMark";
import { RoutineNoteLine } from "./chat/RoutineNoteLine";
import { ReplyQuote } from "./chat/ReplyQuote";
import { MessageActions } from "./chat/MessageActions";
import { PlainText } from "./chat/PlainText";
import { RichText } from "./chat/RichText";
import { MessageMedia } from "./chat/MessageMedia";
import { ReactionChip } from "./chat/Reactions";
import type { ReactionKey } from "./chat/constants";
import { ToolLines } from "./chat/ToolLines";
import { ComputerCard, type ComputerCardProps } from "./chat/ComputerCard";
import { ActivityPill, type ActivityPillProps } from "./chat/ActivityPill";
import { FirstLine } from "./chat/FirstLine";
import { shownReply, splitOnItLead } from "../lib/onItLead";
import { QueuedMark } from "./chat/QueuedMark";
import { isLongReply } from "./chat/replyShape";
import { canReplyTo } from "../lib/replies";
import { cx } from "../ui/cx";
import { parseProposalMessage, parseReport } from "../lib/routineMessages";
import { parseKeyRequestMessage } from "../lib/keyRequests";
import { parseStuckMessage } from "../lib/stuck";
import { parseModelSuggestion } from "../lib/models";
import { parseCreatedCard, parseSuggestion } from "../lib/team";
import type { ApprovalCardOut, AvatarOut, BotOut, MessageOut, StuckCardOut } from "../api/types";

export interface MessageRowProps {
  message: MessageOut;
  runStart: boolean;
  liveText?: string;
  fallbackName: string;
  fallbackAvatar?: AvatarOut;
  team: readonly BotOut[];
  // Every Stuck card this page knows, by card id: a "stuck" message folds once its card is closed.
  stuck?: Readonly<Record<string, StuckCardOut>>;
  // Every Ask and Proposal card this page knows, by card id: an "approval" message shows its card from here.
  approvals?: Readonly<Record<string, ApprovalCardOut>>;
  // Each card's answer line in this chat, by card id (lib/approvals.ts pairCardAnswers): an answered options card
  // shrinks to it.
  answers?: ReadonlyMap<string, string>;
  // Rooms only: a bot's text message gets a Reply that addresses its author.
  onReply?: (author: BotOut) => void;
  // What the bot did while writing this reply (store/live.ts toolLines), oldest first.
  toolLines?: readonly string[];
  // The computer card of the run that wrote this reply, if it used its computer (store/computerRuns.ts).
  computer?: ComputerCardProps;
  // The activity pill of the run that wrote this reply (store/activityRuns.ts): it takes the place of the raw step
  // lines, the waiting dots and a lone computer card.
  pill?: ActivityPillProps;
  // The bot's current activity line, for the words a reply with no text yet shows (FirstLine).
  activity?: string | null;
  // Your own message that waits for a busy bot.
  queued?: boolean;
  // This message's tapback (lib/reactions.ts foldReactions), and what picking one does (chats only).
  reaction?: ReactionKey;
  onReact?: (messageId: string, key: ReactionKey | null) => void;
  // Chats only: Reply on a message puts its quote over the composer (replies track).
  onQuote?: (message: MessageOut) => void;
}

// The routine proposal card is its own chunk (the routines plan keeps the entry bundle in budget).
const RoutineAskCard = lazy(() => import("./chat/RoutineAskCard").then((module) => ({ default: module.RoutineAskCard })));
// Skills: the skill proposal card is its own chunk too.
const SkillAskCard = lazy(() => import("./skills/SkillAskCard"));
// Replies track: the "Update my instructions?" card too.
const InstructionsAskCard = lazy(() => import("./chat/InstructionsAskCard"));
const ConnectorAskCard = lazy(() => import("./connectors/ConnectorAskCard"));

const NO_LINES: readonly string[] = [];

// When a placeholder bubble began (its server-made time), so a re-render never restarts FirstLine's wait.
function startedAt(message: MessageOut): number {
  const made = Date.parse(message.created_at);
  return Number.isNaN(made) ? Date.now() : made;
}

function authorOf(message: MessageOut, team: readonly BotOut[]): BotOut | undefined {
  return message.author_bot_id ? team.find((bot) => bot.id === message.author_bot_id) : undefined;
}

// Handoff lines, activity lines and notices: one quiet row, no bubble.
function QuietRow({ message, kind }: { message: MessageOut; kind: string }) {
  if (kind === "handoff") {
    return (
      <li className="message message--activity message--handoff">
        <span className="message__handoff-arrow" aria-hidden="true">
          ⇄
        </span>
        <span className="message__handoff-text">{message.body}</span>
      </li>
    );
  }
  if (message.role === "activity") {
    return (
      <li className="message message--activity">
        <span className="message__activity-text">{message.body}</span>
      </li>
    );
  }
  return <li className={`message message--notice message--notice-${kind}`}>{message.body}</li>;
}

const NO_STUCK: Readonly<Record<string, StuckCardOut>> = {};
const NO_APPROVALS: Readonly<Record<string, ApprovalCardOut>> = {};

interface RowBodyProps {
  message: MessageOut;
  kind: string;
  text: string;
  streaming: boolean;
  name: string;
  team: readonly BotOut[];
  stuck: Readonly<Record<string, StuckCardOut>>;
  approvals: Readonly<Record<string, ApprovalCardOut>>;
  answers?: ReadonlyMap<string, string>;
  onQuote?: (message: MessageOut) => void;
}

// A card when the body is a valid one for its kind; otherwise the text: a bot's reply as markdown, anything
// else as written, its links drawn safely either way.
function RowBody({ message, kind, text, streaming, name, team, stuck, approvals, answers, onQuote }: RowBodyProps) {
  if (kind === "approval") return <ApprovalMessage body={message.body} cards={approvals} answers={answers} />;
  const created = kind === "bot_created" ? parseCreatedCard(message.body) : null;
  if (created) return <CreatedBotCard card={created} team={team} />;
  const suggestion = kind === "suggestion" ? parseSuggestion(message.body) : null;
  if (suggestion) return <SuggestionCard suggestion={suggestion} team={team} tainted={message.tainted} />;
  const modelCard = kind === "model_suggestion" ? parseModelSuggestion(message.body) : null;
  if (modelCard) return <ModelSuggestionCard messageId={message.id} suggestion={modelCard} tainted={message.tainted} />;
  const blocked = kind === "stuck" ? parseStuckMessage(message.body) : null;
  if (blocked) {
    return (
      <StuckCard data={blocked} card={stuck[blocked.card_id]} botName={name} tainted={message.tainted}
        bot={team.find((member) => member.id === blocked.bot_id)}
        onReply={onQuote && message.seq > 0 ? () => onQuote(message) : undefined} />
    );
  }
  const reportCard = kind === "report" && parseReport(message.body) ? <ReportMessage message={message} /> : null;
  if (reportCard) return reportCard;
  const proposalId = kind === "routine_proposal" ? parseProposalMessage(message.body) : null;
  if (proposalId) return <Suspense fallback={null}><RoutineAskCard proposalId={proposalId} /></Suspense>;
  const skillProposalId = kind === "skill_proposal" ? parseProposalMessage(message.body) : null;
  if (skillProposalId) return <Suspense fallback={null}><SkillAskCard proposalId={skillProposalId} /></Suspense>;
  const instructionsId = kind === "instructions_proposal" ? parseProposalMessage(message.body) : null;
  if (instructionsId) return <Suspense fallback={null}><InstructionsAskCard proposalId={instructionsId} /></Suspense>;
  const keyRequestId = kind === "connector_request" ? parseKeyRequestMessage(message.body) : null;
  if (keyRequestId) return <Suspense fallback={null}><ConnectorAskCard requestId={keyRequestId} /></Suspense>;
  const rich = message.role === "bot" && kind === "text";
  // While the text streams in, a caret follows it (styles/chat-steps.css).
  return (
    <div className={cx("message__body", streaming && "message__body--streaming")} aria-busy={streaming || undefined}>
      {rich ? <RichText text={text} id={message.id} />
        : message.role === "user" && kind === "text" ? <ProjectText text={text} keyPrefix={message.id} />
          : <PlainText text={text} keyPrefix={message.id} />}
    </div>
  );
}

// A Report's hover actions: its time, Copy (its words, never its JSON) and the speaker.
function ReportMeta({ message }: { message: MessageOut }) {
  const report = parseReport(message.body);
  if (!report) return null;
  return (
    <MessageActions text={report.text || report.headline} createdAt={message.created_at}
      speak={{ threadId: message.thread_id, messageId: message.id }} />
  );
}

// Under a settled text message: the web mark (always shown on web-made text) and its hover actions; a bot's reply
// also gets the speaker (voice).
function MessageMeta({ message, isUser, reaction, onReact, onQuote }: {
  message: MessageOut; isUser: boolean; reaction?: ReactionKey; onReact?: (messageId: string, key: ReactionKey | null) => void;
  onQuote?: (message: MessageOut) => void;
}) {
  const botText = !isUser && message.role === "bot" && (message.kind ?? "text") === "text";
  return (
    <>
      {message.tainted && !isUser ? <WebMark className="message__taint" /> : null}
      {reaction ? <ReactionChip reaction={reaction} /> : null}
      <MessageActions text={!isUser && (message.kind ?? "text") === "text" ? shownReply(message.body) : message.body} createdAt={message.created_at} reaction={reaction}
        onReact={onReact ? (key) => onReact(message.id, key) : undefined}
        onQuote={onQuote && canReplyTo(message) ? () => onQuote(message) : undefined}
        speak={botText ? { threadId: message.thread_id, messageId: message.id } : undefined} />
    </>
  );
}

export function MessageRow({
  message, runStart, liveText, fallbackName, fallbackAvatar, team, stuck = NO_STUCK, approvals = NO_APPROVALS, answers, onReply,
  toolLines = NO_LINES, activity = null, queued = false, reaction, onReact, onQuote, computer, pill,
}: MessageRowProps) {
  const kind = message.kind ?? "text";
  // The outcome of an approved step reaches the model only (a "system" message, never published): no row.
  if (kind === "approval_result" || kind === "reaction") return null;
  if (kind === "task_cards") return <TaskCards message={message} />;
  if (kind === "memory_note") return <MemoryNoteRow message={message} />;
  if (kind === "english_fix") return <EnglishFixRow message={message} />;
  if (kind === "memory_offer") return <MemoryOfferRow message={message} />;
  if (kind === "mac_activity") return <MacActivityRow message={message} />;
  if (kind === "program_activity") return <ProgramActivityRow message={message} />;
  if (kind === "instruction_change") return <InstructionChangeRow message={message} />;
  if (kind === "routine_note" || kind === "question_note") return <RoutineNoteLine message={message} />;
  if (kind === "handoff" || message.role === "activity" || message.role === "system") {
    return <QuietRow message={message} kind={kind} />;
  }
  const isUser = message.role === "user";
  const author = authorOf(message, team);
  const name = isUser ? "You" : author?.name ?? fallbackName;
  const avatar = author?.avatar ?? fallbackAvatar;
  const raw = liveText ?? message.body;
  // A reply still being written (seq 0): its robot at work until the answer's first words, then a caret.
  const writing = !isUser && message.seq === 0;
  const botText = !isUser && kind === "text";
  const lead = botText ? splitOnItLead(raw) : { lead: null, rest: raw };
  const typing = writing && !(lead.lead !== null ? lead.rest : raw);
  const text = botText ? shownReply(raw) : raw;
  const doing = typing && lead.lead ? lead.lead : activity;
  const settled = !writing && (kind === "text" || kind === "card_answer");
  const card = !isUser && kind === "text" && isLongReply(text);
  // A working bot's robot sits in its working line (FirstLine, the activity pill), so the side avatar steps aside.
  const working = typing || Boolean(pill?.live);
  return (
    <li className={cx("message", isUser ? "message--user" : "message--bot", runStart && "message--run-start", card && "message--card")}
      data-message-id={message.id}>
      {!isUser && avatar ? (
        <span className="message__avatar">
          {(runStart || typing) && !working ? (
            <Avatar avatar={avatar} status={typing ? "on_it" : "resting"} size={32} label={false} decorative botId={author?.id} />
          ) : null}
        </span>
      ) : null}
      <div className="message__content">
        <div className={`message__author${runStart && !isUser ? "" : " sr-only"}`}>{name}</div>
        {message.reply_quote ? <ReplyQuote quote={message.reply_quote} tainted={message.reply_tainted} /> : null}
        {pill ? <ActivityPill {...pill} technical={toolLines} /> : null}
        {!pill && toolLines.length > 0 ? <ToolLines lines={toolLines} working={writing} textLength={text.length} /> : null}
        {!pill && computer ? <ComputerCard {...computer} /> : null}
        {message.media && message.media.length > 0 ? <MessageMedia media={message.media} /> : null}
        {typing && pill ? null : typing ? <FirstLine text="" name={name} activity={doing} since={startedAt(message)} avatar={avatar} /> : (
          <RowBody message={message} kind={kind} text={text} streaming={writing} name={name} team={team} stuck={stuck} approvals={approvals} answers={answers} onQuote={onQuote} />
        )}
        {settled ? <MessageMeta message={message} isUser={isUser} reaction={reaction} onReact={onReact} onQuote={onQuote} /> : null}
        {kind === "report" && !isUser && !writing ? <ReportMeta message={message} /> : null}
        {queued && isUser ? <QueuedMark /> : null}
        {onReply && author && kind === "text" && !isUser ? (
          <button type="button" className="message__reply" aria-label={`Reply to ${author.name}`} onClick={() => onReply(author)}>
            Reply
          </button>
        ) : null}
      </div>
    </li>
  );
}
