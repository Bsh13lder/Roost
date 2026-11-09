// The Save a password sheet (Vault: passwords V3, owner 2026-11-08), opened from Settings' Add a login and from the
// chat composer's + menu. It posts only to /api/vault/passwords, never to the chat. The password lives only in the
// form's own state: it is emptied the moment Save is pressed, whatever the answer, and goes when the sheet closes.
import { useState, type FormEvent } from "react";
import { Button } from "../../ui/Button";
import { Field } from "../../ui/Field";
import { Input } from "../../ui/Input";
import { Sheet } from "../../ui/Sheet";
import { useOptionalToast } from "../../ui/Toast";
import { ErrorNotice } from "../ErrorNotice";
import { describeError } from "../../api/client";
import { saveVaultPassword, type VaultPasswordOut } from "../../api/vaultPasswords";
import {
  PASSWORD_LABEL, SAVE_PASSWORD_DESCRIPTION, SAVE_PASSWORD_TITLE, SAVED_TOAST, SITE_LABEL, SITE_PLACEHOLDER,
  USERNAME_LABEL, VAULT_HOST_MAX, VAULT_PASSWORD_MAX, VAULT_USERNAME_MAX,
} from "./constants";

export interface SavePasswordSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSaved?: (login: VaultPasswordOut) => void;
}

export function SavePasswordSheet({ open, onOpenChange, onSaved }: SavePasswordSheetProps) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange} title={SAVE_PASSWORD_TITLE} description={SAVE_PASSWORD_DESCRIPTION}>
      {open ? <SavePasswordForm onDone={() => onOpenChange(false)} onSaved={onSaved} /> : null}
    </Sheet>
  );
}

function SavePasswordForm({ onDone, onSaved }: { onDone: () => void; onSaved?: (login: VaultPasswordOut) => void }) {
  const toast = useOptionalToast();
  const [host, setHost] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const typed = password;
    setPassword("");
    if (!host.trim() || !typed) return;
    setBusy(true);
    setError(null);
    try {
      const saved = await saveVaultPassword({ host: host.trim(), username: username.trim(), password: typed });
      toast?.show(SAVED_TOAST, { tone: "ok" });
      onSaved?.(saved);
      onDone();
    } catch (err) {
      setError(describeError(err));
      setBusy(false);
    }
  };
  const cancel = () => {
    setPassword("");
    onDone();
  };
  return (
    <form className="vault-form" onSubmit={(event) => void submit(event)}>
      <Field label={SITE_LABEL}>
        <Input type="text" inputMode="url" autoComplete="off" spellCheck={false} placeholder={SITE_PLACEHOLDER}
          maxLength={VAULT_HOST_MAX} value={host} disabled={busy} onChange={(event) => setHost(event.target.value)} />
      </Field>
      <Field label={USERNAME_LABEL} optional>
        <Input type="text" autoComplete="off" spellCheck={false} maxLength={VAULT_USERNAME_MAX} value={username}
          disabled={busy} onChange={(event) => setUsername(event.target.value)} />
      </Field>
      <Field label={PASSWORD_LABEL}>
        <Input type="password" autoComplete="new-password" spellCheck={false} maxLength={VAULT_PASSWORD_MAX}
          value={password} disabled={busy} onChange={(event) => setPassword(event.target.value)} />
      </Field>
      {error ? <ErrorNotice message={error} /> : null}
      <div className="vault-form__actions">
        <Button variant="ghost" onClick={cancel}>Cancel</Button>
        <Button type="submit" variant="primary" loading={busy} disabled={!host.trim() || !password}>Save</Button>
      </div>
    </form>
  );
}
