import { Outlet, useLocation, useMatch } from "react-router-dom";
import { Home } from "../pages/Home";
import { useAttentionNotifications } from "../hooks/useAttention";
import { useApplyCalm } from "../hooks/useCalmRobots";
import { useRobotEventFeed } from "../hooks/useRobotEvents";
import { useAppTimeZone } from "../lib/timeZone";

// Two panes (S1.4): the chat list (Home) and the open chat, side by side on a
// desktop. On a phone, CSS shows one: the list on "/", the open view elsewhere.
// A new account time zone re-renders the list and mounts the open view afresh,
// so its data and times load again on the new clock.
export function Layout() {
  const { pathname } = useLocation();
  const zone = useAppTimeZone();
  useAttentionNotifications();
  useApplyCalm();
  useRobotEventFeed(useMatch("/bots/:botId")?.params.botId ?? null);
  return (
    <div className="app-shell" data-view={pathname === "/" ? "list" : "detail"}>
      <aside className="app-shell__list" aria-label="Chats pane">
        <Home />
      </aside>
      <main className="app-shell__detail">
        <Outlet key={zone} />
      </main>
    </div>
  );
}
