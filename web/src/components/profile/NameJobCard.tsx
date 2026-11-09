import { useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { PencilIcon } from "../icons";
import * as botsApi from "../../api/bots";
import { describeError } from "../../api/client";
import type { BotOut } from "../../api/types";
import { BOT_LIMITS } from "../../lib/botProfile";
import { checkJob, checkName } from "../../lib/botFields";

interface LineProps {
  label: "Name" | "Job";
  value: string;
  check: (value: string) => string | null;
  save: (value: string) => Promise<BotOut>;
  onSaved: (bot: BotOut) => void;
  nameLevel?: NameLevel;
}

export type NameLevel = "h1" | "h2";

function ShownLine({ label, value, onEdit, level }: { label: LineProps["label"]; value: string; onEdit: () => void; level: NameLevel }) {
  const kind = label.toLowerCase();
  const Heading = level;
  return (
    <div className={`editable editable--${kind}`}>
      {label === "Name"
        ? <Heading className="editable__text editable__name" onClick={onEdit}>{value}</Heading>
        : <p className="editable__text editable__job" onClick={onEdit}>{value}</p>}
      <button type="button" className="editable__edit" aria-label={`Edit ${kind}`} onClick={onEdit}><PencilIcon /></button>
    </div>
  );
}

// One line edited in place: Enter or Save checks it here first (a bad value
// never reaches the server), Escape puts the old value back.
function EditableLine({ label, value, check, save, onSaved, nameLevel = "h1" }: LineProps) {
  const [draft, setDraft] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  if (draft === null) return <ShownLine label={label} value={value} onEdit={() => setDraft(value)} level={nameLevel} />;
  const cancel = () => { setDraft(null); setError(null); };
  const commit = async () => {
    const problem = check(draft);
    if (problem) {
      setError(problem);
      return;
    }
    try {
      onSaved(await save(draft.trim()));
      cancel();
    } catch (err) {
      setError(describeError(err));
    }
  };
  return (
    <div className={`editable editable--open editable--${label.toLowerCase()}`}>
      <div className="editable__row">
        <input className="input editable__input" aria-label={label} value={draft} autoFocus
          maxLength={label === "Name" ? BOT_LIMITS.name : BOT_LIMITS.job} onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") void commit(); if (e.key === "Escape") cancel(); }} />
        <button type="button" className="btn btn--primary btn--small" onClick={() => void commit()}>Save</button>
      </div>
      {error ? <ErrorNotice message={error} /> : null}
    </div>
  );
}

// The name and job under the big avatar, each editable in place (S1.6).
export function NameJobCard({ bot, onChange, nameLevel = "h1" }: { bot: BotOut; onChange: (bot: BotOut) => void; nameLevel?: NameLevel }) {
  return (
    <div className="name-job-card">
      <EditableLine label="Name" value={bot.name} check={checkName} onSaved={onChange} nameLevel={nameLevel}
        save={(name) => botsApi.updateBot(bot.id, { name })} />
      <EditableLine label="Job" value={bot.job} check={checkJob} onSaved={onChange}
        save={(job) => botsApi.updateBot(bot.id, { job })} />
    </div>
  );
}
