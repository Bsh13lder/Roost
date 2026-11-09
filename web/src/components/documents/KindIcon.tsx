import type { DocumentKind } from "../../api/types";

const LABELS: Record<DocumentKind, string> = { doc: "Doc", sheet: "Sheet", pdf: "PDF" };

export function KindIcon({ kind }: { kind: DocumentKind }) {
  return (
    <svg className={`kind-icon kind-icon--${kind}`} role="img" aria-label={LABELS[kind]} viewBox="0 0 20 20" width={20} height={20}>
      <path d="M5 2h7l3 3v13H5z" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinejoin="round" />
      {kind === "doc" ? <path d="M8 9h5M8 12h5M8 15h3" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" /> : null}
      {kind === "sheet" ? <path d="M5 9h10M5 13h10M10 9v9" stroke="currentColor" strokeWidth={1.5} /> : null}
      {kind === "pdf" ? <path d="M7 14h6M8 10l2 2 2-2" stroke="currentColor" strokeWidth={1.5} fill="none" strokeLinecap="round" /> : null}
    </svg>
  );
}
