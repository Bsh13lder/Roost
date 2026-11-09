import { useCallback, useMemo, useRef, useState, type DragEvent } from "react";
import type { PillDrag } from "./TaskPill";
import type { IsoDay } from "../../../ui/date/dates";

const CARD_TYPE = "text/plain";

export interface DayDrop {
  isOver: boolean;
  onDragOver: (event: DragEvent<HTMLElement>) => void;
  onDragLeave: (event: DragEvent<HTMLElement>) => void;
  onDrop: (event: DragEvent<HTMLElement>) => void;
}

export interface CalendarDrag {
  pillDrag: (taskId: string) => PillDrag;
  dayDrop: (day: IsoDay, hourAt?: (event: DragEvent<HTMLElement>) => number) => DayDrop;
}

// Native HTML5 drag of a pill onto a day cell or a week column (G11, no library). The drop reports the task, the
// day and, in the week's time grid, the hour it landed on. Touch screens do not drag: they use → in the day popover.
export function useCalendarDrag(onDrop: (taskId: string, day: IsoDay, hour: number | null) => void): CalendarDrag {
  const [over, setOver] = useState<string | null>(null);
  const current = useRef<string | null>(null);
  const end = useCallback(() => { current.current = null; setOver(null); }, []);

  const pillDrag = useCallback((taskId: string): PillDrag => ({
    draggable: true,
    onDragStart: (event) => {
      current.current = taskId;
      event.dataTransfer?.setData(CARD_TYPE, taskId);
      if (event.dataTransfer) event.dataTransfer.effectAllowed = "move";
    },
    onDragEnd: end,
  }), [end]);

  const dayDrop = useCallback((day: IsoDay, hourAt?: (event: DragEvent<HTMLElement>) => number): DayDrop => {
    const spot = `${day}${hourAt ? "|slots" : ""}`;
    return {
      isOver: over === spot,
      onDragOver: (event) => {
        if (current.current === null) return;
        event.preventDefault();
        if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
        setOver(spot);
      },
      onDragLeave: (event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setOver((now) => (now === spot ? null : now));
      },
      onDrop: (event) => {
        event.preventDefault();
        const id = current.current ?? event.dataTransfer?.getData(CARD_TYPE) ?? "";
        const hour = hourAt ? hourAt(event) : null;
        end();
        if (id) onDrop(id, day, hour);
      },
    };
  }, [end, onDrop, over]);

  return useMemo(() => ({ pillDrag, dayDrop }), [pillDrag, dayDrop]);
}
