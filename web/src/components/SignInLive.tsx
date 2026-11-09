// web/src/components/SignInLive.tsx — the Sign-in card's live screen, right in the chat (owner, 2026-10-22).
// Before Take control the card shows a small view-only preview of the bot's computer, opened only while the card
// is on screen; after it, the screen in control mode fills the chat column at the computer's own shape, and Full
// screen (or a phone) opens the full-screen sheet. noVNC and the sheet stay lazy chunks. The card renders at most
// one of these at a time, so the page never holds a view and a control socket for one bot together.
import { lazy, Suspense, useCallback, useRef, useState } from "react";
import * as deskApi from "../api/desk";
import { describeError } from "../api/client";
import type { BotOut, StuckCardOut } from "../api/types";
import { useOnScreen } from "../hooks/useOnScreen";
import { ErrorNotice } from "./ErrorNotice";

const LiveScreen = lazy(() => import("./computer/LiveScreen").then((module) => ({ default: module.LiveScreen })));
const ControlScreen = lazy(() => import("./computer/ControlScreen").then((module) => ({ default: module.ControlScreen })));

// The small preview: the socket opens when the card scrolls into view and closes when it scrolls away.
// A sleeping computer has nothing to show, so the preview steps aside.
export function SignInPreview({ bot }: { bot: BotOut }) {
  const box = useRef<HTMLDivElement>(null);
  const [asleep, setAsleep] = useState(false);
  const onScreen = useOnScreen(box, !asleep);
  const sleep = useCallback(() => setAsleep(true), []);
  if (asleep) return null;
  return (
    <div ref={box} className="screen-box sign-in-screen sign-in-screen--preview">
      {onScreen ? (
        <Suspense fallback={null}><LiveScreen bot={bot} mode="view" onAsleep={sleep} /></Suspense>
      ) : null}
    </div>
  );
}

// You hold the computer: its screen in the chat column, your clicks and keys going to it (a click focuses it).
// A computer that fell asleep is woken once per hold (as the Computer tab's Take control does), then looked at again.
export function SignInInline({ bot, onControlEnded }: { bot: BotOut; onControlEnded: () => void }) {
  const [attempt, setAttempt] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const woke = useRef(false);
  const wake = useCallback(() => {
    if (woke.current) return;
    woke.current = true;
    deskApi.startBrowser(bot.id)
      .then(() => setAttempt((value) => value + 1))
      .catch((err: unknown) => setError(describeError(err)));
  }, [bot.id]);
  return (
    <>
      <div className="screen-box sign-in-screen sign-in-screen--control">
        <Suspense fallback={null}>
          <LiveScreen key={attempt} bot={bot} mode="control" onAsleep={wake} onControlEnded={onControlEnded} />
        </Suspense>
      </div>
      {error ? <ErrorNotice message={error} /> : null}
    </>
  );
}

// Full screen: the existing sheet, whose I'm done runs the same Keep me signed in question and clear.
export function SignInFullScreen({ bot, card, onClosed }: {
  bot: BotOut; card: StuckCardOut; onClosed: (cleared?: StuckCardOut) => void;
}) {
  return (
    <Suspense fallback={null}>
      <ControlScreen bot={bot} card={card} onClosed={onClosed} />
    </Suspense>
  );
}
