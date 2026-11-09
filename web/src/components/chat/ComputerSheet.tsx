import { useState } from "react";
import { useNavigate } from "react-router-dom";
import * as computerApi from "../../api/computer";
import { describeError } from "../../api/client";
import type { BotOut } from "../../api/types";
import { formatClock } from "../../lib/chatTime";
import { runHost, type ComputerRun } from "../../store/computerRuns";
import { Button } from "../../ui/Button";
import { Sheet } from "../../ui/Sheet";
import { cx } from "../../ui/cx";
import { Avatar } from "../Avatar";
import { ErrorNotice } from "../ErrorNotice";
import { STATUS_LABELS } from "../StatusLabel";
import { OPEN_COMPUTER_LABEL } from "./constants";
import { StepMark } from "./stepIcons";

export interface ComputerSheetProps {
  run: ComputerRun;
  bot: BotOut | undefined;
  live: boolean;
  onClose: () => void;
}

// What the computer card opens: who and where, every step this page saw, newest first, with its time on the account's clock, and
// Open computer and Take control. No screen here (owner, 2026-10-26): it lives on the bot's Computer tab.
export function ComputerSheet({ run, bot, live, onClose }: ComputerSheetProps) {
  const name = bot?.name ?? "The bot";
  const host = runHost(run);
  return (
    <Sheet open onOpenChange={(open) => { if (!open) onClose(); }} title={`${name}’s computer`}
      footer={<SheetActions botId={run.botId} onClose={onClose} />}>
      <div className="cc-sheet">
        <div className="cc-sheet__who">
          {bot ? <Avatar avatar={bot.avatar} status={bot.status} size={40} label={false} decorative botId={bot.id} /> : null}
          <div className="cc-sheet__who-text">
            <span className="cc-sheet__name">{name}</span>
            <span className="cc-sheet__where">{host ?? "On its desktop"}</span>
          </div>
          <span className={cx("cc-sheet__status", live && "cc-sheet__status--live")}>
            {live ? <span className="cc__dot" aria-hidden="true" /> : null}
            {bot ? STATUS_LABELS[bot.status] : "Resting"}
          </span>
        </div>
        <StepList run={run} live={live} />
      </div>
    </Sheet>
  );
}

function StepList({ run, live }: { run: ComputerRun; live: boolean }) {
  const steps = [...run.steps].reverse();
  const first = run.steps[0]?.step ?? 1;
  return (
    <section className="cc-steps" aria-label="Steps">
      <h3 className="cc-steps__title">Steps</h3>
      <ol className="cc-steps__list">
        {steps.map((step, index) => (
          <li key={step.step} className={cx("cc-step", index === 0 && live && "cc-step--now")}>
            <span className="cc-step__mark"><StepMark kind={step.kind} /></span>
            <span className="cc-step__line">{step.line}</span>
            <span className="cc-step__time">{index === 0 && live ? "Now" : formatClock(step.at)}</span>
          </li>
        ))}
      </ol>
      {first > 1 ? <p className="cc-steps__more">{`${first - 1} earlier ${first === 2 ? "step" : "steps"} not shown`}</p> : null}
    </section>
  );
}

// Close, Open computer (the Computer tab, where the screen is) and Take control; the activity pill's sheet shows the
// same buttons when its run used the computer.
export function SheetActions({ botId, onClose }: { botId: string; onClose: () => void }) {
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // The computer panel opens in control: its held state shows the full screen at once (as the Stuck card does).
  const take = async () => {
    setBusy(true);
    setError(null);
    try {
      await computerApi.takeControl(botId);
      onClose();
      navigate(`/bots/${botId}?panel=computer`);
    } catch (err) {
      setError(describeError(err));
      setBusy(false);
    }
  };
  return (
    <div className="cc-sheet__actions">
      {error ? <ErrorNotice message={error} /> : null}
      <Button variant="ghost" onClick={onClose}>Close</Button>
      <Button variant="secondary" onClick={() => { onClose(); navigate(`/bots/${botId}?panel=computer`); }}>
        {OPEN_COMPUTER_LABEL}
      </Button>
      <Button variant="primary" onClick={() => void take()} disabled={busy}>Take control</Button>
    </div>
  );
}
