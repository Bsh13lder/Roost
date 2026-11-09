import { useCallback, useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { BackIcon, CloseIcon } from "../icons";
import { ComputerTab } from "../profile/ComputerTab";
import { LibraryPage } from "../profile/LibraryPage";
import { NotifySwitch } from "../profile/NotifySwitch";
import { SettingsPage } from "../profile/SettingsPage";
import { PlanRoutinesPage } from "../plan/PlanRoutinesPage";
import { ShareTemplateDialog } from "../ShareTemplateDialog";
import { PanelHero } from "./PanelHero";
import { ProfileRows } from "./ProfileRows";
import { PHONE_QUERY, pageLabel, type PanelPage } from "./panelTabs";
import { useMediaQuery } from "../../hooks/useMediaQuery";
import { IconButton } from "../../ui/IconButton";
import { Sheet } from "../../ui/Sheet";
import type { BotOut } from "../../api/types";

type SubPage = Exclude<PanelPage, "profile">;
interface PageProps { bot: BotOut; onChange: (bot: BotOut) => void; onShare: () => void }
const PAGES: Record<SubPage, (props: PageProps) => ReactNode> = {
  plan: ({ bot }) => <PlanRoutinesPage bot={bot} />,
  computer: ({ bot, onChange }) => <ComputerTab bot={bot} onChange={onChange} />,
  library: ({ bot }) => <LibraryPage bot={bot} />,
  settings: (props) => <SettingsPage {...props} />,
};

export interface BotPanelProps {
  bot: BotOut;
  page: PanelPage;
  onPage: (page: PanelPage) => void;
  onClose: () => void;
  onChange: (bot: BotOut) => void;
  control?: boolean; // C3: the bot has an open Stuck card, so its face shows a hand
}

// The profile itself: the hero, one card of rows, then the Notifications card.
function ProfileHome({ bot, onPage, onChange, control }: Omit<BotPanelProps, "onClose" | "page">) {
  return (
    <div className="profile-home">
      <PanelHero bot={bot} onChange={onChange} control={control} />
      <ProfileRows bot={bot} onPage={onPage} />
      <NotifySwitch bot={bot} onChange={onChange} />
    </div>
  );
}

// One row's page: a back arrow to the profile and the page's own heading over its content.
function SubPageView({ page, onPage, ...props }: PageProps & { page: SubPage; onPage: (page: PanelPage) => void }) {
  return (
    <div className={`profile-page profile-page--${page}`}>
      <div className="profile-page__head">
        <IconButton label="Back to the profile" icon={<BackIcon />} onClick={() => onPage("profile")} tooltip={false} />
        <h2 className="profile-page__title">{pageLabel(page)}</h2>
      </div>
      {PAGES[page](props)}
    </div>
  );
}

function PanelBody({ bot, page, onPage, onChange, control }: Omit<BotPanelProps, "onClose">) {
  const [sharing, setSharing] = useState(false);
  const closeShare = useCallback(() => setSharing(false), []);
  return (
    <>
      {page === "profile"
        ? <ProfileHome bot={bot} onPage={onPage} onChange={onChange} control={control} />
        : <SubPageView page={page} bot={bot} onPage={onPage} onChange={onChange} onShare={() => setSharing(true)} />}
      {sharing ? <ShareTemplateDialog bot={bot} onClose={closeShare} /> : null}
    </>
  );
}

// The bot's profile beside its chat (restructure slice 3: rows, no tabs). On a desktop an aside that takes focus as it
// opens and closes on Escape; on a phone the same body in a full-screen sheet.
export function BotPanel(props: BotPanelProps) {
  const { bot, onClose } = props;
  const phone = useMediaQuery(PHONE_QUERY);
  const asideRef = useRef<HTMLElement>(null);
  useEffect(() => { if (!phone) asideRef.current?.focus(); }, [phone]);
  if (phone) {
    return (
      <Sheet open size="full" title={`${bot.name}'s profile`} onOpenChange={(open) => { if (!open) onClose(); }}>
        <PanelBody {...props} />
      </Sheet>
    );
  }
  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key === "Escape" && !event.defaultPrevented) onClose();
  };
  return (
    <aside ref={asideRef} className="bot-panel" aria-label={`${bot.name}'s profile`} tabIndex={-1} onKeyDown={onKeyDown}>
      <div className="bot-panel__head">
        <IconButton label="Close profile" icon={<CloseIcon />} onClick={onClose} />
      </div>
      <div className="bot-panel__body">
        <PanelBody {...props} />
      </div>
    </aside>
  );
}
