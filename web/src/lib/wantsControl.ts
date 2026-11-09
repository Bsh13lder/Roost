// C3: a bot's face shows a hand while it needs you to take control, which is while it has an open Stuck card.
import type { BotOut, StuckCardOut } from "../api/types";

export function wantsControl(
  bot: Pick<BotOut, "id">,
  stuckCards: Readonly<Record<string, StuckCardOut>> | readonly StuckCardOut[],
): boolean {
  const cards: readonly StuckCardOut[] = Array.isArray(stuckCards) ? stuckCards : Object.values(stuckCards);
  return cards.some((card) => card.bot_id === bot.id && card.state === "open");
}
