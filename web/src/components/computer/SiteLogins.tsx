import { useCallback, useEffect, useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { Button } from "../../ui/Button";
import * as vaultApi from "../../api/vault";
import { describeError } from "../../api/client";
import type { SiteLoginOut } from "../../api/types";

// "host · account", or "this time only" for a login Roost signs the computer out of after the task.
function loginLine(login: SiteLoginOut): string {
  const label = login.kept === false ? "this time only" : login.label;
  return label ? `${login.host} · ${label}` : login.host;
}

// Vault: site logins. The accounts you said this bot is signed in with; Forget removes one. Labels only.
// `reloadKey` changes when the full-screen Take control closes, so a new account shows at once.
export function SiteLogins({ botId, reloadKey = 0 }: { botId: string; reloadKey?: number }) {
  const [logins, setLogins] = useState<SiteLoginOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    vaultApi.listSiteLogins(botId)
      .then((rows) => { if (!cancelled) { setLogins(rows); setError(null); } })
      .catch((err: unknown) => { if (!cancelled) setError(describeError(err)); });
    return () => { cancelled = true; };
  }, [botId, reloadKey]);
  // Forget drops the label only; Sign out also makes the bot's Linux computer forget the site.
  const remove = useCallback(async (login: SiteLoginOut, call: (botId: string, loginId: string) => Promise<void>) => {
    setError(null);
    try {
      await call(botId, login.id);
      setLogins((current) => (current ?? []).filter((row) => row.id !== login.id));
    } catch (err) {
      setError(describeError(err));
    }
  }, [botId]);
  return (
    <section className="site-logins" aria-labelledby="site-logins-title">
      <h2 id="site-logins-title" className="site-logins__title">Vault: site logins</h2>
      {logins && logins.length === 0 ? <p className="site-logins__empty">No sign-ins saved yet.</p> : null}
      <ul className="site-logins__list">
        {(logins ?? []).map((login) => (
          <li key={login.id} className="site-logins__row">
            <span className="site-logins__label">{loginLine(login)}</span>
            <Button variant="ghost" size="sm" aria-label={`Sign out of ${login.host}`}
              onClick={() => void remove(login, vaultApi.signOutSiteLogin)}>Sign out</Button>
            <Button variant="ghost" size="sm" aria-label={`Forget ${loginLine(login)}`}
              onClick={() => void remove(login, vaultApi.forgetSiteLogin)}>Forget</Button>
          </li>
        ))}
      </ul>
      {error ? <ErrorNotice message={error} /> : null}
    </section>
  );
}
