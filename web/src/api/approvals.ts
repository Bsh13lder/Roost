// web/src/api/approvals.ts: the Ask and Proposal cards' buttons (approval modes).
import { apiRequest } from "./client";
import type { ApprovalAnswer, ApprovalAnswerExtra, ApprovalCardOut } from "./types";

const cardPath = (cardId: string) => `/api/approvals/${encodeURIComponent(cardId)}`;

export const listApprovals = () => apiRequest<ApprovalCardOut[]>("GET", "/api/approvals");
// `full` keeps whole diffs; otherwise the server cuts each at 400 lines.
// Readers of the same card at the same moment (a chat row and its list) share one request; a settled one is not kept.
const reading = new Map<string, Promise<ApprovalCardOut>>();
export function getApproval(cardId: string, full: boolean): Promise<ApprovalCardOut> {
  const path = full ? `${cardPath(cardId)}?full=1` : cardPath(cardId);
  const known = reading.get(path);
  if (known) return known;
  const request = apiRequest<ApprovalCardOut>("GET", path).finally(() => reading.delete(path));
  reading.set(path, request);
  return request;
}
export const answerApproval = (cardId: string, answer: ApprovalAnswer, extra?: string | ApprovalAnswerExtra) =>
  apiRequest<ApprovalCardOut>("POST", `${cardPath(cardId)}/answer`, {
    answer, ...(typeof extra === "string" ? { text: extra } : extra),
  });
