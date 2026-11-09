import { useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { Badge } from "../../ui/Badge";
import { Button } from "../../ui/Button";
import { Textarea } from "../../ui/Textarea";
import type { ApprovalCardOut } from "../../api/types";
import { StepRow } from "./StepRow";
import { ACCEPT, DECLINE, EDIT, EDIT_LABEL, FROM_WEB_CONTENT, PROPOSAL_CARD_NAME, SEND } from "./constants";
import { closedLine } from "../../lib/approvals";
import { useAnswer } from "./useAnswer";

const EDIT_MAX_CHARS = 2000; // the server's limit on an Edit reply

// The Proposal card (the wire's "plan"): numbered steps and Accept · Edit · Decline. Edit asks what should change.
export function PlanCard({ card: incoming }: { card: ApprovalCardOut }) {
  const { card, pressed, error, send } = useAnswer(incoming);
  const [editing, setEditing] = useState(false);
  const [words, setWords] = useState("");
  if (card.state !== "open") return <p className="approval-line">{closedLine(card)}</p>;
  return (
    <div className="approval approval--plan" role="group" aria-label={PROPOSAL_CARD_NAME}>
      <div className="approval__head">
        <span className="approval__name">{PROPOSAL_CARD_NAME}</span>
        {card.tainted ? <Badge tone="danger" className="message__taint">{FROM_WEB_CONTENT}</Badge> : null}
      </div>
      <ol className="approval__steps">
        {card.steps.map((step, index) => <StepRow key={index} cardId={card.id} index={index} step={step} numbered />)}
      </ol>
      {editing ? (
        <div className="approval__edit">
          <Textarea aria-label={EDIT_LABEL} placeholder={EDIT_LABEL} value={words} maxLength={EDIT_MAX_CHARS}
            disabled={pressed} onChange={(event) => setWords(event.target.value)} />
          <Button variant="primary" size="sm" disabled={pressed || !words.trim()}
            onClick={() => void send("edit", words.trim())}>{SEND}</Button>
        </div>
      ) : null}
      <div className="approval__actions">
        <Button variant="primary" size="sm" disabled={pressed} onClick={() => void send("accept")}>{ACCEPT}</Button>
        <Button size="sm" disabled={pressed} onClick={() => setEditing(true)}>{EDIT}</Button>
        <Button size="sm" disabled={pressed} onClick={() => void send("decline")}>{DECLINE}</Button>
      </div>
      {error ? <ErrorNotice message={error} /> : null}
    </div>
  );
}
