import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorNotice } from "../ErrorNotice";
import { FileIcon, LinkIcon } from "../icons";
import * as profileApi from "../../api/profile";
import { describeError } from "../../api/client";
import type { BotOut } from "../../api/types";
import { formatChatTime } from "../../lib/chatTime";
import { groupLibrary, libraryItems, type LibraryItem } from "../../lib/library";

const KIND_WORDS: Readonly<Record<LibraryItem["kind"], string>> = { document: "Document", note: "Note", link: "Link" };

function ItemBody({ item }: { item: LibraryItem }) {
  return (
    <>
      <span className="library__icon" aria-hidden="true">{item.kind === "link" ? <LinkIcon /> : <FileIcon />}</span>
      <span className="library__text">
        <span className="library__label">{item.label}</span>
        <span className="library__detail">{item.detail || KIND_WORDS[item.kind]}</span>
      </span>
      <time className="library__when" dateTime={item.at}>{formatChatTime(item.at)}</time>
    </>
  );
}

// A link opens in a new tab with no opener and no referrer (Roost never fetches it); a document or note opens on the Board.
function ItemRow({ item }: { item: LibraryItem }) {
  return (
    <li className="library__row">
      {item.external ? (
        <a href={item.href} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer" className="library__link">
          <ItemBody item={item} />
        </a>
      ) : (
        <Link to={item.href} className="library__link"><ItemBody item={item} /></Link>
      )}
      {item.tainted ? <span className="board-chip board-chip--web">from web content</span> : null}
    </li>
  );
}

function useLibrary(botId: string) {
  const [items, setItems] = useState<LibraryItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    Promise.all([profileApi.getMade(botId), profileApi.getLinks(botId)])
      .then(([made, links]) => { if (live) setItems(libraryItems(made, links)); })
      .catch((err: unknown) => { if (live) setError(describeError(err)); });
    return () => { live = false; };
  }, [botId]);
  return { items, error };
}

// The bot's Library (restructure slice 3): the documents and notes it made and the links from its chats, grouped by
// Today, This week and Earlier on the account's days.
export function LibraryPage({ bot }: { bot: BotOut }) {
  const { items, error } = useLibrary(bot.id);
  if (error) return <ErrorNotice message={error} />;
  if (items === null) return <p className="page-loading">Loading&hellip;</p>;
  const groups = groupLibrary(items);
  if (groups.length === 0) {
    return <p className="tab-empty">Nothing here yet. The documents and notes {bot.name} makes, and the links from its chats, show up here.</p>;
  }
  return (
    <div className="library">
      {groups.map((group) => (
        <section key={group.title} className="library__group" aria-label={group.title}>
          <h3 className="settings-group__title">{group.title}</h3>
          <ul className="library__list profile-card">
            {group.items.map((item) => <ItemRow key={item.id} item={item} />)}
          </ul>
        </section>
      ))}
    </div>
  );
}
