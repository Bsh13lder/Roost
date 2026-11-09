import { useEffect, useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { Button } from "../../ui/Button";
import { Field } from "../../ui/Field";
import { Input } from "../../ui/Input";
import { describeError } from "../../api/client";
import { getPayFields, payCard } from "../../api/payments";
import type { ApprovalCardOut, CardPart, PayFieldsOut, PayIn } from "../../api/types";
import { StepRow } from "./StepRow";
import {
  CARD_PART_AUTOCOMPLETE, CARD_PART_LABELS, CARD_PART_MAX, DONT_PAY, PAY_CARD_NAME, PAY_FIELDS_FAILED,
  PAY_IT, PAY_LOADING, PAY_NEW_CARD, PAY_NO_FIELDS, PAY_NOTE, PAY_SAVE_CARD, savedCardLabel,
} from "./constants";
import { closedLine } from "../../lib/approvals";
import { useAnswer } from "./useAnswer";

type Values = Partial<Record<CardPart, string>>;
const NEW = "new";

// The Pay card (owner, 2026-11-05): the bot reached Pay; the fields are only the card parts the page asks for. A saved
// card fills all but the security code, which is asked every time. Pay sends the card in the request body only (never
// kept in the store) and Roost types it into the page, then clicks the same Pay button; Don't pay answers No.
export function PayCard({ card: incoming }: { card: ApprovalCardOut }) {
  const { card, pressed, error, send } = useAnswer(incoming);
  const fields = usePayFields(incoming.id, card.state === "open");
  const [values, setValues] = useState<Values>({});
  const [picked, setPicked] = useState<string>(NEW);
  const [save, setSave] = useState(false);
  const [paying, setPaying] = useState(false);
  const [paid, setPaid] = useState<ApprovalCardOut | null>(null);
  const [payError, setPayError] = useState<string | null>(null);
  const shown = card.state !== "open" ? card : (paid ?? card);
  if (shown.state !== "open") return <p className="approval-line">{closedLine(shown)}</p>;
  const info = fields.data;
  const saved = info?.cards ?? [];
  const usingSaved = picked !== NEW && saved.some((c) => c.id === picked);
  const parts = (info?.parts ?? []).filter((part) => !usingSaved || part === "cvc");
  const busy = pressed || paying;

  const pay = async () => {
    setPaying(true);
    setPayError(null);
    const body: PayIn = usingSaved ? { card_id: picked, cvc: values.cvc ?? "" } : { ...values, save };
    try {
      setPaid(await payCard(card.id, body));
      setValues({});
    } catch (err) {
      setPayError(describeError(err));
      setValues((now) => ({ ...now, cvc: "" }));    // the security code is typed again every time
      setPaying(false);
    }
  };

  return (
    <div className="approval approval--pay" role="group" aria-label={PAY_CARD_NAME}>
      <ul className="approval__steps">
        {card.steps.map((step, index) => <StepRow key={index} cardId={card.id} index={index} step={step} />)}
      </ul>
      {fields.loading ? <p className="approval__note">{PAY_LOADING}</p> : null}
      {fields.failed ? <p className="approval__note">{PAY_FIELDS_FAILED}</p> : null}
      {info?.refusal ? <p className="approval__note" role="note">{info.refusal}</p> : null}
      {info && !info.refusal && info.parts.length === 0 ? <p className="approval__note">{PAY_NO_FIELDS}</p> : null}
      {saved.length > 0 && (info?.parts.length ?? 0) > 0 ? (
        <fieldset className="pay-card__saved" disabled={busy}>
          {saved.map((c) => (
            <label key={c.id} className="pay-card__pick">
              <input type="radio" name={`pay-${card.id}`} checked={picked === c.id} onChange={() => setPicked(c.id)} />
              {savedCardLabel(c.brand, c.last4)}
            </label>
          ))}
          <label className="pay-card__pick">
            <input type="radio" name={`pay-${card.id}`} checked={picked === NEW} onChange={() => setPicked(NEW)} />
            {PAY_NEW_CARD}
          </label>
        </fieldset>
      ) : null}
      {parts.length > 0 ? (
        <form className="pay-card__fields" autoComplete="on" onSubmit={(event) => { event.preventDefault(); void pay(); }}>
          {parts.map((part) => (
            <Field key={part} label={CARD_PART_LABELS[part]}>
              <Input controlSize="sm" value={values[part] ?? ""} disabled={busy} maxLength={CARD_PART_MAX[part]}
                autoComplete={CARD_PART_AUTOCOMPLETE[part]} inputMode={part === "name" ? "text" : "numeric"}
                type={part === "cvc" ? "password" : "text"} spellCheck={false}
                onChange={(event) => setValues((now) => ({ ...now, [part]: event.target.value }))} />
            </Field>
          ))}
          {!usingSaved ? (
            <label className="pay-card__save">
              <input type="checkbox" checked={save} disabled={busy} onChange={(event) => setSave(event.target.checked)} />
              {PAY_SAVE_CARD}
            </label>
          ) : null}
        </form>
      ) : null}
      <p className="approval__note">{PAY_NOTE}</p>
      <div className="approval__actions">
        <Button variant="primary" size="sm" disabled={busy || fields.loading} onClick={() => void pay()}>{PAY_IT}</Button>
        <Button size="sm" disabled={busy} onClick={() => void send("no")}>{DONT_PAY}</Button>
      </div>
      {error ? <ErrorNotice message={error} /> : null}
      {payError ? <ErrorNotice message={payError} /> : null}
    </div>
  );
}

function usePayFields(cardId: string, open: boolean) {
  const [data, setData] = useState<PayFieldsOut | null>(null);
  const [loading, setLoading] = useState(open);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!open) return undefined;
    let live = true;
    getPayFields(cardId)
      .then((got) => { if (live) setData(got); })
      .catch(() => { if (live) setFailed(true); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [cardId, open]);
  return { data, loading, failed };
}
