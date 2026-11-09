// web/src/hooks/useAnsweredCards.ts: which of your answer lines a chat need not draw, because the options card above
// already says "✓ You answered". A card this page never heard of (a reload after it closed) is read once, read-only,
// the same request the card's own row makes (api/approvals.ts shares it).
import { useEffect, useMemo, useState } from "react";
import { getApproval } from "../api/approvals";
import type { ApprovalCardOut, MessageOut } from "../api/types";
import { answerLines, hiddenAnswerIds } from "../lib/approvals";

type Cards = Readonly<Record<string, ApprovalCardOut>>;
const NONE: ReadonlySet<string> = new Set();

function useClosedCards(wanted: readonly string[]): Cards {
  const [found, setFound] = useState<Cards>({});
  const key = wanted.join(" ");
  useEffect(() => {
    let current = true;
    for (const cardId of key ? key.split(" ") : []) {
      getApproval(cardId, false)
        .then((card) => { if (current) setFound((was) => ({ ...was, [cardId]: card })); })
        .catch(() => undefined);
    }
    return () => { current = false; };
  }, [key]);
  return found;
}

// `cards` undefined (a room: several bots, so a line cannot be paired) hides nothing.
export function useHiddenAnswers(messages: readonly MessageOut[], cards: Cards | undefined): ReadonlySet<string> {
  const lines = useMemo(() => (cards ? answerLines(messages) : new Map()), [cards, messages]);
  const wanted = useMemo(
    () => (cards ? [...lines].filter(([id, line]) => line.kind === "ask" && !(id in cards)).map(([id]) => id).sort() : []),
    [cards, lines],
  );
  const closed = useClosedCards(wanted);
  return useMemo(() => (cards ? hiddenAnswerIds(lines, { ...closed, ...cards }) : NONE), [cards, closed, lines]);
}
