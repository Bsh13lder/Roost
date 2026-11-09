import { NavLink } from "react-router-dom";
import { Avatar } from "../Avatar";
import { clearAttention } from "../../lib/attention";
import { cx } from "../../ui/cx";
import type { BotOut, StuckCardOut } from "../../api/types";
import { wantsControl } from "../../lib/wantsControl";

// Narrow widths shrink it to 52px in sidebar.css.
const TILE_AVATAR_SIZE = 64;

export interface AvatarRowProps {
  bots: readonly BotOut[]; // already ordered and capped (lib/sidebar avatarRow)
  attention: ReadonlySet<string>;
  unread: ReadonlySet<string>;
  stuck?: Readonly<Record<string, StuckCardOut>>; // C3: an open Stuck card puts a hand in the bot's eye
}

// Your bots as a grid of tiles: the main bot first, wearing its star, then whoever spoke last. A click
// squishes the ghost on its way to the chat.
export function AvatarRow({ bots, attention, unread, stuck = {} }: AvatarRowProps) {
  if (bots.length === 0) return null;
  return (
    <ul className="avatar-row" aria-label="Your bots">
      {bots.map((bot) => (
        <li key={bot.id} className={cx("avatar-row__item", attention.has(bot.id) && "avatar-row__item--attention")}>
          <NavLink to={`/bots/${bot.id}`} className="avatar-row__link" onClick={() => clearAttention(bot.id)}
            aria-label={unread.has(bot.id) ? `${bot.name}, unread` : bot.name}>
            <Avatar avatar={bot.avatar} status={bot.status} size={TILE_AVATAR_SIZE} label={false} decorative star={bot.is_primary}
              botId={bot.id} poke control={wantsControl(bot, stuck)} />
            <span className="avatar-row__name" aria-hidden="true">{bot.name}</span>
            {bot.is_primary && bot.job ? <span className="avatar-row__job" aria-hidden="true">{bot.job}</span> : null}
            {unread.has(bot.id) ? <span className="avatar-row__unread" aria-hidden="true" /> : null}
          </NavLink>
        </li>
      ))}
    </ul>
  );
}
