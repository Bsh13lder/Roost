import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { INBOX_VIEW } from "./constants";
import { ProjectPeek } from "./rail/ProjectPeek";
import { TasksBoard } from "./TasksBoard";
import { useTaskScope } from "./useTaskScope";
import { scopeProjectId } from "./taskScope";
import { ProjectEditForm } from "../projects/ProjectEditForm";
import { useProjectList } from "../tasks/useProjects";
import { QuickAddProject } from "../tasks/quickAddProject";
import { ProjectChips } from "../workspace/ProjectChips";
import type { ProjectOut } from "../../api/types";
import { Sheet } from "../../ui/Sheet";

// The Workspace's Tasks (app restructure): Today · Inbox · Upcoming, then the project chips (All · a project ·
// No project; the Inbox tab has none, it is every task with no project) with the picked project's card, then the
// rows; a Kanban column's quick add joins the picked project. A new project opens in a sheet and, once made, is
// the chip picked. The pill above adds and searches.
export function TasksArea() {
  const [scope, setScope] = useTaskScope();
  const [params] = useSearchParams();
  const list = useProjectList(true, true);
  const { projects, reload } = list;
  const [creating, setCreating] = useState(false);
  const [goneId, setGoneId] = useState<string | null>(null); // a project the counts answered 404 for
  const pickedId = scope.kind === "project" ? scope.id : null;
  const made = (project?: ProjectOut) => {
    setCreating(false);
    if (!project) return;
    reload();
    setScope({ kind: "project", id: project.id });
  };
  const inbox = params.get("view") === INBOX_VIEW && params.get("layout") !== "kanban";
  const filters = inbox ? null : (
    <>
      <ProjectChips projects={projects} scope={scope} onScope={setScope} onNew={() => setCreating(true)} />
      {scope.kind === "project" ? (
        <ProjectPeek projectId={scope.id} list={list} onAll={() => setScope({ kind: "all" })} gone={goneId === scope.id} />
      ) : null}
    </>
  );
  return (
    <div className="tasks-area">
      <div className="tasks-area__main">
        <QuickAddProject.Provider value={scopeProjectId(scope)}>
          <TasksBoard scope={scope} projects={projects} onGone={() => setGoneId(pickedId)} filters={filters} />
        </QuickAddProject.Provider>
      </div>
      <Sheet open={creating} onOpenChange={setCreating} title="New project">
        {creating ? <ProjectEditForm onDone={made} /> : null}
      </Sheet>
    </div>
  );
}
