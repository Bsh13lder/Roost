import { lazy, Suspense, useState, type ReactElement } from "react";
import { Chip } from "../../ui/Chip";
import { Input } from "../../ui/Input";
import { Popover } from "../../ui/Popover";
import { isWallTime, todayIn, type IsoDay, type WallTime } from "../../ui/date/dates";
import { pickLabel, RESCHEDULE_PICKS } from "./reschedulePicks";

const Calendar = lazy(() => import("../../ui/date/Calendar"));

const TIME_ERROR = "Use a time like 09:30";
const TIME_MAX_LENGTH = 5;

// What a pick says: a day (null: no date) and an optional time of day.
export interface DuePick {
  day: IsoDay | null;
  time: WallTime | null;
}

export interface ReschedulePopoverProps {
  trigger: ReactElement;
  title: string; // "Reschedule “Pay the deposit”" or "Reschedule 3 overdue tasks"
  current: DuePick | null; // the task's own due, marked in the calendar
  onPick: (pick: DuePick) => void;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

// One popover for every place a due date changes (G2): quick picks, a month, a time. A pick applies at once
// and closes it; a time that is not a time stops everything and says so under the field.
export function ReschedulePopover({ trigger, title, current, onPick, open, onOpenChange }: ReschedulePopoverProps) {
  const [inner, setInner] = useState(false);
  const [time, setTime] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const shown = open ?? inner;
  const setOpen = (next: boolean) => {
    setInner(next);
    onOpenChange?.(next);
    if (!next) { setTime(""); setProblem(null); }
  };
  const apply = (day: IsoDay | null) => {
    const typed = time.trim();
    if (day !== null && typed && !isWallTime(typed)) { setProblem(TIME_ERROR); return; }
    onPick({ day, time: day === null || !typed ? null : typed.padStart(TIME_MAX_LENGTH, "0") });
    setOpen(false);
  };
  const today = todayIn();
  return (
    <Popover trigger={trigger} label={title} open={shown} onOpenChange={setOpen} align="start">
      <div className="reschedule">
        <h3 className="reschedule__title">{title}</h3>
        <div className="rs-picks" role="group" aria-label="Quick picks">
          {RESCHEDULE_PICKS.map((pick) => {
            const day = pick.day(today);
            return (
              <Chip key={pick.label} size="sm" onClick={() => apply(day)}>
                {pick.label}{day ? <small>{pickLabel(day)}</small> : null}
              </Chip>
            );
          })}
        </div>
        <Suspense fallback={<p className="date-pop__loading">Loading the calendar…</p>}>
          <Calendar selected={current?.day ?? null} today={today} onSelect={apply} />
        </Suspense>
        <div className="rs-time">
          <label htmlFor="reschedule-time" className="rs-time__label">Time (optional)</label>
          <Input id="reschedule-time" controlSize="md" value={time} maxLength={TIME_MAX_LENGTH} placeholder="09:30"
            invalid={problem !== null} aria-describedby={problem ? "reschedule-time-error" : undefined}
            onChange={(event) => { setTime(event.target.value); setProblem(null); }} />
        </div>
        {problem ? <p id="reschedule-time-error" className="rs-time__error" role="alert">{problem}</p> : null}
      </div>
    </Popover>
  );
}
