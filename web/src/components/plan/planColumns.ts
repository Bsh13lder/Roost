import type { PlanItemOut, PlanStatus } from "../../api/plan";
import type { KanbanColumn } from "../board/kanban/kanbanGroups";

const column = (key: PlanStatus, label: string): KanbanColumn => ({ key, label, dropTarget: true, canAdd: false });

// The Plan's Kanban columns: Planned, On it, Done, and Dropped only when asked for.
export const PLAN_COLUMNS: readonly KanbanColumn[] = [
  column("planned", "Planned"), column("on_it", "On it"), column("done", "Done"), column("dropped", "Dropped"),
];

export const visibleColumns = (showDropped: boolean): readonly KanbanColumn[] =>
  showDropped ? PLAN_COLUMNS : PLAN_COLUMNS.filter((one) => one.key !== "dropped");

export const itemsIn = (items: readonly PlanItemOut[], status: string): PlanItemOut[] =>
  items.filter((one) => one.status === status);

const byTime = (a: PlanItemOut, b: PlanItemOut) => (a.time ?? "99:99").localeCompare(b.time ?? "99:99") || a.line_no - b.line_no;

// Dropped items sit in no day and no list of undated work: they are only on the Kanban's toggle.
const live = (items: readonly PlanItemOut[]) => items.filter((one) => one.status !== "dropped");

export const itemsOnDay = (items: readonly PlanItemOut[], day: string): PlanItemOut[] =>
  live(items).filter((one) => one.date === day).sort(byTime);

export const undated = (items: readonly PlanItemOut[]): PlanItemOut[] => live(items).filter((one) => !one.date);

export const daysWithItems = (items: readonly PlanItemOut[]): ReadonlyMap<string, number> =>
  live(items).reduce((days, one) => (one.date ? new Map(days).set(one.date, (days.get(one.date) ?? 0) + 1) : days), new Map<string, number>());
