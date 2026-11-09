import { useState } from "react";
import { ApiError, describeError } from "../../api/client";
import { forgetMemory } from "../../api/memories";
import { rememberOffer } from "../../api/threads";
import type { MessageOut } from "../../api/types";
import { forgotLine, notRememberedLine, parseMemoryOffer, rememberedLine } from "../../lib/memoryOffer";
import { WebMark } from "./WebMark";
import { Button } from "../../ui/Button";

type Shown = { state: "offered" } | { state: "remembered"; memoryId: string } | { state: "forgot" } | { state: "gone" };

const ALREADY_FORGOTTEN = "Already forgotten.";
const NOT_REMEMBERED = "Not remembered";

const startFrom = (memoryId: string | null): Shown => (memoryId ? { state: "remembered", memoryId } : { state: "offered" });

// "Not remembered: ..." in the chat when a bot could not save a memory itself (it read a web page): the whole
// text, the from-web mark, and Remember it, which saves it as your own. Then "Remembered: ..." with Undo.
export function MemoryOfferRow({ message }: { message: MessageOut }) {
  const offer = parseMemoryOffer(message.body);
  const [shown, setShown] = useState<Shown>(() => startFrom(offer?.memory_id ?? null));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!offer) return <li className="message message--memory">{NOT_REMEMBERED}</li>;

  const act = async (step: () => Promise<Shown>) => {
    setBusy(true);
    setError(null);
    try {
      setShown(await step());
    } catch (err) {
      if (err instanceof ApiError && err.status === 404 && shown.state === "remembered") setShown({ state: "gone" });
      else setError(describeError(err));
    } finally {
      setBusy(false);
    }
  };
  const remember = () => act(async () => startFrom((await rememberOffer(message.thread_id, message.id)).memory.id));
  const undo = (memoryId: string) => act(async () => { await forgetMemory(memoryId); return { state: "forgot" }; });

  if (shown.state === "forgot") return <li className="message message--memory">{forgotLine(offer.text)}</li>;
  if (shown.state === "gone") return <li className="message message--memory">{ALREADY_FORGOTTEN}</li>;
  const remembered = shown.state === "remembered";
  return (
    <li className="message message--memory message--memory-offer" data-message-id={message.id}>
      <span>{remembered ? rememberedLine(offer.text) : notRememberedLine(offer.text)}</span>
      {message.tainted ? <WebMark className="message__taint" /> : null}
      {remembered ? (
        <Button variant="ghost" size="sm" loading={busy} aria-label={`Undo: forget ${offer.text}`}
          onClick={() => void undo(shown.memoryId)}>Undo</Button>
      ) : (
        <Button variant="secondary" size="sm" loading={busy} aria-label={`Remember it: ${offer.text}`}
          onClick={() => void remember()}>Remember it</Button>
      )}
      {error ? <span role="alert">{error}</span> : null}
    </li>
  );
}
