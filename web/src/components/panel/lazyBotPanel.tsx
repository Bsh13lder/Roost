// web/src/components/panel/lazyBotPanel.tsx: the bot's profile panel is its own chunk (its tabs and what only they
// use stay out of the entry). The pill preloads it on hover or focus; the preload and React.lazy share one import.
import { lazy, Suspense } from "react";
import type { BotPanelProps } from "./BotPanel";
import { PHONE_QUERY } from "./panelTabs";
import { useMediaQuery } from "../../hooks/useMediaQuery";

const loadBotPanel = () => import("./BotPanel");
const Panel = lazy(() => loadBotPanel().then((module) => ({ default: module.BotPanel })));

// Warm the chunk before the click; a failed preload is retried by the click itself.
export function preloadBotPanel(): void {
  loadBotPanel().catch(() => undefined);
}

// While the chunk arrives: an empty, busy panel on a desktop so the chat does not jump; nothing on a phone, where the
// profile opens as a sheet.
function Waiting() {
  const phone = useMediaQuery(PHONE_QUERY);
  if (phone) return null;
  return (
    <aside className="bot-panel" aria-label="Loading the profile" aria-busy="true">
      <p className="board-loading">Loading&hellip;</p>
    </aside>
  );
}

export function LazyBotPanel(props: BotPanelProps) {
  return (
    <Suspense fallback={<Waiting />}>
      <Panel {...props} />
    </Suspense>
  );
}
