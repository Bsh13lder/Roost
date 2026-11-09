import { useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { MoreIcon } from "../icons";
import * as projectsApi from "../../api/projects";
import { describeError } from "../../api/client";
import type { ProjectOut } from "../../api/types";
import { Menu, MenuItem, MenuSeparator } from "../../ui/Menu";
import { Button } from "../../ui/Button";

// H9: deleting keeps everything the project held; the copy says where it goes.
const DELETE_NOTE = "Its expenses move to General; its tasks, notes and documents stay, just unlinked.";

export interface ProjectActionsProps {
  project: ProjectOut & { pinned?: boolean };
  onChanged: () => void;
  onDeleted: () => void;
}

// The ⋯ menu of a project's header card (G13): Pin to Money, Archive, and Delete in danger. Delete only
// asks: the confirmation (with the unlinking copy) is DeleteConfirm, shown under the card's top row.
export function useProjectActions({ project, onChanged, onDeleted }: ProjectActionsProps) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const act = (request: () => Promise<unknown>, then: () => void) => {
    setBusy(true);
    setError(null);
    request().then(then).catch((err: unknown) => setError(describeError(err))).finally(() => setBusy(false));
  };
  return {
    confirming, busy, error, askDelete: () => setConfirming(true), cancelDelete: () => setConfirming(false),
    togglePin: () => act(() => projectsApi.pinProject(project.id, !project.pinned), onChanged),
    toggleArchive: () => act(
      () => projectsApi.updateProject(project.id, { status: project.status === "archived" ? "active" : "archived" }), onChanged,
    ),
    remove: () => act(() => projectsApi.deleteProject(project.id), onDeleted),
  };
}

export type ProjectActionState = ReturnType<typeof useProjectActions>;

export function ProjectMenu({ project, actions }: { project: ProjectOut & { pinned?: boolean }; actions: ProjectActionState }) {
  const archived = project.status === "archived";
  return (
    <Menu label={`More for ${project.name}`} trigger={<MoreIcon />}>
      <MenuItem onSelect={actions.togglePin} disabled={actions.busy}>{project.pinned ? "Unpin" : "Pin to Money"}</MenuItem>
      <MenuItem onSelect={actions.toggleArchive} disabled={actions.busy}>{archived ? "Unarchive" : "Archive"}</MenuItem>
      <MenuSeparator />
      <MenuItem danger onSelect={actions.askDelete}>Delete</MenuItem>
    </Menu>
  );
}

export function DeleteConfirm({ project, actions }: { project: ProjectOut; actions: ProjectActionState }) {
  return (
    <>
      {actions.confirming ? (
        <div className="project-actions__confirm" role="group" aria-label={`Delete ${project.name}?`}>
          <p>{DELETE_NOTE}</p>
          <Button variant="danger" size="sm" aria-label={`Delete ${project.name} for good`} disabled={actions.busy}
            onClick={actions.remove}>Delete</Button>
          <Button variant="ghost" size="sm" onClick={actions.cancelDelete}>Cancel</Button>
        </div>
      ) : null}
      {actions.error ? <ErrorNotice message={actions.error} /> : null}
    </>
  );
}
