import { useState } from "react";
import { answerApproval } from "../../api/approvals";
import { ApiError, describeError } from "../../api/client";
import type { ApprovalAnswer, ApprovalAnswerExtra, ApprovalCardOut } from "../../api/types";
import { ALREADY_ANSWERED } from "./constants";

// One press per card: the buttons stay disabled once an answer is sent, whether it landed or the card was already
// answered. Another failure is said on the card and frees the buttons for a second try.
export function useAnswer(card: ApprovalCardOut) {
  const [answered, setAnswered] = useState<ApprovalCardOut | null>(null);
  const [pressed, setPressed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const send = async (answer: ApprovalAnswer, extra?: string | ApprovalAnswerExtra) => {
    if (pressed) return;
    setPressed(true);
    setError(null);
    try {
      setAnswered(await answerApproval(card.id, answer, extra));
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError(ALREADY_ANSWERED);
      } else {
        setError(describeError(err));
        setPressed(false);
      }
    }
  };
  // A closed live copy wins; an open one gives way to what the buttons just got back.
  const current = card.state !== "open" ? card : (answered ?? card);
  return { card: current, pressed, error, send, landed: answered !== null };
}
