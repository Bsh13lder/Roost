import { useCallback, useMemo } from "react";
import { describeError } from "../../api/client";
import * as tasksApi from "../../api/tasks";
import type { TaskRowOut } from "../../api/tasks";
import { useToast } from "../../ui/Toast";

export interface RowEdits {
  move: (task: TaskRowOut, projectId: string | null, name: string) => void; // name: where it went, for the toast
  remove: (task: TaskRowOut) => void;
}

// A Workspace row's ⋯ menu (app restructure): Move to another project, and Delete; each says what it did with an
// Undo (the old project back; the server's restore, Delete's exact Undo). `reload` runs after every write.
export function useRowEdits(reload: () => void): RowEdits {
  const toast = useToast();
  const fail = useCallback((err: unknown) => toast.show(describeError(err), { tone: "danger" }), [toast]);
  const move = useCallback((task: TaskRowOut, projectId: string | null, name: string) => {
    const before = task.project_id;
    if (before === projectId) return;
    tasksApi.updateTask(task.id, { project_id: projectId })
      .then(() => {
        reload();
        toast.show(`Moved to ${name}`, {
          action: { label: "Undo", run: () => { tasksApi.updateTask(task.id, { project_id: before }).then(reload).catch(fail); } },
        });
      })
      .catch(fail);
  }, [fail, reload, toast]);
  const remove = useCallback((task: TaskRowOut) => {
    tasksApi.deleteTask(task.id)
      .then(() => {
        reload();
        toast.show(`Deleted “${task.title}”`, {
          action: { label: "Undo", run: () => { tasksApi.restoreTask(task.id).then(reload).catch(fail); } },
        });
      })
      .catch(fail);
  }, [fail, reload, toast]);
  return useMemo(() => ({ move, remove }), [move, remove]);
}
