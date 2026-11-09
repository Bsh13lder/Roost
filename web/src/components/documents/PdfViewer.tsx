// SPDX-License-Identifier: MIT
// Harvested from LazyClaw web/src/pages/Pdf.tsx lines 16-18, 21-27 @ 21e1002 (react-pdf + its pdf.js worker), adapted for Roost
import { useCallback, useEffect, useRef, useState, type RefObject } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

// pdf.js worker (react-pdf 10 + pdfjs-dist 5): resolved as a module URL so
// Vite emits it as an asset of this lazy chunk.
pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();

const PAGE_WIDTH_PX = 760;

export interface PdfViewerProps {
  url: string;
  title: string;
}

// The page is as wide as the viewer, up to PAGE_WIDTH_PX: a phone shows the
// whole page width instead of a clipped one.
function useFitWidth(ref: RefObject<HTMLElement | null>, max: number): number {
  const [width, setWidth] = useState(max);
  useEffect(() => {
    const element = ref.current;
    if (!element || typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(([entry]) => {
      const available = Math.floor(entry.contentRect.width);
      if (available > 0) setWidth(Math.min(max, available));
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [ref, max]);
  return width;
}

interface PdfNavProps {
  page: number;
  pages: number;
  onPage: (page: number) => void;
}

function PdfNav({ page, pages, onPage }: PdfNavProps) {
  return (
    <div className="pdf-viewer__nav">
      <button type="button" className="btn btn--quiet btn--small" aria-label="Previous page" disabled={page <= 1}
        onClick={() => onPage(page - 1)}>‹</button>
      <span>Page {page} of {pages}</span>
      <button type="button" className="btn btn--quiet btn--small" aria-label="Next page" disabled={page >= pages}
        onClick={() => onPage(page + 1)}>›</button>
    </div>
  );
}

// A PDF on the Board (M2 D4): one page at a time, the page switcher above it.
// Its own lazy chunk.
export default function PdfViewer({ url, title }: PdfViewerProps) {
  const viewerRef = useRef<HTMLDivElement>(null);
  const width = useFitWidth(viewerRef, PAGE_WIDTH_PX);
  const [pages, setPages] = useState(0);
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const loaded = useCallback(({ numPages }: { numPages: number }) => setPages(numPages), []);
  const failed = useCallback(() => setError("This PDF could not be shown."), []);
  if (error) return <p className="board-empty">{error}</p>;
  return (
    <div ref={viewerRef} className="pdf-viewer" aria-label={`PDF ${title}`}>
      {pages > 1 ? <PdfNav page={page} pages={pages} onPage={setPage} /> : null}
      <Document file={url} onLoadSuccess={loaded} onLoadError={failed} loading={<p className="board-loading">Loading&hellip;</p>}>
        <Page pageNumber={page} width={width} />
      </Document>
    </div>
  );
}
