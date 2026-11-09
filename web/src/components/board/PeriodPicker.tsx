import { lazy, Suspense, useState } from "react";
import { RANGE_PRESETS, rangeLabel, type DayRange, type RangePreset } from "./dateRanges";
import { dayLabel } from "./money";
import { Button } from "../../ui/Button";
import { Chip } from "../../ui/Chip";
import { Popover } from "../../ui/Popover";
import type { DayRangeValue, IsoDay } from "../../ui/date/dates";

const Calendar = lazy(() => import("../../ui/date/Calendar"));

export interface PeriodPickerProps {
  preset: RangePreset | null; // null: the whole month on screen
  custom: DayRange | null; // the applied custom range
  today: IsoDay;
  onPreset: (preset: "today" | "week" | null) => void; // null: the whole month
  onCustom: (range: DayRange) => void;
}

// From … / To … over the lazy range calendar, with Cancel and Apply (Apply waits for a first day). Future days are off.
function CustomPicker({ today, start, onApply, onCancel }: {
  today: IsoDay; start: DayRange | null; onApply: (range: DayRange) => void; onCancel: () => void;
}) {
  const [picked, setPicked] = useState<DayRangeValue>(start ?? { from: null, to: null });
  const from = picked.from && picked.to && picked.from > picked.to ? picked.to : picked.from;
  const to = picked.from && picked.to && picked.from > picked.to ? picked.from : picked.to;
  return (
    <div className="range-pick">
      <p className="range-pick__line">
        <span>From {from ? dayLabel(from) : "…"}</span>
        <span>To {to && to !== from ? dayLabel(to) : "…"}</span>
      </p>
      <Suspense fallback={<p className="date-pop__loading">Loading the calendar…</p>}>
        <Calendar mode="range" today={today} max={today} range={{ from, to }} onRange={setPicked} />
      </Suspense>
      <div className="range-pick__foot">
        <Button variant="ghost" size="sm" onClick={onCancel}>Cancel</Button>
        <Button variant="primary" size="sm" disabled={!from} onClick={() => from && onApply({ from, to: to ?? from })}>
          Apply
        </Button>
      </div>
    </div>
  );
}

export const WHOLE_MONTH = "Whole month";
const OFFERED: ReadonlyArray<{ id: Exclude<RangePreset, "custom" | "month" | "last">; label: string }> = [
  { id: "today", label: "Today" }, { id: "week", label: "This week" },
];

/** What the dropdown's button says: the whole month, a preset's name, or a custom range's days. */
export function periodLabel(preset: RangePreset | null, custom: DayRange | null): string {
  if (!preset) return WHOLE_MONTH;
  if (preset === "custom") return custom ? rangeLabel("custom", custom) : WHOLE_MONTH;
  return RANGE_PRESETS.find((item) => item.id === preset)?.label ?? WHOLE_MONTH;
}

function Options({ preset, onPick, onCustom }: {
  preset: RangePreset | null; onPick: (preset: "today" | "week" | null) => void; onCustom: () => void;
}) {
  return (
    <div className="period__options" role="group" aria-label="Period">
      <Chip selected={preset === null} onClick={() => onPick(null)}>{WHOLE_MONTH}</Chip>
      {OFFERED.map((item) => (
        <Chip key={item.id} selected={preset === item.id} onClick={() => onPick(item.id)}>{item.label}</Chip>
      ))}
      <Chip selected={preset === "custom"} onClick={onCustom}>Custom range…</Chip>
    </div>
  );
}

// The Money tab's one period picker (beside the month arrows): Whole month, Today, This week, or a custom range
// over the lazy range calendar. The arrows always show a whole month; the server filters and adds.
export function PeriodPicker({ preset, custom, today, onPreset, onCustom }: PeriodPickerProps) {
  const [open, setOpen] = useState(false);
  const [picking, setPicking] = useState(false);
  const label = periodLabel(preset, custom);
  const toggle = (next: boolean) => { setOpen(next); if (!next) setPicking(false); };
  return (
    <Popover label="Pick a period" open={open} onOpenChange={toggle} align="start"
      trigger={<Button variant="secondary" size="sm" className="period" aria-label={`Period: ${label}`}>{label} ▾</Button>}>
      {picking ? (
        <CustomPicker today={today} start={custom} onCancel={() => toggle(false)}
          onApply={(range) => { onCustom(range); toggle(false); }} />
      ) : (
        <Options preset={preset} onCustom={() => setPicking(true)}
          onPick={(next) => { onPreset(next); toggle(false); }} />
      )}
    </Popover>
  );
}

// A day picked in By days (or from the address): one chip that clears it.
export function DayChip({ day, onClear }: { day: IsoDay; onClear: () => void }) {
  return (
    <div className="rangebar">
      <Chip aria-label={`${dayLabel(day)} ✕ Clear`} onClick={onClear}>{dayLabel(day)} ✕ Clear</Chip>
    </div>
  );
}
