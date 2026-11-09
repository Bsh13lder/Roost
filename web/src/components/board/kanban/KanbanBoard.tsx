import { useCallback, useMemo, useState } from "react";
import {
  columnOf, columnsFor, NO_PROJECT_KEY, visibleTasks, type KanbanColumn as Column, type KanbanContext, type KanbanGroup,
} from "./kanbanGroups";
import { KanbanCard } from "./KanbanCard";
import { KanbanColumn, type DayPicker } from "./KanbanColumn";
import { useKanbanDrag, type KanbanDrag } from "./useKanbanDrag";
import { useKanbanMove, type KanbanMover } from "./useKanbanMove";
import { KANBAN_COLLAPSED_PX } from "../constants";
import type { DuePick } from "../ReschedulePopover";
import { useProjects } from "../../tasks/useProjects";
import type { TaskRowOut } from "../../../api/tasks";
import type { ProjectOut, TaskStepOut } from "../../../api/types";
import { useLiveState } from "../../../hooks/useLiveStore";

export interface KanbanBoardProps {
  tasks: readonly TaskRowOut[]; // the server's `board` view, already sorted (finished ones out unless shown)
  finishedHidden?: boolean; // Show finished is off and some were left out: the empty Done column says so
  group: KanbanGroup;
  split: boolean;
  stepsOpen: ReadonlySet<string>;
  onToggleSteps: (id: string) => void;
  onSteps: (id: string, steps: readonly TaskStepOut[]) => void;
  onOpen: (id: string) => void;
  reload: () => void;
  reschedule: (task: TaskRowOut, pick: DuePick, where?: string) => Promise<void>;
}

interface Pending {
  task: TaskRowOut;
  key: string;
}

const HINTS: Readonly<Record<KanbanGroup, string>> = {
  status: "Drag a card to another column to change its status, or use ⋯ → Move to…",
  due: "Drag a card to another column to change its due date, or use ⋯ → Move to…",
  project: "Drag a card to another column to change its project, or use ⋯ → Move to…",
  priority: "Drag a card to another column to change its priority, or use ⋯ → Move to…",
  bot: "Who made a task is its history, so cards stay in their column. Use ⋯ → Reschedule… to change anything else.",
  list: "Drag a card to another column to change its list, or use ⋯ → Move to…",
};
const hintFor = (group: KanbanGroup): string => HINTS[group];
// Show finished off: Done stays a place to drop a card (it completes it), and says where its cards went.
const FINISHED_HIDDEN = "Finished tasks are hidden";

const gridOf = (columns: readonly Column[], collapsed: ReadonlySet<string>) =>
  columns.map((column) => (collapsed.has(column.key) ? `${KANBAN_COLLAPSED_PX}px` : "minmax(0, 1fr)")).join(" ");

type Lane = { key: string; name: string } | undefined;

// What every row of columns shares: the board's props and the pieces KanbanBoard works out once.
interface RowView {
  props: KanbanBoardProps;
  columns: readonly Column[];
  shown: readonly TaskRowOut[];
  collapsed: ReadonlySet<string>;
  toggle: (key: string) => void;
  drag: KanbanDrag;
  mover: KanbanMover;
  pickerFor: (column: Column) => DayPicker | undefined;
  projectOf: ReadonlyMap<string, ProjectOut>;
  bots: ReturnType<typeof useLiveState>["bots"];
  ctx: KanbanContext; // what the columns are cut from (Split by project cuts its lanes from it too)
}

// One column's cards.
function ColumnCards({ view, column, cards, lane }: { view: RowView; column: Column; cards: readonly TaskRowOut[]; lane: Lane }) {
  const { props, columns, drag, mover, projectOf, bots } = view;
  return cards.map((task) => (
    <KanbanCard key={task.id} task={task} drag={drag.cardProps(task.id)} dragging={drag.dragging === task.id}
      project={task.project_id ? projectOf.get(task.project_id) : undefined}
      bot={task.created_by_bot ? bots[task.created_by_bot] ?? null : null} showWho={props.group !== "bot"}
      moveTo={columns.filter((other) => other.dropTarget && other.key !== column.key)}
      stepsOpen={props.stepsOpen.has(task.id)} onToggleSteps={props.onToggleSteps} onSteps={props.onSteps} onOpen={props.onOpen}
      onMove={(moved, key) => void mover.apply(moved, key, lane?.key)}
      onReschedule={(moved, pick) => void props.reschedule(moved, pick)} />
  ));
}

