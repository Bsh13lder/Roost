import type { ReactNode } from "react";
import type { KanbanColumn as Column, KanbanGroup } from "./kanbanGroups";
import { defaultDueFor } from "./kanbanGroups";
import type { ColumnDrop } from "./useKanbanDrag";
import { QuickAddPopover } from "../QuickAddPopover";
import { ReschedulePopover, type DuePick } from "../ReschedulePopover";
import type { QuickAddDefaults } from "../../tasks/QuickAdd";
import type { TaskRowOut } from "../../../api/tasks";
import { cx } from "../../../ui/cx";

export interface DayPicker {
  open: boolean;
  title: string;
  onOpenChange: (open: boolean) => void;
  onPick: (pick: DuePick) => void;
}

export interface KanbanColumnProps {
  column: Column;
  group: KanbanGroup;
  lane?: { key: string; name: string }; // the project row it sits in (Split by project)
  count: number;
  collapsed: boolean;
  onToggle: (key: string) => void;
  drop: ColumnDrop;
  picker?: DayPicker; // This week and Later: the date picker a drop or Move to… opens
  onAdded: () => void;
  emptyNote?: string; // what an empty column says instead of "Drop a card here"
  children: ReactNode; // the cards
}

const plural = (count: number) => `${count} task${count === 1 ? "" : "s"}`;

// What "+" gives a new task in this column: the column's own value, so it lands where it was added.
function addSetup(group: KanbanGroup, column: Column, lane: KanbanColumnProps["lane"]) {
  const defaults: QuickAddDefaults = {};
  let prefill = "";
  if (group === "priority") defaults.priority = column.key as TaskRowOut["priority"];
  if (group === "list" && column.key !== "none") defaults.category = column.label;
  if (group === "status" && column.key === "in_progress") defaults.status = "in_progress";
  if (group === "project" && column.key !== "none") prefill = `/${column.label} `;
  if (group === "bot" && column.botId) prefill = `@${column.label} `;
  if (lane && lane.key !== "none") prefill = `/${lane.name} `;
  return { defaults, prefill: prefill || undefined };
}

// One Kanban column (G6): a head with the collapse button, a project dot, the name, the count and "+", then
// its cards, or "Drop a card here". A collapsed column is a narrow strip with its name standing up.
export function KanbanColumn({ column, group, lane, count, collapsed, onToggle, drop, picker, onAdded, emptyNote, children }: KanbanColumnProps) {
  const { defaults, prefill } = addSetup(group, column, lane);
  const day = defaultDueFor(group, column.key);
  const askDay = group === "due" && (column.key === "week" || column.key === "later");
  const name = <span className="kcol__name">{column.label}</span>;
  return (
    <section className={cx("kcol", collapsed && "is-collapsed", drop.isOver && "is-over", !column.dropTarget && "is-fixed")}
      aria-label={column.label} data-column={column.key} onDragOver={drop.onDragOver} onDragLeave={drop.onDragLeave} onDrop={drop.onDrop}>
      <div className="kcol__head">
        <button type="button" className="icon-btn" aria-expanded={!collapsed}
          aria-label={`${collapsed ? "Expand" : "Collapse"} ${column.label}`} onClick={() => onToggle(column.key)}>
          {collapsed ? "›" : "⌄"}
        </button>
        {group === "project" && column.color ? <span className="dot" style={{ background: column.color }} aria-hidden="true" /> : null}
        {picker ? (
          <ReschedulePopover title={picker.title} open={picker.open} onOpenChange={picker.onOpenChange} current={null}
            onPick={picker.onPick} trigger={<span className="kcol__anchor">{name}</span>} />
        ) : name}
        <span className="count" aria-label={plural(count)}>{count}</span>
        {column.canAdd ? (
          <QuickAddPopover title={`Add task in ${column.label}`} onAdded={onAdded} defaultDue={day} prefill={prefill}
            defaults={defaults} hint={askDay ? "Type a day" : undefined}
            trigger={<button type="button" className="icon-btn kcol__add" aria-label={`Add a task in ${column.label}`}
              title={`Add in ${column.label}`}>+</button>} />
        ) : null}
      </div>
      {collapsed ? null : children}
      {collapsed || count > 0 ? null : <div className="kcol__empty">{emptyNote ?? (column.dropTarget ? "Drop a card here" : "Nothing here")}</div>}
    </section>
  );
}
