import { useCopy } from "../../hooks/useCopy";
import { formatClock } from "../../lib/chatTime";
import { IconButton } from "../../ui/IconButton";
import { CheckIcon, CopyIcon, ReplyIcon } from "../icons";
import type { ReactionKey } from "./constants";
import { ReactionPicker } from "./Reactions";
import { SpeakButton } from "./SpeakButton";

const COPY_LABEL = { idle: "Copy message", copied: "Copied", failed: "Copy failed" } as const;

// A message's quiet actions (redesign P2): the time it was sent, on the account's clock, a tapback picker, and Copy, which copies
// the message as it was written. They show on hover or keyboard focus (styles/chat.css).
export interface MessageActionsProps {
  text: string;
  createdAt: string;
  reaction?: ReactionKey;
  onReact?: (key: ReactionKey | null) => void; // chats only: rooms have no tapbacks
  onQuote?: () => void; // chats only: reply to this message (a quote chip over the composer)
  speak?: { threadId: string; messageId: string }; // a bot's reply or Report: the speaker that reads it aloud
}

export function MessageActions({ text, createdAt, reaction, onReact, onQuote, speak }: MessageActionsProps) {
  const { state, copy } = useCopy();
  const clock = formatClock(createdAt);
  return (
    <div className="message__actions">
      {clock ? (
        <time className="message__time" dateTime={createdAt}>
          {clock}
        </time>
      ) : null}
      {onReact ? <ReactionPicker current={reaction} onReact={onReact} /> : null}
      {onQuote ? <IconButton label="Reply" tooltip={false} size="sm" icon={<ReplyIcon />} onClick={onQuote} /> : null}
      {speak ? <SpeakButton threadId={speak.threadId} messageId={speak.messageId} /> : null}
      <IconButton label={COPY_LABEL[state]} tooltip={false} size="sm"
        icon={state === "copied" ? <CheckIcon /> : <CopyIcon />} onClick={() => copy(text)} />
    </div>
  );
}
