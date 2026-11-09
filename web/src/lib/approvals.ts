// web/src/lib/approvals.ts: the pieces of the Ask and Proposal cards that need no React.
import type { ApprovalCardOut, ApprovalMessageData, MessageOut } from "../api/types";
import {
  ACCEPTED_PROPOSAL_LINE, CHANGED_LEAD, CHOICE_ANSWERED_LINE, CHOICE_DISMISSED_LINE, DECLINED_PROPOSAL_LINE, EDITED_PROPOSAL_LINE,
  EXPIRED_LINE, FAILED_LINE, NOT_PAID_LEAD, NOT_SENT_LEAD, PAID_LEAD, SENT_LEAD,
} from "../components/approvals/constants";

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

// An "approval" message's body. Anything that is not the expected shape is null, and the row shows nothing odd.
export function parseApprovalMessage(body: string): ApprovalMessageData | null {
  try {
    const data: unknown = JSON.parse(body);
    if (!isRecord(data) || typeof data.card_id !== "string") return null;
    const steps = Array.isArray(data.steps) ? data.steps.filter((t): t is string => typeof t === "string") : [];
    return { card_id: data.card_id, kind: data.kind === "plan" ? "plan" : "ask", steps };
  } catch {
    return null;
  }
}

// The loaded open cards with every live frame on top: the live copy is the newer one.
export function mergeApprovals(
  rest: readonly ApprovalCardOut[], live: Readonly<Record<string, ApprovalCardOut>>,
): Record<string, ApprovalCardOut> {
  return { ...Object.fromEntries(rest.map((card) => [card.id, card])), ...live };
}

// The answer as one quiet line, for a card that is no longer open. The first step names an Ask card's question.
export function closedLine(
  card: Pick<ApprovalCardOut, "kind" | "state" | "steps" | "choice" | "send" | "pay">, titleFallback = "",
): string {
  const title = card.steps[0]?.title ?? titleFallback;
  if (card.state === "expired") return EXPIRED_LINE;
  if (card.state === "failed") return FAILED_LINE;
  if (card.choice) return card.state === "declined" ? CHOICE_DISMISSED_LINE : CHOICE_ANSWERED_LINE;
  if (card.kind === "plan") {
    return card.state === "approved" ? ACCEPTED_PROPOSAL_LINE
      : card.state === "edited" ? EDITED_PROPOSAL_LINE : DECLINED_PROPOSAL_LINE;
  }
  const plain = plainTitle(title);
  if (card.pay) return `${card.state === "approved" ? PAID_LEAD : NOT_PAID_LEAD} ${plain}`;
  if (card.send) {
    const lead = card.state === "approved" ? SENT_LEAD : card.state === "edited" ? CHANGED_LEAD : NOT_SENT_LEAD;
    return `${lead} ${plain}`;
  }
  return card.state === "approved" ? `You said yes: ${plain}` : `You said no: ${plain}`;
}

// A step's title in plain words: "Run a program: curl -sI https://…" says only "Run a program" (the activity pill
// plan: no code in the chat). A title with no colon is already plain.
export function plainTitle(title: string): string {
  const cut = title.indexOf(": ");
  return cut > 0 ? title.slice(0, cut) : title;
}

// Each card's answer line: the card_answer you posted after its "approval" message and before the next one, with
// that message's id and the card's kind. A bot has one open card at a time (talk/runner.py), so in its chat the line
// that follows a card answers that card.
export interface AnswerLine { id: string; body: string; kind: ApprovalMessageData["kind"] }
export function answerLines(messages: readonly MessageOut[]): ReadonlyMap<string, AnswerLine> {
  const lines = new Map<string, AnswerLine>();
  let waiting: ApprovalMessageData | null = null;
  for (const message of messages) {
    if (message.kind === "approval") waiting = parseApprovalMessage(message.body);
    else if (message.kind === "card_answer" && waiting) {
      lines.set(waiting.card_id, { id: message.id, body: message.body, kind: waiting.kind });
      waiting = null;
    }
  }
  return lines;
}

// Each card's answer words, by card id (what an options card shrinks to).
export function pairCardAnswers(messages: readonly MessageOut[]): ReadonlyMap<string, string> {
  return new Map([...answerLines(messages)].map(([cardId, line]) => [cardId, line.body]));
}

// The answer lines a chat need not draw: those under a card that shows the answer itself, an answered options card
// ("✓ You answered") or a closed yes/no card ("You said yes: …"). A dismissed options card keeps your line.
export function hiddenAnswerIds(
  lines: ReadonlyMap<string, AnswerLine>, cards: Readonly<Record<string, ApprovalCardOut | undefined>>,
): ReadonlySet<string> {
  const hidden = new Set<string>();
  for (const [cardId, line] of lines) {
    const card = cards[cardId];
    if (!card || card.kind !== "ask") continue;
    const choiceAnswered = card.choice && card.state === "approved";
    const yesNoClosed = !card.choice && (card.state === "approved" || card.state === "declined");
    if (choiceAnswered || yesNoClosed) hidden.add(line.id);
  }
  return hidden;
}
