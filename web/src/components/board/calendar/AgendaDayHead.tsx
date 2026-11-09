import type { ReactNode } from "react";
import { PlusIcon } from "../../icons";
import { IconButton } from "../../../ui/IconButton";
import { dayText, type IsoDay } from "../../../ui/date/dates";

/** "Today", or "Wed 21 Oct". */
export function agendaLabel(day: IsoDay, today: IsoDay): string {
  return day === today ? "Today" : dayText(day, { weekday: true });
}

export interface AgendaDayHeadProps {
  day: IsoDay;
  today: IsoDay;
  noteMark: ReactNode; // the note icon, when the day has notes
  extra?: ReactNode; // a day's totals
  onAdd: () => void;
}

// One day's header row in an agenda (G14): the date, the note icon, the day's figure and "+".
export function AgendaDayHead({ day, today, noteMark, extra, onAdd }: AgendaDayHeadProps) {
  return (
    <div className="agenda__head">
      <h3 className={day === today ? "agenda__title is-today" : "agenda__title"}>{agendaLabel(day, today)}</h3>
      {noteMark}
      <span className="agenda__sp" />
      {extra}
      <IconButton size="sm" tooltip={false} label={`Add on ${dayText(day, { weekday: true })}`} icon={<PlusIcon />} onClick={onAdd} />
    </div>
  );
}
