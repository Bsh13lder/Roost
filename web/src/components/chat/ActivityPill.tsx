import { lazy, Suspense, useEffect, useState } from "react";
import type { BotOut } from "../../api/types";
import { usePrefersReducedMotion } from "../../hooks/usePrefersReducedMotion";
import { currentKind, currentLine, foldedPillLine, workSteps, type ActivityRun } from "../../store/activityRuns";
import type { ComputerRun } from "../../store/computerRuns";
import { cx } from "../../ui/cx";
import { ChevronIcon } from "../icons";
import { WorkingTimer } from "../WorkingIndicator";
import { ActivityMark, DoneMark } from "./ActivityMark";
import { ComputerCard } from "./ComputerCard";
import { COMPUTER_CARD_FOLD_MS } from "./constants";
import { WorkingBot } from "./WorkingBot";

// The sheet (every step in words, the computer if it was used, Technical details) loads on the first tap.
const ActivitySheet = lazy(() => import("./ActivitySheet").then((module) => ({ default: module.ActivitySheet })));

export interface ActivityPillProps {
  run: ActivityRun;
  bot: BotOut | undefined;
  live: boolean; // the bot is On it and this is its newest run (store/activityRuns.ts isLiveActivity)
  // The same run's computer line, when it used the computer (never its screen: owner, 2026-10-26).
  computer?: { run: ComputerRun; live: boolean };
  technical?: readonly string[]; // the raw step lines (store/live.ts toolLines), only inside Technical details
}

// When the run began (epoch ms), for the live timer; null before its first step.
function startOf(run: ActivityRun): number | null {
  const at = Date.parse(run.steps[0]?.at ?? "");
  return Number.isNaN(at) ? null : at;
}

function usePhase(live: boolean): "live" | "folding" | "folded" {
  const still = usePrefersReducedMotion();
  const [phase, setPhase] = useState<"live" | "folding" | "folded">(live ? "live" : "folded");
  useEffect(() => {
    if (live) { setPhase("live"); return undefined; }
    if (still) { setPhase("folded"); return undefined; }
    setPhase((now) => (now === "live" ? "folding" : now));
    const timer = setTimeout(() => setPhase("folded"), COMPUTER_CARD_FOLD_MS);
    return () => clearTimeout(timer);
  }, [live, still]);
  return phase;
}

// The activity pill (docs/plans/2026-10-23-roost-activity-pill.md): while a bot works, what it is doing in plain
// words beside the bot's own robot, whose eyes act out the step (owner, 2026-10-27: like Grok's moving mark), and the computer's compact line under it when it uses its computer. Afterwards, one
// quiet line ("Worked for 42 s · 6 steps"). A tap opens every step, never code.
export function ActivityPill({ run, bot, live, computer, technical }: ActivityPillProps) {
  const [open, setOpen] = useState(false);
  const phase = usePhase(live);
  const steps = workSteps(run).length;
  return (
    <>
      {phase === "folded" ? (
        <button type="button" className="ap-line" onClick={() => setOpen(true)} data-testid="activity-line"
          aria-label={`${foldedPillLine(run, computer?.run)}. Show the steps`}>
          <span className="ap-line__mark">{steps > 0 ? <DoneMark /> : <ActivityMark kind="think" />}</span>
          <span className="ap-line__text">{foldedPillLine(run, computer?.run)}</span>
          <span className="ap-line__chevron"><ChevronIcon /></span>
        </button>
      ) : (
        <div className={cx("ap", phase === "folding" && "ap--folding")} data-testid="activity-pill">
          <div className="ap__inner">
            <button type="button" className="ap__pill" onClick={() => setOpen(true)}
              aria-label={`${bot?.name ?? "The bot"}: ${currentLine(run)} Show the steps`}>
              {bot ? (
                <span className="ap__mark ap__mark--bot"><WorkingBot avatar={bot.avatar} kind={currentKind(run)} /></span>
              ) : (
                <span className="ap__mark"><ActivityMark kind={currentKind(run)} moving /></span>
              )}
              <span className="ap__line" key={currentLine(run)} aria-live="polite">{currentLine(run)}</span>
              {startOf(run) ? <span className="ap__time"><WorkingTimer since={startOf(run)!} /></span> : null}
              {steps > 0 ? <span className="ap__count">{steps}</span> : null}
            </button>
            {computer ? <ComputerCard run={computer.run} bot={bot} live={computer.live} /> : null}
          </div>
        </div>
      )}
      {open ? (
        <Suspense fallback={null}>
          <ActivitySheet run={run} bot={bot} live={live} computer={computer?.run} technical={technical}
            onClose={() => setOpen(false)} />
        </Suspense>
      ) : null}
    </>
  );
}
