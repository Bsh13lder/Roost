import { chatAccentStyle } from "../lib/chatAccent";
import { Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState, type ReactNode, type RefObject } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { LazyBotPanel, preloadBotPanel } from "../components/panel/lazyBotPanel";
import { usePanelParam } from "../hooks/usePanelParam";
import { Avatar } from "../components/Avatar";
import { BotMenu } from "../components/BotMenu";
import { Composer, type SendMeta } from "../components/Composer";
import type { MentionOption } from "../lib/mentions";
import { ErrorNotice } from "../components/ErrorNotice";
import { BackIcon } from "../components/icons";
import { MessageList } from "../components/MessageList";
import { ReplyChip } from "../components/chat/ReplyQuote";
import { preloadMarkdown } from "../components/chat/RichText";
import { StopButton } from "../components/chat/StopButton";
import { StatusLabel } from "../components/StatusLabel";
import { ThreadsSheet } from "../components/ThreadsSheet";
import { ShareTemplateDialog } from "../components/ShareTemplateDialog";
import { FindBar, findInChat } from "../components/chat/FindBar";
import { ComposerPlus } from "../components/chat/ComposerPlus";
import { MediaTray } from "../components/chat/MediaTray";
import { useMediaTray, type MediaTray as Tray } from "../components/chat/useMediaTray";
import type { MediaOut } from "../api/media";
import { ChatModePill } from "../components/chat/ChatModePill";
import { ChatContext, type ChatShared } from "../components/chat/chatContext";
import { useProjects } from "../components/tasks/useProjects";
import { useOpenTask } from "../components/tasks/useOpenTask";
import { useLiveState } from "../hooks/useLiveStore";
import { useKeepBottom } from "../hooks/useKeepBottom";
import { useSeenAtOpen } from "../hooks/useSeenAtOpen";
import { useReadAloud } from "../hooks/useReadAloud";
import * as botsApi from "../api/bots";
import * as approvalsApi from "../api/approvals";
import * as stuckApi from "../api/stuck";
import * as threadsApi from "../api/threads";
import { describeError } from "../api/client";
import type { ApprovalCardOut, BotOut, MessageOut, StuckCardOut, ThreadOut } from "../api/types";
import { clearAttention } from "../lib/attention";
import { mergeMessages, nextLocalSeq } from "../lib/messages";
import { stillQueued } from "../lib/queued";
import { mergeApprovals } from "../lib/approvals";
import { mergeStuck } from "../lib/stuck";
import { wantsControl } from "../lib/wantsControl";
import { freshest } from "../lib/team";
import { announceThreadsChanged } from "../lib/threadsChanged";
import { quotePreview, quoteSource } from "../lib/replies";

function useChatData(botId: string | undefined, wantedThread: string | null) {
  const [bot, setBot] = useState<BotOut | null>(null);
  const [threads, setThreads] = useState<ThreadOut[]>([]);
  const [thread, setThread] = useState<ThreadOut | null>(null);
  const [main, setMain] = useState<ThreadOut | null>(null);
  const [messages, setMessages] = useState<MessageOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef(0); // a slower, older load (another bot, another thread) never wins
  const load = useCallback(() => {
    if (!botId) return;
    const ticket = ++latest.current;
    setError(null);
    (async () => {
      try {
        // The bot's one chat is `main`; the thread named in `?thread=` (an earlier conversation, a
        // handoff's thread) wins when it is one of the bot's.
        const [loadedBot, loaded, chat] = await Promise.all([
          botsApi.getBot(botId), threadsApi.listThreads(botId), threadsApi.openChat(botId),
        ]);
        const current = loaded.find((t) => t.id === wantedThread) ?? chat;
        const known = loaded.some((t) => t.id === chat.id);
        if (!known) announceThreadsChanged(botId);
        const shown = await threadsApi.listMessages(current.id);
        if (ticket !== latest.current) return;
        setBot(loadedBot);
        setThreads(known ? loaded : [...loaded, chat]);
        setMain(chat);
        setThread(current);
        setMessages(shown);
      } catch (err) {
        if (ticket === latest.current) setError(describeError(err));
      }
    })();
  }, [botId, wantedThread]);
  useEffect(() => load(), [load]);
  return { bot, setBot, threads, thread, main, messages, setMessages, error, load };
}

// Your open Stuck cards, loaded once. Live stuck_card frames keep them current (merged with
// mergeStuck). A failed load is said in the dock, and the cards then show only their line.
function useOpenStuck(onError: (message: string) => void): StuckCardOut[] {
  const [cards, setCards] = useState<StuckCardOut[]>([]);
  useEffect(() => {
    let cancelled = false;
    stuckApi.listStuck()
      .then((loaded) => { if (!cancelled) setCards(loaded); })
      .catch((err: unknown) => { if (!cancelled) onError(describeError(err)); });
    return () => { cancelled = true; };
  }, [onError]);
  return cards;
}

