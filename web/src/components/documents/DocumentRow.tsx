import { useState } from "react";
import { KindIcon } from "./KindIcon";
import { MadeByChip } from "../board/MadeByChip";
import { WebContentChip } from "../board/WebContentChip";
import { relativeTimeAgo } from "../notes/noteHelpers";
import type { DocumentOut } from "../../api/types";

export interface DocumentRowProps {
  document: DocumentOut;
  onOpen: (documentId: string) => void;
  onKeep: (documentId: string) => void;
  onDelete: (documentId: string) => void;
}

export function DocumentRow({ document, onOpen, onKeep, onDelete }: DocumentRowProps) {
  const [confirming, setConfirming] = useState(false);
  return (
    <li className="doc-row">
      <KindIcon kind={document.kind} />
      <button type="button" className="doc-row__open" onClick={() => onOpen(document.id)}>{document.title}</button>
      <span className="doc-row__when">{relativeTimeAgo(document.updated_at)}</span>
      <span className="doc-row__actions">
        <MadeByChip botId={document.created_by_bot} />
        {document.tainted ? <WebContentChip what={document.title} onKeep={() => onKeep(document.id)} /> : null}
        {confirming ? (
          <>
            <button type="button" className="btn btn--danger btn--small" aria-label={`Delete ${document.title} for good`}
              onClick={() => onDelete(document.id)}>Delete</button>
            <button type="button" className="btn btn--quiet btn--small" onClick={() => setConfirming(false)}>Cancel</button>
          </>
        ) : (
          <button type="button" className="btn btn--quiet btn--small" aria-label={`Delete ${document.title}`}
            onClick={() => setConfirming(true)}>Delete</button>
        )}
      </span>
    </li>
  );
}
