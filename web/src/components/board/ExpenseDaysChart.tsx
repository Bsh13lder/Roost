import { useMemo } from "react";
import { dayHeading, ExpenseDays } from "./ExpenseDays";
import { STRIP_DENSE_DAYS, STRIP_LABEL_EVERY, STRIP_MAX_DAYS } from "./constants";
import type { ExpenseActions } from "./useExpenseActions";
import { currencyList, dayLabel, formatMoney } from "./money";
import type { MoneyRangeOut } from "../../api/money";
import { addDays, todayIn, type IsoDay } from "../../ui/date/dates";
import { cx } from "../../ui/cx";

export interface ExpenseDaysChartProps {
  data: MoneyRangeOut;
  selected: IsoDay | null; // the picked day
  onPick: (day: IsoDay | null) => void; // the picked one again: null
  actions: ExpenseActions; // the picked day's group shows under the strip
  today?: IsoDay;
}

/** Every day from `first` to `last`, at most the last `STRIP_MAX_DAYS`. */
function stripDays(first: IsoDay, last: IsoDay): IsoDay[] {
  const days: IsoDay[] = [];
  for (let day = last; day >= first && days.length < STRIP_MAX_DAYS; day = addDays(day, -1)) days.unshift(day);
  return days;
}

const LONG_NAMES: Readonly<Record<string, string>> = { EUR: "euro", USD: "US dollar", GBP: "pound" };

// By days (Board redesign G10): a strip of daily bars, plain buttons and CSS, never an SVG or a library. Each bar's
// height is the server's `bar_percent` (the main currency against the biggest day); other currencies are named in
// the days below, never drawn. Today is bright, the picked day ringed.
export function ExpenseDaysChart({ data, selected, onPick, actions, today = todayIn() }: ExpenseDaysChartProps) {
  const days = useMemo(() => stripDays(data.from, data.to), [data.from, data.to]);
  const byDay = useMemo(() => new Map(data.days.map((entry) => [entry.day, entry])), [data.days]);
  const nth = days.length > STRIP_DENSE_DAYS ? STRIP_LABEL_EVERY : 1;
  const zero = formatMoney("0", data.currency);
  const toggle = (day: IsoDay) => onPick(selected === day ? null : day);
  return (
    <div className="bydays">
      <p className="dnote">
        Bars show {LONG_NAMES[data.currency] ?? data.currency} spending per day; other currencies are listed apart in the
        days below. Today is bright.
      </p>
      <div className="dstrip" role="group" aria-label="Spending per day">
        {days.map((day) => {
          const text = `${dayLabel(day)}: ${currencyList(byDay.get(day)?.totals ?? {}, zero)}`;
          return (
            <button key={day} type="button" title={text} aria-label={text}
              className={cx("dbar", day === today && "is-today", selected === day && "is-sel")} onClick={() => toggle(day)}>
              <span className="dbar__fill" style={{ height: `${byDay.get(day)?.bar_percent ?? 0}%` }} />
            </button>
          );
        })}
      </div>
      <div className="dlabels" aria-hidden="true">
        {days.map((day, index) => (
          <span key={day} className={day === today ? "today" : undefined}>
            {(days.length - 1 - index) % nth === 0 ? Number(day.slice(8)) : ""}
          </span>
        ))}
      </div>
      {data.days.map((entry) => (
        <button key={entry.day} type="button" aria-pressed={selected === entry.day}
          className={cx("xp-day", "dayrow", selected === entry.day && "is-sel")} onClick={() => toggle(entry.day)}>
          <span>{dayHeading(entry.day, today)}</span>
          <span className="num">{currencyList(entry.totals, zero)}</span>
        </button>
      ))}
      {selected ? (
        <div className="bydays__day"><ExpenseDays data={data} showProject actions={actions} today={today} only={selected} /></div>
      ) : (
        <p className="bydays__pick">Pick a bar or a day to see its expenses.</p>
      )}
    </div>
  );
}
