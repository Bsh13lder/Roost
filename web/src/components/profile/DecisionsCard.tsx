import { useCallback, useEffect, useId, useRef, useState } from "react";
import * as memoriesApi from "../../api/memories";
import { describeError } from "../../api/client";
import type { MemoryOut } from "../../api/types";
import { useLiveState } from "../../hooks/useLiveStore";
import { decidedAt, parseDecision } from "../../lib/decisions";
import { Button } from "../../ui/Button";
import { ErrorNotice } from "../ErrorNotice";

// "Decisions" on the Info tab: the options you picked for this bot, each with Forget so it may ask again.
export function DecisionsCard({ botId }: { botId: string }) {
  const headId = useId();
  const version = useLiveState().boardVersion.memories;
  const [rows, setRows] = useState<readonly MemoryOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef(0); // a slower, older load never wins
  const load = useCallback(() => {
    const ticket = ++latest.current;
    memoriesApi.listMemories(botId, { kind: "decision" })
      .then((loaded) => { if (ticket === latest.current) { setRows(loaded); setError(null); } })
      .catch((err: unknown) => { if (ticket === latest.current) setError(describeError(err)); });
  }, [botId]);
  useEffect(() => load(), [load, version]);
  const forget = async (id: string) => {
    try {
      await memoriesApi.forgetMemory(id);
      setRows((now) => now.filter((row) => row.id !== id));
    } catch (err) {
      setError(describeError(err));
    }
  };
  const decisions = rows.flatMap((row) => {
    const parsed = parseDecision(row.text);
    return parsed ? [{ id: row.id, when: decidedAt(row.updated_at), ...parsed }] : [];
  });
  return (
    <section className="info-card decisions" aria-labelledby={headId}>
      <h3 className="decisions__title" id={headId}>Decisions</h3>
      {decisions.length === 0 ? <p className="decisions__empty">No decisions yet.</p> : (
        <ul className="decisions__list">
          {decisions.map((d) => (
            <li key={d.id} className="decisions__item">
              <div className="decisions__text">
                <p className="decisions__question">{d.question}</p>
                <p className="decisions__answer">{d.answer}</p>
                <p className="decisions__when">{d.when}</p>
              </div>
              <Button size="sm" variant="secondary" onClick={() => void forget(d.id)}>Forget</Button>
            </li>
          ))}
        </ul>
      )}
      {error ? <ErrorNotice message={error} /> : null}
    </section>
  );
}
