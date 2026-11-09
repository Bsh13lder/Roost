import { useState, type FormEvent, type ReactNode } from "react";
import { DayNoteLine } from "./DayNoteLine";
import type { DayNoteOut } from "../../../api/dayNotes";
import { CloseIcon } from "../../icons";
import { Button } from "../../../ui/Button";
import { IconButton } from "../../../ui/IconButton";
import { Input } from "../../../ui/Input";
import { dayText, type IsoDay } from "../../../ui/date/dates";

const NOTE_MAX_LENGTH = 500;

export interface DayPopoverProps {
  kind: "tasks" | "money";
  day: IsoDay;
  count: number; // how many tasks or expenses the list holds
  totals?: ReactNode; // the day's money, secondary, in the head
  notes: readonly DayNoteOut[];
  children?: ReactNode; // the list section: pills, or expense rows
  onAddNote: (text: string) => Promise<string | null>; // the problem in a sentence, or null
  onDeleteNote: (note: DayNoteOut) => void;
  footer?: ReactNode; // "Add task" or "Add expense"
  onClose: () => void;
}

// What a calendar day holds, in a panel (G11, G12): the day's tasks or expenses, its Day note with who wrote each
// line and a field to add one, and the way to add a task or an expense on that day. The popover around it is the caller's.
export function DayPopover({ kind, day, count, totals, notes, children, onAddNote, onDeleteNote, footer, onClose }: DayPopoverProps) {
  const [text, setText] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const typed = text.trim();
    if (!typed || busy) return;
    setBusy(true);
    const refused = await onAddNote(typed);
    setBusy(false);
    setProblem(refused);
    if (!refused) setText("");
  };
  return (
    <div className="dpop">
      <div className="dpop__head">
        <h3>{dayText(day, { weekday: true })}</h3>
        {totals ? <span className="dpop__totals">{totals}</span> : null}
        <IconButton label="Close" size="sm" tooltip={false} icon={<CloseIcon />} onClick={onClose} />
      </div>
      <section className="dpop__sec" aria-label={kind === "tasks" ? "Tasks" : "Expenses"}>
        <span className="eyebrow">{kind === "tasks" ? "Tasks" : "Expenses"} · {count}</span>
        <div className="dpop__list">{count > 0 ? children : <p className="dpop__none">Nothing yet.</p>}</div>
      </section>
      <section className="dpop__sec" aria-label="Day note">
        <span className="eyebrow">Day note</span>
        {notes.length > 0 ? notes.map((note) => <DayNoteLine key={note.id} note={note} onDelete={onDeleteNote} />)
          : <p className="dpop__none">No note yet.</p>}
        <form className="dpop__add" onSubmit={(event) => void submit(event)}>
          <Input controlSize="md" aria-label="Add a note for this day" placeholder="Add a note for this day" value={text}
            maxLength={NOTE_MAX_LENGTH} autoComplete="off" invalid={problem !== null}
            onChange={(event) => { setText(event.target.value); setProblem(null); }} />
          <Button type="submit" size="md" variant="primary" disabled={!text.trim()} loading={busy}>Add</Button>
        </form>
        {problem ? <p className="dpop__error" role="alert">{problem}</p> : null}
      </section>
      {footer ? <div className="dpop__foot">{footer}</div> : null}
    </div>
  );
}
