// A small, dismissible note at the top of Home when the daily check found a model. It is one row, folded by
// default ("New model: X" and a chevron); opened, the same row shows "Try it", which lists your bots and opens
// the chosen bot's Info with the Model list open. It never grows past one row, so the chat list stays put.
import { useEffect, useState } from "react";
import { dismissModelNotice, fetchModels } from "../lib/models";
import { readBannerOpen, writeBannerOpen } from "../lib/modelBannerFold";
import type { BotOut } from "../api/types";
import { cx } from "../ui/cx";
import { ChevronDownIcon, ChevronUpIcon, CloseIcon } from "./icons";
import { Menu, MenuLink } from "../ui/Menu";

function TryIt({ bots, modelId }: { bots: readonly BotOut[]; modelId: string }) {
  if (bots.length === 0) return null;
  return (
    <Menu label="Try it" trigger={<span className="model-banner__try">Try it</span>} align="end">
      {bots.map((bot) => (
        <MenuLink key={bot.id} to={`/bots/${bot.id}?panel=settings&try=${encodeURIComponent(modelId)}`}>{bot.name}</MenuLink>
      ))}
    </Menu>
  );
}

export function NewModelBanner({ bots }: { bots: readonly BotOut[] }) {
  const [notice, setNotice] = useState<{ id: string; label: string } | null>(null);
  const [open, setOpen] = useState(readBannerOpen);
  useEffect(() => {
    let live = true;
    fetchModels().then((m) => { if (live) setNotice(m.notice); }).catch(() => undefined);
    return () => { live = false; };
  }, []);
  if (notice === null) return null;
  const dismiss = () => {
    const id = notice.id;
    setNotice(null);
    dismissModelNotice(id).catch(() => undefined);
  };
  const toggle = () => {
    writeBannerOpen(!open);
    setOpen(!open);
  };
  return (
    <div className={cx("model-banner", !open && "model-banner--folded")} role="status">
      <span className="model-banner__text" title={`New model: ${notice.label}`}>New model: {notice.label}</span>
      {open ? <TryIt bots={bots} modelId={notice.id} /> : null}
      <button type="button" className="icon-btn icon-btn--sm" aria-expanded={open}
        aria-label={open ? "Hide new model" : "Show new model"} onClick={toggle}>
        {open ? <ChevronUpIcon /> : <ChevronDownIcon />}
      </button>
      <button type="button" className="icon-btn icon-btn--sm" aria-label="Dismiss" onClick={dismiss}><CloseIcon /></button>
    </div>
  );
}