// One row of columns: the whole board, or one project's lane with Split by project.
function KanbanRow({ view, lane }: { view: RowView; lane: Lane }) {
  const { props, columns, shown, collapsed } = view;
  const { group, finishedHidden = false } = props;
  const inLane = (task: TaskRowOut) => lane === undefined || (task.project_id ?? NO_PROJECT_KEY) === lane.key;
  return (
    <div className="kboard" role="group" aria-label="Kanban board" style={{ gridTemplateColumns: gridOf(columns, collapsed) }}>
      {columns.map((column) => {
        const cards = shown.filter((task) => columnOf(task, group) === column.key && inLane(task));
        return (
          <KanbanColumn key={column.key} column={column} group={group} lane={lane} count={cards.length}
            collapsed={collapsed.has(column.key)} onToggle={view.toggle} drop={view.drag.columnProps(column, lane?.key)}
            picker={view.pickerFor(column)} onAdded={props.reload}
            emptyNote={finishedHidden && group === "status" && column.key === "done" ? FINISHED_HIDDEN : undefined}>
            <ColumnCards view={view} column={column} cards={cards} lane={lane} />
          </KanbanColumn>
        );
      })}
    </div>
  );
}

// Due grouping: dropping a card on Later or This week asks which day; the column holds that picker.
function useDayPicker(group: KanbanGroup) {
  const [pending, setPending] = useState<Pending | null>(null);
  const pickerFor = (mover: KanbanMover) => (column: Column): DayPicker | undefined => {
    if (group !== "due" || (column.key !== "week" && column.key !== "later")) return undefined;
    const mine = pending?.key === column.key ? pending : null;
    return {
      open: mine !== null, title: mine ? `Reschedule “${mine.task.title}”` : `Move to ${column.label}`,
      onOpenChange: (open) => { if (!open) setPending(null); },
      onPick: (pick) => { if (mine) void mover.pickDay(mine.task, column.key, pick); setPending(null); },
    };
  };
  return { setPending, pickerFor };
}

// The board's columns, cards and moves (drag, or Move to…), worked out once for every row.
function useRowView(props: KanbanBoardProps): RowView {
  const { tasks, group, reload, reschedule } = props;
  const projects = useProjects();
  const bots = useLiveState().bots;
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(new Set());
  const ctx = useMemo(() => ({ tasks, projects, bots }), [tasks, projects, bots]);
  const columns = useMemo(() => columnsFor(group, ctx), [group, ctx]);
  const shown = useMemo(() => visibleTasks(tasks, group), [tasks, group]);
  const projectOf = useMemo(() => new Map(projects.map((project) => [project.id, project])), [projects]);
  const byId = useMemo(() => new Map(tasks.map((task) => [task.id, task])), [tasks]);
  const days = useDayPicker(group);
  const mover = useKanbanMove({ group, columns, reload, reschedule, onPickDay: (task, key) => days.setPending({ task, key }) });
  const drag = useKanbanDrag(useCallback((id: string, key: string, lane: string | undefined) => {
    const task = byId.get(id);
    if (task) void mover.apply(task, key, lane);
  }, [byId, mover]));
  const toggle = useCallback((key: string) => setCollapsed((now) =>
    new Set(now.has(key) ? [...now].filter((k) => k !== key) : [...now, key])), []);
  return { props, columns, shown, collapsed, toggle, drag, mover, pickerFor: days.pickerFor(mover), projectOf, bots, ctx };
}

// The Kanban (Board redesign G6). The server picks and sorts the cards (view=board); this cuts them into
// columns by the chosen grouping and moves a card by drag or by Move to…. Collapsed columns are only view
// state. With Split by project (Status only) there is one row per project.
export default function KanbanBoard(props: KanbanBoardProps) {
  const { group, split } = props;
  const view = useRowView(props);
  const lanes = useMemo(() => (split && group === "status" ? columnsFor("project", view.ctx) : []), [split, group, view.ctx]);
  return (
    <div className="kanban">
      {lanes.length === 0 ? <KanbanRow view={view} lane={undefined} /> : lanes.map((lane) => (
        <div key={lane.key} className="klane">
          <div className="klane__head">
            <span className="dot" style={{ background: lane.color ?? "var(--color-border-strong)" }} aria-hidden="true" />{lane.label}
            <span className="count">{view.shown.filter((task) => (task.project_id ?? NO_PROJECT_KEY) === lane.key).length}</span>
          </div>
          <KanbanRow view={view} lane={{ key: lane.key, name: lane.label }} />
        </div>
      ))}
      <p className="kanban__hint">
        {hintFor(group)}{group === "due" ? <> <span>Finished tasks from the past are hidden here.</span></> : null}
      </p>
    </div>
  );
}
