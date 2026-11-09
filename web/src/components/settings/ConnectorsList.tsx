import type { ConnectorOut } from "../../api/connectors";
import { useLiveState } from "../../hooks/useLiveStore";
import { EVERY_BOT } from "../connectors/constants";

// Every connector you added (its key is never shown), with the bots that may use it. Adding and changing one stays
// on a bot's Settings page, where the editor knows which bot "only this bot" means.
export function ConnectorsList({ connectors }: { connectors: readonly ConnectorOut[] }) {
  const bots = useLiveState().bots;
  const who = (c: ConnectorOut) =>
    c.bot_ids === null ? EVERY_BOT : c.bot_ids.map((id) => bots[id]?.name ?? "A retired bot").join(", ");
  if (connectors.length === 0) {
    return <p className="settings-sheet__note">No connectors yet. Add one on a bot&rsquo;s Settings page.</p>;
  }
  return (
    <>
      <ul className="profile-card settings-sheet__list">
        {connectors.map((c) => (
          <li key={c.id} className="settings-sheet__item">
            <span className="settings-sheet__item-main">
              <span className="settings-sheet__item-label">{c.name}</span>
              <span className="settings-sheet__item-detail">{`${c.host} · ${c.key_hint}`}</span>
            </span>
            <span className="settings-sheet__item-value">{who(c)}</span>
          </li>
        ))}
      </ul>
      <p className="settings-sheet__note">Add or change a connector on a bot&rsquo;s Settings page.</p>
    </>
  );
}
