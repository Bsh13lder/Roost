// web/src/components/SecretField.tsx — the Sign-in card's masked field (B3, owner decision 2026-10-23).
// You type your password or code here; Send hands it to the server, which types it straight into the box on the
// bot's own computer. The value lives only in this field's own state, never in a store, a log or the URL, and the
// field empties the moment you send it, whatever the answer. A password has Save in Vault (on by default; Vault:
// passwords, 2026-11-08): the server then keeps it sealed for this site. A one-time code is never saved.
import { useState, type FormEvent } from "react";
import type { SecretFieldKind } from "../api/types";
import { SAVE_IN_VAULT } from "./vault/constants";

export const SECRET_MAX_CHARS = 256; // the server's SECRET_VALUE_MAX_CHARS

export function secretExplanation(host: string, kind: SecretFieldKind, botName: string): string {
  return `Type your ${host} ${kind}; it goes straight into the box on ${botName}'s computer. The bot never sees it.`;
}

export function SecretField({ host, kind, busy, onSend }: {
  host: string; kind: SecretFieldKind; busy: boolean; onSend: (value: string, save: boolean) => Promise<void>;
}) {
  const [value, setValue] = useState("");
  const [save, setSave] = useState(true);
  const savable = kind === "password";
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const typed = value;
    setValue("");
    if (typed) void onSend(typed, savable && save);
  };
  return (
    <form className="secret-field" onSubmit={submit}>
      <input className="field secret-field__input" type="password" autoComplete="off" spellCheck={false}
        maxLength={SECRET_MAX_CHARS} aria-label={`Your ${host} ${kind}`} value={value} disabled={busy}
        onChange={(event) => setValue(event.target.value)} />
      <button type="submit" className="btn btn--primary btn--small" disabled={busy || !value}>Send</button>
      {savable ? (
        <label className="secret-field__save">
          <input type="checkbox" checked={save} disabled={busy} onChange={(event) => setSave(event.target.checked)} />
          {SAVE_IN_VAULT}
        </label>
      ) : null}
    </form>
  );
}
