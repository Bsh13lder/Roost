import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { ErrorNotice } from "../ErrorNotice";
import { Button } from "../../ui/Button";
import * as computerApi from "../../api/computer";
import * as teachApi from "../../api/teach";
import { describeError } from "../../api/client";
import type { BotOut, StuckCardOut } from "../../api/types";

// Control mode (the sheet, the form, noVNC input) is its own chunk: the main bundle stays within its budget.
const ControlScreen = lazy(() => import("./ControlScreen").then((module) => ({ default: module.ControlScreen })));

interface LinuxControlProps {
  bot: BotOut;
  card: StuckCardOut | undefined;
  running: boolean | null; // the computer is awake (null: not known yet)
  wake: () => Promise<void>; // Open it
  onClosed: () => void; // control ended: the tab looks again
}

// Take control of a Linux computer: wake it if it sleeps, take the lock, then the live screen fills the window.
// A computer that is already held (the Stuck card's Take control, another tab) opens the full screen at once.
// Teach is Take control that also records the task you show, for a skill the bot proposes when you are done.
export function LinuxControl({ bot, card, running, wake, onClosed }: LinuxControlProps) {
  const [held, setHeld] = useState(false);
  const [teaching, setTeaching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // A new location (the Stuck card's Take control navigates here) asks the server again who holds the computer.
  const { key: visit } = useLocation();
  useEffect(() => {
    let cancelled = false;
    computerApi.getControl(bot.id)
      .then((control) => { if (!cancelled) setHeld(control.held); })
      .catch((err: unknown) => { if (!cancelled) setError(describeError(err)); });
    teachApi.getTeach(bot.id)
      .then((teach) => { if (!cancelled) setTeaching(teach.teaching); })
      .catch((err: unknown) => { if (!cancelled) setError(describeError(err)); });
    return () => { cancelled = true; };
  }, [bot.id, visit]);
  // Holding a sleeping computer (the Stuck card's Take control) wakes it before the screen opens.
  const waking = useRef(false);
  const latestWake = useRef(wake);
  latestWake.current = wake;
  useEffect(() => {
    if (!held) { waking.current = false; return; }
    if (running !== false || waking.current) return;
    waking.current = true; // once per hold: a refresh of the tab never wakes it twice
    latestWake.current().catch((err: unknown) => setError(describeError(err)));
  }, [held, running]);
  const take = async () => {
    setError(null);
    try {
      setHeld((await computerApi.takeControl(bot.id)).held);
    } catch (err) {
      setError(describeError(err));
    }
  };
  const teach = async () => {
    setError(null);
    try {
      const started = await teachApi.startTeach(bot.id);
      setTeaching(started.teaching);
      setHeld(started.teaching);
    } catch (err) {
      setError(describeError(err));
    }
  };
  return (
    <div className="control">
      <div className="control__actions">
        <Button variant="primary" onClick={() => void take()}>Take control</Button>
        <Button variant="secondary" onClick={() => void teach()}>Teach</Button>
      </div>
      {error ? <ErrorNotice message={error} /> : null}
      {held && running ? (
        <Suspense fallback={null}>
          <ControlScreen bot={bot} card={card} teaching={teaching}
            onClosed={() => { setHeld(false); setTeaching(false); onClosed(); }} />
        </Suspense>
      ) : null}
    </div>
  );
}
