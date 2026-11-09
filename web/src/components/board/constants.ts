// The Board's numbers, in one place.
export const NEXT_WEEK_PICK_DAYS = 4; // "Next week" is Next Monday plus this many days (a Friday)
export const PLUS_WEEK_DAYS = 7; // "+1 week"
export const SATURDAY = 6; // Date.getUTCDay() of a Saturday
export const DAYS_PER_WEEK = 7;
export const TASK_SEARCH_DEBOUNCE_MS = 250; // the Tasks search waits for a pause in typing
export const NEXT_UP_DAYS = 7; // a project page's "Next up": today to six days ahead; 7 or more is "Later"
export const TASK_VIEW_KEYS = ["today", "upcoming", "overdue", "someday", "done"] as const; // keys 1 to 5
// The Workspace's Tasks views (app restructure): the server's views, plus the Inbox (every open task with no project).
export const INBOX_VIEW = "inbox";
export type BoardView = (typeof TASK_VIEW_KEYS)[number] | typeof INBOX_VIEW;
export const MAIN_VIEWS = ["today", INBOX_VIEW, "upcoming"] as const; // the tabs
export const MORE_VIEWS = ["someday", "overdue", "done"] as const; // behind More
export const KANBAN_COLLAPSED_PX = 44; // a collapsed Kanban column's width
export const STRIP_MAX_DAYS = 31; // By days draws the last 31 days of a range
export const STRIP_LABEL_EVERY = 5; // a long strip names every fifth day
export const STRIP_DENSE_DAYS = 16; // more days than this is a long strip
export const CAL_CELL_MAX_PILLS = 3; // a month cell shows this many pills, then "+N more"
export const CAL_CELL_MAX_ROUTINES = 2; // and this many routine lines, then "+N routines"
// The screens whose show / hide choices (Routines, Made by bots, a Plan's Done) are remembered apart (board toggles).
export const SCREEN_BOARD_LIST = "board-list";
export const SCREEN_BOARD_KANBAN = "board-kanban";
export const SCREEN_BOARD_CALENDAR = "board-calendar";
export const SCREEN_PROJECT = "project";
export const SCREEN_PLAN_CALENDAR = "plan-calendar";
export const CAL_FIRST_HOUR = 7; // the week's time grid starts at 07:00...
export const CAL_HOURS = 16; // ...and runs for 16 hours, to 22:00
export const CAL_HOUR_PX = 40; // one hour's height in that grid
export const PHONE_MEDIA = "(max-width: 768px)"; // phone layouts: Kanban swipes, calendars are agendas, the drawer is full screen
export const LONG_PRESS_MS = 500; // a press this long on a task row opens its menu
export const LONG_PRESS_SLOP_PX = 10; // a finger that moves further than this is scrolling, not pressing
