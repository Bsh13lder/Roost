import { useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { useNotificationPermission } from "../../hooks/useAttention";
import * as botsApi from "../../api/bots";
import { describeError } from "../../api/client";
import type { BotOut } from "../../api/types";
import type { BrowserPermission } from "../../lib/attention";

export const NOTIFY_CAPTION = "Get told when this bot finishes or is waiting for you.";

function PermissionHint({ bot, permission, onAsk }: { bot: BotOut; permission: BrowserPermission; onAsk: () => void }) {
  if (!bot.notify) return null;
  // The switch starts on (bots.notify defaults to 1), but the browser asks only after a click.
  if (permission === "default") {
    return <button type="button" className="btn btn--quiet btn--small info-row__action" onClick={onAsk}>Allow browser notifications</button>;
  }
  if (permission === "denied") {
    return <p className="info-row__hint">Your browser blocks notifications for Roost; the chat list still highlights {bot.name}.</p>;
  }
  return null;
}

// S1.10: a finished reply or Asking you, while Roost's tab is hidden, makes a
// browser notification and highlights the bot's row on Home.
export function NotifySwitch({ bot, onChange }: { bot: BotOut; onChange: (bot: BotOut) => void }) {
  const [permission, askPermission] = useNotificationPermission();
  const [error, setError] = useState<string | null>(null);
  const toggle = async () => {
    setError(null);
    const next = !bot.notify;
    if (next && permission === "default") await askPermission();
    try {
      onChange(await botsApi.setNotify(bot.id, next));
    } catch (err) {
      setError(describeError(err));
    }
  };
  // The profile's Notifications card (restructure slice 3): the switch alone in its card, the caption under it.
  return (
    <section className="notify-card" aria-label="Notifications">
      <div className="profile-card">
        <button type="button" role="switch" aria-checked={bot.notify} className="switch switch--row notify-card__switch"
          onClick={() => void toggle()}>
          <span className="switch__label">Notifications</span>
          <span className="switch__track" aria-hidden="true"><span className="switch__thumb" /></span>
        </button>
        <PermissionHint bot={bot} permission={permission} onAsk={() => void askPermission()} />
        {error ? <ErrorNotice message={error} /> : null}
      </div>
      <p className="notify-card__caption">{NOTIFY_CAPTION}</p>
    </section>
  );
}
