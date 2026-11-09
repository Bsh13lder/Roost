import { useCallback, useEffect, useRef, useState } from "react";
import { Badge } from "../../ui/Badge";
import { Button } from "../../ui/Button";
import { Field } from "../../ui/Field";
import { Input } from "../../ui/Input";
import { ApiError, describeError } from "../../api/client";
import * as connectorsApi from "../../api/connectors";
import type { KeyRequestOut } from "../../api/connectors";
import { useLiveState } from "../../hooks/useLiveStore";
import { ADD_A_KEY, KEY_ADDED, KEY_HINT_NEW, KEY_LABEL, LIMITS, MARK, NOT_NOW, REQUEST_GONE, SAID_NOT_NOW, SAVE } from "./constants";

// The Add a key card a bot raises with request_connector: the service, its site and the bot's reason, and a
// write-only key field. Save makes the connector on the server (the same checks as the Connectors fold); the key
// is cleared from the page at once and is never in the chat. A 409 means another press answered it: it reloads.
export default function ConnectorAskCard({ requestId }: { requestId: string }) {
  const version = useLiveState().connectorVersion;
  const [request, setRequest] = useState<KeyRequestOut | null>(null);
  const [secret, setSecret] = useState("");
  const [gone, setGone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const latest = useRef(0);
  const load = useCallback(() => {
    const ticket = ++latest.current;
    connectorsApi.getKeyRequest(requestId)
      .then((loaded) => { if (ticket === latest.current) { setRequest(loaded); setGone(false); } })
      .catch((err: unknown) => {
        if (ticket !== latest.current) return;
        if (err instanceof ApiError && err.status === 404) setGone(true);
        else setError(describeError(err));
      });
  }, [requestId]);
  useEffect(() => load(), [load, version]);

  const decide = async (call: () => Promise<KeyRequestOut>) => {
    setBusy(true);
    setError(null);
    try { setRequest(await call()); setSecret(""); } catch (err) {
      if (err instanceof ApiError && err.status === 409) load();
      else setError(describeError(err));
    } finally { setBusy(false); }
  };
  if (gone) return <p className="skill-card__state">{REQUEST_GONE}</p>;
  if (request === null) return error ? <p className="skill-card__error" role="alert">{error}</p> : null;
  if (request.state !== "open") {
    return <p className="skill-card__state">{request.state === "saved" ? `${KEY_ADDED} · ${request.service}` : SAID_NOT_NOW}</p>;
  }
  return (
    <section className="skill-card" aria-label={ADD_A_KEY}>
      <p className="skill-card__kicker">{ADD_A_KEY}</p>
      <p className="skill-card__name">{request.service}</p>
      <p className="skill-card__when">{request.host}</p>
      <p className="skill-card__when">{request.why}</p>
      {request.tainted ? <Badge tone="danger">{MARK}</Badge> : null}
      <Field label={KEY_LABEL} hint={KEY_HINT_NEW}>
        <Input type="password" autoComplete="new-password" value={secret} maxLength={LIMITS.secret}
          onChange={(event) => setSecret(event.target.value)} />
      </Field>
      {error ? <p className="skill-card__error" role="alert">{error}</p> : null}
      <div className="skill-card__actions">
        <Button variant="primary" size="sm" loading={busy} disabled={!secret}
          onClick={() => void decide(() => connectorsApi.saveKeyRequest(requestId, secret))}>{SAVE}</Button>
        <Button variant="secondary" size="sm" disabled={busy}
          onClick={() => void decide(() => connectorsApi.declineKeyRequest(requestId))}>{NOT_NOW}</Button>
      </div>
    </section>
  );
}

