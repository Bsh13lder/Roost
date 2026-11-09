import { useEffect, useState } from "react";
import { describeError } from "../../../api/client";
import { listRoutineOccurrences } from "../../../api/routines";
import { useLiveState } from "../../../hooks/useLiveStore";
import { groupRoutineDays, type RoutineDays } from "../../../lib/routineDays";
import type { IsoDay } from "../../../ui/date/dates";

const NONE: RoutineDays = new Map();

export interface RoutineDaysInput {
  first: IsoDay;
  last: IsoDay;
  show: boolean; // the Routines switch: off asks for nothing and shows nothing
  botId?: string; // a bot's Plan: only its routines
}

// The routines' run times for a calendar's visible span (GET /api/routines/occurrences), grouped per day. It asks
// again when a routine changes anywhere (routines_changed). Only the newest answer paints; a failed load only leaves
// the calendar without routine lines (a warning in the console), never in the way of the tasks.
export function useRoutineDays({ first, last, show, botId }: RoutineDaysInput): RoutineDays {
  const version = useLiveState().routineVersion?.routines ?? 0;
  const [days, setDays] = useState<RoutineDays>(NONE);
  useEffect(() => {
    if (!show) { setDays(NONE); return undefined; }
    let current = true;
    listRoutineOccurrences(first, last, botId)
      .then((found) => { if (current) setDays(groupRoutineDays(found.occurrences)); })
      .catch((err: unknown) => { if (current) console.warn("Could not load the routines' times:", describeError(err)); });
    return () => { current = false; };
  }, [first, last, show, botId, version]);
  return show ? days : NONE;
}