// Your open Ask and Proposal cards, loaded once; live approval_card frames keep them current.
function useOpenApprovals(onError: (message: string) => void): ApprovalCardOut[] {
  const [cards, setCards] = useState<ApprovalCardOut[]>([]);
  useEffect(() => {
    let cancelled = false;
    approvalsApi.listApprovals()
      .then((loaded) => { if (!cancelled) setCards(loaded); })
      .catch((err: unknown) => { if (!cancelled) onError(describeError(err)); });
    return () => { cancelled = true; };
  }, [onError]);
  return cards;
}

interface HeaderActions {
  onEarlier: () => void; onProfile: () => void; onFind: () => void; onShare: () => void; onFreshStart: () => void;
}

function ChatHeader({ bot, control, onChange, onError, actions, pillHref, open, pillRef }: {
  bot: BotOut; control: boolean; onChange: (bot: BotOut) => void; onError: (m: string | null) => void;
  actions: HeaderActions;
  pillHref: string; open: boolean; pillRef: RefObject<HTMLAnchorElement | null>;
}) {
  return (
    <header className="chat-header">
      <Link to="/" className="icon-btn" aria-label="Back to chats"><BackIcon /></Link>
      <Link to={pillHref} ref={pillRef} className="chat-header__pill" aria-expanded={open}
        onPointerEnter={preloadBotPanel} onFocus={preloadBotPanel}
        aria-label={`${open ? "Close" : "Open"} ${bot.name}'s profile`}>
        <Avatar avatar={bot.avatar} status={bot.status} size={32} label={false} decorative star={bot.is_primary} botId={bot.id}
          control={control} />
        <div className="chat-header__text">
          <h1 className="chat-header__name">{bot.name}</h1>
          <StatusLabel status={bot.status} activity={bot.activity} />
        </div>
      </Link>
      <BotMenu bot={bot} onChange={onChange} onError={onError} {...actions} />
    </header>
  );
}

// The dock: any inline notice, then the pill input alone (Earlier conversations is in the header's ⋯ menu, lead
// task 06). An earlier conversation is read-only: a quiet line and the way back to the chat take the composer's place.
// A task card's title opens the same drawer as the Board's (?task=<id>), its own lazy chunk.
const TaskDrawer = lazy(() => import("../components/tasks/TaskDrawer"));
// A call (call mode) is its own lazy chunk too: the screen, the call's ear and its turn logic.
const CallScreen = lazy(() => import("../components/call/CallScreen"));

function ChatDock({ name, botId, voiceCorrect, notice, readOnly, onIt, onSend, onError, mentions, projects, replyTo, onCancelReply, added, onAdded, modePill, onCall, tray }: {
  name: string; botId: string; notice: string | null; readOnly: boolean; onIt: boolean;
  voiceCorrect: boolean; // the bot's Correct what I say switch: the composer checks a dictation before you send
  tray: Tray; // pictures and a video's frames waiting to go with your next message
  onCall?: () => void; // call mode: the empty composer's round button calls the bot
  modePill?: ReactNode; // the chat mode pill, beside the + (a 1:1 chat with a bot on its Linux computer)
  added: string | null; onAdded: (title: string) => void;
  onSend: (text: string, meta: SendMeta) => Promise<void>; onError: (message: string) => void; mentions?: readonly MentionOption[];
  projects?: readonly MentionOption[];
  replyTo: MessageOut | null; onCancelReply: () => void;
}) {
  return (
    <div className="chat-page__dock">
      {notice ? <ErrorNotice message={notice} /> : null}
      {added ? <p className="chat-dock__added" role="status">Added &ldquo;{added}&rdquo; to your documents. Ask {name} to read it.</p> : null}
      {onIt && !readOnly ? <StopButton botId={botId} name={name} onError={onError} /> : null}
      {readOnly ? (
        <div className="chat-readonly">
          <p className="chat-readonly__text">An earlier conversation, read-only.</p>
          <Link to={`/bots/${botId}`} className="chat-readonly__back">Back to the chat</Link>
        </div>
      ) : (
        <div className="chat-composer">
          {replyTo ? <ReplyChip quote={quotePreview(quoteSource(replyTo))} onCancel={onCancelReply} /> : null}
          <MediaTray tray={tray} />
          <Composer onSend={onSend} placeholder={`Message ${name}`} mentions={mentions} projects={projects}
            voice={{ onError, botId, correct: voiceCorrect }} call={onCall && !onIt ? { name, onCall } : undefined}
            allowEmpty={tray.items.length > 0}
            leading={<><ComposerPlus onAdded={onAdded} onError={onError} onPictures={tray.addPictures}
              onVideo={(file) => void tray.addVideo(file)} />{modePill}</>} />
        </div>
      )}
    </div>
  );
}

