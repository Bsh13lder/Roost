import { apiRequest, apiUpload } from "./client";
import { withConflict } from "./conflict";
import type { DocumentDetailOut, DocumentKind, DocumentOut } from "./types";

// The user's documents (M2 D2/D4): the same records every docs-role bot works on.

const MAX_DOCUMENT_TITLE_LENGTH = 120; // roost/constants.py

export interface DocumentSaveIn {
  base_revision: number;
  payload?: Record<string, unknown>;
  title?: string;
}

export interface DocumentCreateIn {
  kind: "doc" | "sheet";
  title: string;
  project_id?: string; // the project it belongs to (a project page's Docs tab)
}

export interface DocumentListFilter {
  projectId?: string; // only that project's documents
}

const path = (documentId: string) => `/api/documents/${encodeURIComponent(documentId)}`;

export function listDocuments(kind?: DocumentKind, filter: DocumentListFilter = {}): Promise<DocumentOut[]> {
  const params = [
    kind ? `kind=${kind}` : "",
    filter.projectId ? `project_id=${encodeURIComponent(filter.projectId)}` : "",
  ].filter((part) => part !== "");
  return apiRequest<DocumentOut[]>("GET", params.length > 0 ? `/api/documents?${params.join("&")}` : "/api/documents");
}

export function getDocument(documentId: string): Promise<DocumentDetailOut> {
  return apiRequest<DocumentDetailOut>("GET", path(documentId));
}

export function createDocument(input: DocumentCreateIn): Promise<DocumentOut> {
  return apiRequest<DocumentOut>("POST", "/api/documents", input);
}

// A stale base_revision throws RevisionConflictError<DocumentDetailOut> carrying the stored copy.
export function saveDocument(documentId: string, input: DocumentSaveIn): Promise<DocumentOut> {
  return withConflict<DocumentOut, DocumentDetailOut>(apiRequest<DocumentOut>("PUT", path(documentId), input));
}

// An uploaded PDF is outside content: it arrives marked "from web content" until Kept.
export function uploadPdf(file: File): Promise<DocumentOut> {
  const title = (file.name.replace(/\.pdf$/i, "").trim() || "Untitled PDF").slice(0, MAX_DOCUMENT_TITLE_LENGTH);
  return apiUpload<DocumentOut>(`/api/documents/pdf?title=${encodeURIComponent(title)}`, file, "application/pdf");
}

// Put a document in a project, or with null take it out. The revision stays, so an open editor
// is not disturbed (H12).
export function setDocumentProject(documentId: string, projectId: string | null): Promise<DocumentOut> {
  return apiRequest<DocumentOut>("PUT", `${path(documentId)}/project`, { project_id: projectId });
}

export function pdfUrl(documentId: string): string {
  return `${path(documentId)}/pdf`;
}

// Keep: the user vouches for a web-made or uploaded document (only here — no bot can).
export function keepDocument(documentId: string): Promise<DocumentOut> {
  return apiRequest<DocumentOut>("POST", `${path(documentId)}/keep`);
}

export function deleteDocument(documentId: string): Promise<void> {
  return apiRequest<void>("DELETE", path(documentId));
}
