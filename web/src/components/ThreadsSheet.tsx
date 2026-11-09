import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { formatChatTime } from "../lib/chatTime";
import type { ThreadOut } from "../api/types";

// The chat ⋯ menu's Earlier conversations (S1.5, lead task 06): a bottom sheet on a phone, a
// centred dialog on a desktop. Escape, × or a tap outside closes it.
export function ThreadsSheet({ threads, mainId, currentId, botId, onClose }: {
  threads: readonly ThreadOut[]; mainId: string; currentId: string; botId: string; onClose: () => void;
}) {
  const navigate = useNavigate();
  const dialog = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);
  useEffect(() => dialog.current?.focus(), []);
  // The bot's one chat is the Chat itself; listThreads is oldest first.
  const newestFirst = threads.filter((thread) => thread.id !== mainId).reverse();
  return (
    <>
      <div className="sheet-backdrop" aria-hidden="true" onClick={onClose} />
      <div className="sheet" role="dialog" aria-modal="true" aria-label="Earlier conversations" tabIndex={-1} ref={dialog}>
        <header className="sheet__head">
          <h2 className="sheet__title">Earlier conversations</h2>
          <button type="button" className="icon-btn" aria-label="Close" onClick={onClose}>×</button>
        </header>
        {newestFirst.length === 0 ? <p className="sheet__empty">No earlier conversations.</p> : null}
        <ul className="sheet__list">
          {newestFirst.map((thread) => (
            <li key={thread.id}>
              <button type="button" className="sheet__row" aria-current={thread.id === currentId ? "true" : undefined}
                onClick={() => { onClose(); navigate(`/bots/${botId}?thread=${thread.id}`); }}>
                <span className="sheet__row-title">{thread.title ?? "Conversation"}</span>
                <time className="sheet__row-time" dateTime={thread.created_at}>{formatChatTime(thread.created_at)}</time>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </>
  );
}
