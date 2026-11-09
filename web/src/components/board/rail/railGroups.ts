import type { ProjectOut } from "../../../api/types";

export interface RailGroups {
  pinned: readonly ProjectOut[]; // active and pinned (the pin the Money tab sets)
  active: readonly ProjectOut[]; // the other active ones
  archived: readonly ProjectOut[];
}

// The rail's projects, in the server's order within each group.
export function railGroups(projects: readonly ProjectOut[]): RailGroups {
  const live = projects.filter((project) => project.status !== "archived");
  return {
    pinned: live.filter((project) => project.pinned === true),
    active: live.filter((project) => project.pinned !== true),
    archived: projects.filter((project) => project.status === "archived"),
  };
}
