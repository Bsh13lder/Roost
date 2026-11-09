import { lazy, Suspense, useState } from "react";
import { CalendarIcon } from "../../components/icons";
import { Chip } from "../Chip";
import { IconButton } from "../IconButton";
import { Popover } from "../Popover";
import { joinDue, pickedParts, todayIn, type IsoDay, type WallTime } from "./dates";
import { TIME_CHIPS, type QuickPick } from "./picks";

const Calendar = lazy(() => import("./Calendar"));

export interface CalendarPopoverProps {
  value: string; // the field's text
  withTime: boolean;
  picks: readonly QuickPick[];
  max?: IsoDay;
  disabled?: boolean;
  onPick: (value: string) => void;
}

function TimeChips({ day, time, onPick }: { day: IsoDay; time: WallTime | null; onPick: (value: string) => void }) {
  return (
    <div className="date-pop__row" role="group" aria-label="Time">
      {TIME_CHIPS.map((chip) => (
        <Chip key={chip} size="sm" selected={time === chip} onClick={() => onPick(joinDue(day, chip))}>{chip}</Chip>
      ))}
      {time ? <Chip size="sm" onClick={() => onPick(joinDue(day, null))}>No time</Chip> : null}
    </div>
  );
}

// The calendar button and its panel: quick picks, the month grid, and for a due its time chips. A
// day keeps the time already chosen; the panel closes once the value is complete.
export function CalendarPopover({ value, withTime, picks, max, disabled = false, onPick }: CalendarPopoverProps) {
  const [open, setOpen] = useState(false);
  const today = todayIn();
  const parts = pickedParts(value);
  const pickDay = (day: IsoDay | null) => {
    onPick(day ? joinDue(day, parts?.time ?? null) : "");
    if (!withTime || day === null) setOpen(false);
  };
  const pickTime = (next: string) => { onPick(next); setOpen(false); };
  return (
    <Popover open={open} onOpenChange={setOpen} label={withTime ? "Pick a day and a time" : "Pick a day"}
      trigger={<IconButton label="Open calendar" icon={<CalendarIcon />} variant="secondary" disabled={disabled} />}>
      <div className="date-pop__row" role="group" aria-label="Quick picks">
        {picks.map((pick) => (
          <Chip key={pick.label} size="sm" onClick={() => pickDay(pick.day(today))}>{pick.label}</Chip>
        ))}
      </div>
      <Suspense fallback={<p className="date-pop__loading">Loading the calendar…</p>}>
        <Calendar selected={parts?.day ?? null} today={today} max={max} onSelect={(day) => pickDay(day)} />
      </Suspense>
      {withTime ? <TimeChips day={parts?.day ?? today} time={parts?.time ?? null} onPick={pickTime} /> : null}
    </Popover>
  );
}
