import type { ReactNode } from "react";
import { ChevronIcon } from "../icons";
import { initials } from "../sidebar/SidebarFoot";
import { PAYMENT_CARDS_TITLE } from "./PaymentCardsList";
import { MAC_FOLDERS_TITLE } from "./MacFoldersList";
import { Switch } from "../../ui/Switch";
import { useAccent } from "../../hooks/useAccent";
import { useNotificationPermission } from "../../hooks/useAttention";
import { useCalmSetting } from "../../hooks/useCalmRobots";
import { ACCENTS } from "../../lib/accent";
import { APP_VERSION } from "../../lib/appVersion";
import { CONNECTORS_TITLE } from "../connectors/constants";
import { VAULT_PASSWORDS_TITLE } from "../vault/constants";

// One group: a rounded card with its name for screen readers (the sheet's look follows the owner's pictures).
export function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="settings-sheet__group" aria-label={title}>
      <div className="profile-card">{children}</div>
    </section>
  );
}

function Row({ label, value, onOpen }: { label: string; value: string | null; onOpen: () => void }) {
  return (
    <button type="button" className="profile-row" onClick={onOpen}>
      <span className="profile-row__label">{label}</span>
      {value ? <span className="profile-row__value">{value}</span> : null}
      <span className="profile-row__chevron" aria-hidden="true"><ChevronIcon /></span>
    </button>
  );
}

export function AccountGroup({ username }: { username: string }) {
  return (
    <Group title="Account">
      <div className="settings-sheet__account">
        <span className="sidebar-foot__initials settings-sheet__initials" aria-hidden="true">{initials(username)}</span>
        <span className="settings-sheet__username">{username}</span>
      </div>
    </Group>
  );
}

export type Counted = number | "error" | null; // null while it loads
const counted = (count: Counted, one: string, many: string): string | null => {
  if (count === null) return null;
  if (count === "error") return "Couldn't load";
  return `${count} ${count === 1 ? one : many}`;
};

export function ConnectionsGroup({ connectors, folders, cards, passwords, onConnectors, onFolders, onCards, onPasswords }: {
  connectors: Counted; folders: Counted; cards: Counted; passwords: Counted; onConnectors: () => void;
  onFolders: () => void; onCards: () => void; onPasswords: () => void;
}) {
  return (
    <Group title="Connections">
      <Row label={CONNECTORS_TITLE} value={counted(connectors, "connector", "connectors")} onOpen={onConnectors} />
      <Row label={MAC_FOLDERS_TITLE} value={counted(folders, "folder", "folders")} onOpen={onFolders} />
      <Row label={PAYMENT_CARDS_TITLE} value={counted(cards, "card", "cards")} onOpen={onCards} />
      <Row label={VAULT_PASSWORDS_TITLE} value={counted(passwords, "login", "logins")} onOpen={onPasswords} />
    </Group>
  );
}

export function AppearanceGroup() {
  const [accent, choose] = useAccent();
  const [calm, setCalm] = useCalmSetting();
  return (
    <Group title="Appearance">
      <div className="settings-sheet__field">
        <span className="settings-sheet__label" id="accent-colour-label">Accent colour</span>
        <div className="accent-swatches" role="radiogroup" aria-labelledby="accent-colour-label">
          {ACCENTS.map(({ id, label }) => (
            <label key={id} className="accent-swatch" data-accent={id}>
              <input type="radio" name="accent-colour" className="sr-only" value={id} checked={accent === id}
                onChange={() => choose(id)} aria-label={label} />
              <span className="accent-swatch__dot" aria-hidden="true" />
            </label>
          ))}
        </div>
      </div>
      <div className="settings-sheet__field">
        <Switch checked={calm} onChange={setCalm}>Calm robots</Switch>
      </div>
    </Group>
  );
}

const PERMISSION_WORDS = {
  granted: "On in this browser.", denied: "This browser blocks notifications for Roost.",
  unsupported: "This browser can't show notifications.",
} as const;

export function NotificationsGroup() {
  const [permission, ask] = useNotificationPermission();
  return (
    <Group title="Notifications">
      <div className="settings-sheet__field">
        {permission === "default"
          ? <button type="button" className="btn btn--secondary btn--sm" onClick={() => void ask()}>Allow browser notifications</button>
          : <span className="settings-sheet__label">{PERMISSION_WORDS[permission]}</span>}
        <p className="settings-sheet__note">Each bot has its own Notifications switch on its profile.</p>
      </div>
    </Group>
  );
}

export function VersionGroup() {
  return (
    <Group title="Version">
      <div className="settings-sheet__field settings-sheet__version">
        <span className="settings-sheet__label">Version</span>
        <span className="profile-row__value">{APP_VERSION}</span>
      </div>
    </Group>
  );
}
