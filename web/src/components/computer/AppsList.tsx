import { useCallback, useEffect, useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { Button } from "../../ui/Button";
import * as appsApi from "../../api/apps";
import { describeError } from "../../api/client";
import type { BotAppOut } from "../../api/types";

// Install an app: the packages the owner said Yes to on this bot's Linux computer. Remove is the owner's own click,
// so it needs no card. Plain on purpose; it borrows the Vault list's look until it gets its own. A new reloadKey (the
// bot's status) loads it again, so an app the bot just installed shows without a page reload.
export function AppsList({ botId, reloadKey }: { botId: string; reloadKey?: string }) {
  const [apps, setApps] = useState<BotAppOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    appsApi.listApps(botId)
      .then((rows) => { if (!cancelled) { setApps(rows); setError(null); } })
      .catch((err: unknown) => { if (!cancelled) setError(describeError(err)); });
    return () => { cancelled = true; };
  }, [botId, reloadKey]);
  const remove = useCallback(async (app: BotAppOut) => {
    setError(null);
    try {
      await appsApi.removeApp(botId, app.id);
      setApps((current) => (current ?? []).filter((row) => row.id !== app.id));
    } catch (err) {
      setError(describeError(err));
    }
  }, [botId]);
  return (
    <section className="site-logins" aria-labelledby="bot-apps-title">
      <h2 id="bot-apps-title" className="site-logins__title">Apps</h2>
      {apps && apps.length === 0 ? <p className="site-logins__empty">No apps installed yet.</p> : null}
      <ul className="site-logins__list">
        {(apps ?? []).map((app) => (
          <li key={app.id} className="site-logins__row">
            <span className="site-logins__label">{app.package}</span>
            <Button variant="ghost" size="sm" aria-label={`Remove ${app.package}`}
              onClick={() => void remove(app)}>Remove</Button>
          </li>
        ))}
      </ul>
      {error ? <ErrorNotice message={error} /> : null}
    </section>
  );
}
