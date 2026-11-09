import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "../../ui/Button";
import { describeError } from "../../api/client";
import * as connectorsApi from "../../api/connectors";
import type { ConnectorOut } from "../../api/connectors";
import { useLiveState } from "../../hooks/useLiveStore";
import { ErrorNotice } from "../ErrorNotice";
import { CONNECTORS_EMPTY, EVERY_BOT, NEW_CONNECTOR, ONLY_THIS_BOT } from "./constants";
import { ConnectorEditor } from "./ConnectorEditor";

type Editing = { connector: ConnectorOut | null } | null;

const replaceOrAdd = (list: readonly ConnectorOut[], next: ConnectorOut) =>
  list.some((one) => one.id === next.id) ? list.map((one) => (one.id === next.id ? next : one)) : [...list, next];

const whoText = (c: ConnectorOut, botId: string) =>
  c.bot_ids === null ? EVERY_BOT : c.bot_ids.includes(botId) ? ONLY_THIS_BOT : "Other bots";

// The Connectors fold on the Info tab: every connector (name, site, key hint, who may use it), Add and the editor.
// This file is the lazy chunk's entry, so none of it is in the main bundle.
export default function ConnectorsSection({ botId }: { botId: string }) {
  const version = useLiveState().connectorVersion;
  const [connectors, setConnectors] = useState<readonly ConnectorOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<Editing>(null);
  const latest = useRef(0);
  const load = useCallback(() => {
    const ticket = ++latest.current;
    connectorsApi.listConnectors()
      .then((loaded) => { if (ticket === latest.current) { setConnectors(loaded); setError(null); } })
      .catch((err: unknown) => { if (ticket === latest.current) setError(describeError(err)); });
  }, []);
  useEffect(() => load(), [load, version]);

  return (
    <div className="skills">
      <div className="skills__head">
        <Button size="sm" variant="secondary" onClick={() => setEditing({ connector: null })}>{NEW_CONNECTOR}</Button>
      </div>
      {connectors?.length === 0 ? <p className="skills__empty">{CONNECTORS_EMPTY}</p> : null}
      <ul className="skills__list">
        {(connectors ?? []).map((c) => (
          <li key={c.id} className="skill-row">
            <button type="button" className="skill-row__main" onClick={() => setEditing({ connector: c })}>
              <span className="skill-row__name">{c.name}</span>
              <span className="skill-row__when">{`${c.host} · ${c.key_hint} · ${whoText(c, botId)}`}</span>
            </button>
          </li>
        ))}
      </ul>
      {error ? <ErrorNotice message={error} onRetry={load} /> : null}
      {editing ? (
        <ConnectorEditor connector={editing.connector} botId={botId} onClose={() => setEditing(null)}
          onSaved={(saved) => { setConnectors((now) => replaceOrAdd(now ?? [], saved)); setEditing(null); }}
          onDeleted={(id) => { setConnectors((now) => (now ?? []).filter((one) => one.id !== id)); setEditing(null); }} />
      ) : null}
    </div>
  );
}
