// web/src/api/payments.ts: the Pay card (roost/gateway/routes/payments.py) and Vault: cards.
import { apiRequest } from "./client";
import type { ApprovalCardOut, PayFieldsOut, PayIn, SavedCardOut } from "./types";

const payPath = (cardId: string) => `/api/approvals/${encodeURIComponent(cardId)}/pay`;

export const getPayFields = (cardId: string) => apiRequest<PayFieldsOut>("GET", payPath(cardId));
// The card goes only in this body: never in a URL, a log or the store.
export const payCard = (cardId: string, body: PayIn) => apiRequest<ApprovalCardOut>("POST", payPath(cardId), body);
export const listPaymentCards = () => apiRequest<SavedCardOut[]>("GET", "/api/payment-cards");
export const deletePaymentCard = (id: string) =>
  apiRequest<void>("DELETE", `/api/payment-cards/${encodeURIComponent(id)}`);
