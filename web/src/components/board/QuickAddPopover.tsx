import { useContext, useState, type ReactElement } from "react";
import { ExpenseLine } from "./ExpenseLine";
import { QuickAdd, type QuickAddDefaults } from "../tasks/QuickAdd";
import { QuickAddProject } from "../tasks/quickAddProject";
import type { ExpenseLineOut } from "../../api/money";
import type { ExpenseOut } from "../../api/types";
import { Popover } from "../../ui/Popover";

export interface QuickAddBodyProps {
  kind?: "task" | "expense"; // what the line adds (a task by default)
  title: string; // "Add task in Tomorrow"
  onAdded: () => void;
  onExpenseAdded?: (made: ExpenseOut, line: ExpenseLineOut) => void; // an expense line: what it made
  defaultDue?: string;
  prefill?: string;
  defaults?: QuickAddDefaults;
  hint?: string;
  placeholder?: string; // an example for the empty line
  dayBadge?: string; // "Due Wed 21 Oct", the first chip until the line names a day
  defaultDay?: string; // an expense line: the day of a line that names none ("On Wed 21 Oct" shows first)
}

// What sits inside the popover: a title, Task 5's QuickAdd and a quiet hint. A calendar day's popover shows it
// in place of the day's panel (G11). A task joins the project the Tasks rail picked, unless the line names another.
export function QuickAddBody({
  kind = "task", title, onAdded, onExpenseAdded, defaultDue, prefill, defaults, hint, placeholder, dayBadge, defaultDay,
}: QuickAddBodyProps) {
  const projectId = useContext(QuickAddProject);
  return (
    <div className="qpop">
      <h3 className="qpop__title">{title}</h3>
      {kind === "expense" ? (
        <ExpenseLine autoFocus defaultDay={defaultDay} placeholder={placeholder} submitLabel="Add expense"
          onAdded={(made, line) => { onExpenseAdded?.(made, line); onAdded(); }} />
      ) : (
        <QuickAdd autoFocus projectId={projectId} defaultDue={defaultDue} prefill={prefill} defaults={defaults} onAdded={onAdded}
          placeholder={placeholder} dayBadge={dayBadge} />
      )}
      {hint ? <p className="qpop__hint">{hint}</p> : null}
    </div>
  );
}

export interface QuickAddPopoverProps {
  kind?: "task" | "expense";
  trigger: ReactElement;
  title: string; // "Add task in Tomorrow"
  onAdded: () => void;
  defaultDue?: string; // "YYYY-MM-DD", used when the line names no day
  prefill?: string; // the line starts as this ("/Casa Nueva ")
  defaults?: QuickAddDefaults;
  hint?: string; // a quiet line under the field ("Type a day")
  defaultDay?: string; // kind "expense": the day of a line that names none
  onExpenseAdded?: QuickAddBodyProps["onExpenseAdded"];
}

// The task quick-add in a small popover (Board redesign G6): a Kanban column's "+" and a calendar day's (G11, G12: kind "expense" holds the expense line).
// It holds Task 5's QuickAdd, which reads the line on the server, so every chip and token works here too.
// Adding a task closes it.
export function QuickAddPopover({
  kind, trigger, title, onAdded, defaultDue, prefill, defaults, hint, defaultDay, onExpenseAdded,
}: QuickAddPopoverProps) {
  const [open, setOpen] = useState(false);
  return (
    <Popover trigger={trigger} label={title} open={open} onOpenChange={setOpen} align="start">
      <QuickAddBody kind={kind} title={title} defaultDue={defaultDue} prefill={prefill} defaults={defaults} hint={hint}
        defaultDay={defaultDay} onExpenseAdded={onExpenseAdded}
        onAdded={() => { setOpen(false); onAdded(); }} />
    </Popover>
  );
}
