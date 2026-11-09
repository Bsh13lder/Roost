import { lazy, Suspense, useEffect, useState } from "react";
import type { BotOut } from "../../api/types";
import { usePrefersReducedMotion } from "../../hooks/usePrefersReducedMotion";
import { runHost, type ComputerRun } from "../../store/computerRuns";
import { cx } from "../../ui/cx";
import { ChevronIcon } from "../icons";
import { MonitorMark, StepMark } from "./stepIcons";
import { COMPUTER_CARD_FOLD_MS } from "./constants";

// The sheet (the steps, Open computer, Take control) is its own chunk: it loads on the first tap.
const ComputerSheet = lazy(() => import("./ComputerSheet").then((module) => ({ default: module.ComputerSheet })));

export interface ComputerCardProps {
  run: ComputerRun;
  bot: BotOut | undefined;
  live: boolean; // the bot is On it and this is its newest run (store/computerRuns.ts isLiveRun)
}

const stepCount = (run: ComputerRun) => run.steps.at(-1)?.step ?? run.steps.length;

export function foldedLine(run: ComputerRun): string {
  const count = stepCount(run);
  const host = runHost(run);
  return ["Used its computer", host, `${count} ${count === 1 ? "step" : "steps"}`].filter(Boolean).join(" · ");
}

// Live while the run works, folded once it ends: the card shrinks away (COMPUTER_CARD_FOLD_MS) and one quiet
// line takes its place. Reduced motion folds at once.
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

// The computer card (docs/plans/2026-10-23-roost-computer-card.md; owner, 2026-10-26: the chat never shows the
// screen): while the bot works, one compact line with where it is, what it just did and the step number; a tap opens
// the steps sheet, whose Open computer goes to the Computer tab, where the live screen lives. Once the run ends,
// every run, the newest too, is one quiet line that opens the same steps.
export function ComputerCard({ run, bot, live }: ComputerCardProps) {
  const [open, setOpen] = useState(false);
  const phase = usePhase(live);
  const name = bot?.name ?? "The bot";
  return (
    <>
      {phase === "folded" ? (
        <button type="button" className="cc-line" onClick={() => setOpen(true)} aria-label={`${foldedLine(run)}. Show the steps`}>
          <span className="cc-line__mark"><MonitorMark /></span>
          <span className="cc-line__text">{foldedLine(run)}</span>
          <span className="cc-line__chevron"><ChevronIcon /></span>
        </button>
      ) : (
        <LiveLine run={run} name={name} folding={phase === "folding"} onOpen={() => setOpen(true)} />
      )}
      {open ? (
        <Suspense fallback={null}>
          <ComputerSheet run={run} bot={bot} live={live} onClose={() => setOpen(false)} />
        </Suspense>
      ) : null}
    </>
  );
}

function LiveLine({ run, name, folding, onOpen }: { run: ComputerRun; name: string; folding: boolean; onOpen: () => void }) {
  const host = runHost(run);
  const now = run.steps.at(-1);
  const line = now?.line ?? "Getting ready";
  return (
    <div className={cx("cc", folding && "cc--folding")} data-testid="computer-card">
      <div className="cc__inner">
        <button type="button" className="cc__pill" onClick={onOpen}
          aria-label={`${name}’s computer${host ? ` on ${host}` : ""}: ${line}. Show the steps`}>
          <span className="cc__mark">{now ? <StepMark kind={now.kind} /> : <MonitorMark />}</span>
          {host ? <span className="cc__host">{host}</span> : null}
          <span className="cc__line" key={now?.step}>{line}</span>
          <span className="cc__count">Step {stepCount(run)}</span>
        </button>
      </div>
    </div>
  );
}
