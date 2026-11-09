import { useCallback, useEffect, useRef, useState, type RefObject } from "react";
import * as documentsApi from "../../../api/documents";
import { describeError } from "../../../api/client";
import { RevisionConflictError } from "../../../api/conflict";
import type { DocumentDetailOut } from "../../../api/types";
import type { UniverKit } from "./kit";

export const DOCUMENT_AUTOSAVE_MS = 800;
export type SaveState = "saved" | "saving" | "error";

export interface DocumentConflict {
  current: DocumentDetailOut;
  mine: Record<string, unknown>;
}

export interface UniverAutosave {
  state: SaveState;
  error: string | null;
  overwrite: (conflict: DocumentConflict) => Promise<void>;
  discardPending: () => void;
}

// One save against a known revision: the new revision on success, the stored
// copy handed to ``onConflict`` on a stale one, a plain message otherwise.
function usePersist(documentId: string, revision: { current: number },
  onConflict: (conflict: DocumentConflict) => void) {
  const [state, setState] = useState<SaveState>("saved");
  const [error, setError] = useState<string | null>(null);
  const persist = useCallback(async (payload: Record<string, unknown>, base: number) => {
    setState("saving");
    try {
      const saved = await documentsApi.saveDocument(documentId, { payload, base_revision: base });
      revision.current = saved.revision;
      setState("saved");
      setError(null);
    } catch (err) {
      if (err instanceof RevisionConflictError) {
        setState("saved");
        onConflict({ current: err.current as DocumentDetailOut, mine: payload });
        return;
      }
      setState("error");
      setError(describeError(err));
    }
  }, [documentId, revision, onConflict]);
  return { state, error, persist };
}

// Mounts ``doc`` with ``kit`` and saves the editor's snapshot a moment after
// the last edit — and when the editor goes away — always against the revision
// it last saw (LazyClaw's Docs/Sheets lifecycle). A snapshot unchanged since
// the editor opened it is never sent. A stale revision goes to ``onConflict``; nothing is overwritten.
export function useUniverAutosave(
  kit: UniverKit, doc: DocumentDetailOut, containerRef: RefObject<HTMLDivElement | null>,
  onConflict: (conflict: DocumentConflict) => void,
): UniverAutosave {
  const revision = useRef(doc.revision);
  const discard = useRef(false);
  const { state, error, persist } = usePersist(doc.id, revision, onConflict);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return undefined;
    revision.current = doc.revision;
    discard.current = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const flush = () => {
      const snapshot = editor.snapshot();
      if (!snapshot || JSON.stringify(snapshot) === lastJson) return;
      lastJson = JSON.stringify(snapshot);
      void persist(snapshot, revision.current);
    };
    const editor = kit.mount(container, doc.payload ?? {}, () => {
      clearTimeout(timer);
      timer = setTimeout(flush, DOCUMENT_AUTOSAVE_MS);
    });
    // Compared against the editor's own first snapshot, not the stored one:
    // Univer fills in defaults on opening, and that alone is not an edit.
    let lastJson = JSON.stringify(editor.snapshot() ?? doc.payload ?? {});
    return () => {
      clearTimeout(timer);
      if (!discard.current) flush();
      editor.dispose();
    };
  }, [kit, doc, containerRef, persist]);

  const overwrite = useCallback((conflict: DocumentConflict) => persist(conflict.mine, conflict.current.revision),
    [persist]);
  const discardPending = useCallback(() => { discard.current = true; }, []);
  return { state, error, overwrite, discardPending };
}
