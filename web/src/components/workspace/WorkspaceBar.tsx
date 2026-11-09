import { FindAddPill } from "./FindAddPill";
import { WORKSPACE_SECTIONS, type WorkspaceSection } from "./sections";
import { Segmented } from "../../ui/Segmented";

export interface WorkspaceBarProps {
  section: WorkspaceSection;
  onSection: (section: WorkspaceSection) => void;
  projectId?: string; // the project chip picked: where the pill's new task goes
}

// The Workspace's bar: Tasks · Notes · Calendar and the "Add or find anything…" pill. On a desktop it sits at the
// top; on a phone width it is the bottom bar (workspace.css).
export function WorkspaceBar({ section, onSection, projectId }: WorkspaceBarProps) {
  return (
    <div className="workspace-bar">
      <FindAddPill projectId={projectId} />
      <Segmented label="Workspace sections" options={WORKSPACE_SECTIONS} value={section} onChange={onSection} />
    </div>
  );
}
