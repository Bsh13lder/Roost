import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Sheet } from "../../ui/Sheet";
import { describeError } from "../../api/client";
import * as routinesApi from "../../api/routines";
import type { RoutineOut, RoutineRunOut } from "../../api/routines";
import { ErrorNotice } from "../ErrorNotice";
import { RUN_STATE_WORDS } from "./constants";
import { zoneStamp } from "./zoneTime";

// A routine's runs, newest first, each in plain words. A run with a Report links to the chat.
export function RoutineHistory({ botId, routine, onClose }: { botId: string; routine: RoutineOut; onClose: () => void }) {
  const [runs, setRuns] = useState<readonly RoutineRunOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    routinesApi.listRuns(routine.id)
      .then((loaded) => { if (live) setRuns(loaded); })
      .catch((err: unknown) => { if (live) setError(describeError(err)); });
    return () => { live = false; };
  }, [routine.id]);
  return (
    <Sheet open title={`History · ${routine.builtin ? "End-of-day summary" : routine.name}`} onOpenChange={(open) => { if (!open) onClose(); }}>
      {error ? <ErrorNotice message={error} /> : null}
      {runs === null && !error ? <p className="routine-history__empty">Loading&hellip;</p> : null}
      {runs?.length === 0 ? <p className="routine-history__empty">No runs yet.</p> : null}
      <ul className="routine-history">
        {(runs ?? []).map((run) => (
          <li key={run.id} className="routine-history__run">
            <span className={`routine-history__state routine-history__state--${run.state}`}>{RUN_STATE_WORDS[run.state]}</span>
            <span className="routine-history__when">{zoneStamp(run.slot_at)}</span>
            {run.missed_count > 1 ? <span className="routine-history__note">{`${run.missed_count} runs missed`}</span> : null}
            {run.note ? <span className="routine-history__note">{run.note}</span> : null}
            {run.report_message_id ? (
              <Link className="routine-history__link" to={`/bots/${botId}#${run.report_message_id}`} onClick={onClose}>See the Report</Link>
            ) : null}
          </li>
        ))}
      </ul>
    </Sheet>
  );
}
