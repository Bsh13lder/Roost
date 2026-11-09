import { DayNoteIcon } from "../../icons";
import { dayText, type IsoDay } from "../../../ui/date/dates";

export interface DayNoteMarkProps {
  day: IsoDay;
  count: number; // how many note lines the day has
  onOpen: () => void;
}

// The note icon on a day (G11, G12): shown only when the day has notes; it opens the day's panel.
export function DayNoteMark({ day, count, onOpen }: DayNoteMarkProps) {
  if (count === 0) return null;
  return (
    <button type="button" className="note-ic" title={`Day note · ${count} line${count === 1 ? "" : "s"}`}
      aria-label={`Day note for ${dayText(day, { weekday: true })}`} onClick={(event) => { event.stopPropagation(); onOpen(); }}>
      <DayNoteIcon />
    </button>
  );
}
