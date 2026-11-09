import type { ReactNode } from "react";
import { useScreenToggle } from "../../hooks/useScreenToggle";
import { Switch } from "../../ui/Switch";

export const ROUTINES_LABEL = "Routines";
export const BOT_MADE_LABEL = "Made by bots";
export const DONE_LABEL = "Done";

export interface ShowTogglesProps {
  screen: string; // whose choices these are (SCREEN_* in constants.ts)
  routines?: boolean; // a calendar: the Routines switch
  botMade?: boolean; // tasks: the Made by bots switch
  done?: ReactNode; // the shared Show finished switch, where the screen has one
  ownDone?: boolean; // a screen with its own Done switch (a bot's Plan), remembered with the others
  botMadeHidden?: number; // how many bot-made tasks the screen is leaving out, said while that switch is off
}

// Show / hide on a screen (board toggles, 2026-10-26): Routines on a calendar, Done, and Made by bots. Each is
// remembered per screen in this browser; Show finished stays the one shared switch it always was.
export function ShowToggles({ screen, routines = false, botMade = true, done, ownDone = false, botMadeHidden = 0 }: ShowTogglesProps) {
  const [showRoutines, setRoutines] = useScreenToggle(screen, "routines");
  const [showMade, setMade] = useScreenToggle(screen, "botMade");
  const [showDone, setDone] = useScreenToggle(screen, "done");
  return (
    <span className="show-toggles" role="group" aria-label="Show">
      {routines ? <Switch checked={showRoutines} onChange={setRoutines}>{ROUTINES_LABEL}</Switch> : null}
      {ownDone ? <Switch checked={showDone} onChange={setDone}>{DONE_LABEL}</Switch> : null}
      {done}
      {botMade ? <Switch checked={showMade} onChange={setMade}>{BOT_MADE_LABEL}</Switch> : null}
      {botMade && !showMade && botMadeHidden > 0 ? <span className="show-toggles__count">{botMadeHidden} by bots hidden</span> : null}
    </span>
  );
}
