// SPDX-License-Identifier: MIT
// Adapted from LazyClaw web/src/pages/Documents.tsx lines 1-9 @ 21e1002 (one lazy chunk per kind), for Roost
import { lazy, Suspense } from "react";
import { pdfUrl } from "../../api/documents";
import type { DocumentDetailOut } from "../../api/types";

// Each kind is its own lazy chunk: opening a sheet doesn't pull in pdf.js, and
// opening a PDF doesn't pull in the Univer engine (D4).
const DocEditor = lazy(() => import("./univer/DocEditor"));
const SheetEditor = lazy(() => import("./univer/SheetEditor"));
const PdfViewer = lazy(() => import("./PdfViewer"));

export interface DocumentOpenProps {
  document: DocumentDetailOut;
  onBack: () => void;
}

function Editor({ document }: { document: DocumentDetailOut }) {
  if (document.kind === "doc") return <DocEditor document={document} />;
  if (document.kind === "sheet") return <SheetEditor document={document} />;
  return <PdfViewer url={pdfUrl(document.id)} title={document.title} />;
}

export function DocumentOpen({ document, onBack }: DocumentOpenProps) {
  return (
    <section className="doc-open" aria-label={document.title}>
      <div className="doc-open__bar">
        <button type="button" className="btn btn--quiet btn--small" onClick={onBack}>← Documents</button>
        <h3 className="doc-open__title">{document.title}</h3>
      </div>
      <Suspense fallback={<p className="board-loading">Opening&hellip;</p>}>
        <Editor document={document} />
      </Suspense>
    </section>
  );
}
