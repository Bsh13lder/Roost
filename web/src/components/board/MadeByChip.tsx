import { useLiveState } from "../../hooks/useLiveStore";

// Which bot made a row (design: the shared Board). NULL means the user, or a bot since retired: no chip.
export function MadeByChip({ botId }: { botId: string | null }) {
  const live = useLiveState();
  if (!botId) return null;
  const name = live.bots[botId]?.name;
  return name ? <span className="board-chip board-chip--maker">by {name}</span> : null;
}
