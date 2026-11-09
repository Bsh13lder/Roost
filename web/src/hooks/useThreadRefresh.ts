import { useEffect, useRef } from "react";
import type { ThreadOut } from "../api/types";
import { onThreadsChanged } from "../lib/threadsChanged";

// M2 D6: the sidebar's Threads list follows the open bot's threads live. It
// reloads when Talk announces a thread, and when a live message names a thread
// the list hasn't seen (a handoff's "From <asker>" thread, a reply in a thread
// made elsewhere). Each unknown thread id triggers one reload, never a loop.
export function useThreadRefresh(
  botId: string | undefined,
  threads: readonly ThreadOut[],
  liveThreadIds: readonly string[],
  reload: () => void,
): void {
  useEffect(() => onThreadsChanged((changed) => {
    if (changed === botId) reload();
  }), [botId, reload]);

  const asked = useRef<ReadonlySet<string>>(new Set());
  useEffect(() => {
    if (!botId) return;
    const known = new Set(threads.map((thread) => thread.id));
    const fresh = liveThreadIds.filter((id) => !known.has(id) && !asked.current.has(id));
    if (fresh.length === 0) return;
    asked.current = new Set([...asked.current, ...fresh]);
    reload();
  }, [botId, threads, liveThreadIds, reload]);
}
