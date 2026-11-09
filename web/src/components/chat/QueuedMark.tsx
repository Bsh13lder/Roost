import { QUEUED_LINE } from "./constants";

// Under a message of yours that waits for a busy bot.
export function QueuedMark() {
  return <p className="message__queued" role="status">{QUEUED_LINE}</p>;
}
