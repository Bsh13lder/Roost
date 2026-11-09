// Reply quotes (replies track): the quote above a message that answers another, and the chip above the composer
// while you write a reply (× drops it). Text is text: never markdown, never a link.
import { WebMark } from "./WebMark";
import { IconButton } from "../../ui/IconButton";
import { CloseIcon } from "../icons";

export function ReplyQuote({ quote, tainted }: { quote: string; tainted?: boolean }) {
  return (
    <blockquote className="reply-quote" aria-label="Replying to">
      <span className="reply-quote__text">{quote}</span>
      {tainted ? <WebMark /> : null}
    </blockquote>
  );
}

export function ReplyChip({ quote, onCancel }: { quote: string; onCancel: () => void }) {
  return (
    <div className="reply-chip">
      <span className="reply-chip__label">Replying to</span>
      <span className="reply-chip__text">{quote}</span>
      <IconButton label="Cancel reply" size="sm" tooltip={false} icon={<CloseIcon />} onClick={onCancel} />
    </div>
  );
}
