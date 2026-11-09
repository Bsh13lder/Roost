// web/src/components/workspace/calendar/agendaItems.ts: the picked day's lines in the Workspace's Calendar (app
// restructure): the tasks with no time first ("All day"), then the timed ones and the day's routine runs (board
// toggles) in order, and on today a now line at the account's current time, between the lines before it and after it.
import { dueTime } from "../../board/calendar/taskPlacement";
import type { TaskRowOut } from "../../../api/tasks";
import type { RoutineDayEntry } from "../../../lib/routineDays";
import type { WallTime } from "../../../ui/date/dates";

export type AgendaItem =
  | { kind: "task"; task: TaskRowOut; time: WallTime | null }
  | { kind: "routine"; entry: RoutineDayEntry; time: WallTime }
  | { kind: "now"; time: WallTime };

type Timed = Exclude<AgendaItem, { kind: "now" }>;

/** The day's tasks and routines as agenda lines; `now` (the account's "HH:MM") puts the now line in, on today only. */
export function agendaItems(tasks: readonly TaskRowOut[], now: WallTime | null,
  routines: readonly RoutineDayEntry[] = []): AgendaItem[] {
  const lines = tasks.map((task): Timed => ({ kind: "task", task, time: dueTime(task) }));
  const runs = routines.map((entry): Timed => ({ kind: "routine", entry, time: entry.times[0] ?? "" }));
  const untimed = lines.filter((line) => line.time === null);
  const timed = [...lines.filter((line) => line.time !== null), ...runs]
    .sort((a, b) => (a.time ?? "").localeCompare(b.time ?? ""));
  if (now === null) return [...untimed, ...timed];
  const before = timed.filter((line) => (line.time ?? "") <= now);
  const after = timed.filter((line) => (line.time ?? "") > now);
  return [...untimed, ...before, { kind: "now", time: now }, ...after];
}
