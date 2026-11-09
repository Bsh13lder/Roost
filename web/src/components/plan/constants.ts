export const PLAN_CHANGED_TEXT = "The Plan changed; try again.";
export const NO_DATE = "No date";
export const NOTHING_TEXT = "Nothing on this day.";
export const CONFLICT_TEXT = "The Plan changed since you opened it.";

export const unreadableText = (count: number) => `${count} ${count === 1 ? "line" : "lines"} couldn't be read`;

export const VIEWS = [
  { id: "calendar", label: "Calendar" }, { id: "kanban", label: "Kanban" }, { id: "text", label: "Text" },
] as const;
export type PlanViewId = (typeof VIEWS)[number]["id"];
