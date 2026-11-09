import { useState } from "react";
import { CalendarGrid } from "../board/calendar/CalendarGrid";
import { CalendarToolbar } from "../board/calendar/CalendarToolbar";
import { RoutineChip } from "../board/calendar/RoutineChip";
import { useCalendarSpan } from "../board/calendar/useCalendarSpan";
import { useRoutineDays } from "../board/calendar/useRoutineDays";
import { SCREEN_PLAN_CALENDAR } from "../board/constants";
import { ShowToggles } from "../board/ShowToggles";
import { useScreenToggle } from "../../hooks/useScreenToggle";
import { dayText, todayIn, type IsoDay } from "../../ui/date/dates";
import type { PlanItemOut } from "../../api/plan";
import { NOTHING_TEXT, NO_DATE } from "./constants";
import { PlanItemMeta } from "./PlanItemBits";
import { daysWithItems, itemsOnDay, undated } from "./planColumns";

function ItemList({ label, items }: { label: string; items: readonly PlanItemOut[] }) {
  return (
    <ul className="plan-day__list" aria-label={label}>
      {items.map((item) => (
        <li key={item.id ?? `line-${item.line_no}`} className={item.status === "done" ? "plan-day__item is-done" : "plan-day__item"}>
          <span className="plan-day__text">{item.text}</span>
          <PlanItemMeta item={item} />
        </li>
      ))}
    </ul>
  );
}

const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? "" : "s"}`;

function Corner({ items, runs }: { items: number; runs: number }) {
  if (!items && !runs) return null;
  const words = [items ? plural(items, "item") : "", runs ? plural(runs, "routine") : ""].filter(Boolean).join(", ");
  return (
    <span className="csum"><span className="csum__n" title={words}>
      <i className="cdot" aria-hidden="true" />{items || runs}</span></span>
  );
}

export interface PlanCalendarProps {
  items: readonly PlanItemOut[];
  today?: IsoDay;
  botId?: string; // whose Plan: its routines' runs show on the days (board toggles)
}

// The Plan as a month (or week): a dot and a count on each day that has items, the chosen day's list below it
// sorted by time with the bot's routine runs under it, and the undated items under "No date". It reuses the
// Board's grid and toolbar. Its Routines and Done switches are remembered for every Plan in this browser.
export function PlanCalendar({ items, today = todayIn(), botId }: PlanCalendarProps) {
  const span = useCalendarSpan();
  const [selected, setSelected] = useState<IsoDay>(today);
  const [showDone] = useScreenToggle(SCREEN_PLAN_CALENDAR, "done");
  const [showRoutines] = useScreenToggle(SCREEN_PLAN_CALENDAR, "routines");
  const routines = useRoutineDays({ first: span.first, last: span.last, show: showRoutines && botId !== undefined, botId });
  const shown = showDone ? items : items.filter((item) => item.status !== "done");
  const counts = daysWithItems(shown);
  const loose = undated(shown);
  const dayItems = itemsOnDay(shown, selected);
  const dayRuns = routines.get(selected) ?? [];
  const dayLabel = dayText(selected, { weekday: true });
  return (
    <section className="plan-cal" aria-label="Plan calendar">
      <CalendarToolbar span={span} allowFuture onMode={span.setMode} />
      <ShowToggles screen={SCREEN_PLAN_CALENDAR} routines={botId !== undefined} ownDone botMade={false} />
      <CalendarGrid label={span.label} days={span.days} month={span.mode === "month" ? span.month : null} today={today}
        selected={selected} noteMark={() => null} body={() => null} onAdd={setSelected} onCell={setSelected}
        addLabel="Show"
        corner={(day, inMonth) => (inMonth ? <Corner items={counts.get(day) ?? 0} runs={routines.get(day)?.length ?? 0} /> : null)} />
      <h4 className="plan-day__title">{dayLabel}</h4>
      {dayItems.length > 0 ? <ItemList label={dayLabel} items={dayItems} /> : null}
      {dayRuns.length > 0 ? (
        <ul className="plan-day__routines" aria-label={`Routines on ${dayLabel}`}>
          {dayRuns.map((entry) => <li key={entry.routineId}><RoutineChip entry={entry} showBot={false} /></li>)}
        </ul>
      ) : null}
      {dayItems.length === 0 && dayRuns.length === 0 ? <p className="plan-day__empty">{NOTHING_TEXT}</p> : null}
      {loose.length > 0 ? (
        <>
          <h4 className="plan-day__title">{NO_DATE}</h4>
          <ItemList label={NO_DATE} items={loose} />
        </>
      ) : null}
    </section>
  );
}
