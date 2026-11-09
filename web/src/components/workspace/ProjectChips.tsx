import { railGroups } from "../board/rail/railGroups";
import type { TaskScope } from "../board/taskScope";
import { MoreIcon } from "../icons";
import { ALL_MONEY_HREF } from "./sections";
import type { ProjectOut } from "../../api/types";
import { Chip } from "../../ui/Chip";
import { Menu, MenuItem, MenuLink, MenuSeparator } from "../../ui/Menu";

export interface ProjectChipsProps {
  projects: readonly ProjectOut[];
  scope: TaskScope;
  onScope: (scope: TaskScope) => void;
  onNew: () => void; // New project
}

const isPicked = (scope: TaskScope, id: string) => scope.kind === "project" && scope.id === id;

// The projects a chip is shown for: the live ones, pinned first, and an archived one only while it is picked.
export function chipProjects(projects: readonly ProjectOut[], scope: TaskScope): readonly ProjectOut[] {
  const groups = railGroups(projects);
  return [...groups.pinned, ...groups.active, ...groups.archived.filter((project) => isPicked(scope, project.id))];
}

// The Workspace's filter chips (app restructure): All · each project (pinned first) · No project, and a menu with
// All money (the old Money page, nothing lost) and New project.
export function ProjectChips({ projects, scope, onScope, onNew }: ProjectChipsProps) {
  return (
    <div className="ws-chips">
      <div className="ws-chips__row" role="group" aria-label="Filter by project">
        <Chip size="sm" selected={scope.kind === "all"} onClick={() => onScope({ kind: "all" })}>All</Chip>
        {chipProjects(projects, scope).map((project) => (
          <Chip key={project.id} size="sm" selected={isPicked(scope, project.id)}
            onClick={() => onScope({ kind: "project", id: project.id })}>
            <span className="project-dot" style={{ background: project.color }} aria-hidden="true" />{project.name}
          </Chip>
        ))}
        <Chip size="sm" selected={scope.kind === "inbox"} onClick={() => onScope({ kind: "inbox" })}>No project</Chip>
      </div>
      <Menu label="Projects and money" trigger={<MoreIcon />}>
        <MenuLink to={ALL_MONEY_HREF}>All money</MenuLink>
        <MenuSeparator />
        <MenuItem onSelect={onNew}>New project</MenuItem>
      </Menu>
    </div>
  );
}
