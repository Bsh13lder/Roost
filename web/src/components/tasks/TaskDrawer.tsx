import { useCallback, useEffect, useRef, useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { CommentThread } from "./CommentThread";
import { StepList } from "./StepList";
import { TaskActivity } from "./TaskActivity";
import { DrawerHead } from "./DrawerHead";
import { TaskMoneyPanel } from "./TaskMoneyPanel";
import { TaskProps } from "./TaskProps";
import { useProjects } from "./useProjects";
import { useTaskDraft } from "./useTaskDraft";
import { useTitleSave } from "./autosave";
import { useTaskActions } from "../board/useTaskActions";
import { useLiveState } from "../../hooks/useLiveStore";
import { useMediaQuery } from "../../hooks/useMediaQuery";
import { PHONE_MEDIA } from "../board/constants";
import * as tasksApi from "../../api/tasks";
import { ApiError, describeError } from "../../api/client";
import type { TaskDetailOut } from "../../api/types";
import { Button } from "../../ui/Button";
import { Sheet } from "../../ui/Sheet";

export interface TaskDrawerProps {
  taskId: string;
  onClose: () => void;
}

const OPEN: ReadonlySet<TaskDetailOut["status"]> = new Set(["todo", "in_progress"]);
const GONE_TEXT = "This task is gone. It may have been deleted somewhere else.";

// The task, reloaded whenever a task or money frame arrives (a bot ticked a step, an expense was filed).
// A 404 means it was deleted (or never was the user's): the drawer says so instead of an error.
function useTaskDetail(taskId: string) {
  const { tasks, money } = useLiveState().boardVersion;
  const [task, setTask] = useState<TaskDetailOut | null>(null);
  const [gone, setGone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef(0);
  const reload = useCallback(() => {
    const ticket = ++latest.current;
    tasksApi.getTask(taskId)
      .then((found) => { if (ticket === latest.current) { setTask(found); setGone(false); setError(null); } })
      .catch((err: unknown) => {
        if (ticket !== latest.current) return;
        if (err instanceof ApiError && err.status === 404) { setTask(null); setGone(true); return; }
        setError(describeError(err));
      });
  }, [taskId]);
  useEffect(() => reload(), [reload, tasks, money]);
  return { task, gone, error, reload };
}

// The foot: Mark failed (quiet) and Delete task at the far right (danger, with a second step). There is no
// Save: every edit saves on its own (lead task 01).
function DrawerActions({ task, onChanged, onDeleted }: { task: TaskDetailOut; onChanged: () => void; onDeleted: () => void }) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const act = (request: () => Promise<unknown>, then: () => void) => {
    setBusy(true);
    setError(null);
    request().then(then).catch((err: unknown) => setError(describeError(err))).finally(() => setBusy(false));
  };
  return (
    <div className="task-drawer__actions">
      {OPEN.has(task.status) ? (
        <Button variant="ghost" size="sm" disabled={busy} onClick={() => act(() => tasksApi.failTask(task.id), onChanged)}>
          Mark failed
        </Button>
      ) : null}
      {confirming ? (
        <div className="task-drawer__confirm" role="group" aria-label={`Delete ${task.title}?`}>
          <p>Its steps and comments go with it.</p>
          <Button variant="danger" size="sm" aria-label={`Delete ${task.title} for good`} disabled={busy}
            onClick={() => act(() => tasksApi.deleteTask(task.id), onDeleted)}>Delete for good</Button>
          <Button variant="ghost" size="sm" onClick={() => setConfirming(false)}>Cancel</Button>
        </div>
      ) : (
        <Button variant="danger" size="sm" className="task-drawer__delete" onClick={() => setConfirming(true)}>Delete task</Button>
      )}
      {error ? <ErrorNotice message={error} /> : null}
    </div>
  );
}

// The loaded task: hooks that need it (the properties, the title, the row actions), and the whole drawer.
// Closing it (Close, Escape, a click outside) first saves a property still being typed; the title saves as it
// loses focus, and both save when the drawer goes away by any other road.
function LoadedDrawer({ task, reload, onClose }: { task: TaskDetailOut; reload: () => void; onClose: () => void }) {
  const projects = useProjects();
  const [problem, setProblem] = useState<string | null>(null);
  const draft = useTaskDraft(task, reload);
  const saveTitle = useTitleSave(task, reload);
  const actions = useTaskActions(reload, setProblem);
  const phone = useMediaQuery(PHONE_MEDIA);
  const project = projects.find((found) => found.id === task.project_id);
  return (
    <Sheet open title={task.title} size={phone ? "full" : "default"} onOpenChange={(open) => { if (!open) { void draft.commit(); onClose(); } }}
      footer={<DrawerActions task={task} onChanged={reload} onDeleted={onClose} />}>
      <div className="task-drawer">
        <DrawerHead task={task} project={project} completing={actions.completing.has(task.id)}
          onComplete={() => actions.complete({ ...task, money: null, due_bucket: "later" })}
          onTitle={saveTitle} onTitleLeave={(title) => tasksApi.updateTaskOnLeave(task.id, { title })} onKeep={() => actions.keep(task.id)} />
        {problem ? <ErrorNotice message={problem} /> : null}
        <TaskProps task={task} projects={projects} draft={draft} onDue={(pick) => void actions.one(task, pick)} />
        <StepList task={task} spent={task.money?.steps} currency={task.money?.currency}
          money={task.money?.steps_money} onChanged={reload} />
        <TaskMoneyPanel task={task} onChanged={reload} />
        <CommentThread task={task} />
        <TaskActivity task={task} onChanged={reload} />
      </div>
    </Sheet>
  );
}

// One task, everything about it, in a Sheet from the right (G5): the title in the head, the crumbs, its
// properties as a list, then Steps, Money, Comments and Activity. Its own lazy chunk (TasksBoard imports it
// through React.lazy only).
export default function TaskDrawer({ taskId, onClose }: TaskDrawerProps) {
  const { task, gone, error, reload } = useTaskDetail(taskId);
  const phone = useMediaQuery(PHONE_MEDIA);
  if (task) return <LoadedDrawer task={task} reload={reload} onClose={onClose} />;
  return (
    <Sheet open title={gone ? "Task not found" : "Loading…"} size={phone ? "full" : "default"} onOpenChange={(open) => { if (!open) onClose(); }}>
      {error ? <ErrorNotice message={error} onRetry={reload} /> : null}
      {gone ? <p className="task-drawer__gone">{GONE_TEXT}</p> : null}
    </Sheet>
  );
}
