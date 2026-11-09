import type { TaskCountsOut } from "../../api/tasks";

// The one Today number (lead task 05): open tasks overdue or due today, the same set the Tasks › Today list shows.
// The Board's Tasks tab, the Today chip and the Today stat all show this; the server's `today` alone is due today.
export function todayCount(counts: TaskCountsOut): number {
  return counts.overdue + counts.today;
}
