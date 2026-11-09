import { lazy, Suspense, useMemo, useRef, useState, type ReactNode } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { ProjectTasksEmpty, TasksEmpty } from "./BoardEmpty";
import { MoveToSheet } from "./MoveToSheet";
import { TaskGroups } from "./TaskGroups";
import { useTaskActions } from "./useTaskActions";
import { useRowEdits } from "./useRowEdits";
import { useBoardList, type BoardList } from "./useBoardList";
import { useTaskView, type TaskViewState } from "./useTaskView";
import { QuickAdd } from "../tasks/QuickAdd";
import { useOpenTask } from "../tasks/useOpenTask";
import { useProjects } from "../tasks/useProjects";
import { WorkspaceTasksHead } from "../workspace/WorkspaceTasksHead";
import { ALL_TASKS, scopeQuery, type TaskScope } from "./taskScope";
import { ShowFinishedSwitch } from "../ShowFinishedSwitch";
import { ShowToggles } from "./ShowToggles";
import type { TaskRowOut } from "../../api/tasks";
import type { ProjectOut, TaskMoneyOut } from "../../api/types";

// The drawer and everything only it uses are their own chunk (redesign P3): the Board's entry stays small.
const TaskDrawer = lazy(() => import("../tasks/TaskDrawer"));
// The Kanban (G6) is its own chunk too: the list's entry does not carry it.
const KanbanBoard = lazy(() => import("./kanban/KanbanBoard"));
// So is the Calendar (G11), with the grid the money calendar shares.
const TaskCalendar = lazy(() => import("./calendar/TaskCalendar"));

export interface TasksBoardProps {
  projectId?: string; // one project's tasks of every status (its page); a new task joins it
  leadBotId?: string | null; // that project's lead bot: its empty state names it
  currency?: string; // superseded: a row's money now comes with the row (G3)
  money?: Readonly<Record<string, TaskMoneyOut>>; // superseded, see above
  scope?: TaskScope; // the Workspace's project chip: every view narrowed to one project; none is All
  projects?: readonly ProjectOut[]; // the chips' projects, so the rows' pills need no second request
  onGone?: () => void; // the counts say the picked project is gone (404)
  filters?: ReactNode; // the Workspace's project chips (and the picked project's card), under the view tabs
}

type ProjectLookup = ReturnType<typeof useProjectLookup>;
type Actions = ReturnType<typeof useTaskActions>;

// Each task's project, by id: the Workspace shows its colour and name on the row; a project's page does not.
function useProjectLookup(projectId: string | undefined, given: readonly ProjectOut[] | undefined) {
  const fetched = useProjects(projectId === undefined && given === undefined);
  const projects = given ?? fetched;
  return useMemo(() => new Map(projects.map((project) => [project.id, { name: project.name, color: project.color }])), [projects]);
}

// The Workspace's head (view tabs, chips, layouts, sort, Show finished); a project's page has only the switch.
interface HeadProps extends Pick<TasksBoardProps, "projectId" | "onGone" | "filters"> {
  state: TaskViewState;
  list: BoardList;
  scope: TaskScope;
}

function BoardHead({ state, list, projectId, scope, onGone, filters }: HeadProps) {
  const done = list.allFinished ? null : <ShowFinishedSwitch hidden={list.hidden} />;
  const switcher = (
    <ShowToggles screen={list.screen} routines={state.layout === "calendar" && !projectId} done={done}
      botMadeHidden={list.botMadeHidden} />
  );
  if (projectId) return <div className="tasks-top tasks-top--project">{switcher}</div>;
  return (
    <WorkspaceTasksHead view={state.view} onView={list.toView} filters={filters} layout={state.layout} onLayout={state.setLayout}
      sort={state.sort} onSort={state.setSort}
      kanban={{ group: state.group, onGroup: state.setGroup, sort: state.ksort, onSort: state.setKsort,
        split: state.split, onSplit: state.setSplit }}
      onExpandAll={() => state.expandAll(list.flat.map((task) => task.id))} onCollapseAll={state.collapseAll}
      finished={switcher} countsFor={scopeQuery(scope)} onCountsGone={onGone} />
  );
}

interface BodyProps {
  state: TaskViewState;
  list: BoardList;
  actions: Actions;
  projects: ProjectLookup;
  onOpen: (taskId: string) => void;
  projectId?: string;
  leadBotId: string | null;
  scope: TaskScope;
  edits?: { onMove: (task: TaskRowOut) => void; onDelete: (task: TaskRowOut) => void }; // the Workspace's rows
}

