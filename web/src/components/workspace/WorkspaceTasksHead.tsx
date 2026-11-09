import type { ReactNode } from "react";
import { TaskViewTabs } from "./TaskViewTabs";
import type { BoardView } from "../board/constants";
import { KanbanToolbar, type KanbanToolbarProps } from "../board/kanban/KanbanToolbar";
import { useInboxCount } from "../board/rail/useInboxCount";
import { todayCount } from "../board/todayCount";
import { useTaskCounts } from "../board/useTaskCounts";
import type { TaskLayout } from "../board/useTaskView";
import { MoreIcon } from "../icons";
import type { TaskSort } from "../../api/tasks";
import { Menu, MenuItem } from "../../ui/Menu";
import { Segmented } from "../../ui/Segmented";
import { Select } from "../../ui/Select";

export interface WorkspaceTasksHeadProps {
  view: BoardView;
  onView: (view: BoardView) => void;
  filters: ReactNode; // the project chips and the picked project's card
  layout: TaskLayout;
  onLayout: (layout: TaskLayout) => void;
  kanban: KanbanToolbarProps;
  sort: TaskSort;
  onSort: (sort: TaskSort) => void;
  onExpandAll: () => void;
  onCollapseAll: () => void;
  finished: ReactNode; // the Show finished switch, or null on Done
  countsFor?: string; // the project_id the chips narrowed the counts to ("none" for No project)
  onCountsGone?: () => void; // the server knows no such project (404)
}

const LAYOUTS = [{ id: "list", label: "List" }, { id: "kanban", label: "Kanban" }] as const;
const SORTS = [{ value: "due", label: "Sort: Due" }, { value: "priority", label: "Sort: Priority" }] as const;

function ListTools({ sort, onSort, onExpandAll, onCollapseAll }: Pick<WorkspaceTasksHeadProps, "sort" | "onSort" | "onExpandAll" | "onCollapseAll">) {
  return (
    <div className="tasks-tools">
      <Select size="md" label="Sort" value={sort === "priority" ? "priority" : "due"} options={SORTS}
        onChange={(next) => onSort(next === "priority" ? "priority" : "due")} />
      <Menu label="More options" trigger={<MoreIcon />}>
        <MenuItem onSelect={onExpandAll}>Expand all subtasks</MenuItem>
        <MenuItem onSelect={onCollapseAll}>Collapse all subtasks</MenuItem>
      </Menu>
    </div>
  );
}

// Over the Workspace's tasks (app restructure): Today · Inbox · Upcoming (More: Someday, Overdue, Done), the
// project chips, then List · Kanban with the list's sort or the Kanban's grouping, and Show finished. The search is
// the Workspace's pill.
export function WorkspaceTasksHead(props: WorkspaceTasksHeadProps) {
  const { view, onView, filters, layout, onLayout, kanban, finished, countsFor, onCountsGone } = props;
  const counts = useTaskCounts(countsFor, onCountsGone);
  const inbox = useInboxCount();
  const list = layout !== "kanban";
  return (
    <div className="ws-tasks-head">
      {list ? (
        <TaskViewTabs view={view} onView={onView}
          counts={{ today: counts ? todayCount(counts) : null, inbox, upcoming: counts?.upcoming_14 ?? null }} />
      ) : null}
      {filters}
      <div className="tasks-top">
        <Segmented label="Task layout" options={LAYOUTS} value={list ? "list" : "kanban"} onChange={onLayout} />
        {list ? <ListTools {...props} /> : <KanbanToolbar {...kanban} />}
        {finished}
      </div>
    </div>
  );
}
