import { useEffect, useState } from "react";
import { Field } from "../../ui/Field";
import { Select, type SelectOption } from "../../ui/Select";
import { fetchModels, modelHint, type ModelChoiceOut } from "../../lib/models";

// A routine's own model (owner, 2026-11-09): "Same as the bot" by default, or one of the bot models. Two failed
// runs in a row on it go back to the bot's model, and the chat says so.
export const SAME_AS_BOT = "same"; // a Select value is never ""

export interface RoutineModelFieldProps {
  value: string | null; // a model id, or null for the bot's
  onChange: (value: string | null) => void;
}

const optionFor = (choice: ModelChoiceOut): SelectOption => ({ value: choice.id, label: choice.label, hint: modelHint(choice) });

export function RoutineModelField({ value, onChange }: RoutineModelFieldProps) {
  const [choices, setChoices] = useState<ModelChoiceOut[]>([]);
  useEffect(() => {
    let live = true;
    fetchModels().then((models) => { if (live) setChoices(models.choices.filter((c) => !c.new)); }).catch(() => undefined);
    return () => { live = false; };
  }, []);
  const known = value === null || choices.some((c) => c.id === value);
  const options: SelectOption[] = [
    { value: SAME_AS_BOT, label: "Same as the bot" },
    ...choices.map(optionFor),
    ...(known ? [] : [{ value: value as string, label: value as string }]),
  ];
  return (
    <Field label="Model" hint="A cheaper model suits a simple check. Two failed runs in a row go back to the bot's.">
      <Select value={value ?? SAME_AS_BOT} options={options}
        onChange={(picked) => onChange(picked === SAME_AS_BOT ? null : picked)} />
    </Field>
  );
}
