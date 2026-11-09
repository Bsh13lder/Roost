import { useState } from "react";
import { Switch } from "../../ui/Switch";
import { describeError } from "../../api/client";
import { setWorkspaceInternet } from "../../api/workspace";
import type { BotOut } from "../../api/types";
import { ErrorNotice } from "../ErrorNotice";
import { INTERNET_LABEL, INTERNET_OFF_LINE, INTERNET_ON_LINE } from "./constants";

// Internet in the workspace (A4), in the Workspace files area: off by default. Switching asks the keeper to make the
// workspace again (its files stay), so the switch waits for the answer and hands back the updated bot.
export function WorkspaceInternetSwitch({ bot, onChange }: { bot: BotOut; onChange: (bot: BotOut) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const toggle = async (next: boolean) => {
    setBusy(true);
    setError(null);
    try {
      onChange(await setWorkspaceInternet(bot.id, next));
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="info-row info-row--switch">
      <Switch checked={bot.workspace_internet} disabled={busy} onChange={(next) => void toggle(next)}>
        {INTERNET_LABEL}
      </Switch>
      <p className="info-row__hint">{bot.workspace_internet ? INTERNET_ON_LINE : INTERNET_OFF_LINE}</p>
      {error ? <ErrorNotice message={error} /> : null}
    </div>
  );
}
