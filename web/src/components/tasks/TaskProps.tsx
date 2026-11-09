import { useState, type KeyboardEvent, type ReactElement, type ReactNode } from "react";
import { PriorityMark } from "../board/PriorityMark";
import { ReschedulePopover, type DuePick } from "../board/ReschedulePopover";
import { formatMoney } from "../board/money";
import {
  EstimateEditor, ListEditor, PRIORITIES, PriorityEditor, ProjectEditor, ReminderEditor, RepeatEditor, SliceEditor,
} from "./propEditors";
import { NO_PROJECT, type TaskDraft } from "./useTaskDraft";
import type { ProjectOut, TaskDetailOut } from "../../api/types";
import { Popover } from "../../ui/Popover";
import { dayText, dueParts } from "../../ui/date/dates";

const MINUTES_PER_HOUR = 60;

const Faint = ({ children }: { children: ReactNode }) => <span className="faint">{children}</span>;

// "Wed 21 Oct, 09:30" for a stored or picked due, or the words themselves when the server must read them.
export function dueWords(due: string | null): string | null {
  if (!due) return null;
  const parts = dueParts(due.replace(" ", "T"));
  if (!parts) return due;
  const day = dayText(parts.day, { weekday: true });
  return parts.time ? `${day}, ${parts.time}` : day;
}

// "~45 min", "~2 h", "~1 h 30 min".
export function estimateWords(minutes: number): string {
  const hours = Math.floor(minutes / MINUTES_PER_HOUR);
  const rest = minutes % MINUTES_PER_HOUR;
  return `~${[hours ? `${hours} h` : "", rest ? `${rest} min` : ""].filter(Boolean).join(" ")}`;
}

// "~1h 30m", "~2h", "45" as minutes; 0 when there is nothing to read.
function minutesOf(text: string): number {
  const hours = Number(/(\d+)\s*h/i.exec(text)?.[1] ?? 0);
  const rest = /(\d+)\s*m/i.exec(text)?.[1] ?? (/h/i.test(text) ? "0" : /(\d+)/.exec(text)?.[1] ?? "0");
  return hours * MINUTES_PER_HOUR + Number(rest);
}

// A reminder "2026-10-21 08:30" in words; none, with a timed due, is "At the due time".
function reminderWords(text: string, due: string | null): ReactNode {
  const words = dueWords(text.trim() || null);
  if (words) return words.replace(",", "");
  return dueParts(due ?? "")?.time ? "At the due time" : <Faint>None</Faint>;
}

// Enter in a one-line field inside the editor (not while an input method is composing) means "done".
const isDoneKey = (event: KeyboardEvent) => event.key === "Enter" && !event.nativeEvent.isComposing
  && event.target instanceof HTMLInputElement;

// One property: its label, and a quiet value button that opens its editor. Closing the editor (Enter, Escape,
// a click or focus outside) saves what was typed.
function PropRow({ label, value, spoken, onDone, children }: { label: string; value: ReactNode; spoken: string; onDone: () => void; children: ReactElement }) {
  const [open, setOpen] = useState(false);
  const close = () => { setOpen(false); onDone(); };
  return (
    <>
      <dt>{label}</dt>
      <dd>
        <Popover label={`Edit ${label}`} align="start" open={open} onOpenChange={(next) => (next ? setOpen(true) : close())}
          trigger={<button type="button" className="prop-btn" aria-label={`${label}, ${spoken}`}>{value}</button>}>
          <div className="prop-editor" onKeyDown={(event) => { if (isDoneKey(event)) { event.preventDefault(); close(); } }}>{children}</div>
        </Popover>
      </dd>
    </>
  );
}

export interface TaskPropsProps {
  task: TaskDetailOut;
  projects: readonly ProjectOut[];
  draft: TaskDraft;
  onDue: (pick: DuePick) => void;
}

// The task's properties as a list: a label and a quiet value button that opens its editor in a popover.
// Every property saves on its own: Due through the reschedule popover, a pick (priority, project) at once,
// and typed words when the editor closes.
export function TaskProps({ task, projects, draft: staged, onDue }: TaskPropsProps) {
  const { draft, set, pick, commit } = staged;
  const done = () => void commit();
  const project = projects.find((found) => found.id === draft.project);
  // The budget's currency: the project's, or General's for a task in no project (the server's money says which).
  const currency = project?.currency ?? (draft.project === NO_PROJECT ? task.money?.currency : undefined);
  const due = dueWords(task.due_date);
  const dueDay = dueParts(task.due_date ?? "");
  const minutes = minutesOf(draft.estimate);
  const priority = PRIORITIES.find((option) => option.value === draft.priority)?.label ?? "";
  const reminder = reminderWords(draft.reminder, task.due_date);
  return (
    <dl className="props" aria-label="Properties">
      <dt>Due</dt>
      <dd>
        <ReschedulePopover title={`Reschedule “${task.title}”`} current={dueDay} onPick={onDue}
          trigger={<button type="button" className="prop-btn" aria-label={`Due, ${due ?? "none"}`}>{due ?? <Faint>Add a day</Faint>}</button>} />
      </dd>
      <PropRow label="Reminder" onDone={done} value={reminder} spoken={typeof reminder === "string" ? reminder : "none"}>
        <ReminderEditor value={draft.reminder} onChange={(value) => set("reminder", value)} due={task.due_date}
          onPick={(value) => pick("reminder", value)} />
      </PropRow>
      <PropRow label="Repeat" onDone={done} value={draft.repeat.trim() || <Faint>Never</Faint>} spoken={draft.repeat.trim() || "never"}>
        <RepeatEditor value={draft.repeat} onChange={(value) => set("repeat", value)} />
      </PropRow>
      <PropRow label="Priority" onDone={done} value={<><PriorityMark priority={draft.priority} />{priority}</>} spoken={priority}>
        <PriorityEditor value={draft.priority} onChange={(value) => pick("priority", value)} />
      </PropRow>
      <PropRow label="Project" onDone={done} value={project ? <><span className="dot" style={{ background: project.color }} aria-hidden="true" />{project.name}</> : <Faint>None</Faint>} spoken={project?.name ?? "none"}>
        <ProjectEditor value={draft.project} projects={projects} current={task.project_id ?? NO_PROJECT}
          onChange={(value) => pick("project", value)} />
      </PropRow>
      <PropRow label="Budget" onDone={done} value={draft.slice.trim() && currency ? formatMoney(draft.slice, currency) : <Faint>Add a budget</Faint>} spoken={draft.slice.trim() || "none"}>
        <SliceEditor value={draft.slice} onChange={(value) => set("slice", value)} />
      </PropRow>
      <PropRow label="List" onDone={done} value={draft.list.trim() || <Faint>Add a list</Faint>} spoken={draft.list.trim() || "none"}>
        <ListEditor value={draft.list} onChange={(value) => set("list", value)} />
      </PropRow>
      <PropRow label="Estimate" onDone={done} value={minutes > 0 ? estimateWords(minutes) : <Faint>~ Add an estimate</Faint>} spoken={minutes > 0 ? estimateWords(minutes) : "none"}>
        <EstimateEditor value={draft.estimate} onChange={(value) => set("estimate", value)} />
      </PropRow>
    </dl>
  );
}
