import { useEffect, useState } from "react";
import { DayPicker, type DateRange } from "react-day-picker";
import "../../styles/calendar.css";
import { dateToDay, dayToDate, type DayRangeValue, type IsoDay } from "./dates";

interface CalendarBase {
  today: IsoDay; // the account's today, not the browser's
  max?: IsoDay; // the last day it offers
}

export interface SingleCalendarProps extends CalendarBase {
  mode?: "single";
  selected: IsoDay | null;
  onSelect: (day: IsoDay) => void;
}

export interface RangeCalendarProps extends CalendarBase {
  mode: "range";
  range: DayRangeValue;
  onRange: (range: DayRangeValue) => void;
}

export type CalendarProps = SingleCalendarProps | RangeCalendarProps;

const asRange = (value: DayRangeValue): DateRange | undefined =>
  value.from ? { from: dayToDate(value.from), to: value.to ? dayToDate(value.to) : undefined } : undefined;

const fromRange = (range: DateRange | undefined): DayRangeValue => ({
  from: range?.from ? dateToDay(range.from) : null, to: range?.to ? dateToDay(range.to) : null,
});

// The month grid (react-day-picker), its own lazy chunk: only CalendarPopover and the Money date filter
// import it, through React.lazy, so the main bundle never carries it (tests/bundleGuard.test.ts). The month
// shown follows the chosen day when it changes from outside (a quick pick in another month) and the arrows
// turn it. In range mode the first click is the start and the second the end (Board redesign G10).
export default function Calendar(props: CalendarProps) {
  const focus = props.mode === "range" ? props.range.to ?? props.range.from : props.selected;
  const [month, setMonth] = useState(() => dayToDate(focus ?? props.today));
  useEffect(() => {
    if (focus) setMonth(dayToDate(focus));
  }, [focus]);
  const shared = {
    month, onMonthChange: setMonth, today: dayToDate(props.today), weekStartsOn: 1 as const,
    disabled: props.max ? { after: dayToDate(props.max) } : undefined,
  };
  if (props.mode === "range") {
    const { onRange } = props;
    return <DayPicker {...shared} mode="range" selected={asRange(props.range)} onSelect={(next) => onRange(fromRange(next))} />;
  }
  const { onSelect } = props;
  return (
    <DayPicker {...shared} mode="single" selected={props.selected ? dayToDate(props.selected) : undefined}
      onSelect={(date) => { if (date) onSelect(dateToDay(date)); }} />
  );
}
