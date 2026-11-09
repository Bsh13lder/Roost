import { useEffect, useRef } from "react";
import { CloseIcon, SearchIcon } from "../icons";
import { IconButton } from "../../ui/IconButton";
import { Input } from "../../ui/Input";
import type { MessageOut } from "../../api/types";

// Find in chat (restructure slice 3): the messages whose words hold the query, any case. Only what this browser has
// loaded is searched; a blank query keeps every message.
export function findInChat(messages: readonly MessageOut[], query: string): MessageOut[] {
  const needle = query.trim().toLocaleLowerCase();
  if (!needle) return [...messages];
  return messages.filter((message) => message.body.toLocaleLowerCase().includes(needle));
}

export function FindBar({ query, found, onQuery, onClose }: {
  query: string; found: number; onQuery: (query: string) => void; onClose: () => void;
}) {
  const boxRef = useRef<HTMLInputElement>(null);
  useEffect(() => { boxRef.current?.focus(); }, []);
  return (
    <div className="find-bar" role="search">
      <span className="find-bar__icon" aria-hidden="true"><SearchIcon /></span>
      <Input ref={boxRef} type="search" aria-label="Find in chat" placeholder="Find in chat" controlSize="sm" value={query}
        onChange={(event) => onQuery(event.target.value)}
        onKeyDown={(event) => { if (event.key === "Escape") { event.preventDefault(); onClose(); } }} />
      {query.trim() ? <span className="find-bar__count" aria-live="polite">{found} found</span> : null}
      <IconButton label="Close find" icon={<CloseIcon />} onClick={onClose} tooltip={false} />
    </div>
  );
}
