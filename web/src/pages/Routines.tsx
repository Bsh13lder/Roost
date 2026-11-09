import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { describeError } from "../api/client";
import * as routinesApi from "../api/routines";
import type { HubRoutineOut, HubRunOut, RoutineOut } from "../api/routines";
import { useLiveState } from "../hooks/useLiveStore";
import { ErrorNotice } from "../components/ErrorNotice";
import { RUN_STATE_WORDS } from "../components/routines/constants";
import { zoneStamp } from "../components/routines/zoneTime";
import { RoutineEditor } from "../components/routines/RoutineEditor";
import { RoutineHistory } from "../components/routines/RoutineHistory";
import { RoutineRow } from "../components/routines/RoutineRow";
import { TemplatesList } from "../components/routines/TemplatesList";

const RECENT_RUNS = 20;

type Panel = { kind: "edit"; botId: string; routine: RoutineOut } | { kind: "history"; routine: HubRoutineOut } | null;
type Loaded = { routines: readonly HubRoutineOut[]; runs: readonly HubRunOut[] };

// "Last: Done · Wed 21 Oct 10:07", and the run's note when it has one.
function lastResult(routine: HubRoutineOut): string | null {
  if (!routine.last_state) return null;
  const when = zoneStamp(routine.last_finished_at ?? routine.last_run_at);
  const note = routine.last_note ? ` · ${routine.last_note}` : "";
  return `Last: ${RUN_STATE_WORDS[routine.last_state]}${when ? ` · ${when}` : ""}${note}`;
}

function useHubData() {
  const version = useLiveState().routineVersion?.routines;
  const [data, setData] = useState<Loaded | null>(null);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef(0); // a slower, older load never wins
  const load = useCallback(() => {
    const ticket = ++latest.current;
    Promise.all([routinesApi.listAllRoutines(), routinesApi.listRecentRuns(RECENT_RUNS)])
      .then(([routines, runs]) => { if (ticket === latest.current) { setData({ routines, runs }); setError(null); } })
      .catch((err: unknown) => { if (ticket === latest.current) setError(describeError(err)); });
  }, []);
  useEffect(() => load(), [load, version]);
  return { data, error, load };
}

function RecentRuns({ runs }: { runs: readonly HubRunOut[] }) {
  if (runs.length === 0) return <p className="routines__empty">No runs yet.</p>;
  return (
    <ul className="routines__list">
      {runs.map((run) => (
        <li key={run.id} className="routines-page__run">
          <Link to={`/bots/${run.bot_id}/routines/${run.routine_id}/log`}>{run.routine_name}</Link>
          {` · ${run.bot_name} · ${RUN_STATE_WORDS[run.state]} · ${zoneStamp(run.finished_at ?? run.slot_at)}`}
        </li>
      ))}
    </ul>
  );
}

// Every routine of every bot in one place (a lazy page at /routines): the switch, Run now, Edit, History and the
// last result; the newest runs across bots; and the routine templates, each with "Add to…" a bot.
export function Routines() {
  const bots = Object.values(useLiveState().bots);
  const { data, error, load } = useHubData();
  const [panel, setPanel] = useState<Panel>(null);
  const close = () => setPanel(null);
  const changed = (_next: RoutineOut) => load();

  return (
    <div className="routines-page">
      <h1 className="routines-page__title">Routines</h1>
      {error ? <ErrorNotice message={error} onRetry={load} /> : null}
      <section className="info-card routines" aria-label="Your routines">
        <h2 className="routines__title">Your routines</h2>
        {data === null ? <p className="routines__loading">Loading&hellip;</p> : null}
        {data?.routines.length === 0 ? <p className="routines__empty">No routines yet. Add one from a template below.</p> : null}
        <ul className="routines__list">
          {(data?.routines ?? []).map((routine) => (
            <RoutineRow key={routine.id} routine={routine} onChanged={changed} onRemoved={() => load()}
              onEdit={() => setPanel({ kind: "edit", botId: routine.bot_id, routine })} onHistory={() => setPanel({ kind: "history", routine })}
              extra={<p className="routine-row__next">{routine.bot_name}{lastResult(routine) ? ` · ${lastResult(routine)}` : ""}</p>} />
          ))}
        </ul>
      </section>
      <section className="info-card routines" aria-label="Recent runs">
        <h2 className="routines__title">Recent runs</h2>
        <RecentRuns runs={data?.runs ?? []} />
      </section>
      <section className="info-card routines" aria-label="Templates">
        <h2 className="routines__title">Templates</h2>
        <TemplatesList bots={bots} onAdded={load}
          onNeedsEdit={(botId, routine) => setPanel({ kind: "edit", botId, routine })} />
      </section>
      {panel?.kind === "edit" ? (
        <RoutineEditor botId={panel.botId} routine={panel.routine} onClose={close}
          onSaved={() => { load(); close(); }} />
      ) : null}
      {panel?.kind === "history" ? <RoutineHistory botId={panel.routine.bot_id} routine={panel.routine} onClose={close} /> : null}
    </div>
  );
}
