import { useCallback, useEffect, useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { LockIcon, PlusIcon } from "../icons";
import { AddFolderSheet } from "./AddFolderSheet";
import { Button } from "../../ui/Button";
import { Popover } from "../../ui/Popover";
import * as macApi from "../../api/mac";
import { describeError } from "../../api/client";
import type { BotOut, GrantOut } from "../../api/types";
import { ACCESS_OPTIONS, FOLDERS_TITLE, READ_POLICY_OPTIONS } from "../approvals/constants";

const labelOf = <T extends string>(options: ReadonlyArray<{ id: T; label: string }>, id: T) =>
  options.find((option) => option.id === id)?.label ?? id;

function RevokeButton({ grant, onRevoked }: { grant: GrantOut; onRevoked: (id: string) => void }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const revoke = async () => {
    setBusy(true);
    setError(null);
    try {
      await macApi.revokeGrant(grant.id);
      onRevoked(grant.id);
    } catch (err) {
      setError(describeError(err));
      setBusy(false);
    }
  };
  const scope = grant.bot_id === null ? " It stops for every bot." : "";
  return (
    <Popover label={`Stop sharing ${grant.label}?`} open={open} onOpenChange={setOpen}
      trigger={<Button size="sm" variant="ghost" aria-label={`Revoke ${grant.label}`}>Revoke</Button>}>
      <div className="folders-card__confirm">
        <p>Stop sharing {grant.label}?{scope} Your files stay where they are.</p>
        {error ? <ErrorNotice message={error} /> : null}
        <Button size="sm" variant="danger" loading={busy} onClick={() => void revoke()}>Revoke</Button>
      </div>
    </Popover>
  );
}

function FolderRow({ grant, onRevoked }: { grant: GrantOut; onRevoked: (id: string) => void }) {
  return (
    <li className="info-row folders-card__row">
      <div className="folders-card__head">
        <span className="info-row__label">{grant.label}</span>
        {grant.bot_id === null ? <span className="folders-card__all"><LockIcon />All bots</span> : null}
        <RevokeButton grant={grant} onRevoked={onRevoked} />
      </div>
      <code className="folders-card__path">{grant.path}</code>
      <p className="info-row__hint folders-card__rules">
        <span>{labelOf(ACCESS_OPTIONS, grant.access)}</span>
        <span>Reads: {labelOf(READ_POLICY_OPTIONS, grant.read_policy)}</span>
      </p>
    </li>
  );
}

// The Info tab's Folders card: this bot's Mac folders and the all-bots ones, a Revoke on each, and Add folder.
export function FoldersCard({ bot }: { bot: BotOut }) {
  const [grants, setGrants] = useState<GrantOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const load = useCallback(() => {
    setError(null);
    macApi.listGrants(bot.id).then(setGrants).catch((err: unknown) => setError(describeError(err)));
  }, [bot.id]);
  useEffect(() => load(), [load]);
  return (
    <section className="info-card folders-card" aria-label={FOLDERS_TITLE}>
      <div className="info-row folders-card__title-row">
        <h3 className="info-card__title">{FOLDERS_TITLE}</h3>
        <Button size="sm" onClick={() => setAdding(true)}><PlusIcon />Add folder</Button>
      </div>
      {error ? <div className="info-row"><ErrorNotice message={error} onRetry={load} /></div> : null}
      {grants && grants.length === 0 ? <p className="info-row info-row__hint">No folders yet.</p> : null}
      {grants && grants.length > 0 ? (
        <ul className="folders-card__list">
          {grants.map((grant) => (
            <FolderRow key={grant.id} grant={grant} onRevoked={(id) => setGrants((now) => (now ?? []).filter((g) => g.id !== id))} />
          ))}
        </ul>
      ) : null}
      <AddFolderSheet open={adding} onOpenChange={setAdding} botId={bot.id}
        onAdded={(grant) => setGrants((now) => [...(now ?? []), grant])} />
    </section>
  );
}
