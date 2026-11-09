import { ErrorNotice } from "../ErrorNotice";
import { Badge } from "../../ui/Badge";
import { Button } from "../../ui/Button";
import type { ApprovalCardOut } from "../../api/types";
import { PayCard } from "./PayCard";
import { SendCard } from "./SendCard";
import { StepRow } from "./StepRow";
import { FROM_WEB_CONTENT, NO, OPEN_SITE, YES, YES_SESSION } from "./constants";
import { closedLine } from "../../lib/approvals";
import { useAnswer } from "./useAnswer";

// An Ask card: one step and Yes · Yes for this session (only when offered) · No; an Open card says Open · No. Once answered, or if it arrives
// closed, it is the answer as one quiet line.
export function ApprovalCard({ card }: { card: ApprovalCardOut }) {
  if (card.pay) return <PayCard card={card} />;
  return card.send ? <SendCard card={card} /> : <AskCard card={card} />;
}

function AskCard({ card: incoming }: { card: ApprovalCardOut }) {
  const { card, pressed, error, send } = useAnswer(incoming);
  if (card.state !== "open") return <p className="approval-line">{closedLine(card)}</p>;
  const opensSite = card.steps.length === 1 && card.steps[0].tool === "open_page" && card.steps[0].floor === "new_site";
  return (
    <div className="approval" role="group" aria-label="Needs your OK">
      {(card.from_web ?? card.tainted) ? <Badge tone="danger" className="message__taint">{FROM_WEB_CONTENT}</Badge> : null}
      <ul className="approval__steps">
        {card.steps.map((step, index) => <StepRow key={index} cardId={card.id} index={index} step={step} />)}
      </ul>
      <div className="approval__actions">
        <Button variant="primary" size="sm" disabled={pressed} onClick={() => void send("yes")}>{opensSite ? OPEN_SITE : YES}</Button>
        {card.session_offer ? (
          <Button size="sm" disabled={pressed} onClick={() => void send("yes_session")}>{YES_SESSION}</Button>
        ) : null}
        <Button size="sm" disabled={pressed} onClick={() => void send("no")}>{NO}</Button>
      </div>
      {error ? <ErrorNotice message={error} /> : null}
    </div>
  );
}
