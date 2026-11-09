import { useCallback, useMemo, useRef, useState } from "react";
import { Sheet } from "../../ui/Sheet";
import { Button } from "../../ui/Button";
import { useToast } from "../../ui/Toast";
import * as computerApi from "../../api/computer";
import * as stuckApi from "../../api/stuck";
import { describeError } from "../../api/client";
import type { BotOut, StuckCardOut } from "../../api/types";
import type { UseLiveScreenOptions } from "../../hooks/useLiveScreen";
import { useMediaQuery } from "../../hooks/useMediaQuery";
import { ErrorNotice } from "../ErrorNotice";
import { GiveBackForm } from "./GiveBackForm";
import { LiveScreen } from "./LiveScreen";
import { TeachBar } from "./TeachBar";
import { TouchKeys, type LiveControls } from "./TouchKeys";
import { CONTROL_GIVEN_BACK_TEXT, TOUCH_POINTER_QUERY } from "./constants";

interface ControlScreenProps extends Pick<UseLiveScreenOptions, "openSocket" | "loadRfb"> {
  bot: BotOut;
  card?: StuckCardOut; // the bot's open Stuck card: I'm done clears it, so the bot carries on
  teaching?: boolean; // Teach a task: the bar says I'm done teaching instead of I'm done
  onClosed: (cleared?: StuckCardOut) => void; // control ended, by you or by the server (with the cleared card)
}

interface BarProps {
  bot: BotOut;
  card?: StuckCardOut;
  onClosed: (cleared?: StuckCardOut) => void;
}

const noop = () => {};

// What I'm done sends with a Stuck card: the account and, on a Sign-in card, Keep me signed in. Nothing: no body.
function clearOptions(account: string | undefined, keep: boolean | undefined): stuckApi.ClearOptions | undefined {
  if (!account && keep === undefined) return undefined;
  return { ...(account ? { account } : {}), ...(keep !== undefined ? { keep } : {}) };
}

// I'm done → "Which account did you use?" → Give it back (or clear the Stuck card with it).
function GiveBackBar({ bot, card, onClosed }: BarProps) {
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const done = async (account: string | undefined, keep?: boolean) => {
    setBusy(true);
    setError(null);
    try {
      if (card) return onClosed(await stuckApi.clearStuck(card.id, clearOptions(account, keep)));
      await (account ? computerApi.giveBack(bot.id, account) : computerApi.giveBack(bot.id));
      onClosed();
    } catch (err) {
      setError(describeError(err));
      setBusy(false);
    }
  };
  if (asking) {
    return (
      <GiveBackForm host={card?.host || undefined} signIn={Boolean(card?.sign_in)} busy={busy} error={error}
        onConfirm={(a, keep) => void done(a, keep)} onBack={() => { setAsking(false); setError(null); }} />
    );
  }
  return (
    <>
      <span className="control-screen__state">You&apos;re in control</span>
      <Button variant="primary" size="md" onClick={() => setAsking(true)}>I&apos;m done</Button>
      {error ? <ErrorNotice message={error} /> : null}
    </>
  );
}

// The full-screen Take control (Computers 2.0, C2): the bot's live screen fills the window and your clicks, keys,
// scrolls and pastes go to it while you hold control. Escape belongs to the page, so it never closes this.
// On a touch screen (a phone's browser over Tailscale) taps are clicks and a keyboard row types for you.
export function ControlScreen({ bot, card, teaching, onClosed, openSocket, loadRfb }: ControlScreenProps) {
  const toast = useToast();
  const ended = useCallback(() => { toast.show(CONTROL_GIVEN_BACK_TEXT); onClosed(); }, [toast, onClosed]);
  const touch = useMediaQuery(TOUCH_POINTER_QUERY);
  const live = useRef<LiveControls | null>(null);
  const controls = useMemo<LiveControls>(() => ({
    typeText: (text) => live.current?.typeText(text),
    pressKey: (key) => live.current?.pressKey(key),
  }), []);
  return (
    <Sheet open bare size="full" title={`${bot.name}'s computer, full screen`} onOpenChange={noop}>
      <div className="control-screen">
        <div className="control-screen__stage">
          <LiveScreen bot={bot} mode="control" onAsleep={ended} onControlEnded={ended} controlsRef={live}
            openSocket={openSocket} loadRfb={loadRfb} />
        </div>
        {touch ? <TouchKeys controls={controls} /> : null}
        <div className="control-screen__bar">
          {teaching
            ? <TeachBar bot={bot} onClosed={onClosed} />
            : <GiveBackBar bot={bot} card={card} onClosed={onClosed} />}
        </div>
      </div>
    </Sheet>
  );
}
