import { useState } from "react";
import type { BotOut, RunStepOut } from "../../api/types";
import { formatClock } from "../../lib/chatTime";
import { foldedPillLine, timelineSteps, type ActivityRun } from "../../store/activityRuns";
import type { ComputerRun } from "../../store/computerRuns";
import { Button } from "../../ui/Button";
import { Sheet } from "../../ui/Sheet";
import { cx } from "../../ui/cx";
import { Avatar } from "../Avatar";
import { ChevronIcon } from "../icons";
import { STATUS_LABELS } from "../StatusLabel";
import { ActivityMark } from "./ActivityMark";
import { SheetActions } from "./ComputerSheet";
import { WebMark } from "./WebMark";

export interface ActivitySheetProps {
  run: ActivityRun;
  bot: BotOut | undefined;
  live: boolean;
  computer?: ComputerRun;
  technical?: readonly string[];
  onClose: () => void;
}

// What the activity pill opens: who, how long, every step in plain words with its time on the account's clock (the running one says
// Now), Open computer when the run used it (the screen lives on the Computer tab), and Technical details.
export function ActivitySheet({ run, bot, live, computer, technical = [], onClose }: ActivitySheetProps) {
  const name = bot?.name ?? "The bot";
  const footer = computer ? <SheetActions botId={run.botId} onClose={onClose} />
    : <div className="cc-sheet__actions"><Button variant="secondary" onClick={onClose}>Close</Button></div>;
  return (
    <Sheet open onOpenChange={(open) => { if (!open) onClose(); }} title={`What ${name} did`} footer={footer}>
      <div className="as">
        <div className="cc-sheet__who">
          {bot ? <Avatar avatar={bot.avatar} status={bot.status} size={40} label={false} decorative botId={bot.id} /> : null}
          <div className="cc-sheet__who-text">
            <span className="cc-sheet__name">{name}</span>
            <span className="cc-sheet__where">{foldedPillLine(run, computer)}</span>
          </div>
          <span className={cx("cc-sheet__status", live && "cc-sheet__status--live")}>
            {live ? <span className="cc__dot" aria-hidden="true" /> : null}
            {bot ? STATUS_LABELS[bot.status] : "Resting"}
          </span>
        </div>
        <Timeline run={run} live={live} />
        {technical.length > 0 ? <Technical lines={technical} /> : null}
      </div>
    </Sheet>
  );
}

// A note: the bot's own words between steps (owner, 2026-11-04), a quiet sentence on the thread with the Web mark
// when the run had read outside content.
function NoteRow({ step }: { step: RunStepOut }) {
  return (
    <li className="as-step as-step--note">
      <span className="as-step__mark"><ActivityMark kind="note" /></span>
      <span className="as-step__line">
        {step.line}
        {step.tainted ? <WebMark className="as-step__web" /> : null}
      </span>
      <span className="as-step__time">{formatClock(step.at)}</span>
    </li>
  );
}

function Timeline({ run, live }: { run: ActivityRun; live: boolean }) {
  const steps = timelineSteps(run);
  if (steps.length === 0) {
    return <p className="as__empty">{live ? "Thinking it over. Steps show here as it works." : "It only thought this one through."}</p>;
  }
  return (
    <section aria-label="Steps">
      <h3 className="cc-steps__title">Steps</h3>
      <ol className="as__list">
        {steps.map((step) => {
          if (step.kind === "note") return <NoteRow key={step.step} step={step} />;
          const now = live && step.state === "start";
          return (
            <li key={step.step} className={cx("as-step", now && "as-step--now", step.state === "failed" && "as-step--failed")}>
              <span className="as-step__mark"><ActivityMark kind={step.kind} moving={now} /></span>
              <span className="as-step__line">
                {step.line}
                {step.state === "failed" ? <span className="as-step__note">Didn’t finish</span> : null}
              </span>
              <span className="as-step__time">{now ? "Now" : formatClock(step.at)}</span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function Technical({ lines }: { lines: readonly string[] }) {
  const [open, setOpen] = useState(false);
  return (
    <section className="as-tech">
      <button type="button" className="as-tech__toggle" aria-expanded={open} onClick={() => setOpen((was) => !was)}>
        <span className={cx("as-tech__chevron", open && "as-tech__chevron--open")}><ChevronIcon /></span>
        Technical details
      </button>
      {open ? (
        <ol className="as-tech__list">
          {lines.map((line, index) => <li key={`${index}-${line}`}>{line}</li>)}
        </ol>
      ) : null}
    </section>
  );
}
