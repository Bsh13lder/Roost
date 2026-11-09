import { useState, type FormEvent } from "react";
import { describeError } from "../../api/client";
import type { MemoryKind } from "../../api/types";
import { Button } from "../../ui/Button";
import { Field } from "../../ui/Field";
import { Select } from "../../ui/Select";
import { Textarea } from "../../ui/Textarea";
import { KIND_LABELS, MEMORY_TEXT_MAX } from "./constants";

export interface MemoryDraftIn {
  text: string;
  kind: MemoryKind;
}

export interface MemoryFormProps {
  initial?: MemoryDraftIn;
  kinds: readonly MemoryKind[];
  onSave: (draft: MemoryDraftIn) => Promise<void>;
  onCancel: () => void;
}

// Add or edit one memory. The server's sentence for a refusal shows under the field, and the text stays.
export function MemoryForm({ initial, kinds, onSave, onCancel }: MemoryFormProps) {
  const [text, setText] = useState(initial?.text ?? "");
  const [kind, setKind] = useState<MemoryKind>(initial?.kind ?? kinds[0]);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const trimmed = text.trim();
    if (!trimmed) { setError("Write what to remember."); return; }
    setError(null);
    setSaving(true);
    try {
      await onSave({ text: trimmed, kind });
    } catch (err) {
      setError(describeError(err));
      setSaving(false);
    }
  };
  return (
    <form className="memory-form" onSubmit={(event) => void submit(event)}>
      <Field label="Memory" error={error}>
        <Textarea value={text} maxLength={MEMORY_TEXT_MAX} onChange={(event) => setText(event.target.value)} />
      </Field>
      {kinds.length > 1 ? (
        <Field label="Kind">
          <Select value={kind} onChange={setKind} size="md"
            options={kinds.map((value) => ({ value, label: KIND_LABELS[value] }))} />
        </Field>
      ) : null}
      <div className="memory-form__actions">
        <Button type="submit" variant="primary" size="sm" loading={saving}>Save</Button>
        <Button variant="ghost" size="sm" onClick={onCancel}>Cancel</Button>
      </div>
    </form>
  );
}
