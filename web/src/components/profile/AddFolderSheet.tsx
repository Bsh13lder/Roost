import { useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { Button } from "../../ui/Button";
import { Field } from "../../ui/Field";
import { Input } from "../../ui/Input";
import { Segmented } from "../../ui/Segmented";
import { Sheet } from "../../ui/Sheet";
import * as macApi from "../../api/mac";
import { describeError } from "../../api/client";
import type { GrantAccess, GrantOut, ReadPolicy } from "../../api/types";
import { ACCESS_OPTIONS, FOLDER_HINT, READ_POLICY_OPTIONS, SCOPE_OPTIONS } from "../approvals/constants";

type Scope = (typeof SCOPE_OPTIONS)[number]["id"];

// A label to start from: the folder's own name.
const folderName = (path: string) => path.replace(/\/+$/, "").split("/").pop() ?? "";

export interface AddFolderSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  botId: string;
  onAdded: (grant: GrantOut) => void;
}

// Share a Mac folder: type its path or press Choose folder… (the Mac's own window), name it, and say how it may be used.
export function AddFolderSheet({ open, onOpenChange, botId, onAdded }: AddFolderSheetProps) {
  const [path, setPath] = useState("");
  const [label, setLabel] = useState("");
  const [access, setAccess] = useState<GrantAccess>("read");
  const [policy, setPolicy] = useState<ReadPolicy>("ask_each");
  const [scope, setScope] = useState<Scope>("bot");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const choose = async () => {
    setError(null);
    try {
      const picked = (await macApi.pickFolder()).path;
      if (picked) setPath(picked);
    } catch (err) {
      setError(describeError(err));
    }
  };
  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const grant = await macApi.addGrant({
        path: path.trim(), label: label.trim() || folderName(path.trim()), access, read_policy: policy,
        bot_id: scope === "all" ? null : botId,
      });
      onAdded(grant);
      setPath("");
      setLabel("");
      onOpenChange(false);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  };
  const footer = (
    <Button variant="primary" loading={busy} disabled={!path.trim()} onClick={() => void save()}>Save</Button>
  );
  return (
    <Sheet open={open} onOpenChange={onOpenChange} title="Add folder" footer={footer}>
      <div className="add-folder">
        <Field label="Path" hint={FOLDER_HINT}>
          <Input value={path} onChange={(event) => setPath(event.target.value)} placeholder="/Users/you/Documents" />
        </Field>
        <Button size="sm" onClick={() => void choose()}>Choose folder…</Button>
        <Field label="Label" optional>
          <Input value={label} maxLength={40} onChange={(event) => setLabel(event.target.value)} />
        </Field>
        <div className="add-folder__choice">
          <span className="field__label">Access</span>
          <Segmented label="Access" options={ACCESS_OPTIONS} value={access} onChange={setAccess} />
        </div>
        <div className="add-folder__choice">
          <span className="field__label">Reads</span>
          <Segmented label="Reads" options={READ_POLICY_OPTIONS} value={policy} onChange={setPolicy} />
        </div>
        <div className="add-folder__choice">
          <span className="field__label">For</span>
          <Segmented label="For" options={SCOPE_OPTIONS} value={scope} onChange={setScope} />
        </div>
        {error ? <ErrorNotice message={error} /> : null}
      </div>
    </Sheet>
  );
}
