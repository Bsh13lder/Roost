import { useCallback, useEffect, useRef, useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { DocumentOpen } from "./DocumentOpen";
import { DocumentRow } from "./DocumentRow";
import { useLiveState } from "../../hooks/useLiveStore";
import * as documentsApi from "../../api/documents";
import { describeError } from "../../api/client";
import type { DocumentDetailOut, DocumentOut } from "../../api/types";

type NewKind = "doc" | "sheet";
const NEW_TITLE: Record<NewKind, string> = { doc: "Untitled doc", sheet: "Untitled sheet" };

function DocumentsToolbar({ onNew, onUpload }: { onNew: (kind: NewKind) => void; onUpload: (file: File) => void }) {
  const fileRef = useRef<HTMLInputElement>(null);
  return (
    <div className="documents-toolbar">
      <button type="button" className="btn btn--primary" onClick={() => onNew("doc")}>New doc</button>
      <button type="button" className="btn btn--quiet" onClick={() => onNew("sheet")}>New sheet</button>
      <button type="button" className="btn btn--quiet" onClick={() => fileRef.current?.click()}>Upload PDF</button>
      <input ref={fileRef} type="file" accept="application/pdf" hidden aria-label="PDF file" onChange={(event) => {
        const file = event.target.files?.[0];
        event.target.value = "";
        if (file) onUpload(file);
      }} />
    </div>
  );
}

interface ListAreaProps {
  documents: DocumentOut[] | null;
  onOpen: (id: string) => void;
  onKeep: (id: string) => void;
  onDelete: (id: string) => void;
}

function DocumentsListArea({ documents, onOpen, onKeep, onDelete }: ListAreaProps) {
  if (documents === null) return <p className="board-loading">Loading&hellip;</p>;
  if (documents.length === 0) {
    return <p className="board-empty">No documents yet. Make one here, or ask a bot to “save … in a document”.</p>;
  }
  return (
    <ul className="doc-list" aria-label="Your documents">
      {documents.map((document) => (
        <DocumentRow key={document.id} document={document} onOpen={onOpen} onKeep={onKeep} onDelete={onDelete} />
      ))}
    </ul>
  );
}

// In a project, a new doc or sheet is made in it; an uploaded PDF is put in it right after the upload.
function useDocumentActions(load: () => void, open: (id: string) => void, fail: (err: unknown) => void,
  projectId: string | undefined) {
  const link = (meta: DocumentOut) => (projectId ? documentsApi.setDocumentProject(meta.id, projectId) : Promise.resolve(meta));
  return {
    create: (kind: NewKind) => {
      const input = { kind, title: NEW_TITLE[kind] };
      documentsApi.createDocument(projectId ? { ...input, project_id: projectId } : input)
        .then((meta) => open(meta.id)).catch(fail);
    },
    upload: (file: File) => {
      documentsApi.uploadPdf(file).then(link).then((meta) => { load(); open(meta.id); }).catch(fail);
    },
    keep: (id: string) => { documentsApi.keepDocument(id).then(load).catch(fail); },
    remove: (id: string) => { documentsApi.deleteDocument(id).then(load).catch(fail); },
  };
}

export interface DocumentsBoardProps {
  projectId?: string; // one project's documents (its page's Docs tab); a new one joins that project
  openId?: string | null; // a document to open now (the project page's "New document" line made it)
}

// The user's documents, shared by every bot (D1), or one project's. The
// list reloads on every documents_changed frame.
export default function DocumentsBoard({ projectId, openId = null }: DocumentsBoardProps) {
  const live = useLiveState();
  const [documents, setDocuments] = useState<DocumentOut[] | null>(null);
  const [open, setOpen] = useState<DocumentDetailOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fail = useCallback((err: unknown) => setError(describeError(err)), []);
  const load = useCallback(() => {
    const request = projectId ? documentsApi.listDocuments(undefined, { projectId }) : documentsApi.listDocuments();
    request.then((found) => { setDocuments(found); setError(null); }).catch(fail);
  }, [fail, projectId]);
  useEffect(() => load(), [load, live.boardVersion.documents]);
  const openDocument = useCallback((id: string) => { documentsApi.getDocument(id).then(setOpen).catch(fail); }, [fail]);
  useEffect(() => { if (openId) openDocument(openId); }, [openId, openDocument]);
  const actions = useDocumentActions(load, openDocument, fail, projectId);

  if (open) return <DocumentOpen key={open.id} document={open} onBack={() => { setOpen(null); load(); }} />;
  return (
    <section className="documents-board" aria-label="Documents">
      <DocumentsToolbar onNew={actions.create} onUpload={actions.upload} />
      {error ? <ErrorNotice message={error} onRetry={load} /> : null}
      <DocumentsListArea documents={documents} onOpen={openDocument} onKeep={actions.keep} onDelete={actions.remove} />
    </section>
  );
}
