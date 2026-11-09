import { KANBAN_GROUPS, KANBAN_SORTS, type KanbanGroup } from "./kanbanGroups";
import type { TaskSort } from "../../../api/tasks";
import { Select } from "../../../ui/Select";
import { Switch } from "../../../ui/Switch";

export interface KanbanToolbarProps {
  group: KanbanGroup;
  onGroup: (group: KanbanGroup) => void;
  sort: TaskSort;
  onSort: (sort: TaskSort) => void;
  split: boolean;
  onSplit: (split: boolean) => void;
}

const GROUP_OPTIONS = KANBAN_GROUPS.map((g) => ({ value: g.value, label: `Group by: ${g.label}` }));
const SORT_OPTIONS = KANBAN_SORTS.map((s) => ({ value: s.value, label: `Sort cards by: ${s.label}` }));

// The Kanban's tools (G6), in place of the list's view chips: how to group, how to sort the cards, and
// Split by project (one row per project, columns by status), which only makes sense while grouped by Status.
export function KanbanToolbar({ group, onGroup, sort, onSort, split, onSplit }: KanbanToolbarProps) {
  const byStatus = group === "status";
  return (
    <div className="tasks-tools kanban-tools">
      <Select size="md" label="Group by" value={group} options={GROUP_OPTIONS} onChange={onGroup} />
      <Select size="md" label="Sort cards by" value={sort} options={SORT_OPTIONS} onChange={onSort} />
      <Switch checked={split && byStatus} disabled={!byStatus} onChange={onSplit} title="One row per project, columns by status">
        Split by project
      </Switch>
    </div>
  );
}
