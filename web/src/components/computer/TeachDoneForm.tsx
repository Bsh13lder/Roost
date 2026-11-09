import { useState, type FormEvent } from "react";
import { Button } from "../../ui/Button";
import { Field } from "../../ui/Field";
import { Input } from "../../ui/Input";
import { TEACH_DESCRIPTION_MAX } from "./constants";

interface TeachDoneFormProps {
  busy: boolean;
  error: string | null; // why the last stop failed
  onConfirm: (description: string | undefined) => void;
  onDiscard: () => void;
  onBack: () => void;
}

const TOO_LONG = `Keep it to ${TEACH_DESCRIPTION_MAX} characters or fewer.`;

// "I'm done teaching": an optional line on what the task is, then the bot drafts a skill you Save or not.
export function TeachDoneForm({ busy, error, onConfirm, onDiscard, onBack }: TeachDoneFormProps) {
  const [description, setDescription] = useState("");
  const [tooLong, setTooLong] = useState(false);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const text = description.trim();
    if (text.length > TEACH_DESCRIPTION_MAX) return setTooLong(true);
    setTooLong(false);
    onConfirm(text || undefined);
  };
  return (
    <form className="give-back" onSubmit={submit}>
      <Field label="What is this task?" optional className="give-back__field"
        hint="The bot turns what you showed into a skill. Nothing is saved until you press Save skill in the chat."
        error={tooLong ? TOO_LONG : error}>
        <Input value={description} onChange={(event) => setDescription(event.target.value)} controlSize="md"
          autoComplete="off" autoFocus />
      </Field>
      <div className="give-back__actions">
        <Button type="submit" variant="primary" size="md" loading={busy}>Make the skill</Button>
        <Button variant="ghost" size="md" disabled={busy} onClick={onDiscard}>Discard</Button>
        <Button variant="ghost" size="md" disabled={busy} onClick={onBack}>Back</Button>
      </div>
    </form>
  );
}
