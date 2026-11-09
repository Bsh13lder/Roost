import { useState, type FormEvent } from "react";
import { Button } from "../../ui/Button";
import { Field } from "../../ui/Field";
import { Input } from "../../ui/Input";
import { ACCOUNT_MAX_CHARS } from "./constants";
import { NEVER_SEES_PASSWORD } from "../../lib/stuck";

interface GiveBackFormProps {
  host?: string; // the site the computer is on, when known
  signIn?: boolean; // a Sign-in card: ask "Keep me signed in on this computer?" with Yes / No, this time
  busy: boolean;
  error: string | null; // why the last give-back failed
  onConfirm: (account: string | undefined, keep?: boolean) => void;
  onBack: () => void;
}

const TOO_LONG = `Keep the account to ${ACCOUNT_MAX_CHARS} characters or fewer.`;
const KEEP_QUESTION = "Keep me signed in on this computer?";

function hintFor(host: string | undefined, signIn: boolean): string | undefined {
  const saved = host ? `Saved for ${host}, so the bot knows which one it is signed in with.` : undefined;
  if (!signIn) return saved;
  return saved ? `${saved} ${NEVER_SEES_PASSWORD}` : NEVER_SEES_PASSWORD;
}

// "Which account did you use?" (optional): the label is kept in Vault: site logins, never a password.
export function GiveBackForm({ host, signIn = false, busy, error, onConfirm, onBack }: GiveBackFormProps) {
  const [account, setAccount] = useState("");
  const [tooLong, setTooLong] = useState(false);
  const confirm = (keep?: boolean) => {
    const label = account.trim();
    if (label.length > ACCOUNT_MAX_CHARS) return setTooLong(true);
    setTooLong(false);
    if (keep === undefined) onConfirm(label || undefined);
    else onConfirm(label || undefined, keep);
  };
  // Enter in the account box keeps the login on a Sign-in card (the primary answer), as the button does.
  const submit = (event: FormEvent) => {
    event.preventDefault();
    confirm(signIn ? true : undefined);
  };
  return (
    <form className="give-back" onSubmit={submit}>
      <Field label="Which account did you use?" optional className="give-back__field"
        hint={hintFor(host, signIn)}
        error={tooLong ? TOO_LONG : error}>
        <Input value={account} onChange={(event) => setAccount(event.target.value)} controlSize="md"
          autoComplete="off" autoFocus />
      </Field>
      {signIn ? (
        <div className="give-back__actions" role="group" aria-label={KEEP_QUESTION}>
          <span className="give-back__question">{KEEP_QUESTION}</span>
          <Button type="submit" variant="primary" size="md" loading={busy}>Yes, keep me signed in</Button>
          <Button variant="secondary" size="md" disabled={busy} onClick={() => confirm(false)}>No, this time</Button>
          <Button variant="ghost" size="md" disabled={busy} onClick={onBack}>Back</Button>
        </div>
      ) : (
        <div className="give-back__actions">
          <Button type="submit" variant="primary" size="md" loading={busy}>Give it back</Button>
          <Button variant="ghost" size="md" disabled={busy} onClick={onBack}>Back</Button>
        </div>
      )}
    </form>
  );
}