// "@" in a bot's chat lists your other bots (the server hands the message to the ones you name).
function otherBots(team: readonly { id: string; name: string }[], botId: string): MentionOption[] {
  return team.filter((member) => member.id !== botId).map(({ id, name }) => ({ id, name }));
}

export function Chat() {
  const { botId } = useParams<{ botId: string }>();
  const [searchParams] = useSearchParams();
  const live = useLiveState();
  const data = useChatData(botId, searchParams.get("thread"));
  const [notice, setNotice] = useState<string | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [queuedIds, setQueuedIds] = useState<ReadonlySet<string>>(new Set());
  const [replyTo, setReplyTo] = useState<MessageOut | null>(null); // Reply: the message your next one answers
  const [find, setFind] = useState<string | null>(null); // Find in chat: null while the bar is closed
  const [sharing, setSharing] = useState(false);
  const [added, setAdded] = useState<string | null>(null); // the title of a PDF the composer's + just added
  const [calling, setCalling] = useState(false); // call mode: the call screen is open
  const tray = useMediaTray();
  const openStuck = useOpenStuck(setNotice);
  const openApprovals = useOpenApprovals(setNotice);
  const keepBottom = useKeepBottom();
  const panel = usePanelParam();
  const pillRef = useRef<HTMLAnchorElement>(null);
  const seenAtOpen = useSeenAtOpen(botId ?? "");
  // #project: your projects, for the composer's "#" list, the chips in your bubbles and a task card's project.
  const projectList = useProjects();
  const projects = useMemo(() => projectList.map(({ id, name }) => ({ id, name })), [projectList]);
  const task = useOpenTask();
  // Read replies aloud: a reply that arrives in this open chat plays by itself; not during a call, which speaks it.
  useReadAloud(data.thread?.id, data.thread ? live.messagesByThread[data.thread.id] : undefined, live.bots,
    botId ? live.bots[botId] ?? data.bot : null, calling);
  const shared = useMemo<ChatShared>(() => ({ projects, openTask: task.open }), [projects, task.open]);
  useEffect(() => { if (botId) clearAttention(botId); }, [botId, live.cursor]);
  // Fetch the markdown renderer while the thread loads, so its replies never flash as plain text first.
  useEffect(() => { void preloadMarkdown(); }, []);

  if (!botId) return null;
  if (data.error) return <ErrorNotice message={data.error} onRetry={data.load} />;
  if (!data.bot || data.bot.id !== botId || !data.thread || !data.main) return <p className="page-loading">Loading&hellip;</p>;
  const thread = data.thread;
  const main = data.main;
  const readOnly = thread.kind === "chat" && thread.id !== main.id;
  const bot = freshest(data.bot, live.bots[botId]);
  const all = mergeMessages(data.messages, live.messagesByThread[thread.id] ?? []);
  const stuck = mergeStuck(openStuck, live.stuckCards);
  const control = wantsControl(bot, stuck);
  const approvals = mergeApprovals(openApprovals, live.approvalCards);

  // Your message, sent; its id (a call waits for the reply after it, and marks its turns with `call`).
  const sendText = async (text: string, options: threadsApi.SendOptions = {}, media: MediaOut[] = []): Promise<string> => {
    setNotice(null);
    try {
      // The server's id, so the live echo of this same message dedupes against it. A message the bot's run
      // reads mid-work (status "steered") shows nothing special; only one that waits for a busy bot is Queued.
      const quoted = replyTo && replyTo.thread_id === thread.id ? replyTo : null;
      const { message_id, queued } = await threadsApi.sendMessage(thread.id, text, quoted?.id, options);
      if (queued) setQueuedIds((prev) => new Set([...prev, message_id]));
      setReplyTo(null);
      data.setMessages((prev) => [...prev, {
        id: message_id, thread_id: thread.id, role: "user", body: text, tainted: false,
        seq: nextLocalSeq(all), created_at: new Date().toISOString(), kind: "text", author_bot_id: null,
        reply_to: quoted?.id ?? null, reply_quote: quoted ? quotePreview(quoteSource(quoted)) : null,
        reply_tainted: quoted ? quoted.tainted && quoted.kind !== "stuck" : false, // a card's quote is fixed words
        ...(media.length > 0 ? { media } : {}),
      }]);
      return message_id;
    } catch (err) {
      setNotice(describeError(err));
      throw err; // Composer keeps the typed text
    }
  };
  // Pictures first: they upload, then your words go with them; a failed upload keeps both and says why.
  const onSend = async (text: string, meta: SendMeta) => {
    const options: threadsApi.SendOptions = meta.spoken
      ? { spoken: true, ...(meta.heard !== undefined ? { heard: meta.heard, fixes: meta.fixes ?? [] } : {}) }
      : {};
    if (tray.items.length === 0) { await sendText(text, options); return; }
    const media = await tray.upload(thread.id);
    if (!media) throw new Error("upload failed"); // the tray says why; the Composer keeps the words
    await sendText(text, { ...options, mediaIds: media.map((item) => item.id) }, media);
    tray.clear();
  };

  // A tapback: the server's stored row joins the list at once (its live echo dedupes by id).
  const onReact = async (messageId: string, key: string | null) => {
    setNotice(null);
    try {
      const stored = await threadsApi.reactTo(thread.id, messageId, key);
      data.setMessages((prev) => [...prev, stored]);
    } catch (err) {
      setNotice(describeError(err));
    }
  };

  const onFreshStart = async () => {
    try {
      const line = await threadsApi.freshStart(thread.id);
      data.setMessages((prev) => (prev.some((m) => m.id === line.id) ? prev : [...prev, line]));
    } catch (err) {
      setNotice(describeError(err));
    }
  };

  const closePanel = () => { panel.close(); pillRef.current?.focus(); };
  const actions: HeaderActions = {
    onEarlier: () => setSheetOpen(true), onProfile: () => panel.open("profile"), onFind: () => setFind(""),
    onShare: () => setSharing(true), onFreshStart: () => void onFreshStart(),
  };
  const shown = find === null ? all : findInChat(all, find);

  return (
    <ChatContext.Provider value={shared}>
    <div className={panel.page ? "chat-page chat-page--panel" : "chat-page"} style={chatAccentStyle(bot.avatar.color)}>
      <div className="chat-page__main">
      <ChatHeader bot={bot} control={control} onChange={data.setBot} onError={setNotice} actions={actions} pillRef={pillRef}
        pillHref={panel.hrefFor(panel.page ? null : "profile")} open={panel.page !== null} />
      {find === null ? null
        : <FindBar query={find} found={shown.length} onQuery={setFind} onClose={() => setFind(null)} />}
      <div className="chat-page__scroll" ref={keepBottom}>
        <MessageList messages={shown} streaming={live.streaming} botName={bot.name} botAvatar={bot.avatar}
          team={Object.values(live.bots)} stuck={stuck} approvals={approvals} toolLines={live.toolLines} computerRuns={live.computerRuns} activityRuns={live.activityRuns}
          newAfter={thread.id === main.id ? seenAtOpen : null}
          queued={stillQueued(all, queuedIds)} activity={bot.activity} onReact={onReact}
          onQuote={readOnly ? undefined : setReplyTo} />
      </div>
      <ChatDock name={bot.name} botId={botId} notice={notice} readOnly={readOnly} onSend={onSend} tray={tray}
        voiceCorrect={bot.voice?.correct_speech ?? bot.voice?.correct_english ?? false}
        onIt={bot.status === "on_it"} onError={setNotice} added={added} onAdded={(title) => { setNotice(null); setAdded(title); }}
        mentions={thread.kind === "chat" ? otherBots(Object.values(live.bots), botId) : undefined}
        projects={thread.kind === "chat" ? projects : undefined}
        modePill={thread.kind === "chat" && bot.computer === "linux"
          ? <ChatModePill bot={bot} onChange={data.setBot} onError={setNotice} /> : undefined}
        onCall={thread.kind === "chat" && !readOnly ? () => setCalling(true) : undefined}
        replyTo={replyTo && replyTo.thread_id === thread.id ? replyTo : null} onCancelReply={() => setReplyTo(null)} />
      </div>
      {panel.page ? <LazyBotPanel bot={bot} page={panel.page} onPage={panel.select} onClose={closePanel} onChange={data.setBot}
        control={control} /> : null}
      {sharing ? <ShareTemplateDialog bot={bot} onClose={() => setSharing(false)} /> : null}
      {sheetOpen ? <ThreadsSheet threads={data.threads} mainId={main.id} currentId={thread.id} botId={botId} onClose={() => setSheetOpen(false)} /> : null}
      {calling ? (
        <Suspense fallback={null}>
          <CallScreen bot={bot} threadId={thread.id} messages={all} approvals={Object.values(approvals)}
            stuck={Object.values(stuck)} streaming={live.streaming} speechReady={live.speechReady} onSend={sendText}
            onClose={() => setCalling(false)} />
        </Suspense>
      ) : null}
      {task.openId ? <Suspense fallback={null}><TaskDrawer taskId={task.openId} onClose={task.close} /></Suspense> : null}
    </div>
    </ChatContext.Provider>
  );
}
