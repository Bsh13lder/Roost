import { useCallback, useEffect, useId, useRef, useState } from "react";
import * as memoriesApi from "../../api/memories";
import { describeError } from "../../api/client";
import type { BotOut, MemoryKind, MemoryOut } from "../../api/types";
import { useLiveState } from "../../hooks/useLiveStore";
import { Button } from "../../ui/Button";
import { ErrorNotice } from "../ErrorNotice";
import { ABOUT_YOU_KINDS, BOT_KINDS } from "./constants";
import { MemoryForm, type MemoryDraftIn } from "./MemoryForm";
import { MemoryRow } from "./MemoryRow";

type Side = "about" | "bot";

function useMemories(botId: string, faded: boolean, version: number) {
  const [memories, setMemories] = useState<readonly MemoryOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef(0); // a slower, older load never wins
  const load = useCallback(() => {
    const ticket = ++latest.current;
    memoriesApi.listMemories(botId, { faded })
      .then((loaded) => { if (ticket === latest.current) { setMemories(loaded); setError(null); } })
      .catch((err: unknown) => { if (ticket === latest.current) setError(describeError(err)); });
  }, [botId, faded]);
  useEffect(() => load(), [load, version]);
  return { memories, error, setError, load };
}

interface GroupProps {
  title: string;
  side: Side;
  rows: readonly MemoryOut[];
  adding: boolean;
  kinds: readonly MemoryKind[];
  onAdd: () => void;
  onCancel: () => void;
  onSave: (draft: MemoryDraftIn) => Promise<void>;
  onChanged: () => void;
  onError: (message: string | null) => void;
}

function MemoryGroup({ title, rows, adding, kinds, onAdd, onCancel, onSave, onChanged, onError }: GroupProps) {
  const headId = useId();
  return (
    <div className="memory-group" role="group" aria-labelledby={headId}>
      <div className="memory-group__head">
        <h3 className="memory-group__title" id={headId}>{title}</h3>
        <Button variant="secondary" size="sm" onClick={onAdd} disabled={adding}>Add</Button>
      </div>
      {adding ? <MemoryForm kinds={kinds} onSave={onSave} onCancel={onCancel} /> : null}
      {rows.length === 0 ? <p className="memory-group__empty">Nothing yet.</p> : (
        <ul className="memory-list">
          {rows.map((memory) => <MemoryRow key={memory.id} memory={memory} onChanged={onChanged} onError={onError} />)}
        </ul>
      )}
    </div>
  );
}

// "What I remember" on the Info tab: what you and this bot have told each other, to keep, change or forget.
export function MemoryPanel({ bot }: { bot: BotOut }) {
  const headId = useId();
  const version = useLiveState().boardVersion.memories;
  const [faded, setFaded] = useState(false);
  const [adding, setAdding] = useState<Side | null>(null);
  const { memories, error, setError, load } = useMemories(bot.id, faded, version);
  const add = async (side: Side, draft: MemoryDraftIn) => {
    await memoriesApi.addMemory(side === "about" ? { ...draft } : { ...draft, bot_id: bot.id });
    setAdding(null);
    load();
  };
  const group = (side: Side, title: string) => (
    <MemoryGroup title={title} side={side} rows={memories.filter((m) => (m.bot_id === null) === (side === "about"))}
      adding={adding === side} kinds={side === "about" ? ABOUT_YOU_KINDS : BOT_KINDS}
      onAdd={() => setAdding(side)} onCancel={() => setAdding(null)} onSave={(draft) => add(side, draft)}
      onChanged={load} onError={setError} />
  );
  return (
    <section className="info-card memory-panel" aria-labelledby={headId}>
      <div className="memory-panel__head">
        <h2 className="info-card__title" id={headId}>What I remember</h2>
        <Button variant="ghost" size="sm" aria-pressed={faded} onClick={() => setFaded((on) => !on)}>Show faded</Button>
      </div>
      {error ? <ErrorNotice message={error} /> : null}
      {group("about", "About you")}
      {group("bot", "This bot's")}
    </section>
  );
}
