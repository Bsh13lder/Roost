import { useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { Badge } from "../../ui/Badge";
import { Button } from "../../ui/Button";
import { IconButton } from "../../ui/IconButton";
import { Input } from "../../ui/Input";
import { CloseIcon } from "../icons";
import type { ApprovalAnswerExtra, ApprovalCardOut, ChoiceOut } from "../../api/types";
import { closedLine } from "../../lib/approvals";
import {
  CHOICE_DONE_LEAD, CHOICE_OWN_MAX, CHOICE_SEND, CHOICE_SHOW_OPTIONS, CHOICE_YOUR_ANSWER, DISMISS, FROM_WEB_CONTENT, SAFE_MARK,
  TYPE_YOUR_OWN,
} from "./constants";
import { useAnswer } from "./useAnswer";

type Send = ReturnType<typeof useAnswer>["send"];

function OwnAnswer({ pressed, send }: { pressed: boolean; send: Send }) {
  const [words, setWords] = useState("");
  const text = words.trim();
  return (
    <form className="choice__own" onSubmit={(e) => { e.preventDefault(); if (text) void send("own", { text }); }}>
      <Input controlSize="sm" aria-label={TYPE_YOUR_OWN} placeholder={TYPE_YOUR_OWN} maxLength={CHOICE_OWN_MAX}
        value={words} disabled={pressed} onChange={(e) => setWords(e.target.value)} />
      <Button size="sm" type="submit" disabled={pressed || !text}>{CHOICE_SEND}</Button>
    </form>
  );
}

function Options({ choice, pressed, send }: { choice: ChoiceOut; pressed: boolean; send: Send }) {
  return (
    <div className="choice__options">
      {choice.options.map((option, index) => {
        const safe = index === choice.safe;
        return (
          <Button key={index} size="sm" variant={safe ? "primary" : "secondary"} disabled={pressed}
            onClick={() => void send("pick", { choice: index })}>
            {option}{safe ? <span className="choice__safe">{SAFE_MARK}</span> : null}
          </Button>
        );
      })}
    </div>
  );
}

// An answered card: one calm line, a check and your answer; the question and the options wait behind Show options.
function ChoiceDone({ choice, answer }: { choice: ChoiceOut; answer: string }) {
  return (
    <details className="choice-done">
      <summary className="choice-done__line">
        <span className="choice-done__tick" aria-hidden="true">✓</span> {CHOICE_DONE_LEAD}{" "}
        <span className="choice-done__answer">{answer}</span>
        <span className="choice-done__more">{CHOICE_SHOW_OPTIONS}</span>
      </summary>
      <p className="choice-done__question">{choice.question}</p>
      <ul className="choice-done__options" aria-label="Options">
        {choice.options.map((option, index) => <li key={index}>{option}{option === answer ? CHOICE_YOUR_ANSWER : ""}</li>)}
      </ul>
    </details>
  );
}

// The words a press sends: the stored option it names, or your own.
const wordsOf = (choice: ChoiceOut | null | undefined, extra?: string | ApprovalAnswerExtra): string | null =>
  typeof extra === "object" ? (extra.text ?? (extra.choice === undefined ? null : choice?.options[extra.choice] ?? null)) : null;

// An options card: the question, one button per option (the safe one first in weight), your own words when allowed,
// and Dismiss, which counts as No. Text is always React text. Once answered it shrinks to ChoiceDone, from what was
// pressed here or from the answer line that followed it in the chat (`answer`, lib/approvals.ts pairCardAnswers).
export function ChoiceCard({ card: incoming, answer }: { card: ApprovalCardOut; answer?: string }) {
  const { card, pressed, error, send: sendAnswer, landed } = useAnswer(incoming);
  const [said, setSaid] = useState<string | null>(null);
  const send: Send = (kind, extra) => { setSaid(wordsOf(incoming.choice, extra)); return sendAnswer(kind, extra); };
  const choice = card.choice;
  const words = answer ?? (landed ? said : null); // the chat's answer line is the truth once it is there
  if (card.state === "approved" && choice && words) return <ChoiceDone choice={choice} answer={words} />;
  if (card.state !== "open" || !choice) return <p className="approval-line">{closedLine(card)}</p>;
  return (
    <div className="approval choice" role="group" aria-label="Needs your choice">
      {card.tainted ? <Badge tone="danger" className="message__taint">{FROM_WEB_CONTENT}</Badge> : null}
      <p className="choice__question">{choice.question}</p>
      <Options choice={choice} pressed={pressed} send={send} />
      {choice.own ? <OwnAnswer pressed={pressed} send={send} /> : null}
      <div className="choice__foot">
        {choice.why ? <p className="choice__why">{choice.why}</p> : <span />}
        <IconButton size="sm" label={DISMISS} icon={<CloseIcon />} disabled={pressed} onClick={() => void send("no")} />
      </div>
      {error ? <ErrorNotice message={error} /> : null}
    </div>
  );
}
