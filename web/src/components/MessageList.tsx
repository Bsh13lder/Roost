import { useEffect, useMemo, useRef } from "react";
import { Avatar } from "./Avatar";
import { MessageRow } from "./MessageRow";
import type { ApprovalCardOut, AvatarOut, BotOut, MessageOut, StuckCardOut } from "../api/types";
import { chatMarks, firstUnreadId } from "../lib/chatMarks";
import { pairCardAnswers } from "../lib/approvals";
import { useHiddenAnswers } from "../hooks/useAnsweredCards";
import { foldReactions, isReactionMessage } from "../lib/reactions";
import type { ReactionKey } from "./chat/constants";
import { ComputerCard, type ComputerCardProps } from "./chat/ComputerCard";
import { isLiveRun, placeRuns, type ComputerRun, type ComputerRuns } from "../store/computerRuns";
import { isLiveActivity, type ActivityRun, type ActivityRuns } from "../store/activityRuns";
import { ActivityPill, type ActivityPillProps } from "./chat/ActivityPill";
import { EnglishFixRow } from "./chat/EnglishFixRow";
import { placeEnglishFixes } from "../lib/englishFix";

export interface MessageListProps {
  messages: MessageOut[];
  streaming?: Record<string, string>;
  botName: string;
  botAvatar?: AvatarOut;
  // The whole team, so a bot message is named and drawn by its own
  // author (author_bot_id) and a suggestion card knows who already exists.
  team?: readonly BotOut[];
  // Chat passes the Stuck cards it knows (GET /api/stuck merged with live frames), by card id.
  stuck?: Readonly<Record<string, StuckCardOut>>;
  // Chat passes the Ask and Proposal cards it knows (GET /api/approvals merged with live frames), by card id.
  approvals?: Readonly<Record<string, ApprovalCardOut>>;
  // Rooms pass this so each bot message offers Reply; Chat does not.
  onReply?: (author: BotOut) => void;
  // What each reply's bot did while writing it, by message id (store/live.ts toolLines, redesign P2).
  toolLines?: Readonly<Record<string, readonly string[]>>;
  // The newest time you had seen in this chat when you opened it: a New line goes above the first reply after it.
  newAfter?: string | null;
  // Ids of your messages that wait for a busy bot (lib/queued.ts stillQueued).
  queued?: ReadonlySet<string>;
  // The bot's current activity line, for a reply with no words yet.
  activity?: string | null;
  // Chats pass this so a message offers tapbacks; rooms do not.
  onReact?: (messageId: string, key: ReactionKey | null) => void;
  onQuote?: (message: MessageOut) => void; // chats only: Reply on a message (replies track)
  // The computer card: every run's screen steps (store/live.ts computerRuns); chats pass it.
  computerRuns?: ComputerRuns;
  // The activity pill: every run's steps in plain words (store/live.ts activityRuns); chats pass it. A chat that
  // has it draws no raw step lines and no program rows: those live in the pill's sheet.
  activityRuns?: ActivityRuns;
}

const NO_TEAM: readonly BotOut[] = [];
const NO_QUEUED: ReadonlySet<string> = new Set();
const NO_LINES: Readonly<Record<string, readonly string[]>> = {};
const NO_RUNS: ComputerRuns = {};
const NO_ACTIVITY: ActivityRuns = {};
// Rows whose words are for the machine: in a chat with the pill they show only in its Technical details.
const TECHNICAL_KINDS = new Set(["program_activity"]);

// Messenger layout: the bot on the left (its small avatar on the first
// bubble of each run), you on the right, activity lines as quiet rows
// between them. The author is always in the markup for screen readers;
// visually it shows only where a new run starts — a new speaker, or a
// different bot speaking in the same role.
function isRunStart(messages: readonly MessageOut[], index: number): boolean {
  if (index === 0) return true;
  const previous = messages[index - 1];
  const current = messages[index];
  return previous.role !== current.role || previous.author_bot_id !== current.author_bot_id;
}

function EmptyThread({ botName, botAvatar }: { botName: string; botAvatar?: AvatarOut }) {
  return (
    <div className="message-list__empty">
      {botAvatar ? <Avatar avatar={botAvatar} status="resting" size={72} label={false} decorative /> : null}
      <p className="message-list__empty-title">Say hello to {botName}.</p>
      <p className="message-list__empty-hint">
        Ask a question or hand it a task. It works in its own browser and shows what it&rsquo;s doing as it
        goes.
      </p>
    </div>
  );
}

export function MessageList({ messages: everything, ...rest }: MessageListProps) {
  // Tapbacks are stored as messages but drawn under their target, never as rows of their own.
  const withAnswers = useMemo(() => everything.filter((m) => !isReactionMessage(m)), [everything]);
  const reactions = useMemo(() => foldReactions(everything), [everything]);
  // Only a chat pairs cards with answer lines: it has one bot, so one open card at a time (a room has several).
  const answers = useMemo(() => (rest.approvals ? pairCardAnswers(withAnswers) : undefined), [rest.approvals, withAnswers]);
  // Your answer bubble is not drawn under an options card that already shows it.
  const hidden = useHiddenAnswers(withAnswers, rest.approvals);
  const plain = rest.activityRuns !== undefined;
  const shown = useMemo(
    () => withAnswers.filter((m) => !hidden.has(m.id) && !(plain && TECHNICAL_KINDS.has(m.kind ?? "text"))),
    [withAnswers, hidden, plain],
  );
  // Correct my English: an english_fix line is drawn right under the message of yours it names.
  const placed = useMemo(() => placeEnglishFixes(shown), [shown]);
  return <Rows messages={placed.rows} fixes={placed.under} reactions={reactions} answers={answers} {...rest} />;
}

