import { DateField } from "./DateField";
import { FUTURE_PICKS, type QuickPick } from "./picks";

export interface DateTimePickerProps {
  value: string; // "", "2026-10-16", "2026-10-16 09:00" (account wall time), or the words typed
  onChange: (value: string) => void;
  label?: string;
  placeholder?: string;
  picks?: readonly QuickPick[];
  disabled?: boolean;
}

// A day and, if you like, a time: typed ("tomorrow at 9") or picked, with time chips (redesign P1).
// What it holds goes to the gateway as it is: a task's due_date takes words or ISO, on the account's time.
export function DateTimePicker({ picks = FUTURE_PICKS, ...rest }: DateTimePickerProps) {
  return <DateField {...rest} picks={picks} withTime />;
}
