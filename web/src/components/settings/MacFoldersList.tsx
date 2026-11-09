import type { GrantOut } from "../../api/types";
import { useLiveState } from "../../hooks/useLiveStore";

export const MAC_FOLDERS_TITLE = "Your Mac: folders";

// Every folder you granted, with the bot it is for. Adding and revoking stay on each bot's Settings page.
export function MacFoldersList({ grants }: { grants: readonly GrantOut[] }) {
  const bots = useLiveState().bots;
  if (grants.length === 0) {
    return <p className="settings-sheet__note">No folders yet. Add one on a bot&rsquo;s Settings page.</p>;
  }
  return (
    <>
      <ul className="profile-card settings-sheet__list">
        {grants.map((grant) => (
          <li key={grant.id} className="settings-sheet__item">
            <span className="settings-sheet__item-main">
              <span className="settings-sheet__item-label">{grant.label}</span>
              <span className="settings-sheet__item-detail">{grant.path}</span>
            </span>
            <span className="settings-sheet__item-value">
              {grant.bot_id === null ? "Every bot" : bots[grant.bot_id]?.name ?? "A retired bot"}
            </span>
          </li>
        ))}
      </ul>
      <p className="settings-sheet__note">Add or revoke a folder on a bot&rsquo;s Settings page.</p>
    </>
  );
}
