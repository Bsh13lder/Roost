import { useMemo, useState } from "react";
import { AgendaDayHead, agendaLabel } from "./AgendaDayHead";
import { DayNoteLine } from "./DayNoteLine";
import { ExpenseDayList } from "./ExpenseDayList";
import { monthDays } from "./monthCells";
import { MonthStrip } from "./MonthStrip";
import type { ExpenseCalendarProps } from "./calendarProps";
import { useDayNotes } from "./useDayNotes";
import { useExpenseDayPanel } from "./useExpenseDayPanel";
import { useLiveState } from "../../../hooks/useLiveStore";
import { todayIn, type IsoDay } from "../../../ui/date/dates";

// The Money Calendar on a phone (G14): an agenda under a month strip. The month's days that have expenses or notes,
// newest first; each header has the day's totals per currency (the server's), the note icon and "+", the day's notes
// sit under it, then G9's rows. A picked strip day shows alone.
export function ExpenseAgenda({ range, month, actions, onChanged }: ExpenseCalendarProps) {
  const version = useLiveState().boardVersion.dayNotes;
  const today = todayIn();
  const days = useMemo(() => monthDays(month).filter((day) => day.startsWith(month)), [month]);
  const notes = useDayNotes(days[0], days[days.length - 1], version);
  const [picked, setPicked] = useState<IsoDay | null>(null);
  const { wrap, add, noteMark, totalsOf } = useExpenseDayPanel({ range, month, notes, actions, onChanged });
  const spent = useMemo(() => new Set(range.expenses.map((expense) => expense.spent_at)), [range.expenses]);
  const has = (day: IsoDay) => spent.has(day) || (notes.byDay.get(day)?.length ?? 0) > 0;
  const marks = useMemo(() => new Set(days.filter(has)), [days, spent, notes.byDay]); // eslint-disable-line react-hooks/exhaustive-deps
  const shown = picked ? [picked] : days.filter(has).reverse();

  return (
    <section className="mcal agenda" aria-label="Expense agenda">
      <MonthStrip month={month} today={today} marks={marks} picked={picked} onPick={setPicked} />
      {shown.length === 0 ? <p className="agenda__none">No expenses.</p> : null}
      {shown.map((day) => (
        <section key={day} className="agenda__day" aria-label={agendaLabel(day, today)}>
          {wrap(day, (
            <div className="agenda__headwrap">
              <AgendaDayHead day={day} today={today} noteMark={noteMark(day)} onAdd={() => add(day)}
                extra={<span className="agenda__total num">{totalsOf(day)}</span>} />
            </div>
          ))}
          {(notes.byDay.get(day) ?? []).map((note) => <DayNoteLine key={note.id} note={note} onDelete={(one) => void notes.remove(one)} />)}
          <ExpenseDayList range={range} day={day} actions={actions} />
        </section>
      ))}
    </section>
  );
}
