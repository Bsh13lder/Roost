import { useEffect, useState } from "react";
import { BackIcon } from "../icons";
import { PHONE_QUERY } from "../panel/panelTabs";
import { ConnectorsList } from "./ConnectorsList";
import { MAC_FOLDERS_TITLE, MacFoldersList } from "./MacFoldersList";
import { PAYMENT_CARDS_TITLE, PaymentCardsList } from "./PaymentCardsList";
import { VaultPasswordsList } from "./VaultPasswordsList";
import { TimeZoneGroup } from "./TimeZoneGroup";
import {
  AccountGroup, AppearanceGroup, ConnectionsGroup, NotificationsGroup, VersionGroup, type Counted,
} from "./SettingsGroups";
import { Button } from "../../ui/Button";
import { IconButton } from "../../ui/IconButton";
import { Sheet } from "../../ui/Sheet";
import * as connectorsApi from "../../api/connectors";
import type { ConnectorOut } from "../../api/connectors";
import * as macApi from "../../api/mac";
import * as paymentsApi from "../../api/payments";
import * as vaultPasswordsApi from "../../api/vaultPasswords";
import type { VaultPasswordOut } from "../../api/vaultPasswords";
import type { GrantOut, SavedCardOut } from "../../api/types";
import { useAuth } from "../../hooks/useAuth";
import { useMediaQuery } from "../../hooks/useMediaQuery";
import { CONNECTORS_TITLE } from "../connectors/constants";
import { VAULT_PASSWORDS_TITLE } from "../vault/constants";

type View = "main" | "connectors" | "folders" | "cards" | "passwords";
type Loaded<T> = readonly T[] | "error" | null;

// One list for the Connections card, loaded as the sheet opens; a failure shows "Couldn't load" on its row.
function useList<T>(open: boolean, load: () => Promise<T[]>): Loaded<T> {
  const [list, setList] = useState<Loaded<T>>(null);
  useEffect(() => {
    if (!open) return;
    let live = true;
    load().then((loaded) => { if (live) setList(loaded); }).catch((err: unknown) => {
      console.warn("Settings could not load a list.", err);
      if (live) setList("error");
    });
    return () => { live = false; };
  }, [open, load]);
  return list;
}

const countOf = <T,>(list: Loaded<T>): Counted => (list === null || list === "error" ? list : list.length);

function SubView({ title, onBack, children }: { title: string; onBack: () => void; children: React.ReactNode }) {
  return (
    <div className="settings-sheet__sub">
      <div className="profile-page__head">
        <IconButton label="Back to Settings" icon={<BackIcon />} onClick={onBack} tooltip={false} />
        <h3 className="profile-page__title">{title}</h3>
      </div>
      {children}
    </div>
  );
}

// Settings (restructure slice 3), opened from your initials: grouped rounded cards, Sign out last in the danger style.
export function SettingsSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { user, logout } = useAuth();
  const phone = useMediaQuery(PHONE_QUERY);
  const [view, setView] = useState<View>("main");
  const connectors = useList<ConnectorOut>(open, connectorsApi.listConnectors);
  const grants = useList<GrantOut>(open, macApi.listGrants);
  const cards = useList<SavedCardOut>(open, paymentsApi.listPaymentCards);
  const passwords = useList<VaultPasswordOut>(open, vaultPasswordsApi.listVaultPasswords);
  const back = () => setView("main");
  return (
    <Sheet open={open} size={phone ? "full" : "default"} title="Settings"
      onOpenChange={(next) => { if (!next) { setView("main"); onClose(); } }}>
      {view === "connectors" ? (
        <SubView title={CONNECTORS_TITLE} onBack={back}>
          {Array.isArray(connectors) ? <ConnectorsList connectors={connectors} /> : null}
        </SubView>
      ) : null}
      {view === "folders" ? (
        <SubView title={MAC_FOLDERS_TITLE} onBack={back}>
          {Array.isArray(grants) ? <MacFoldersList grants={grants} /> : null}
        </SubView>
      ) : null}
      {view === "cards" ? (
        <SubView title={PAYMENT_CARDS_TITLE} onBack={back}>
          {Array.isArray(cards) ? <PaymentCardsList cards={cards} /> : null}
        </SubView>
      ) : null}
      {view === "passwords" ? (
        <SubView title={VAULT_PASSWORDS_TITLE} onBack={back}>
          {Array.isArray(passwords) ? <VaultPasswordsList logins={passwords} /> : null}
        </SubView>
      ) : null}
      {view === "main" ? (
        <div className="settings-sheet">
          <AccountGroup username={user?.username ?? ""} />
          <TimeZoneGroup />
          <ConnectionsGroup connectors={countOf(connectors)} folders={countOf(grants)} cards={countOf(cards)}
            passwords={countOf(passwords)} onConnectors={() => setView("connectors")}
            onFolders={() => setView("folders")} onCards={() => setView("cards")}
            onPasswords={() => setView("passwords")} />
          <AppearanceGroup />
          <NotificationsGroup />
          <VersionGroup />
          <Button variant="danger" block onClick={() => void logout()}>Sign out</Button>
        </div>
      ) : null}
    </Sheet>
  );
}
