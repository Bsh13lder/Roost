import { useCallback, useEffect, useId, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ChatList } from "../components/ChatList";
import { NewModelBanner } from "../components/NewModelBanner";
import { ErrorNotice } from "../components/ErrorNotice";
import { AvatarRow } from "../components/sidebar/AvatarRow";
import { SidebarFoot } from "../components/sidebar/SidebarFoot";
import { SidebarTop } from "../components/sidebar/SidebarTop";
import { NewRoomDialog } from "../components/NewRoomDialog";
import { TokensLine } from "../components/usage/TokensLine";
import { useAttention } from "../hooks/useAttention";
import { useLiveState } from "../hooks/useLiveStore";
import { useUnread } from "../hooks/useUnread";
import { useOpenProposals } from "../hooks/useOpenProposals";
import { useOpenSkillProposals } from "../hooks/useOpenSkillProposals";
import { useOpenKeyRequests } from "../hooks/useOpenKeyRequests";
import { useOpenQuestions } from "../hooks/useOpenQuestions";
import * as botsApi from "../api/bots";
import * as chatsApi from "../api/chats";
import * as stuckApi from "../api/stuck";
import { describeError } from "../api/client";
import type { BotOut, ChatRowOut, StuckCardOut } from "../api/types";
import type { LiveState } from "../store/live";
import { avatarRow } from "../lib/sidebar";
import { askRows, type AskRow } from "../lib/myTurn";
import { mergeStuck, myTurnLine, openStuckCards } from "../lib/stuck";
import { onTeamChanged } from "../lib/teamChanged";

// Messages the server has stored. A bot's empty placeholder (seq 0) doesn't
// count, and its reply replaces it in place under the same id: counting
// only stored messages is what makes that reply refresh the row.
const storedMessageCount = (live: LiveState) =>
  Object.values(live.messagesByThread).reduce((total, list) => total + list.filter((m) => m.seq > 0).length, 0);

// Home reloads when a message is stored or the team changes (a created or retired bot).
// useHomeData and useStuckList share this trigger, so either change reloads both.
function useReloadOn(live: LiveState, reload: () => void) {
  const messages = storedMessageCount(live);
  const team = Object.keys(live.bots).length;
  useEffect(() => reload(), [reload, messages, team]);
  useEffect(() => onTeamChanged(reload), [reload]);
}

// Your bots and chats. Only the newest load may answer: an older one that lands last is dropped.
function useHomeData(live: LiveState) {
  const [bots, setBots] = useState<BotOut[] | null>(null);
  const [rows, setRows] = useState<ChatRowOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  const latestLoad = useRef(0);
  const reload = useCallback(() => {
    const load = ++latestLoad.current;
    setError(null);
    Promise.all([botsApi.listBots(), chatsApi.listChats()])
      .then(([loadedBots, loadedRows]) => {
        if (load === latestLoad.current) { setBots(loadedBots); setRows(loadedRows); }
      })
      .catch((err: unknown) => { if (load === latestLoad.current) setError(describeError(err)); });
  }, []);
  useReloadOn(live, reload);
  return { bots, rows, error, reload };
}

// Your open Stuck cards for My turn, loaded on their own: a failed GET /api/stuck never hides
// the bots and chats, and only My turn says so, with Retry. Same trigger as useHomeData, so a
// new card's chat line reloads it. Only the newest load may answer.
function useStuckList(live: LiveState) {
  const [cards, setCards] = useState<StuckCardOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  const latestLoad = useRef(0);
  const reload = useCallback(() => {
    const load = ++latestLoad.current;
    setError(null);
    stuckApi.listStuck()
      .then((loaded) => { if (load === latestLoad.current) setCards(loaded); })
      .catch((err: unknown) => { if (load === latestLoad.current) setError(describeError(err)); });
  }, []);
  useReloadOn(live, reload);
  return { cards, error, reload };
}

