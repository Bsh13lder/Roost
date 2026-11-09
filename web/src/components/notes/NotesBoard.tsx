import { useCallback, useEffect, useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { NoteEditor } from "./NoteEditor";
import { NoteList } from "./NoteList";
import { MAX_NOTE_QUERY_LENGTH } from "./noteHelpers";
import { useLiveState } from "../../hooks/useLiveStore";
import * as notesApi from "../../api/notes";
import { describeError } from "../../api/client";
import type { NoteSummaryOut } from "../../api/types";

interface ToolbarProps {
  search: string;
  onSearch: (text: string) => void;
  onSubmit: () => void;
  onNew: () => void;
}

function NotesToolbar({ search, onSearch, onSubmit, onNew }: ToolbarProps) {
  return (
    <form role="search" className="notes-toolbar" onSubmit={(event) => { event.preventDefault(); onSubmit(); }}>
      <input type="search" aria-label="Search notes" placeholder="Search notes" value={search}
        maxLength={MAX_NOTE_QUERY_LENGTH} onChange={(event) => onSearch(event.target.value)} />
      <button type="submit" className="btn btn--quiet">Search</button>
      <button type="button" className="btn btn--primary" onClick={onNew}>New note</button>
    </form>
  );
}

interface ListAreaProps {
  notes: NoteSummaryOut[] | null;
  query: string;
  onOpen: (noteId: string) => void;
  onKeep: (noteId: string) => void;
}

function NotesListArea({ notes, query, onOpen, onKeep }: ListAreaProps) {
  if (notes === null) return <p className="board-loading">Loading&hellip;</p>;
  if (notes.length === 0) {
    return <p className="board-empty">{query ? `No note matches “${query}”.` : "No notes yet. Write one, or tell any bot “note: …”."}</p>;
  }
  return <NoteList notes={notes} onOpen={onOpen} onKeep={onKeep} />;
}

export interface NotesBoardProps {
  projectId?: string; // one project's notes (its page's Notes tab); a new note joins that project
  openId?: string | null; // a note to open now (the project page's "New note" line made it)
}

// The user's notes, shared by every bot (D1), or one project's. The list reloads on every
// notes_changed frame (a bot or another window changed a note). The project is asked for
// only when there is one, so the Board's own call stays listNotes(query).
export default function NotesBoard({ projectId, openId: requested = null }: NotesBoardProps) {
  const live = useLiveState();
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [notes, setNotes] = useState<NoteSummaryOut[] | null>(null);
  const [openId, setOpenId] = useState<string | null>(requested);
  useEffect(() => { if (requested) setOpenId(requested); }, [requested]);
  const [error, setError] = useState<string | null>(null);
  const fail = useCallback((err: unknown) => setError(describeError(err)), []);

  const load = useCallback(() => {
    const request = projectId ? notesApi.listNotes(query, { projectId }) : notesApi.listNotes(query);
    request.then((found) => { setNotes(found); setError(null); }).catch(fail);
  }, [query, fail, projectId]);
  useEffect(() => load(), [load, live.boardVersion.notes]);

  const create = useCallback((title?: string) => {
    const input = { title: title ?? "Untitled note", content: title ? `# ${title}\n\n` : "" };
    notesApi.createNote(projectId ? { ...input, project_id: projectId } : input)
      .then((note) => setOpenId(note.id)).catch(fail);
  }, [fail, projectId]);
  const keep = (noteId: string) => { notesApi.keepNote(noteId).then(load).catch(fail); };
  const close = useCallback(() => { setOpenId(null); load(); }, [load]);
  // An emptied search box (typed away, or its clear button) lists every note again.
  const typeSearch = (text: string) => {
    setSearch(text);
    if (!text.trim()) setQuery("");
  };

  return (
    <section className="notes-board" aria-label="Notes">
      {openId ? null : (
        <NotesToolbar search={search} onSearch={typeSearch} onSubmit={() => setQuery(search.trim())} onNew={() => create()} />
      )}
      {error ? <ErrorNotice message={error} onRetry={load} /> : null}
      {openId
        ? <NoteEditor key={openId} noteId={openId} onClose={close} onOpenNote={setOpenId} onCreateNote={create} />
        : <NotesListArea notes={notes} query={query} onOpen={setOpenId} onKeep={keep} />}
    </section>
  );
}
