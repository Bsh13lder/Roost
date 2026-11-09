import { useEffect, useState } from "react";
import { getApproval } from "../../api/approvals";
import { parseApprovalMessage, plainTitle } from "../../lib/approvals";
import type { ApprovalCardOut } from "../../api/types";
import { ApprovalCard } from "./ApprovalCard";
import { ChoiceCard } from "./ChoiceCard";
import { PlanCard } from "./PlanCard";

// A card this page never heard of (a reload after it closed) but that was answered: ask for it once, read-only,
// so an options card can still shrink to its answer. Nothing is asked for a card no answer line follows.
function useClosedCard(cardId: string | null, known: boolean, answered: boolean): ApprovalCardOut | null {
  const [card, setCard] = useState<ApprovalCardOut | null>(null);
  useEffect(() => {
    if (!cardId || known || !answered) return undefined;
    let current = true;
    getApproval(cardId, false).then((found) => { if (current) setCard(found); }).catch(() => undefined);
    return () => { current = false; };
  }, [cardId, known, answered]);
  return card;
}

// An "approval" message in the chat: the live card by its id (Ask or Proposal). A page that never heard of the card
// shows the question's words only, with no buttons: a button here could not know the card is still open. `answers`
// is each card's answer line in this chat (lib/approvals.ts pairCardAnswers).
export function ApprovalMessage({ body, cards, answers }: {
  body: string; cards: Readonly<Record<string, ApprovalCardOut>>; answers?: ReadonlyMap<string, string>;
}) {
  const data = parseApprovalMessage(body);
  const answer = data ? answers?.get(data.card_id) : undefined;
  const fetched = useClosedCard(data?.kind === "ask" ? data.card_id : null, !!data && data.card_id in cards, answer !== undefined);
  if (!data) return null;
  const live = cards[data.card_id];
  // A closed card read once after a reload says its answer in plain words, like a live one does.
  const card = live ?? (fetched && fetched.state !== "open" ? fetched : undefined);
  if (!card) return <p className="approval-line">{data.steps.map(plainTitle).join(" · ")}</p>;
  if (card.choice) return <ChoiceCard key={card.id} card={card} answer={answer} />;
  return card.kind === "plan" ? <PlanCard key={card.id} card={card} /> : <ApprovalCard key={card.id} card={card} />;
}
