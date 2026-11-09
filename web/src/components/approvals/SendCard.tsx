import { useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { Badge } from "../../ui/Badge";
import { Button } from "../../ui/Button";
import { Textarea } from "../../ui/Textarea";
import type { ApprovalCardOut } from "../../api/types";
import { StepRow } from "./StepRow";
import {
  CHANGE_IT, CHANGE_IT_LABEL, CHANGE_MAX_CHARS, DONT_SEND, FROM_WEB_CONTENT, SEND_CARD_NAME, SEND_CHANGE, SEND_IT,
} from "./constants";
import { closedLine } from "../../lib/approvals";
import { useAnswer } from "./useAnswer";

// The Send card (owner, 2026-11-03): the bot filled the form with its own text; every box it typed shows whole, and
// Send · Don't send · Change it… answer it. Change it… asks what it should say instead and sends that as your words.
export function SendCard({ card: incoming }: { card: ApprovalCardOut }) {
  const { card, pressed, error, send } = useAnswer(incoming);
  const [editing, setEditing] = useState(false);
  const [words, setWords] = useState("");
  if (card.state !== "open") return <p className="approval-line">{closedLine(card)}</p>;
  return (
    <div className="approval" role="group" aria-label={SEND_CARD_NAME}>
      {card.from_web ? <Badge tone="danger" className="message__taint">{FROM_WEB_CONTENT}</Badge> : null}
      <ul className="approval__steps">
        {card.steps.map((step, index) => <StepRow key={index} cardId={card.id} index={index} step={step} />)}
      </ul>
      {editing ? (
        <div className="approval__edit">
          <Textarea aria-label={CHANGE_IT_LABEL} placeholder={CHANGE_IT_LABEL} value={words} maxLength={CHANGE_MAX_CHARS}
            disabled={pressed} onChange={(event) => setWords(event.target.value)} />
          <Button variant="primary" size="sm" disabled={pressed || !words.trim()}
            onClick={() => void send("edit", words.trim())}>{SEND_CHANGE}</Button>
        </div>
      ) : null}
      <div className="approval__actions">
        <Button variant="primary" size="sm" disabled={pressed} onClick={() => void send("yes")}>{SEND_IT}</Button>
        <Button size="sm" disabled={pressed} onClick={() => void send("no")}>{DONT_SEND}</Button>
        <Button size="sm" disabled={pressed || editing} onClick={() => setEditing(true)}>{CHANGE_IT}</Button>
      </div>
      {error ? <ErrorNotice message={error} /> : null}
    </div>
  );
}
