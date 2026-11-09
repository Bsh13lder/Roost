import { useEffect, useState } from "react";
import { MAX_AMOUNT_TEXT } from "../board/money";
import { MAX_LIST } from "../board/taskLimits";
import { NO_PROJECT, type DraftFields } from "./useTaskDraft";
import * as tasksApi from "../../api/tasks";
import type { ProjectOut, TaskOut } from "../../api/types";
import { Input } from "../../ui/Input";
import { Select, type SelectOption } from "../../ui/Select";
import { DateTimePicker } from "../../ui/date/DateTimePicker";
import { Button } from "../../ui/Button";
import { remindPicks } from "./remindPicks";

const REPEAT_CHECK_MS = 300;
const MAX_WORDS = 60;

export const PRIORITIES: ReadonlyArray<SelectOption<TaskOut["priority"]>> = [
  { value: "urgent", label: "Urgent" }, { value: "high", label: "High" }, { value: "medium", label: "Medium" },
  { value: "low", label: "Low" },
];

// The open projects (and the task's own, if it sits in an archived one) plus None. General is never one.
export function projectOptions(projects: readonly ProjectOut[], current: string): ReadonlyArray<SelectOption> {
  const shown = projects.filter((project) => project.status === "active" || project.id === current);
  return [{ value: NO_PROJECT, label: "None" }, ...shown.map((project) => ({ value: project.id, label: project.name }))];
}

export interface EditorProps<K extends keyof DraftFields> {
  value: DraftFields[K];
  onChange: (value: DraftFields[K]) => void;
}

// Remind me: a day and time, or a quick pick before a timed due (a pick saves at once).
export function ReminderEditor({ value, onChange, due, onPick }: EditorProps<"reminder"> & {
  due: string | null; onPick: (value: string) => void;
}) {
  const picks = remindPicks(due);
  return (
    <>
      <DateTimePicker label="Reminder" value={value} placeholder="empty: at the due time" onChange={onChange} />
      {picks.length ? (
        <div className="prop-editor__picks" role="group" aria-label="Quick reminders">
          {picks.map((pick) => (
            <Button key={pick.label} size="sm" variant="ghost" onClick={() => onPick(pick.text)}>{pick.label}</Button>
          ))}
        </div>
      ) : null}
    </>
  );
}

// Words the server reads: asks it as the user types, and says why it can't when it can't.
export function RepeatEditor({ value, onChange }: EditorProps<"repeat">) {
  const [problem, setProblem] = useState<string | null>(null);
  useEffect(() => {
    const words = value.trim();
    if (!words) { setProblem(null); return undefined; }
    let current = true;
    const timer = window.setTimeout(() => {
      tasksApi.parseQuickLine({ text: words })
        .then((line) => { if (current) setProblem(line.repeat_problem); })
        .catch(() => { if (current) setProblem(null); });
    }, REPEAT_CHECK_MS);
    return () => { current = false; window.clearTimeout(timer); };
  }, [value]);
  return (
    <>
      <Input aria-label="Repeat" controlSize="md" value={value} maxLength={MAX_WORDS} placeholder="every Monday, monthly…"
        invalid={problem !== null} onChange={(e) => onChange(e.target.value)} />
      {problem ? <p className="prop-editor__problem" role="status">{problem}</p> : null}
    </>
  );
}

export function PriorityEditor({ value, onChange }: EditorProps<"priority">) {
  return <Select label="Priority" size="md" value={value} options={PRIORITIES} onChange={onChange} />;
}

export function ProjectEditor({ value, onChange, projects, current }: EditorProps<"project"> & { projects: readonly ProjectOut[]; current: string }) {
  return <Select label="Project" size="md" value={value} options={projectOptions(projects, current)} onChange={onChange} />;
}

export function ListEditor({ value, onChange }: EditorProps<"list">) {
  return <Input aria-label="List" controlSize="md" value={value} maxLength={MAX_LIST} placeholder="Home, Work…"
    onChange={(e) => onChange(e.target.value)} />;
}

export function EstimateEditor({ value, onChange }: EditorProps<"estimate">) {
  return <Input aria-label="Estimate" controlSize="md" value={value} maxLength={MAX_WORDS} placeholder="~45m, ~2h"
    onChange={(e) => onChange(e.target.value)} />;
}

export function SliceEditor({ value, onChange }: EditorProps<"slice">) {
  return <Input aria-label="Budget" inputMode="decimal" controlSize="md" value={value} maxLength={MAX_AMOUNT_TEXT}
    placeholder="empty: none" onChange={(e) => onChange(e.target.value)} />;
}
