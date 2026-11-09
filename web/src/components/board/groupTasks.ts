import { INBOX_VIEW, NEXT_UP_DAYS, type BoardView } from "./constants";
import { daysAhead } from "./taskChips";
import type { TaskRowOut } from "../../api/tasks";
import { addDays, dayText, type IsoDay } from "../../ui/date/dates";

export interface TaskGroup {
  key: string;
  title: string;
  tone?: "danger";
  rows: readonly TaskRowOut[];
  action?: "reschedule-all";
}

const DAY_LENGTH = "YYYY-MM-DD".length;
const OPEN: ReadonlySet<TaskRowOut["status"]> = new Set(["todo", "in_progress"]);
const dayOf = (row: TaskRowOut): string | null => (row.due_date ? row.due_date.slice(0, DAY_LENGTH) : null);

const nonEmpty = (groups: readonly TaskGroup[]): readonly TaskGroup[] => groups.filter((group) => group.rows.length > 0);

// The server has already picked and sorted the rows of a view (Task 10); these only cut them into headed groups,
// in the mockup's order. Empty groups are left out, and rows keep the server's order inside a group.
export function groupsFor(view: BoardView, rows: readonly TaskRowOut[], today: IsoDay): readonly TaskGroup[] {
  if (view === INBOX_VIEW) return nonEmpty([{ key: "inbox", title: "No project", rows }]);
  if (view === "today") {
    return nonEmpty([
      { key: "overdue", title: "Overdue", tone: "danger", action: "reschedule-all", rows: rows.filter((row) => (dayOf(row) ?? today) < today) },
      { key: "today", title: `Due today · ${dayText(today, { weekday: true })}`, rows: rows.filter((row) => dayOf(row) === today) },
    ]);
  }
  if (view === "upcoming") return upcomingGroups(rows, today);
  if (view === "overdue") return nonEmpty([{ key: "overdue", title: "Overdue", tone: "danger", action: "reschedule-all", rows }]);
  if (view === "someday") return nonEmpty([{ key: "someday", title: "No date", rows }]);
  return nonEmpty([{ key: "done", title: "Done", rows }]); // newest first and capped, not only this week
}

function upcomingGroups(rows: readonly TaskRowOut[], today: IsoDay): readonly TaskGroup[] {
  const days = [...new Set(rows.map(dayOf).filter((day): day is string => day !== null))].sort();
  const tomorrow = addDays(today, 1);
  return days.map((day) => ({
    key: day,
    title: day === tomorrow ? `Tomorrow · ${dayText(day, { weekday: true })}` : dayText(day, { weekday: true }),
    rows: rows.filter((row) => dayOf(row) === day),
  }));
}

const byDue = (a: TaskRowOut, b: TaskRowOut): number => (a.due_date ?? "9999").localeCompare(b.due_date ?? "9999");

// A project's page (G13 uses it too): Overdue, Next up (today to six days ahead), Later (seven or more days, or
// no date) and Done (everything closed). Open rows are sorted by due date.
export function projectGroups(rows: readonly TaskRowOut[], today: IsoDay): readonly TaskGroup[] {
  const open = rows.filter((row) => OPEN.has(row.status)).sort(byDue);
  const ahead = (row: TaskRowOut): number | null => (row.due_date ? daysAhead(row.due_date, today) : null);
  return nonEmpty([
    { key: "overdue", title: "Overdue", tone: "danger", rows: open.filter((row) => (ahead(row) ?? 0) < 0) },
    { key: "next", title: "Next up", rows: open.filter((row) => { const n = ahead(row); return n !== null && n >= 0 && n < NEXT_UP_DAYS; }) },
    { key: "later", title: "Later", rows: open.filter((row) => { const n = ahead(row); return n === null || n >= NEXT_UP_DAYS; }) },
    { key: "done", title: "Done", rows: rows.filter((row) => !OPEN.has(row.status)) },
  ]);
}
