import { useCallback, useEffect, useRef, useState } from "react";
import { describeError } from "../../../api/client";
import { listDocuments } from "../../../api/documents";
import { listNotes } from "../../../api/notes";
import type { DocumentOut, NoteSummaryOut } from "../../../api/types";
import { useLiveState } from "../../../hooks/useLiveStore";

export interface NotesTreeData {
  notes: readonly NoteSummaryOut[] | null; // null until the first answer
  documents: readonly DocumentOut[];
  error: string | null;
  reload: () => void;
}

// Every note and document (GET /api/notes, /api/documents), newest answer only; again when either changes anywhere.
export function useNotesTree(): NotesTreeData {
  const { notes: notesVersion, documents: docsVersion } = useLiveState().boardVersion;
  const [found, setFound] = useState<{ notes: readonly NoteSummaryOut[] | null; documents: readonly DocumentOut[] }>(
    { notes: null, documents: [] });
  const [error, setError] = useState<string | null>(null);
  const latest = useRef(0);
  const reload = useCallback(() => {
    const ticket = ++latest.current;
    Promise.all([listNotes(), listDocuments()])
      .then(([notes, documents]) => { if (ticket === latest.current) { setFound({ notes, documents }); setError(null); } })
      .catch((err: unknown) => { if (ticket === latest.current) setError(describeError(err)); });
  }, []);
  useEffect(() => reload(), [reload, notesVersion, docsVersion]);
  return { ...found, error, reload };
}
