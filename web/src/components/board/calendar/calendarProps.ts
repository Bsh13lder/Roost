import type { MoneyRangeOut } from "../../../api/money";
import type { ExpenseActions } from "../useExpenseActions";
import type { TaskScope } from "../taskScope";

// A project as a pill shows it: its name and its colour.
export interface ProjectLook {
  name: string;
  color: string;
}

// What the two lazy calendars (and their phone agendas) are given by the Tasks and Money boards.
export interface TaskCalendarProps {
  projects: ReadonlyMap<string, ProjectLook>;
  onOpen: (taskId: string) => void;
  scope?: TaskScope; // the Tasks rail's selection: one project's tasks only (none: All)
  ownDone?: boolean; // the Workspace's Calendar: finished tasks follow its own Done switch, not Show finished
}

export interface ExpenseCalendarProps {
  range: MoneyRangeOut; // the month's days and rows (GET /api/money/range), as the Money tab loaded them
  month: string; // "YYYY-MM"
  actions: ExpenseActions;
  onChanged: () => void; // an expense was added or undone: load again
}
