// web/src/components/workspace/sections.ts: the Workspace's places (app restructure, R2). The Board became the
// Workspace: Tasks · Notes · Calendar. Money is no longer a section; its old address (?tab=money) opens All money,
// reached from the project chips' menu. Every old Board link still lands on the right thing.

export type WorkspaceSection = "tasks" | "notes" | "calendar";
export type WorkspacePlace = WorkspaceSection | "money";

export const WORKSPACE_SECTIONS: ReadonlyArray<{ id: WorkspaceSection; label: string }> = [
  { id: "tasks", label: "Tasks" }, { id: "notes", label: "Notes" }, { id: "calendar", label: "Calendar" },
];

export const SECTION_PARAM = "tab";
export const SEARCH_PARAM = "q"; // the pill's words: the tasks' search and the notes' filter
export const OLD_PROJECTS_TAB = "projects"; // ?tab=projects, from before: All tasks
export const WORKSPACE_HREF = "/board?tab=tasks";
export const ALL_MONEY_HREF = "/board?tab=money";

const OLD_TABS: Readonly<Record<string, WorkspacePlace>> = {
  tasks: "tasks", notes: "notes", documents: "notes", calendar: "calendar", money: "money",
};

/** The place an address opens: an old tab maps to its new home, the old Tasks calendar layout to Calendar. */
export function sectionOf(params: URLSearchParams): WorkspacePlace {
  const place = OLD_TABS[params.get(SECTION_PARAM) ?? ""] ?? "tasks";
  return place === "tasks" && params.get("layout") === "calendar" ? "calendar" : place;
}
