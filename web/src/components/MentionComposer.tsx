import {
  useCallback, useEffect, useId, useLayoutEffect, useRef, useState,
  type ChangeEvent, type KeyboardEvent, type RefObject,
} from "react";
import { COMPOSER_MAX_ROWS } from "./chat/constants";
import { MentionList } from "./MentionList";
import { useAutoGrow } from "../hooks/useAutoGrow";
import { isSendKey } from "../lib/composerKeys";
import {
  handleListKey, insertMention, matchingOptions, mentionQuery, withReplyMention, type MentionOption,
} from "../lib/mentions";

export { insertMention, mentionQuery, withReplyMention, type MentionOption };

// The room composer: Enter sends, Shift+Enter is a newline, and typing "@"
// opens a list of members plus @everyone (ArrowUp/ArrowDown move, Enter or
// Tab picks, Escape closes). Mentions are resolved to bot ids by the
// server when the post arrives (plan Task 6) — which is also how Reply
// routes: it only puts "@<author> " in front of the draft.

// Set by a message's Reply button; a new nonce re-applies the same name.
export interface ReplyTarget {
  name: string;
  nonce: number;
}

export interface MentionComposerProps {
  members: readonly MentionOption[];
  onSend: (text: string) => Promise<void>;
  placeholder: string;
  replyTo?: ReplyTarget | null;
}

const EVERYONE: MentionOption = { id: "everyone", name: "everyone" };

function mentionOptions(query: string | null, members: readonly MentionOption[]): MentionOption[] {
  return matchingOptions(query, [...members, EVERYONE]);
}

// React moves the caret to the end when it rewrites a controlled value.
// The returned (stable) setter asks for the caret at `at`; it is applied
// in the same commit that writes the new value — never later, so it can't
// land in the middle of what the user types next.
function useCaretPlacement(boxRef: RefObject<HTMLTextAreaElement | null>) {
  const pending = useRef<number | null>(null);
  useLayoutEffect(() => {
    const at = pending.current;
    if (at === null) return;
    pending.current = null;
    boxRef.current?.setSelectionRange(at, at);
  });
  return useCallback((at: number) => {
    pending.current = at;
  }, []);
}

type EditDraft = (text: string, caret: number, moveCaret?: boolean) => void;

// The draft text and where the caret is in it. `edit` is stable (the
// Reply effect depends on it); `moveCaret` puts the real caret there too.
function useDraft(boxRef: RefObject<HTMLTextAreaElement | null>) {
  const [text, setText] = useState("");
  const [caret, setCaret] = useState(0);
  const placeCaret = useCaretPlacement(boxRef);
  const edit = useCallback<EditDraft>(
    (next, at, moveCaret = false) => {
      if (moveCaret) placeCaret(at);
      setText(next);
      setCaret(at);
    },
    [placeCaret],
  );
  return { text, caret, setCaret, edit };
}

function useReplyMention(replyTo: ReplyTarget | null, boxRef: RefObject<HTMLTextAreaElement | null>, edit: EditDraft) {
  useEffect(() => {
    if (!replyTo) return;
    const box = boxRef.current;
    const next = withReplyMention(box?.value ?? "", replyTo.name);
    edit(next, next.length, true);
    box?.focus();
  }, [replyTo, boxRef, edit]);
}

// Clears the box only once the send succeeds; a failed send keeps the
// text for another try (the caller shows the error).
function useSender(onSend: (text: string) => Promise<void>, onSent: () => void) {
  const [sending, setSending] = useState(false);
  const send = (text: string) => {
    const trimmed = text.trim();
    if (trimmed.length === 0 || sending) return;
    setSending(true);
    onSend(trimmed)
      .then(onSent)
      .catch(() => {
        // The caller already recorded the error; this only decides whether the box clears.
      })
      .finally(() => setSending(false));
  };
  return { sending, send };
}

function SendButton({ disabled, onClick }: { disabled: boolean; onClick: () => void }) {
  return (
    <button type="button" className="composer__send" onClick={onClick} disabled={disabled}>
      <svg className="composer__send-icon" viewBox="0 0 20 20" width={18} height={18} aria-hidden="true" focusable="false">
        <path d="M10 16V4M4.5 9.5 10 4l5.5 5.5" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <span className="sr-only">Send</span>
    </button>
  );
}

export function MentionComposer({ members, onSend, placeholder, replyTo = null }: MentionComposerProps) {
  const boxRef = useRef<HTMLTextAreaElement>(null);
  const { text, caret, setCaret, edit } = useDraft(boxRef);
  const [active, setActive] = useState(0);
  const [dismissed, setDismissed] = useState(false);
  const listId = useId();
  useReplyMention(replyTo, boxRef, edit);
  const { sending, send } = useSender(onSend, () => edit("", 0));
  useAutoGrow(boxRef, text, COMPOSER_MAX_ROWS);
  const options = dismissed ? [] : mentionOptions(mentionQuery(text.slice(0, caret)), members);
  const open = options.length > 0;
  const highlighted = Math.min(active, options.length - 1);

  const pick = (option: MentionOption) => {
    const next = insertMention(text, caret, option.name);
    edit(next.text, next.caret, true);
  };
  const onChange = (event: ChangeEvent<HTMLTextAreaElement>) => {
    edit(event.target.value, event.target.selectionStart);
    setDismissed(false);
    setActive(0);
  };
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    const keys = { count: options.length, setActive, pick: () => pick(options[highlighted]), dismiss: () => setDismissed(true) };
    if (open && handleListKey(event, keys)) return;
    if (isSendKey(event)) {
      event.preventDefault();
      send(text);
    }
  };

  return (
    <div className="composer composer--regular mention-composer">
      {/* readOnly (not disabled) while sending keeps focus in the box for the next message. */}
      <textarea
        ref={boxRef} className="composer__box" value={text} rows={1} placeholder={placeholder}
        aria-label="Message the room" aria-autocomplete="list" aria-busy={sending} readOnly={sending}
        aria-controls={open ? listId : undefined} aria-activedescendant={open ? `${listId}-${highlighted}` : undefined}
        onChange={onChange}
        onSelect={(event) => setCaret(event.currentTarget.selectionStart)}
        onKeyDown={onKeyDown}
      />
      {open ? <MentionList id={listId} options={options} active={highlighted} onPick={pick} /> : null}
      <SendButton disabled={sending || text.trim().length === 0} onClick={() => send(text)} />
    </div>
  );
}
