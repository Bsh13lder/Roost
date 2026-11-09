// web/src/components/workspace/notes/treeFolders.ts: the Workspace's Notes tree (app restructure, R2): one folder per
// project that holds a note or a document, then No project; each folder lists its notes and documents by title.
import type { DocumentKind, DocumentOut, NoteSummaryOut, ProjectOut } from "../../../api/types";

export type TreeKind = "note" | DocumentKind;

export interface TreeItem {
  kind: TreeKind;
  id: string;
  title: string;
}

export interface TreeFolder {
  id: string; // a project's id, or NO_PROJECT_FOLDER
  name: string;
  color?: string;
  items: readonly TreeItem[];
}

export const NO_PROJECT_FOLDER = "none";
export const NO_PROJECT_NAME = "No project";

const byTitle = (a: TreeItem, b: TreeItem) => a.title.localeCompare(b.title, undefined, { sensitivity: "base" });
const matches = (title: string, query: string) => title.toLocaleLowerCase().includes(query.toLocaleLowerCase());

function itemsOf(notes: readonly NoteSummaryOut[], documents: readonly DocumentOut[]) {
  return [
    ...notes.map((note) => ({ item: { kind: "note" as const, id: note.id, title: note.title }, projectId: note.project_id })),
    ...documents.map((doc) => ({ item: { kind: doc.kind, id: doc.id, title: doc.title }, projectId: doc.project_id })),
  ];
}

/** The folders to draw: the projects (in the list's order) that hold an item matching `query`, then No project. */
export function buildFolders(notes: readonly NoteSummaryOut[], documents: readonly DocumentOut[],
  projects: readonly ProjectOut[], query = ""): TreeFolder[] {
  const wanted = query.trim();
  const all = itemsOf(notes, documents).filter(({ item }) => !wanted || matches(item.title, wanted));
  const known = new Set(projects.map((project) => project.id));
  const inFolder = (id: string | null) => all.filter(({ projectId }) =>
    (id === null ? projectId === null || !known.has(projectId) : projectId === id)).map(({ item }) => item).sort(byTitle);
  const folders: TreeFolder[] = [
    ...projects.map((project) => ({ id: project.id, name: project.name, color: project.color, items: inFolder(project.id) })),
    { id: NO_PROJECT_FOLDER, name: NO_PROJECT_NAME, items: inFolder(null) },
  ];
  return folders.filter((folder) => folder.items.length > 0);
}

/** "1 file", "3 files". */
export const filesText = (count: number): string => `${count} file${count === 1 ? "" : "s"}`;
