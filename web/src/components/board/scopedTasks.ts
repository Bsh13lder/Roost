// web/src/components/board/scopedTasks.ts: the Tasks area's requests, narrowed to the rail's selection (lead tasks
// 15 and 20). The server filters: project_id=<id> for a project, project_id=none for the Inbox, so every cap (the
// Done view's newest 100) holds within the selection, and the rows are shown as they come.
import { listTasks, type TaskListFilter, type TaskRowOut } from "../../api/tasks";
import { scopeQuery, type TaskScope } from "./taskScope";

/** Any listing (a view, or the Calendar's span), narrowed to the selection. */
export function askTasks(scope: TaskScope, filter: TaskListFilter): Promise<TaskRowOut[]> {
  const within = scopeQuery(scope);
  return listTasks({ ...filter, ...(within ? { projectId: within } : {}) });
}
