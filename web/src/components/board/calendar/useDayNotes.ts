import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { addDayNote, deleteDayNote, listDayNotes, type DayNoteOut } from "../../../api/dayNotes";
import { describeError } from "../../../api/client";
import { useToast } from "../../../ui/Toast";
import type { IsoDay } from "../../../ui/date/dates";

export interface DayNotes {
  byDay: ReadonlyMap<IsoDay, readonly DayNoteOut[]>;
  add: (day: IsoDay, text: string) => Promise<string | null>; // the problem in a sentence, or null when it worked
  remove: (note: DayNoteOut) => Promise<void>; // deletes, then offers Undo
}

// The day notes of the visible days (G11). It reloads when a day note changes anywhere (`version`, the
// day_notes_changed frame) and after its own writes. Delete says so with an Undo that writes the same text again.
export function useDayNotes(first: IsoDay, last: IsoDay, version: number): DayNotes {
  const toast = useToast();
  const [notes, setNotes] = useState<readonly DayNoteOut[]>([]);
  const latest = useRef(0);
  const load = useCallback(() => {
    const ticket = ++latest.current;
    listDayNotes(first, last)
      .then((found) => { if (ticket === latest.current) setNotes(found); })
      .catch((err: unknown) => console.warn("Could not load the day notes:", describeError(err)));
  }, [first, last]);
  useEffect(() => load(), [load, version]);

  const add = useCallback(async (day: IsoDay, text: string) => {
    try {
      await addDayNote(day, text);
    } catch (err) {
      return describeError(err);
    }
    load();
    return null;
  }, [load]);

  const remove = useCallback(async (note: DayNoteOut) => {
    try {
      await deleteDayNote(note.id);
    } catch (err) {
      toast.show(describeError(err), { tone: "danger" });
      return;
    }
    load();
    toast.show("Note deleted", {
      action: { label: "Undo", run: () => { void add(note.day, note.text).then((problem) => { if (problem) toast.show(problem, { tone: "danger" }); }); } },
    });
  }, [add, load, toast]);

  const byDay = useMemo(() => {
    const grouped = new Map<IsoDay, DayNoteOut[]>();
    for (const note of notes) grouped.set(note.day, [...(grouped.get(note.day) ?? []), note]);
    return grouped;
  }, [notes]);
  return useMemo(() => ({ byDay, add, remove }), [byDay, add, remove]);
}
