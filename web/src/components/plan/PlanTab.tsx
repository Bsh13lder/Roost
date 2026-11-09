import { Suspense, lazy } from "react";
import type { BotOut } from "../../api/types";

// The Plan tab's entry. The calendar, the Kanban and the text editor are one lazy chunk, so none of it is in the
// main bundle.
const PlanView = lazy(() => import("./PlanView"));

export function PlanTab({ bot }: { bot: BotOut }) {
  return (
    <Suspense fallback={<p className="plan-loading">Loading the Plan&hellip;</p>}>
      <PlanView bot={bot} />
    </Suspense>
  );
}