const LOADING = <p className="board-loading">Loading&hellip;</p>;

// The tasks themselves: the list's groups, the Kanban or the Calendar, with loading, error and empty states.
function BoardBody({ state, list, actions, projects, onOpen, projectId, leadBotId, scope, edits }: BodyProps) {
  const { tasks, layout } = state;
  return (
    <>
      {state.error ? <ErrorNotice message={state.error} onRetry={state.load} /> : null}
      {tasks === null && !state.error && layout !== "calendar" ? LOADING : null}
      {tasks !== null && list.grouped && list.flat.length === 0 ? (
        projectId ? <ProjectTasksEmpty leadBotId={leadBotId} /> : <TasksEmpty />
      ) : null}
      {layout === "kanban" && list.shownTasks !== null ? (
        <Suspense fallback={LOADING}>
          <KanbanBoard tasks={list.shownTasks} finishedHidden={list.hidden > 0} group={state.group} split={state.split}
            stepsOpen={state.stepsOpen} onToggleSteps={state.toggleSteps} onSteps={state.setSteps} onOpen={onOpen}
            reload={state.load} reschedule={actions.one} />
        </Suspense>
      ) : null}
      {layout === "calendar" ? (
        <Suspense fallback={LOADING}><TaskCalendar projects={projects} onOpen={onOpen} scope={scope} /></Suspense>
      ) : null}
      <TaskGroups groups={list.groups} cursor={list.cursor} showProject={projectId === undefined} projects={projects}
        stepsOpen={state.stepsOpen} canRescheduleAll={!state.q} onRescheduleAll={(pick) => void actions.overdue(pick)}
        row={{ onToggleSteps: state.toggleSteps, onComplete: actions.complete, onOpen, onFail: actions.fail,
          onKeep: actions.keep, onReschedule: (task, pick) => void actions.one(task, pick), onSteps: state.setSteps, ...edits }} />
    </>
  );
}

function Shortcuts({ hidden, views }: { hidden: boolean; views: boolean }) {
  return (
    <div className="shortcuts" aria-hidden="true" hidden={hidden}>
      <span><kbd>j</kbd> <kbd>k</kbd> move</span><span><kbd>x</kbd> done</span><span><kbd>t</kbd> tomorrow</span>
      <span><kbd>Enter</kbd> open</span><span><kbd>/</kbd> search</span><span><kbd>q</kbd> add</span>
      {views ? <span><kbd>1</kbd>–<kbd>5</kbd> views</span> : null}
    </div>
  );
}

// The user's tasks, shared by every bot (D1): the Workspace's views over groups of one-line rows (its pill searches
// and adds), or one project's tasks grouped Overdue / Next up / Later / Done with a quick-add line. It reloads when
// a task changes anywhere.
export function TasksBoard({ projectId, leadBotId = null, scope = ALL_TASKS, projects: given, onGone, filters }: TasksBoardProps) {
  const state = useTaskView(projectId, scope);
  const projects = useProjectLookup(projectId, given);
  const { openId, open, close } = useOpenTask();
  const actions = useTaskActions(state.load, state.setError);
  const rowEdits = useRowEdits(state.load);
  const [moving, setMoving] = useState<TaskRowOut | null>(null);
  const boardRef = useRef<HTMLElement>(null);
  const list = useBoardList({ state, projectId, actions, onOpen: open, boardRef });
  const edits = projectId ? undefined : { onMove: setMoving, onDelete: rowEdits.remove };
  return (
    <section className="tasks-board" aria-label="Tasks" ref={boardRef}>
      <BoardHead state={state} list={list} projectId={projectId} scope={scope} onGone={onGone} filters={filters} />
      {projectId ? <QuickAdd projectId={projectId} onAdded={() => state.load()} /> : null}
      <BoardBody state={state} list={list} actions={actions} projects={projects} onOpen={open} projectId={projectId}
        leadBotId={leadBotId} scope={scope} edits={edits} />
      <Shortcuts hidden={!list.grouped} views={!projectId} />
      {edits ? <MoveToSheet task={moving} projects={given ?? []} onPick={rowEdits.move} onClose={() => setMoving(null)} /> : null}
      {openId ? <Suspense fallback={null}><TaskDrawer taskId={openId} onClose={close} /></Suspense> : null}
    </section>
  );
}
