import { useId } from "react";
import type { DateKind } from "../../api/dates";
import { cx } from "../cx";
import { MAX_DATE_TEXT } from "../constants";
import { controlA11y, useFieldControl } from "../Field";
import { CalendarPopover } from "./CalendarPopover";
import { friendlyDue, type IsoDay } from "./dates";
import { useDateReading, type DateReading } from "./useDateReading";
import type { QuickPick } from "./picks";

export interface DateFieldProps {
  value: string; // what the gateway reads: "", "2026-10-16", "2026-10-16 09:00", or the words typed
  onChange: (value: string) => void;
  withTime: boolean;
  picks: readonly QuickPick[];
  label?: string; // the text box's name when it is not inside a Field
  placeholder?: string;
  max?: IsoDay;
  kind?: DateKind; // how the gateway reads typed words: a task's due (default) or an expense's day
  disabled?: boolean;
}

function previewText(reading: DateReading, withTime: boolean): string {
  if (reading.kind === "reading") return "Reading…";
  if (reading.kind === "read") return friendlyDue(reading.parts, withTime);
  if (reading.kind === "error") return reading.message;
  return "";
}

// The typeable date box shared by DatePicker and DateTimePicker: the text, the calendar button, and
// a line saying how the gateway reads the text.
export function DateField({ value, onChange, withTime, picks, label, placeholder, max, kind = "due", disabled = false }: DateFieldProps) {
  const previewId = useId();
  const reading = useDateReading(value, kind);
  const a11y = controlA11y(useFieldControl(), { describedBy: previewId, invalid: reading.kind === "error" });
  return (
    <div className="date-field">
      <div className="date-field__row">
        <input {...a11y} className="input date-field__input" aria-label={a11y.id ? undefined : label} value={value}
          placeholder={placeholder} maxLength={MAX_DATE_TEXT} disabled={disabled} autoComplete="off"
          onChange={(event) => onChange(event.target.value)} />
        <CalendarPopover value={value} withTime={withTime} picks={picks} max={max} disabled={disabled} onPick={onChange} />
      </div>
      <p id={previewId} className={cx("date-field__preview", `date-field__preview--${reading.kind}`)} aria-live="polite">
        {previewText(reading, withTime)}
      </p>
    </div>
  );
}
