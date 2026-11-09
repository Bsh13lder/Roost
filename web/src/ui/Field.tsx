import { createContext, useContext, useId, type ReactNode } from "react";
import { cx } from "./cx";

// What a control inside a Field takes from it: its id (the label points at it), what describes it,
// and whether it holds an error. Input, Textarea, Select and the date pickers read it.
export interface FieldControl {
  id: string;
  labelId: string;
  describedBy: string | undefined;
  invalid: boolean;
}

const FieldContext = createContext<FieldControl | null>(null);

export function useFieldControl(): FieldControl | null {
  return useContext(FieldContext);
}

export interface FieldProps {
  label: ReactNode;
  hint?: ReactNode; // a line under the control
  error?: string | null; // replaces nothing: shown under the hint, and marks the control invalid
  optional?: boolean; // says "optional" beside the label
  className?: string;
  children: ReactNode; // one control
}

// A labelled control (redesign P1): label, the control, a hint and an error, wired for screen readers.
export function Field({ label, hint, error = null, optional = false, className, children }: FieldProps) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : null;
  const errorId = error ? `${id}-error` : null;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;
  const control: FieldControl = { id: `${id}-control`, labelId: `${id}-label`, describedBy, invalid: Boolean(error) };
  return (
    <div className={cx("field", className)}>
      <div className="field__head">
        <label className="field__label" id={control.labelId} htmlFor={control.id}>{label}</label>
        {optional ? <span className="field__optional">optional</span> : null}
      </div>
      <FieldContext.Provider value={control}>{children}</FieldContext.Provider>
      {hintId ? <p id={hintId} className="field__hint">{hint}</p> : null}
      {errorId ? <p id={errorId} className="field__error" role="alert">{error}</p> : null}
    </div>
  );
}

export interface ControlA11y {
  id: string | undefined;
  "aria-describedby": string | undefined;
  "aria-invalid": true | undefined;
}

// The id and aria a control inside a Field should carry, merged with the control's own.
export function controlA11y(
  field: FieldControl | null, own: { id?: string; describedBy?: string; invalid?: boolean } = {},
): ControlA11y {
  const describedBy = [field?.describedBy, own.describedBy].filter(Boolean).join(" ") || undefined;
  return {
    id: own.id ?? field?.id,
    "aria-describedby": describedBy,
    "aria-invalid": own.invalid || field?.invalid ? true : undefined,
  };
}
