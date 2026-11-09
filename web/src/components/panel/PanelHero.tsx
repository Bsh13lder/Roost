import { useState } from "react";
import { Avatar } from "../Avatar";
import { AvatarEditor } from "../profile/AvatarEditor";
import { NameJobCard } from "../profile/NameJobCard";
import { GroupLabel } from "./GroupLabel";
import { StatusLabel } from "../StatusLabel";
import { Button } from "../../ui/Button";
import type { BotOut } from "../../api/types";
import { useLiveState } from "../../hooks/useLiveStore";
import { usedLabels } from "../../lib/sidebar";

const HERO_SIZE = 112;

function MainMark({ bot }: { bot: BotOut }) {
  return bot.is_primary ? <span className="panel-hero__main" role="img" aria-label="Main bot">Main bot</span> : null;
}

// The profile's top (restructure slice 3): the big robot (the main bot wears its star), the name, the job and Edit.
// Edit opens the existing editors in place: the look, the name and job, and the sidebar label. The name is an h2:
// the chat header keeps the page's one h1.
export function PanelHero({ bot, onChange, control = false }: {
  bot: BotOut; onChange: (bot: BotOut) => void; control?: boolean;
}) {
  const live = useLiveState();
  const [editing, setEditing] = useState(false);
  if (editing) {
    return (
      <div className="panel-hero panel-hero--editing">
        <AvatarEditor bot={bot} onChange={onChange} control={control} />
        <NameJobCard bot={bot} onChange={onChange} nameLevel="h2" />
        <GroupLabel bot={bot} labels={usedLabels(Object.values(live.bots), bot.id)} onChange={onChange} />
        <Button size="sm" variant="secondary" onClick={() => setEditing(false)}>Done</Button>
      </div>
    );
  }
  return (
    <div className="panel-hero">
      <Avatar avatar={bot.avatar} status={bot.status} activity={bot.activity} size={HERO_SIZE} label={false} decorative
        star={bot.is_primary} botId={bot.id} poke control={control} />
      <h2 className="panel-hero__name">{bot.name}</h2>
      {bot.job ? <p className="panel-hero__job">{bot.job}</p> : null}
      <div className="panel-hero__state">
        <MainMark bot={bot} />
        <StatusLabel status={bot.status} activity={bot.activity} />
      </div>
      <Button size="sm" variant="secondary" className="panel-hero__edit" onClick={() => setEditing(true)}>Edit</Button>
    </div>
  );
}
