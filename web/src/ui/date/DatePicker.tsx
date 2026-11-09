import type { DateKind } from "../../api/dates";
import { DateField } from "./DateField";
import { FUTURE_PICKS, type QuickPick } from "./picks";
import type { IsoDay } from "./dates";

export interface DatePickerProps {
  value: string; // "", "2026-10-16", or the words typed; resolveDay turns words into a day before saving
  onChange: (value: string) => void;
  label?: string; // the text box's name when it is not inside a Field
  placeholder?: string;
  picks?: readonly QuickPick[]; // FUTURE_PICKS by default (Today, Tomorrow, Next week, No date)
  max?: IsoDay; // the last day the calendar offers (an expense: today)
  kind?: DateKind; // "spent" for an expense's day (read by parse_spent_at); a task's due reading by default
  disabled?: boolean;
}

// A day you can type ("next friday", "2026-10-20") or pick (redesign P1).
export function DatePicker({ picks = FUTURE_PICKS, ...rest }: DatePickerProps) {
  return <DateField {...rest} picks={picks} withTime={false} />;
}
