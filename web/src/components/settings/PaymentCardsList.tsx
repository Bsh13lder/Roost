import { useState } from "react";
import { Button } from "../../ui/Button";
import { ErrorNotice } from "../ErrorNotice";
import { deletePaymentCard } from "../../api/payments";
import { describeError } from "../../api/client";
import type { SavedCardOut } from "../../api/types";
import { savedCardLabel } from "../approvals/constants";

export const PAYMENT_CARDS_TITLE = "Vault: cards";

// Vault: cards (owner, 2026-11-05): the cards you saved from a Pay card, as brand and last 4 only. Roost never keeps
// the security code, so a Pay card always asks for it. Delete removes a card at once.
export function PaymentCardsList({ cards }: { cards: readonly SavedCardOut[] }) {
  const [shown, setShown] = useState<readonly SavedCardOut[]>(cards);
  const [error, setError] = useState<string | null>(null);
  const remove = async (id: string) => {
    setError(null);
    try {
      await deletePaymentCard(id);
      setShown((now) => now.filter((c) => c.id !== id));
    } catch (err) {
      setError(describeError(err));
    }
  };
  return (
    <>
      {shown.length === 0 ? (
        <p className="settings-sheet__note">No saved cards. Tick Save this card on a Pay card to keep one.</p>
      ) : (
        <ul className="profile-card settings-sheet__list">
          {shown.map((c) => (
            <li key={c.id} className="settings-sheet__item">
              <span className="settings-sheet__item-main">
                <span className="settings-sheet__item-label">{savedCardLabel(c.brand, c.last4)}</span>
              </span>
              <Button size="sm" variant="danger" onClick={() => void remove(c.id)}>Delete</Button>
            </li>
          ))}
        </ul>
      )}
      {error ? <ErrorNotice message={error} /> : null}
      <p className="settings-sheet__note">Saved cards are encrypted. The security code is never kept.</p>
    </>
  );
}
