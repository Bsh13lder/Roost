import { MoreIcon } from "./icons";
import { Menu, MenuItem, MenuSeparator } from "../ui/Menu";
import * as botsApi from "../api/bots";
import { describeError } from "../api/client";
import type { BotOut } from "../api/types";
import { announceTeamChanged } from "../lib/teamChanged";
import { RETIRE_LABEL, RETIRE_MAIN_HINT, useRetireBot } from "../hooks/useRetireBot";

export interface BotMenuProps {
  bot: BotOut;
  onChange: (bot: BotOut) => void;
  onError: (message: string | null) => void;
  // The chat header gives these (restructure slice 3): View profile, Find in chat, Share as Template, and Earlier
  // conversations (lead task 06). Each item shows only when its action is given.
  onProfile?: () => void;
  onFind?: () => void;
  onShare?: () => void;
  onEarlier?: () => void;
  onFreshStart?: () => void;
}

function ChatItems({ onProfile, onFind, onShare, onEarlier, onFreshStart }: Omit<BotMenuProps, "bot" | "onChange" | "onError">) {
  return (
    <>
      {onProfile ? <MenuItem onSelect={onProfile}>View profile</MenuItem> : null}
      {onFind ? <MenuItem onSelect={onFind}>Find in chat</MenuItem> : null}
      {onShare ? <MenuItem onSelect={onShare}>Share as Template</MenuItem> : null}
      {onEarlier ? <MenuItem onSelect={onEarlier}>Earlier conversations</MenuItem> : null}
      {onFreshStart ? (
        <MenuItem onSelect={onFreshStart} title="Hide earlier web content from the bot, so its next replies start clean">
          Fresh start
        </MenuItem>
      ) : null}
      {onProfile || onFind || onShare || onEarlier || onFreshStart ? <MenuSeparator /> : null}
    </>
  );
}

// The bot's ⋯ menu on its chat: View profile, Find in chat, Share as Template and Earlier conversations, then the
// bot's own switches, and Retire this bot last, in the danger style. The main bot can't be retired: the star moves
// first (S1 D4).
export function BotMenu({ bot, onChange, onError, ...chat }: BotMenuProps) {
  const retire = useRetireBot(bot);
  const run = (action: () => Promise<unknown>) => {
    onError(null);
    action().catch((err: unknown) => onError(describeError(err)));
  };
  const makeMain = async () => {
    onChange(await botsApi.starBot(bot.id));
    announceTeamChanged();
  };
  return (
    <Menu label={`${bot.name} menu`} trigger={<MoreIcon />}>
      <ChatItems {...chat} />
      <MenuItem onSelect={() => run(() => botsApi.stopBot(bot.id))} disabled={bot.status !== "on_it"}>Stop</MenuItem>
      <MenuItem onSelect={() => run(async () => onChange(await botsApi.setOffDuty(bot.id, !bot.off_duty)))}>
        {bot.off_duty ? "Back on duty" : "Off duty"}
      </MenuItem>
      {bot.is_primary ? null : (
        <MenuItem onSelect={() => run(async () => onChange(await botsApi.setPinned(bot.id, !bot.pinned)))}>
          {bot.pinned ? "Unpin" : "Pin"}
        </MenuItem>
      )}
      {bot.is_primary ? null : <MenuItem onSelect={() => run(makeMain)}>Make main bot</MenuItem>}
      <MenuSeparator />
      <MenuItem onSelect={() => run(retire)} disabled={bot.is_primary} danger
        title={bot.is_primary ? RETIRE_MAIN_HINT : undefined}>
        {RETIRE_LABEL}
      </MenuItem>
    </Menu>
  );
}
