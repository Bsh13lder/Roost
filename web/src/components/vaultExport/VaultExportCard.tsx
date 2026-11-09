import { useEffect, useState } from "react";
import { describeError } from "../../api/client";
import {
  getVaultExport, putVaultExport, runVaultExport, setProjectExport, type ExportCode, type VaultExportOut,
} from "../../api/vaultExport";
import { Button } from "../../ui/Button";
import { Select } from "../../ui/Select";
import { Switch } from "../../ui/Switch";
import { ErrorNotice } from "../ErrorNotice";

const NONE = "none";

const RESULT_TEXT: Record<ExportCode, string> = {
  ok: "Exported.",
  partial: "Exported part of it; the rest follows in a minute.",
  no_grant: "That folder is gone or read-only. Choose another.",
  away: "Roost's keeper is away; it will try again.",
  failed: "Some files could not be written.",
  off: "Nothing to export yet.",
};

export function resultLine(code: ExportCode | null, written: number, conflicts: number): string | null {
  if (!code) return null;
  if (code !== "ok" && code !== "partial") return RESULT_TEXT[code];
  const kept = conflicts ? `, ${conflicts} kept as you edited them (a .conflict copy sits beside each)` : "";
  return `${RESULT_TEXT[code]} ${written} written${kept}.`;
}

type Step = () => Promise<VaultExportOut>;

interface RowsProps {
  state: VaultExportOut;
  busy: boolean;
  act: (step: Step) => void;
}

// The folder, Export journals, Export now and the last result: shown while the project's switch is on.
function ExportRows({ state, busy, act }: RowsProps) {
  if (state.grants.length === 0) {
    return <p className="vault-export__note">Share a folder first: a bot&apos;s Profile, Info, Your Mac: folders, with Read and write.</p>;
  }
  const options = [{ value: NONE, label: "No folder" }, ...state.grants.map((g) => ({ value: g.id, label: g.label }))];
  const line = resultLine(state.last.result, state.last.written, state.last.conflicts);
  const exportNow = async () => {
    const ran = await runVaultExport();
    return { ...state, last: { result: ran.result, written: ran.written, conflicts: ran.conflicts, at: null } };
  };
  return (
    <div className="vault-export__rows">
      <Select label="Folder" size="md" value={state.grant_id ?? NONE} options={options} disabled={busy}
        onChange={(value) => act(() => putVaultExport(value === NONE ? null : value, state.journals))} />
      <Switch checked={state.journals} disabled={busy}
        onChange={(next) => act(() => putVaultExport(state.grant_id, next))}>Export journals</Switch>
      <Button size="sm" variant="secondary" loading={busy} disabled={!state.grant_id} onClick={() => act(exportNow)}>
        Export now
      </Button>
      <p className="vault-export__note">Roost writes into a Roost folder there and never deletes your files.</p>
      {line ? <p className="vault-export__note" role="status">{line}</p> : null}
    </div>
  );
}

// "Export to my vault" on a project's page (obsidian track): the project's switch (off by default) and, while
// it is on, where it goes. A lazy chunk.
export default function VaultExportCard({ projectId }: { projectId: string }) {
  const [state, setState] = useState<VaultExportOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let live = true;
    getVaultExport()
      .then((loaded) => { if (live) setState(loaded); })
      .catch((err: unknown) => { if (live) setError(describeError(err)); });
    return () => { live = false; };
  }, []);
  const act = (step: Step) => {
    setBusy(true);
    step()
      .then((next) => { setState(next); setError(null); })
      .catch((err: unknown) => setError(describeError(err)))
      .finally(() => setBusy(false));
  };
  if (!state) return error ? <ErrorNotice message={error} /> : null;
  const on = state.projects.includes(projectId);
  const toggle = (next: boolean) => act(async () => {
    await setProjectExport(projectId, next);
    const projects = next ? [...state.projects, projectId] : state.projects.filter((id) => id !== projectId);
    return { ...state, projects };
  });
  return (
    <section className="info-card vault-export" aria-label="Export to my vault">
      <Switch checked={on} disabled={busy} onChange={toggle}>Export to my vault</Switch>
      {on ? <ExportRows state={state} busy={busy} act={act} /> : null}
      {error ? <ErrorNotice message={error} /> : null}
    </section>
  );
}
