import { chatAccentStyle } from "../lib/chatAccent";
import { useCallback, useEffect, useState, type Dispatch, type SetStateAction } from "react";
import { Link, useParams } from "react-router-dom";
import { Avatar } from "../components/Avatar";
import { ErrorNotice } from "../components/ErrorNotice";
import { BackIcon } from "../components/icons";
import { MentionComposer, type ReplyTarget } from "../components/MentionComposer";
import { MessageList } from "../components/MessageList";
import { preloadMarkdown } from "../components/chat/RichText";
import { useKeepBottom } from "../hooks/useKeepBottom";
import { useLiveState } from "../hooks/useLiveStore";
import * as botsApi from "../api/bots";
import * as roomsApi from "../api/rooms";
import { describeError } from "../api/client";
import { mergeMessages, nextLocalSeq } from "../lib/messages";
import type { BotOut, MessageOut, RoomOut } from "../api/types";

// A room (D-E / D-G): one shared conversation with 2–6 bots. A post goes
// to the bots it @mentions, @everyone to all of them, and anything else
// to the coordinator — the server binds the mentions (plan Task 6).

const PLACEHOLDER = "Message the room… (@ to mention)";

function RoomHeader({ room, members }: { room: RoomOut; members: BotOut[] }) {
  return (
    <header className="room-header">
      <div className="room-header__title">
        <Link to="/" className="icon-btn room-header__back" aria-label="Back to chats"><BackIcon /></Link>
        <h1 className="room-header__name">{room.name}</h1>
      </div>
      <ul className="room-header__members" aria-label="Members">
        {members.map((bot) => (
          <li key={bot.id} className="room-header__member">
            <Avatar avatar={bot.avatar} status={bot.status} size={28} label={false} decorative botId={bot.id} />
            <span className="room-header__member-name">{bot.name}</span>
            {bot.id === room.coordinator_id ? <span className="room-header__role">coordinator</span> : null}
          </li>
        ))}
      </ul>
    </header>
  );
}

function RoomEmpty({ coordinator }: { coordinator?: BotOut }) {
  return (
    <div className="message-list__empty">
      <p className="message-list__empty-title">Say hello to the room.</p>
      <p className="message-list__empty-hint">
        Type @ to ask one bot, or @everyone to ask them all.
        {coordinator ? ` Anything else goes to ${coordinator.name}, the coordinator.` : null}
      </p>
    </div>
  );
}

interface RoomData {
  room: RoomOut | null;
  team: BotOut[];
  messages: MessageOut[];
  setMessages: Dispatch<SetStateAction<MessageOut[]>>;
  error: string | null;
  load: () => void;
}

function useRoomData(roomId: string): RoomData {
  const [room, setRoom] = useState<RoomOut | null>(null);
  const [team, setTeam] = useState<BotOut[]>([]);
  const [messages, setMessages] = useState<MessageOut[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    Promise.all([roomsApi.getRoom(roomId), botsApi.listBots(), roomsApi.listRoomMessages(roomId)])
      .then(([loadedRoom, bots, stored]) => {
        setRoom(loadedRoom);
        setTeam(bots);
        setMessages(stored);
      })
      .catch((err: unknown) => setError(describeError(err)));
  }, [roomId]);

  useEffect(() => {
    load();
  }, [load]);

  return { room, team, messages, setMessages, error, load };
}

// Your post, shown under the server's id at once (the WS echo of the
// same id then dedupes in mergeMessages) and ordered before any reply.
function ownPost(id: string, room: RoomOut, text: string, shown: readonly MessageOut[]): MessageOut {
  return {
    id, thread_id: room.thread_id, role: "user", body: text, tainted: false,
    seq: nextLocalSeq(shown), created_at: new Date().toISOString(), kind: "text", author_bot_id: null,
  };
}

function RoomView({ roomId }: { roomId: string }) {
  const { room, team, messages, setMessages, error, load } = useRoomData(roomId);
  // Separate from `error`: a failed send must not replace the conversation (same as Talk).
  const [sendError, setSendError] = useState<string | null>(null);
  const [replyTo, setReplyTo] = useState<ReplyTarget | null>(null);
  const live = useLiveState();
  const keepBottom = useKeepBottom();
  // Fetch the markdown renderer while the room loads, so its replies never flash as plain text first.
  useEffect(() => { void preloadMarkdown(); }, []);

  if (error) return <ErrorNotice message={error} onRetry={load} />;
  if (!room) return <p className="page-loading">Loading&hellip;</p>;

  const liveTeam = team.map((bot) => live.bots[bot.id] ?? bot);
  const members = room.member_ids.flatMap((id) => liveTeam.filter((bot) => bot.id === id));
  const allMessages = mergeMessages(messages, live.messagesByThread[room.thread_id] ?? []);

  const onSend = async (text: string) => {
    setSendError(null);
    try {
      const { message_id } = await roomsApi.postRoomMessage(room.id, text);
      setMessages((prev) => [...prev, ownPost(message_id, room, text, allMessages)]);
    } catch (err) {
      setSendError(describeError(err));
      throw err;
    }
  };
  const reply = (author: BotOut) => setReplyTo((prev) => ({ name: author.name, nonce: (prev?.nonce ?? 0) + 1 }));

  return (
    <div className="chat-page room-page" style={chatAccentStyle(members.find((bot) => bot.id === room.coordinator_id)?.avatar.color)}>
      <RoomHeader room={room} members={members} />
      <div className="chat-page__scroll" ref={keepBottom}>
        {allMessages.length === 0 ? (
          <RoomEmpty coordinator={members.find((bot) => bot.id === room.coordinator_id)} />
        ) : (
          <MessageList messages={allMessages} streaming={live.streaming} botName="the room" team={liveTeam} onReply={reply}
            toolLines={live.toolLines} />
        )}
      </div>
      <div className="chat-page__dock">
        {sendError ? <ErrorNotice message={sendError} /> : null}
        <MentionComposer members={members} onSend={onSend} placeholder={PLACEHOLDER} replyTo={replyTo} />
      </div>
    </div>
  );
}

export function Room() {
  const { roomId } = useParams<{ roomId: string }>();
  if (!roomId) return null;
  // A fresh view per room, so switching rooms never carries over a draft,
  // a reply target or the last room's messages.
  return <RoomView key={roomId} roomId={roomId} />;
}
