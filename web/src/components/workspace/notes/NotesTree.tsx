import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { buildFolders } from "./treeFolders";
import { TreeFolderRow } from "./TreeFolderRow";
import { useNotesTree } from "./useNotesTree";
import { SEARCH_PARAM } from "../sections";
import { DocumentOpen } from "../../documents/DocumentOpen";
import { ErrorNotice } from "../../ErrorNotice";
import { NoteEditor } from "../../notes/NoteEditor";
import { useProjects } from "../../tasks/useProjects";
import { describeError } from "../../../api/client";
import { getDocument } from "../../../api/documents";
import { createNote } from "../../../api/notes";
import type { DocumentDetailOut } from "../../../api/types";
import { DOCUMENT_PARAM, NOTE_PARAM } from "../../../pages/boardPaths";
import { Button } from "../../../ui/Button";

export interface NotesTreeProps {
  openNote?: string | null; // ?note=: open in the note editor
  openDocument?: string | null; // ?document=: open in its editor
}

// The open item lives in the address (?note=, ?document=), so a reload or an old Board link opens the same one.
function useOpenItem() {
  const [params, setParams] = useSearchParams();
  const set = useCallback((key: string | null, id: string | null) => setParams((current) => {
    const next = new URLSearchParams(current);
    next.delete(NOTE_PARAM);
    next.delete(DOCUMENT_PARAM);
    if (key && id) next.set(key, id);
    return next;
  }), [setParams]);
  return {
    query: params.get(SEARCH_PARAM) ?? "",
    openNote: (id: string) => set(NOTE_PARAM, id),
    openDocument: (id: string) => set(DOCUMENT_PARAM, id),
    close: () => set(null, null),
  };
}

function OpenDocument({ id, onBack }: { id: string; onBack: () => void }) {
  const [document, setDocument] = useState<DocumentDetailOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let current = true;
    getDocument(id).then((found) => { if (current) setDocument(found); })
      .catch((err: unknown) => { if (current) setError(describeError(err)); });
    return () => { current = false; };
  }, [id]);
  if (error) return <ErrorNotice message={error} />;
  return document ? <DocumentOpen key={document.id} document={document} onBack={onBack} /> : <p className="board-loading">Loading&hellip;</p>;
}

// The Workspace's Notes (app restructure, R2), a lazy chunk: one tree of notes and documents, a folder per project
// (and No project) with its count, filtered by the pill's words. A note opens in the note editor, a document in its
// own; New note makes one and opens it.
export default function NotesTree({ openNote = null, openDocument = null }: NotesTreeProps) {
  const data = useNotesTree();
  const projects = useProjects();
  const item = useOpenItem();
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());
  const [problem, setProblem] = useState<string | null>(null);
  const folders = useMemo(() => buildFolders(data.notes ?? [], data.documents, projects, item.query),
    [data.notes, data.documents, projects, item.query]);
  const toggle = (id: string) => setExpanded((open) => new Set(open.has(id) ? [...open].filter((one) => one !== id) : [...open, id]));
  const create = (title?: string) => {
    createNote({ title: title ?? "Untitled note", content: title ? `# ${title}\n\n` : "" })
      .then((made) => item.openNote(made.id)).catch((err: unknown) => setProblem(describeError(err)));
  };
  if (openNote) {
    return <NoteEditor key={openNote} noteId={openNote} onClose={item.close} onOpenNote={item.openNote} onCreateNote={create} />;
  }
  if (openDocument) return <OpenDocument id={openDocument} onBack={item.close} />;
  return (
    <section className="ntree" aria-labelledby="ntree-title">
      <div className="ntree__head">
        <h2 id="ntree-title" className="ntree__title">Notes</h2>
        <Button size="sm" variant="primary" onClick={() => create()}>New note</Button>
      </div>
      {data.error ? <ErrorNotice message={data.error} onRetry={data.reload} /> : null}
      {problem ? <ErrorNotice message={problem} /> : null}
      {data.notes === null && !data.error ? <p className="board-loading">Loading&hellip;</p> : null}
      {data.notes !== null && folders.length === 0 ? (
        <p className="board-empty">{item.query ? `Nothing matches “${item.query}”.` : "No notes yet. Write one, or tell any bot “note: …”."}</p>
      ) : null}
      <ul className="ntree__list">
        {folders.map((folder) => (
          <TreeFolderRow key={folder.id} folder={folder} open={item.query !== "" || expanded.has(folder.id)}
            onToggle={() => toggle(folder.id)} onOpenNote={item.openNote} onOpenDocument={item.openDocument} />
        ))}
      </ul>
    </section>
  );
}
