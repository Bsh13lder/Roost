import { useCallback, useMemo, useState } from "react";
import { useReschedule, type Reschedule } from "./useReschedule";
import { describeError } from "../../api/client";
import * as tasksApi from "../../api/tasks";
import type { TaskRowOut } from "../../api/tasks";
import { useToast } from "../../ui/Toast";

export interface TaskActions extends Reschedule {
  completing: ReadonlySet<string>;
  complete: (task: TaskRowOut) => void;
  fail: (taskId: string) => void;
  keep: (taskId: string) => void;
}

const NONE: ReadonlySet<string> = new Set();

// What a row can do (G3): complete with an Undo toast, mark failed, keep, and reschedule (G2's popover logic).
// `reload` runs after every write; `onError` gets a plain sentence. Undo of a complete reopens the task and, when
// a repeat made the next one, deletes that copy (Task 10's contract).
export function useTaskActions(reload: () => void, onError: (message: string) => void): TaskActions {
  const toast = useToast();
  const reschedule = useReschedule(reload);
  const [completing, setCompleting] = useState<ReadonlySet<string>>(NONE);
  const fail = useCallback((err: unknown) => onError(describeError(err)), [onError]);

  const undoComplete = useCallback(async (taskId: string, nextId: string | null | undefined) => {
    try {
      await tasksApi.reopenTask(taskId);
      if (nextId) await tasksApi.deleteTask(nextId);
    } catch (err) {
      toast.show(describeError(err), { tone: "danger" });
    }
    reload();
  }, [reload, toast]);

  const complete = useCallback((task: TaskRowOut) => {
    setCompleting((ids) => new Set([...ids, task.id]));
    tasksApi.completeTask(task.id)
      .then((done) => {
        toast.show(`“${task.title}” done`, { action: { label: "Undo", run: () => void undoComplete(task.id, done.next_id) } });
        reload();
      })
      .catch(fail)
      .finally(() => setCompleting((ids) => new Set([...ids].filter((id) => id !== task.id))));
  }, [fail, reload, toast, undoComplete]);

  const markFailed = useCallback((taskId: string) => { tasksApi.failTask(taskId).then(reload).catch(fail); }, [fail, reload]);
  const keep = useCallback((taskId: string) => { tasksApi.keepTask(taskId).then(reload).catch(fail); }, [fail, reload]);
  return useMemo(() => ({ ...reschedule, completing, complete, fail: markFailed, keep }),
    [reschedule, completing, complete, markFailed, keep]);
}
