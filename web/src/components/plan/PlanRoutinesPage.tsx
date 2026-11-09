import { Suspense, lazy } from "react";
import { PlanTab } from "./PlanTab";
import type { BotOut } from "../../api/types";

// The routines are their own chunk (routines plan, bundle budget).
const RoutinesSection = lazy(() => import("../routines/RoutinesSection"));

// Plan & routines (restructure slice 3): the bot's Plan (Calendar · Kanban · Text), then its routines under it.
export function PlanRoutinesPage({ bot }: { bot: BotOut }) {
  return (
    <div className="plan-routines">
      <PlanTab bot={bot} />
      <Suspense fallback={<p className="routines__loading">Loading routines&hellip;</p>}>
        <RoutinesSection botId={bot.id} />
      </Suspense>
    </div>
  );
}
