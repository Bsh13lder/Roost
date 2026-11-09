import { Link } from "react-router-dom";
import { routineLink, routineTimeWords, routineWords, type RoutineDayEntry } from "../../../lib/routineDays";
import { RepeatIcon } from "../../icons";

// One routine's runs on one day, as a quiet line on a calendar (board toggles): a repeat mark, the time on the account's clock
// ("09:00 +3" when it runs more that day), the routine's name and its bot's. Unlike a task it has no project wash and
// does not drag; a tap opens the routine's run log.
export function RoutineChip({ entry, showBot = true }: { entry: RoutineDayEntry; showBot?: boolean }) {
  const words = routineWords(entry);
  return (
    <Link className="rchip" to={routineLink(entry)} title={words} aria-label={words}>
      <span className="rchip__mark" aria-hidden="true"><RepeatIcon /></span>
      <span className="rchip__time">{routineTimeWords(entry)}</span>
      <span className="rchip__name">{entry.routineName}</span>
      {showBot && entry.botName ? <span className="rchip__bot">{entry.botName}</span> : null}
    </Link>
  );
}

// A day's routine lines, at most `max` of them, then "+N routines" in words.
export function RoutineLines({ entries, max, showBot = true }: { entries: readonly RoutineDayEntry[]; max?: number; showBot?: boolean }) {
  const shown = max === undefined ? entries : entries.slice(0, max);
  const more = entries.length - shown.length;
  return (
    <>
      {shown.map((entry) => <RoutineChip key={entry.routineId} entry={entry} showBot={showBot} />)}
      {more > 0 ? <span className="rchip__more">+{more} routine{more === 1 ? "" : "s"}</span> : null}
    </>
  );
}
