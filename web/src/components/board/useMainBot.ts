import { useMemo } from "react";
import { useLiveState } from "../../hooks/useLiveStore";
import type { BotOut } from "../../api/types";

/** The main bot (the one wearing the star) from the live bots list, or null before any exists. */
export function useMainBot(): BotOut | null {
  const bots = useLiveState().bots;
  return useMemo(() => Object.values(bots).find((bot) => bot.is_primary) ?? null, [bots]);
}

/** A bot by id from the live list, or null. */
export function useBotById(id: string | null | undefined): BotOut | null {
  const bots = useLiveState().bots;
  return id ? bots[id] ?? null : null;
}
