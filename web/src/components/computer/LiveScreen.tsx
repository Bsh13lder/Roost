import { useEffect, useRef, type MutableRefObject } from "react";
import { ComputerAsleep } from "../profile/ComputerAsleep";
import { PointerRing } from "./PointerRing";
import { useLiveScreen, type UseLiveScreenOptions } from "../../hooks/useLiveScreen";
import type { BotOut } from "../../api/types";
import type { LiveControls } from "./TouchKeys";

interface LiveScreenProps extends Pick<UseLiveScreenOptions, "openSocket" | "loadRfb"> {
  bot: BotOut;
  mode: "view" | "control"; // control only while you hold the computer (Take control)
  onAsleep: () => void; // the computer went to sleep: the tab shows Computer is asleep
  onControlEnded?: () => void; // control mode: the server gave it back (4000) or it was not held (4409)
  controlsRef?: MutableRefObject<LiveControls | null>; // control mode: the touch keyboard row types through this
}

// A Linux bot's computer, live. View is watch only; control passes your clicks, keys, scrolls and pastes
// through while you hold it. noVNC draws into the container; the states sit over it, and so does the ring that
// shows where the bot just clicked (C3).
export function LiveScreen({ bot, mode, onAsleep, onControlEnded, controlsRef, openSocket, loadRfb }: LiveScreenProps) {
  const target = useRef<HTMLDivElement>(null);
  const { state, retry, typeText, pressKey } = useLiveScreen({ botId: bot.id, target, mode, onControlEnded, openSocket, loadRfb });
  useEffect(() => {
    if (!controlsRef) return undefined;
    controlsRef.current = { typeText, pressKey };
    return () => { controlsRef.current = null; };
  }, [controlsRef, typeText, pressKey]);
  useEffect(() => { if (state === "asleep") onAsleep(); }, [state, onAsleep]);
  return (
    <>
      <div ref={target} className="live-screen" aria-label={`${bot.name}’s screen, live`} role="img"
        hidden={state === "asleep"} />
      {state === "live" ? <PointerRing botId={bot.id} canvasRef={target} /> : null}
      {state === "connecting" ? <p className="screen-box__state live-screen__state">Looking at {bot.name}&rsquo;s screen&hellip;</p> : null}
      {state === "unreachable" ? (
        <p className="screen-box__state live-screen__state">Can&rsquo;t reach {bot.name}&rsquo;s screen ·{" "}
          <button type="button" className="link-btn" onClick={retry}>Retry</button></p>
      ) : null}
      {state === "asleep" ? <ComputerAsleep bot={bot} onOpen={retry} /> : null}
    </>
  );
}
