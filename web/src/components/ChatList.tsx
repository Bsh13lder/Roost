import { useEffect, useId, useState } from "react";
import { NavLink } from "react-router-dom";
import { Avatar } from "./Avatar";
import { statusWords } from "./StatusLabel";
import { WorkingDots, WorkingTimer } from "./WorkingIndicator";
import { formatChatTime } from "../lib/chatTime";
import { clearAttention } from "../lib/attention";
import { plainText } from "../lib/plainText";
import { chatSections, type ChatSection } from "../lib/sidebar";
import { cx } from "../ui/cx";
import { Menu, MenuItem } from "../ui/Menu";
import { MoreIcon } from "./icons";
import * as botsApi from "../api/bots";
import { describeError } from "../api/client";
import type { BotOut, BotStatus, ChatRowOut, StuckCardOut } from "../api/types";
import { wantsControl } from "../lib/wantsControl";

const BUSY: ReadonlySet<BotStatus> = new Set(["on_it", "asking_you", "stuck"]);
const KIND_MARK: Record<string, string> = { handoff: "⇄ ", card: "▣ " };

export interface ChatListProps {
  rows: readonly ChatRowOut[];
  bots: Readonly<Record<string, BotOut>>;
  query: string;
  attention: ReadonlySet<string>;
  // Chats with a message you have not seen (hooks/useUnread): each gets a dot.
  unread?: ReadonlySet<string>;
  // Your Stuck cards (C3): a bot with an open one shows a hand in its eye.
  stuck?: Readonly<Record<string, StuckCardOut>>;
  now?: Date;
}

interface SectionProps {
  section: ChatSection;
  bots: Readonly<Record<string, BotOut>>;
  attention: ReadonlySet<string>;
  unread: ReadonlySet<string>;
  stuck: Readonly<Record<string, StuckCardOut>>;
  now?: Date;
}

const NO_STUCK: Readonly<Record<string, StuckCardOut>> = {};
const NOTHING_UNREAD: ReadonlySet<string> = new Set();

// The status has a start time only on the client: it is when this row last saw it change.
function useStatusSince(botId: string, status: BotStatus): number {
  const [since, setSince] = useState(() => Date.now());
  useEffect(() => setSince(Date.now()), [botId, status]);
  return since;
}

function StatusLine({ bot }: { bot: BotOut }) {
  const since = useStatusSince(bot.id, bot.status);
  const words = statusWords(bot.status, bot.activity);
  return (
    <span className={`chat-row__status chat-row__status--${words.tone}`}>
      <WorkingDots />
      <span>{words.word}{words.activity ? ` · ${words.activity}` : ""}</span>
      <span aria-hidden="true"> · </span>
      <WorkingTimer since={since} />
    </span>
  );
}

function Preview({ row }: { row: ChatRowOut }) {
  if (!row.preview) return <span className="chat-row__preview chat-row__preview--empty">No messages yet</span>;
  const mark = row.preview_kind ? KIND_MARK[row.preview_kind] ?? "" : "";
  const words = plainText(row.preview);
  return <span className="chat-row__preview">{mark}{row.from_you ? `You: ${words}` : words}</span>;
}

interface ChatRowProps {
  row: ChatRowOut;
  bot?: BotOut;
  highlighted: boolean;
  unread: boolean;
  control: boolean;
  now?: Date;
}

// A bot's row menu: Pin moves it up to the robot row. The result comes back as a live bot_updated frame.
function RowMenu({ bot, onError }: { bot: BotOut; onError: (message: string | null) => void }) {
  const pin = () => {
    onError(null);
    botsApi.setPinned(bot.id, true).catch((err: unknown) => onError(describeError(err)));
  };
  return (
    <div className="chat-row__menu">
      <Menu label={`${bot.name} menu`} trigger={<MoreIcon />}>
        <MenuItem onSelect={pin}>Pin</MenuItem>
      </Menu>
    </div>
  );
}

// The active row (NavLink's aria-current="page") has a soft fill; its ghost shows the status and plays its events.
function ChatRow({ row, bot, highlighted, unread, control, now }: ChatRowProps) {
  const [error, setError] = useState<string | null>(null);
  const href = row.kind === "bot" ? `/bots/${row.id}` : `/rooms/${row.id}`;
  return (
    <li className={cx("chat-row", highlighted && "chat-row--attention", unread && "chat-row--unread")}>
      <NavLink to={href} className="chat-row__link" onClick={() => clearAttention(row.id)}>
        {bot ? (
          <Avatar avatar={bot.avatar} status={bot.status} size={44} label={false} decorative star={bot.is_primary} botId={bot.id} control={control} />
        ) : (
          <span className="chat-row__room" aria-hidden="true">#</span>
        )}
        <span className="chat-row__text">
          <span className="chat-row__top">
            <span className="chat-row__name">
              {row.name}{bot?.is_primary ? <span className="sr-only">, your main bot</span> : null}
            </span>
            <time className="chat-row__time" dateTime={row.last_at}>{formatChatTime(row.last_at, now)}</time>
          </span>
          <span className="chat-row__bottom">
            {bot && BUSY.has(bot.status) ? <StatusLine bot={bot} /> : <Preview row={row} />}
            {unread ? <span className="chat-row__unread"><span className="sr-only">Unread</span></span> : null}
          </span>
        </span>
      </NavLink>
      {bot ? <RowMenu bot={bot} onError={setError} /> : null}
      {error ? <p className="chat-row__error" role="alert">{error}</p> : null}
    </li>
  );
}

function Section({ section, bots, attention, unread, stuck, now }: SectionProps) {
  const titleId = useId();
  return (
    <section aria-labelledby={section.label ? titleId : undefined}>
      {section.label ? <h2 id={titleId} className="chat-section__title">{section.label}</h2> : null}
      <ul className="chat-list">
        {section.rows.map((row) => (
          <ChatRow key={`${row.kind}-${row.id}`} row={row} bot={row.kind === "bot" ? bots[row.id] : undefined}
            highlighted={attention.has(row.id)} unread={unread.has(row.id)}
            control={row.kind === "bot" && wantsControl({ id: row.id }, stuck)} now={now} />
        ))}
      </ul>
    </section>
  );
}

// What an empty list says: a search that found nothing, or truly no chats. When every bot is pinned up in
// the robot row (the main bot always is), the list is just empty: there are chats, they are above.
function emptyText(rows: readonly ChatRowOut[], query: string): string | null {
  if (query.trim()) return "No chats match.";
  return rows.length === 0 ? "No chats yet." : null;
}

// The chats in sections: the ungrouped bots and rooms first, then one section per label.
export function ChatList({ rows, bots, query, attention, unread = NOTHING_UNREAD, stuck = NO_STUCK, now }: ChatListProps) {
  const sections = chatSections(rows, bots, query);
  if (sections.length === 0) {
    const text = emptyText(rows, query);
    return text ? <p className="chat-list__empty">{text}</p> : <nav aria-label="Chats" />;
  }
  return (
    <nav aria-label="Chats">
      {sections.map((section) => (
        <Section key={section.label ?? "ungrouped"} section={section} bots={bots} attention={attention} unread={unread} stuck={stuck} now={now} />
      ))}
    </nav>
  );
}
