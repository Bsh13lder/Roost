import { useMemo, useState } from "react";
import { CalendarGrid } from "./CalendarGrid";
import { DayNoteLine } from "./DayNoteLine";
import { ExpenseAgenda } from "./ExpenseAgenda";
import { ExpenseDayCell } from "./ExpenseDayCell";
import { ExpenseDayList } from "./ExpenseDayList";
import { monthDays } from "./monthCells";
import { useDayNotes } from "./useDayNotes";
import type { ExpenseCalendarProps } from "./calendarProps";
import { useExpenseDayPanel } from "./useExpenseDayPanel";
import { PHONE_MEDIA } from "../constants";
import { useLiveState } from "../../../hooks/useLiveStore";
import { useMediaQuery } from "../../../hooks/useMediaQuery";
import { Button } from "../../../ui/Button";
import { dayText, todayIn, type IsoDay } from "../../../ui/date/dates";

const CAPTION = "Other currencies are shown apart (blue), never added together.";

// The Money tab's month grid (G12): a month of day cards with the server's totals per currency, the clicked day's
// list beside it, and a "+" on each day that opens the expense line with that day filled. A lazy chunk. Nothing is
// added up here, and a void expense is out of every figure (the server's rule).
function ExpenseGridCalendar({ range, month, actions, onChanged }: ExpenseCalendarProps) {
  const version = useLiveState().boardVersion.dayNotes;
  const days = useMemo(() => monthDays(month), [month]);
  const notes = useDayNotes(days[0], days[days.length - 1], version);
  const [selected, setSelected] = useState<IsoDay | null>(null);
  const today = todayIn();
  const entries = useMemo(() => new Map(range.days.map((entry) => [entry.day, entry])), [range.days]);
  const { wrap, add, noteMark, totalsOf } = useExpenseDayPanel({ range, month, notes, actions, onChanged });
  const corner = (day: IsoDay, inside: boolean) => {
    const count = entries.get(day)?.count ?? 0;
    if (!inside || count === 0) return null;
    const title = `${count} expense${count === 1 ? "" : "s"}`;
    return <span className="csum"><span className="csum__n" title={title}><i className="cdot" aria-hidden="true" />{count}</span></span>;
  };

  return (
    <div className="mcal">
      <CalendarGrid label={`Expenses ${month}`} days={days} month={month} today={today} selected={selected}
        noteMark={noteMark} corner={corner} onAdd={add} onCell={setSelected}
        body={(day, inside) => (inside ? <ExpenseDayCell entry={entries.get(day)} currency={range.currency} /> : null)}
        wrap={wrap} caption={CAPTION} />
      <aside className="mcal__side" aria-label="Selected day">
        {selected === null ? <p className="mcal__hint">Click a day to see its expenses.</p> : (
          <>
            <div className="xp-day">
              <span className="mcal__day">{dayText(selected, { weekday: true })}{noteMark(selected)}</span>
              <span className="num">{totalsOf(selected)}</span>
            </div>
            {(notes.byDay.get(selected) ?? []).map((note) => <DayNoteLine key={note.id} note={note} onDelete={(one) => void notes.remove(one)} />)}
            <ExpenseDayList range={range} day={selected} actions={actions} />
            <Button variant="ghost" size="sm" onClick={() => setSelected(null)}>Clear</Button>
          </>
        )}
      </aside>
    </div>
  );
}

// The Money tab's Calendar: the month grid, or on a phone the agenda under a month strip (G14). A lazy chunk.
export default function ExpenseCalendar(props: ExpenseCalendarProps) {
  const phone = useMediaQuery(PHONE_MEDIA);
  return phone ? <ExpenseAgenda {...props} /> : <ExpenseGridCalendar {...props} />;
}