// Open questions, routine proposals and skill proposals for My turn, loaded on their own (like the Stuck cards): a failed load
// says so in My turn, with Retry, and never hides the bots and chats.
function useAskRows(bots: Readonly<Record<string, BotOut>>) {
  const questions = useOpenQuestions();
  const proposals = useOpenProposals();
  const skills = useOpenSkillProposals();
  const keys = useOpenKeyRequests();
  const reloadQuestions = questions.reload;
  const reloadProposals = proposals.reload;
  const reloadSkills = skills.reload;
  const reloadKeys = keys.reload;
  const retry = useCallback(() => { reloadQuestions(); reloadProposals(); reloadSkills(); reloadKeys(); },
    [reloadQuestions, reloadProposals, reloadSkills, reloadKeys]);
  return {
    rows: askRows(questions.questions, proposals.proposals ?? [], bots, skills.proposals ?? [], keys.requests ?? []),
    error: questions.error ?? proposals.error ?? skills.error ?? keys.error, retry,
  };
}

interface MyTurnProps {
  cards: readonly StuckCardOut[];
  asks: readonly AskRow[];
  bots: Readonly<Record<string, BotOut>>;
  error: string | null;
  onRetry: () => void;
}

// The Stuck cards waiting on you, newest first. Each row opens that bot's chat on the card's thread.
// Shown only while a card is open, or while the list failed to load: then its own ErrorNotice says
// why, with Retry, and the rest of Home is untouched. A card of a bot no longer on the team is left out.
function MyTurn({ cards, asks, bots, error, onRetry }: MyTurnProps) {
  const titleId = useId();
  const shown = cards.filter((card) => bots[card.bot_id]);
  if (shown.length === 0 && asks.length === 0 && !error) return null;
  return (
    <section className="my-turn" aria-labelledby={titleId}>
      <h2 id={titleId} className="my-turn__title">My turn</h2>
      {error ? <ErrorNotice message={error} onRetry={onRetry} /> : null}
      {shown.length + asks.length > 0 ? (
        <ul className="my-turn__list">
          {asks.map((ask) => (
            <li key={ask.key}>
              <Link className="my-turn__row" to={ask.to}>
                <span className="my-turn__mark" aria-hidden="true">?</span>
                <span className="my-turn__text">{ask.text}</span>
              </Link>
            </li>
          ))}
          {shown.map((card) => (
            <li key={card.id}>
              <Link className="my-turn__row" to={`/bots/${card.bot_id}?thread=${encodeURIComponent(card.thread_id)}`}>
                <span className="my-turn__mark" aria-hidden="true">!</span>
                <span className="my-turn__text">
                  {myTurnLine(bots[card.bot_id].name, card)}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

export function Home() {
  const live = useLiveState();
  const { bots, rows, error, reload } = useHomeData(live);
  const stuckList = useStuckList(live);
  const [query, setQuery] = useState("");
  const [roomOpen, setRoomOpen] = useState(false);
  const attention = useAttention();
  const unread = useUnread(rows);
  const navigate = useNavigate();
  const byId: Record<string, BotOut> = Object.fromEntries((bots ?? []).map((bot) => [bot.id, live.bots[bot.id] ?? bot]));
  const stuck = mergeStuck(stuckList.cards, live.stuckCards);
  const waiting = openStuckCards(stuck);
  const asks = useAskRows(byId);
  const searching = query.trim() !== "";
  return (
    <div className="home">
      <SidebarTop query={query} onQuery={setQuery} onNewRoom={() => setRoomOpen(true)} />
      <div className="sidebar-scroll">
        <NewModelBanner bots={Object.values(byId)} />
        {error ? <ErrorNotice message={error} onRetry={reload} /> : null}
        {!searching ? <AvatarRow bots={avatarRow(Object.values(byId))} attention={attention} unread={unread} stuck={stuck} /> : null}
        {!searching ? (
          <MyTurn cards={waiting} asks={asks.rows} bots={byId} error={stuckList.error ?? asks.error}
            onRetry={() => { stuckList.reload(); asks.retry(); }} />
        ) : null}
        {bots === null && !error ? <p className="page-loading">Loading your chats&hellip;</p> : null}
        {bots !== null ? <ChatList rows={rows} bots={byId} query={query} attention={attention} unread={unread} stuck={stuck} /> : null}
        {!searching ? <TokensLine /> : null}
      </div>
      <SidebarFoot />
      {roomOpen ? (
        <NewRoomDialog bots={Object.values(byId)} onClose={() => setRoomOpen(false)}
          onCreated={(room) => { setRoomOpen(false); reload(); navigate(`/rooms/${room.id}`); }} />
      ) : null}
    </div>
  );
}
