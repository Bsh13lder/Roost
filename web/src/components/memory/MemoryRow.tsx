import { useState } from "react";
import * as memoriesApi from "../../api/memories";
import { describeError } from "../../api/client";
import type { MemoryKind, MemoryOut } from "../../api/types";
import { zoneDayKey } from "../../lib/chatTime";
import { Badge } from "../../ui/Badge";
import { Button } from "../../ui/Button";
import { Chip } from "../../ui/Chip";
import { dayText } from "../../ui/date/dates";
import { ABOUT_YOU_KINDS, BOT_KINDS, KIND_LABELS, SOURCE_LABELS } from "./constants";
import { MemoryForm, type MemoryDraftIn } from "./MemoryForm";

export interface MemoryRowProps {
  memory: MemoryOut;
  onChanged: () => void;
  onError: (message: string | null) => void;
}

const dayOf = (iso: string) => {
  const when = new Date(iso);
  return Number.isNaN(when.getTime()) ? "" : dayText(zoneDayKey(when));
};

// One memory: its text as plain text, what it is, when and who, and what you can do with it.
export function MemoryRow({ memory, onChanged, onError }: MemoryRowProps) {
  const [editing, setEditing] = useState(false);
  const faded = memory.archived_at !== null;
  const kinds: readonly MemoryKind[] = memory.bot_id === null ? ABOUT_YOU_KINDS : BOT_KINDS;
  const run = (action: () => Promise<unknown>) => {
    onError(null);
    action().then(onChanged).catch((err: unknown) => onError(describeError(err)));
  };
  const save = async (draft: MemoryDraftIn) => {
    const patch = {
      ...(draft.text !== memory.text ? { text: draft.text } : {}),
      ...(draft.kind !== memory.kind ? { kind: draft.kind } : {}),
    };
    if (Object.keys(patch).length > 0) await memoriesApi.updateMemory(memory.id, patch);
    setEditing(false);
    onChanged();
  };
  if (editing) {
    return (
      <li className="memory-row memory-row--editing">
        <MemoryForm initial={{ text: memory.text, kind: memory.kind }} kinds={kinds} onSave={save}
          onCancel={() => setEditing(false)} />
      </li>
    );
  }
  return (
    <li className={faded ? "memory-row memory-row--faded" : "memory-row"}>
      <p className="memory-row__text">{memory.text}</p>
      <div className="memory-row__meta">
        <Chip size="sm" disabled>{KIND_LABELS[memory.kind]}</Chip>
        <span>{dayOf(memory.updated_at)}</span>
        <span>{SOURCE_LABELS[memory.source]}</span>
        {memory.tainted ? <Badge tone="danger">from web content</Badge> : null}
      </div>
      <div className="memory-row__actions">
        <Button variant="ghost" size="sm" onClick={() => setEditing(true)}>Edit</Button>
        {faded ? (
          <Button variant="ghost" size="sm" onClick={() => run(() => memoriesApi.updateMemory(memory.id, { restore: true }))}>
            Restore
          </Button>
        ) : (
          <Button variant="ghost" size="sm" aria-pressed={memory.pinned}
            onClick={() => run(() => memoriesApi.updateMemory(memory.id, { pinned: !memory.pinned }))}>
            {memory.pinned ? "Unpin" : "Pin"}
          </Button>
        )}
        <Button variant="ghost" size="sm" onClick={() => run(() => memoriesApi.forgetMemory(memory.id))}>Forget</Button>
      </div>
    </li>
  );
}
