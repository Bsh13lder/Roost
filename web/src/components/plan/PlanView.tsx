import { useCallback, useEffect, useRef, useState } from "react";
import { Segmented } from "../../ui/Segmented";
import { useToast } from "../../ui/Toast";
import { describeError } from "../../api/client";
import * as planApi from "../../api/plan";
import type { PlanOut, PlanStatus } from "../../api/plan";
import type { BotOut } from "../../api/types";
import { useLiveState } from "../../hooks/useLiveStore";
import { ErrorNotice } from "../ErrorNotice";
import { PlanCalendar } from "./PlanCalendar";
import { PlanKanban } from "./PlanKanban";
import { PlanText } from "./PlanText";
import { PLAN_CHANGED_TEXT, VIEWS, unreadableText, type PlanViewId } from "./constants";
import { currentFromConflict } from "./planConflict";
import "../../styles/plan.css";

// The bot's Plan, loaded once and again when a newer revision is announced (plan_changed). Only the newest load answers.
function usePlan(botId: string) {
  const announced = useLiveState().planRevisions?.[botId] ?? 0;
  const [plan, setPlan] = useState<PlanOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef(0);
  const reload = useCallback(() => {
    const ticket = ++latest.current;
    planApi.getPlan(botId)
      .then((loaded) => { if (ticket === latest.current) { setPlan(loaded); setError(null); } })
      .catch((err: unknown) => { if (ticket === latest.current) setError(describeError(err)); });
  }, [botId]);
  useEffect(() => reload(), [reload]);
  const known = plan?.revision ?? 0;
  useEffect(() => { if (plan && announced > known) reload(); }, [announced, known, plan, reload]);
  return { plan, setPlan, error, reload };
}

// The Plan tab's body: a Calendar, a Kanban and the text, over the same Plan. A move sends the item's id with the
// revision this screen read; a 409 reloads the Plan and says to try again.
export default function PlanView({ bot }: { bot: BotOut }) {
  const { plan, setPlan, error, reload } = usePlan(bot.id);
  const [view, setView] = useState<PlanViewId>("calendar");
  const toast = useToast();

  const move = useCallback(async (itemId: string, status: PlanStatus) => {
    if (!plan) return;
    try {
      setPlan(await planApi.patchPlanItem(bot.id, itemId, plan.revision, { status }));
    } catch (err) {
      if (currentFromConflict(err)) {
        reload();
        toast.show(PLAN_CHANGED_TEXT, { tone: "danger" });
      } else {
        toast.show(describeError(err), { tone: "danger" });
      }
    }
  }, [bot.id, plan, reload, setPlan, toast]);

  if (error && !plan) return <ErrorNotice message={error} onRetry={reload} />;
  if (!plan) return <p className="plan-loading">Loading the Plan&hellip;</p>;
  return (
    <div className="plan-view">
      <Segmented label="Plan view" options={VIEWS} value={view} onChange={setView} />
      {plan.unreadable > 0 ? <p className="plan-view__unreadable">{unreadableText(plan.unreadable)}</p> : null}
      {view === "calendar" ? <PlanCalendar items={plan.items} botId={bot.id} /> : null}
      {view === "kanban" ? <PlanKanban items={plan.items} onMove={(id, status) => void move(id, status)} /> : null}
      {view === "text" ? <PlanText botId={bot.id} plan={plan} onSaved={setPlan} /> : null}
    </div>
  );
}
