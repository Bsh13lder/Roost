import { apiRequest } from "./client";
import { withConflict } from "./conflict";
import type { NoteOut, NoteSummaryOut } from "./types";

// The user's notes (M2 D1/D4): the same records every notes-role bot works on.

export interface NoteIn {
  title?: string | null;
  content: string;
  tags?: string[];
  project_id?: string; // the project it belongs to (a project page's Notes tab)
}

export interface NoteSaveIn {
  base_revision: number;
  title?: string;
  content?: string;
  tags?: string[];
  pinned?: boolean;
}

export interface NoteListFilter {
  projectId?: string; // only that project's notes
}

const path = (noteId: string) => `/api/notes/${encodeURIComponent(noteId)}`;

export function listNotes(query = "", filter: NoteListFilter = {}): Promise<NoteSummaryOut[]> {
  const q = query.trim();
  const params = [
    q ? `q=${encodeURIComponent(q)}` : "",
    filter.projectId ? `project_id=${encodeURIComponent(filter.projectId)}` : "",
  ].filter((part) => part !== "");
  return apiRequest<NoteSummaryOut[]>("GET", params.length > 0 ? `/api/notes?${params.join("&")}` : "/api/notes");
}

export function getNote(noteId: string): Promise<NoteOut> {
  return apiRequest<NoteOut>("GET", path(noteId));
}

export function createNote(input: NoteIn): Promise<NoteOut> {
  return apiRequest<NoteOut>("POST", "/api/notes", input);
}

// A stale base_revision throws RevisionConflictError<NoteOut> carrying the stored note.
export function saveNote(noteId: string, input: NoteSaveIn): Promise<NoteOut> {
  return withConflict<NoteOut, NoteOut>(apiRequest<NoteOut>("PUT", path(noteId), input));
}

// Keep: the user vouches for a note marked "from web content" (only here — no bot can).
export function keepNote(noteId: string): Promise<NoteOut> {
  return apiRequest<NoteOut>("POST", `${path(noteId)}/keep`);
}

export function deleteNote(noteId: string): Promise<void> {
  return apiRequest<void>("DELETE", path(noteId));
}
