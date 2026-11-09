import { useCallback, useRef, useState } from "react";
import { ConflictNotice } from "../../board/ConflictNotice";
import type { DocumentDetailOut } from "../../../api/types";
import type { UniverKit } from "./kit";
import { useUniverAutosave, type DocumentConflict, type SaveState } from "./useUniverAutosave";

const SAVE_LABEL: Record<SaveState, string> = { saved: "Saved", saving: "Saving…", error: "Not saved" };

export interface UniverEditorProps {
  kit: UniverKit;
  document: DocumentDetailOut;
}

// A doc or a sheet in the Univer editor, saved as you go (M2 D4).
export function UniverEditor({ kit, document }: UniverEditorProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [shown, setShown] = useState(document);
  const [conflict, setConflict] = useState<DocumentConflict | null>(null);
  const onConflict = useCallback((found: DocumentConflict) => setConflict(found), []);
  const save = useUniverAutosave(kit, shown, containerRef, onConflict);

  // Theirs replaces mine on screen; my unsaved edit is dropped, never saved.
  const loadLatest = () => {
    if (!conflict) return;
    save.discardPending();
    setShown(conflict.current);
    setConflict(null);
  };
  // Mine stays on screen and is saved over their revision.
  const keepMine = () => {
    if (!conflict) return;
    setConflict(null);
    void save.overwrite(conflict);
  };
  return (
    <div className="univer-shell">
      <p className="univer-shell__state" aria-live="polite">{SAVE_LABEL[save.state]}{save.error ? `: ${save.error}` : ""}</p>
      {conflict ? <ConflictNotice what="document" onLoad={loadLatest} onKeep={keepMine} /> : null}
      <div ref={containerRef} className="univer-editor" data-testid="univer-editor" />
    </div>
  );
}
