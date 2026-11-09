import { useCallback, useEffect, useId, useRef, useState } from "react";
import { Button } from "../../ui/Button";
import { describeError } from "../../api/client";
import * as routinesApi from "../../api/routines";
import type { RoutineOut } from "../../api/routines";
import { useLiveState } from "../../hooks/useLiveStore";
import { ErrorNotice } from "../ErrorNotice";
import { RoutineEditor } from "./RoutineEditor";
import { RoutineHistory } from "./RoutineHistory";
import { RoutineRow } from "./RoutineRow";

type Panel = { kind: "edit"; routine: RoutineOut | null } | { kind: "history"; routine: RoutineOut } | null;

const replaceOrAdd = (list: readonly RoutineOut[], next: RoutineOut) =>
  list.some((one) => one.id === next.id) ? list.map((one) => (one.id === next.id ? next : one)) : [...list, next];

// "Routines" on the Info tab: the bot's scheduled jobs with a switch each, Run now, Edit, History and Delete,
// and New routine. It reloads on routines_changed. A lazy chunk (the Info tab reaches it through React.lazy).
export function RoutinesCard({ botId }: { botId: string }) {
  const headId = useId();
  const version = useLiveState().routineVersion?.routines;
  const [routines, setRoutines] = useState<readonly RoutineOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [panel, setPanel] = useState<Panel>(null);
  const latest = useRef(0); // a slower, older load never wins
  const load = useCallback(() => {
    const ticket = ++latest.current;
    routinesApi.listRoutines(botId)
      .then((loaded) => { if (ticket === latest.current) { setRoutines(loaded); setError(null); } })
      .catch((err: unknown) => { if (ticket === latest.current) setError(describeError(err)); });
  }, [botId]);
  useEffect(() => load(), [load, version]);
  const close = () => setPanel(null);
  return (
    <section className="info-card routines" aria-labelledby={headId}>
      <div className="routines__head">
        <h3 className="routines__title" id={headId}>Routines</h3>
        <Button size="sm" variant="secondary" onClick={() => setPanel({ kind: "edit", routine: null })}>New routine</Button>
      </div>
      {routines?.length === 0 ? <p className="routines__empty">No routines yet. Ask your bot to set one up, or add one here.</p> : null}
      <ul className="routines__list">
        {(routines ?? []).map((routine) => (
          <RoutineRow key={routine.id} routine={routine}
            onChanged={(next) => setRoutines((now) => replaceOrAdd(now ?? [], next))}
            onRemoved={(id) => setRoutines((now) => (now ?? []).filter((one) => one.id !== id))}
            onEdit={(one) => setPanel({ kind: "edit", routine: one })}
            onHistory={(one) => setPanel({ kind: "history", routine: one })} />
        ))}
      </ul>
      {error ? <ErrorNotice message={error} onRetry={load} /> : null}
      {panel?.kind === "edit" ? (
        <RoutineEditor botId={botId} routine={panel.routine} onClose={close}
          onSaved={(saved) => { setRoutines((now) => replaceOrAdd(now ?? [], saved)); close(); }} />
      ) : null}
      {panel?.kind === "history" ? <RoutineHistory botId={botId} routine={panel.routine} onClose={close} /> : null}
    </section>
  );
}
