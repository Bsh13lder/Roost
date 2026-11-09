import { useEffect, useState, type ReactNode } from "react";
import { BookIcon, ChevronIcon, ClockIcon, GearIcon, ScreenIcon } from "../icons";
import * as deskApi from "../../api/desk";
import * as routinesApi from "../../api/routines";
import type { BotOut, DeskStatusOut } from "../../api/types";
import { useLiveState } from "../../hooks/useLiveStore";
import { computerWord, routinesOnLabel } from "../../lib/profileRows";
import { pageLabel, type PanelPage } from "./panelTabs";

// How many of the bot's routines are on; null until known (a failed load shows no value, never a wrong one).
function useRoutinesOn(botId: string): number | null {
  const version = useLiveState().routineVersion?.routines;
  const [on, setOn] = useState<number | null>(null);
  useEffect(() => {
    let live = true;
    routinesApi.listRoutines(botId)
      .then((list) => { if (live) setOn(list.filter((one) => one.enabled).length); })
      .catch(() => { if (live) setOn(null); });
    return () => { live = false; };
  }, [botId, version]);
  return on;
}

// The computer's state, read again when the bot's status changes (a run wakes it).
function useDesk(botId: string, status: string): DeskStatusOut | null {
  const [desk, setDesk] = useState<DeskStatusOut | null>(null);
  useEffect(() => {
    let live = true;
    deskApi.getDeskStatus(botId).then((read) => { if (live) setDesk(read); }).catch(() => { if (live) setDesk(null); });
    return () => { live = false; };
  }, [botId, status]);
  return desk;
}

function Row({ page, icon, value, onPage }: { page: PanelPage; icon: ReactNode; value?: string; onPage: (page: PanelPage) => void }) {
  return (
    <li>
      <button type="button" className="profile-row" onClick={() => onPage(page)}>
        <span className="profile-row__icon" aria-hidden="true">{icon}</span>
        <span className="profile-row__label">{pageLabel(page)}</span>
        {value ? <span className="profile-row__value">{value}</span> : null}
        <span className="profile-row__chevron" aria-hidden="true"><ChevronIcon /></span>
      </button>
    </li>
  );
}

// The profile's one card of rows, each opening its own page.
export function ProfileRows({ bot, onPage }: { bot: BotOut; onPage: (page: PanelPage) => void }) {
  const on = useRoutinesOn(bot.id);
  const desk = useDesk(bot.id, bot.status);
  return (
    <ul className="profile-rows" aria-label={`${bot.name}'s pages`}>
      <Row page="plan" icon={<ClockIcon />} value={on === null ? undefined : routinesOnLabel(on)} onPage={onPage} />
      <Row page="computer" icon={<ScreenIcon />} value={computerWord(bot.status, desk)} onPage={onPage} />
      <Row page="library" icon={<BookIcon />} onPage={onPage} />
      <Row page="settings" icon={<GearIcon />} onPage={onPage} />
    </ul>
  );
}