const NO_FIXES: ReadonlyMap<string, readonly MessageOut[]> = new Map();

function Rows({
  messages, reactions, streaming = {}, botName, botAvatar, team = NO_TEAM, stuck, approvals, onReply, toolLines = NO_LINES, newAfter = null,
  queued = NO_QUEUED, activity = null, onReact, onQuote, answers, computerRuns = NO_RUNS, activityRuns = NO_ACTIVITY, fixes = NO_FIXES,
}: Omit<MessageListProps, "messages"> & {
  messages: readonly MessageOut[]; reactions: ReadonlyMap<string, ReactionKey>; answers?: ReadonlyMap<string, string>;
  fixes?: ReadonlyMap<string, readonly MessageOut[]>;
}) {
  const endRef = useRef<HTMLDivElement>(null);
  const threadId = messages[0]?.thread_id ?? "";
  // A computer run with a pill of the same run is drawn inside that pill, never on its own.
  const loneCards = useMemo(
    () => Object.fromEntries(Object.entries(computerRuns).filter(([runId]) => !(runId in activityRuns))),
    [computerRuns, activityRuns],
  );
  const runs = useMemo(() => placeRuns(loneCards, threadId, messages), [loneCards, threadId, messages]);
  const pills = useMemo(() => placeRuns(activityRuns, threadId, messages), [activityRuns, threadId, messages]);
  const botOf = (botId: string) => team.find((bot) => bot.id === botId);
  // Every computer run, the newest too, folds to its line when it ends: the screen lives on the Computer tab.
  const cardFor = (run: ComputerRun | undefined) => run ? {
    run, bot: botOf(run.botId), live: isLiveRun(computerRuns, run, botOf(run.botId)),
  } : undefined;
  // A run is over once its reply has settled (or its empty reply went away when it parked on a card): the bot's
  // next run must not wake the old pill up before its own first step arrives.
  const openReplies = useMemo(() => new Set(messages.filter((m) => m.seq === 0).map((m) => m.id)), [messages]);
  const pillFor = (run: ActivityRun | undefined): ActivityPillProps | undefined => {
    if (!run) return undefined;
    const bot = botOf(run.botId);
    const card = computerRuns[run.runId];
    const replyOpen = run.anchorId === null || openReplies.has(run.anchorId);
    return {
      run, bot, live: replyOpen && isLiveActivity(activityRuns, run, bot),
      computer: card ? { run: card, live: isLiveRun(computerRuns, card, bot) } : undefined,
    };
  };
  // A run whose reply is gone (it parked on a card) or unknown (a reload mid-run) gets a row of its own.
  const runRow = (run: ComputerRun) => (
    <li key={run.runId} className="message message--bot message--computer">
      <span className="message__avatar" />
      <div className="message__content"><ComputerCard {...(cardFor(run) as ComputerCardProps)} /></div>
    </li>
  );
  const pillRow = (run: ActivityRun) => (
    <li key={`pill-${run.runId}`} className="message message--bot message--computer">
      <span className="message__avatar" />
      <div className="message__content"><ActivityPill {...(pillFor(run) as ActivityPillProps)} /></div>
    </li>
  );
  const unreadId = firstUnreadId(messages, newAfter);
  const streamedLength = Object.values(streaming).reduce((total, text) => total + text.length, 0);
  const stepCount = Object.values(toolLines).reduce((total, lines) => total + lines.length, 0);
  const pillSteps = Object.values(activityRuns).reduce((total, run) => total + run.steps.length, 0);
  // Keep the newest message in view as messages arrive, replies stream in and steps are added.
  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "end" });
  }, [messages.length, streamedLength, stepCount, runs.inRow.size, runs.before.size, runs.end.length, pillSteps]);

  if (messages.length === 0) return <EmptyThread botName={botName} botAvatar={botAvatar} />;

  return (
    <>
      <ul className="message-list" aria-label="Messages">
        {chatMarks(messages, newAfter).map((item) => {
          if (item.kind === "day") {
            return <li key={item.id} className="message-date" role="separator" aria-label={item.label}>{item.label}</li>;
          }
          if (item.kind === "new") {
            return <li key={item.id} className="message-new" role="separator" aria-label="New messages">New</li>;
          }
          return [
            ...(pills.before.get(item.message.id) ?? []).map(pillRow),
            ...(runs.before.get(item.message.id) ?? []).map(runRow),
            <MessageRow
              key={item.message.id}
              message={item.message}
              runStart={item.dayStart || item.message.id === unreadId || isRunStart(messages, item.index)}
              liveText={streaming[item.message.id]}
              toolLines={toolLines[item.message.id]}
              activity={activity}
              queued={queued.has(item.message.id)}
              fallbackName={botName}
              fallbackAvatar={botAvatar}
              team={team}
              stuck={stuck}
              approvals={approvals}
              answers={answers}
              onReply={onReply}
              reaction={reactions.get(item.message.id)}
              onReact={onReact}
              onQuote={onQuote}
              computer={cardFor(runs.inRow.get(item.message.id))}
              pill={pillFor(pills.inRow.get(item.message.id))}
            />,
            ...(fixes.get(item.message.id) ?? []).map((fix) => <EnglishFixRow key={fix.id} message={fix} />),
          ];
        })}
        {pills.end.map(pillRow)}
        {runs.end.map(runRow)}
      </ul>
      <div ref={endRef} className="message-list__end" />
    </>
  );
}
