import { useState } from "react";
import { Button } from "../../ui/Button";
import { Switch } from "../../ui/Switch";
import { ErrorNotice } from "../ErrorNotice";
import { describeError } from "../../api/client";
import { deleteVaultPassword, patchVaultPassword, type VaultPasswordOut } from "../../api/vaultPasswords";
import { SavePasswordSheet } from "../vault/SavePasswordSheet";
import {
  ADD_LOGIN, ALWAYS_LABEL, VAULT_PASSWORDS_EMPTY, VAULT_PASSWORDS_NOTE, deleteQuestion, loginDetail,
} from "../vault/constants";

// The saved login replaces its old row (saving the same site and user name again keeps its id), or joins the list.
const withLogin = (list: readonly VaultPasswordOut[], login: VaultPasswordOut): readonly VaultPasswordOut[] =>
  list.some((l) => l.id === login.id) ? list.map((l) => (l.id === login.id ? login : l)) : [...list, login];

// Vault: passwords (owner, 2026-11-08): your saved site logins as site, user name and last use. A password is never
// shown (there is no "show password"); Always for this site lets Roost type it with no card. Delete asks first.
export function VaultPasswordsList({ logins }: { logins: readonly VaultPasswordOut[] }) {
  const [shown, setShown] = useState<readonly VaultPasswordOut[]>(logins);
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = async (work: () => Promise<void>) => {
    setError(null);
    try {
      await work();
    } catch (err) {
      setError(describeError(err));
    }
  };
  const setAlways = (login: VaultPasswordOut, always: boolean) => run(async () => {
    const saved = await patchVaultPassword(login.id, { always });
    setShown((now) => withLogin(now, saved));
  });
  const remove = (login: VaultPasswordOut) => run(async () => {
    if (!window.confirm(deleteQuestion(login.host, login.username))) return;
    await deleteVaultPassword(login.id);
    setShown((now) => now.filter((l) => l.id !== login.id));
  });
  return (
    <>
      {shown.length === 0 ? <p className="settings-sheet__note">{VAULT_PASSWORDS_EMPTY}</p> : (
        <ul className="profile-card settings-sheet__list">
          {shown.map((login) => (
            <li key={login.id} className="settings-sheet__item">
              <span className="settings-sheet__item-main">
                <span className="settings-sheet__item-label">{login.host}</span>
                <span className="settings-sheet__item-detail">{loginDetail(login.username, login.last_used_at)}</span>
                <span className="vault-login__always">
                  <Switch checked={login.always} onChange={(next) => void setAlways(login, next)}>{ALWAYS_LABEL}</Switch>
                </span>
              </span>
              <Button size="sm" variant="danger" onClick={() => void remove(login)}>Delete</Button>
            </li>
          ))}
        </ul>
      )}
      {error ? <ErrorNotice message={error} /> : null}
      <Button variant="secondary" onClick={() => setAdding(true)}>{ADD_LOGIN}</Button>
      <p className="settings-sheet__note">{VAULT_PASSWORDS_NOTE}</p>
      <SavePasswordSheet open={adding} onOpenChange={setAdding}
        onSaved={(login) => setShown((now) => withLogin(now, login))} />
    </>
  );
}
