import { useState } from "react";
import { Button } from "../../ui/Button";
import { Field } from "../../ui/Field";
import { Input } from "../../ui/Input";
import { Segmented } from "../../ui/Segmented";
import { Sheet } from "../../ui/Sheet";
import { Textarea } from "../../ui/Textarea";
import { describeError } from "../../api/client";
import * as connectorsApi from "../../api/connectors";
import type { AuthStyle, ConnectorFields, ConnectorOut } from "../../api/connectors";
import {
  AUTH_NAME_LABEL, DELETE_QUESTION, EVERY_BOT, KEY_HINT_KEEP, KEY_HINT_NEW, KEY_LABEL, LIMITS, NEW_CONNECTOR,
  ONLY_THIS_BOT, PREFIXES_HINT, PREFIXES_LABEL, SAVE, STYLE_OPTIONS, WHO_LABEL,
} from "./constants";

export interface ConnectorEditorProps {
  connector: ConnectorOut | null; // null: a new one
  botId: string;
  onClose: () => void;
  onSaved: (connector: ConnectorOut) => void;
  onDeleted: (id: string) => void;
}

type Who = "all" | "this";

interface Form {
  name: string;
  purpose: string;
  base_url: string;
  auth_style: AuthStyle;
  auth_name: string;
  prefixes: string;
  secret: string;
  who: Who;
}

const WHO_OPTIONS = [{ id: "all", label: EVERY_BOT }, { id: "this", label: ONLY_THIS_BOT }] as const;

const formOf = (c: ConnectorOut | null): Form => ({
  name: c?.name ?? "", purpose: c?.purpose ?? "", base_url: c?.base_url ?? "", auth_style: c?.auth_style ?? "bearer",
  auth_name: c?.auth_name ?? "", prefixes: (c?.allowed_prefixes ?? []).join("\n"), secret: "",
  who: c?.bot_ids ? "this" : "all",
});

// What is sent: every field, the key only when typed (it is never loaded back), and who may use it.
export function fieldsOf(form: Form, botId: string): ConnectorFields {
  const prefixes = form.prefixes.split("\n").map((line) => line.trim()).filter(Boolean);
  const who = form.who === "all" ? { all_bots: true } : { bot_ids: [botId] };
  return {
    name: form.name, purpose: form.purpose, base_url: form.base_url, auth_style: form.auth_style,
    auth_name: form.auth_name, allowed_prefixes: prefixes, ...(form.secret ? { secret: form.secret } : {}), ...who,
  };
}

// A connector's form in a Sheet. The key field is always empty: the saved key is never sent back to the page.
export function ConnectorEditor({ connector, botId, onClose, onSaved, onDeleted }: ConnectorEditorProps) {
  const [form, setForm] = useState<Form>(() => formOf(connector));
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [asking, setAsking] = useState(false);
  const set = <K extends keyof Form>(key: K) => (value: Form[K]) => setForm((now) => ({ ...now, [key]: value }));

  const run = async (work: () => Promise<void>) => {
    setSaving(true);
    setError(null);
    try { await work(); } catch (err) { setError(describeError(err)); } finally { setSaving(false); }
  };
  const save = () => run(async () => {
    const fields = fieldsOf(form, botId);
    if (connector === null) {
      const { all_bots: _all, ...created } = fields;
      onSaved(await connectorsApi.addConnector(created));
    } else {
      onSaved(await connectorsApi.changeConnector(connector.id, fields));
    }
  });
  const remove = () => run(async () => {
    if (connector) { await connectorsApi.deleteConnector(connector.id); onDeleted(connector.id); }
  });

  return (
    <Sheet open title={connector ? connector.name : NEW_CONNECTOR} onOpenChange={(open) => { if (!open) onClose(); }}
      footer={(
        <>
          {connector && !asking ? <Button variant="ghost" onClick={() => setAsking(true)}>Delete</Button> : null}
          <Button variant="ghost" onClick={onClose}>Close</Button>
          <Button variant="primary" loading={saving} onClick={() => void save()}>{SAVE}</Button>
        </>
      )}>
      <div className="skill-editor">
        {asking ? (
          <div className="skill-editor__ask" role="group" aria-label="Are you sure?">
            <p>{DELETE_QUESTION}</p>
            <Button size="sm" variant="danger" loading={saving} onClick={() => void remove()}>Yes, delete it</Button>
            <Button size="sm" variant="ghost" onClick={() => setAsking(false)}>Cancel</Button>
          </div>
        ) : null}
        <Field label="Name">
          <Input value={form.name} maxLength={LIMITS.name} onChange={(e) => set("name")(e.target.value)} />
        </Field>
        <Field label="What it is for" optional>
          <Input value={form.purpose} maxLength={LIMITS.purpose} onChange={(e) => set("purpose")(e.target.value)} />
        </Field>
        <Field label="Address" hint="https only, such as https://api.example.com/v1">
          <Input value={form.base_url} maxLength={LIMITS.url} inputMode="url"
            onChange={(e) => set("base_url")(e.target.value)} />
        </Field>
        <Segmented label="How the key is sent" options={STYLE_OPTIONS} value={form.auth_style}
          onChange={set("auth_style")} />
        <Field label={AUTH_NAME_LABEL[form.auth_style]} optional={form.auth_style === "bearer"}>
          <Input value={form.auth_name} maxLength={64} onChange={(e) => set("auth_name")(e.target.value)} />
        </Field>
        <Field label={KEY_LABEL} hint={connector ? `${connector.key_hint}. ${KEY_HINT_KEEP}` : KEY_HINT_NEW}>
          <Input type="password" autoComplete="new-password" value={form.secret} maxLength={LIMITS.secret}
            onChange={(e) => set("secret")(e.target.value)} />
        </Field>
        <Field label={PREFIXES_LABEL} hint={PREFIXES_HINT} optional>
          <Textarea value={form.prefixes} onChange={(e) => set("prefixes")(e.target.value)} />
        </Field>
        <Segmented label={WHO_LABEL} options={WHO_OPTIONS} value={form.who} onChange={set("who")} />
        {error ? <p className="skill-editor__error" role="alert">{error}</p> : null}
      </div>
    </Sheet>
  );
}
