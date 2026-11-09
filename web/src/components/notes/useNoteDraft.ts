import { useCallback, useEffect, useRef, useState } from "react";
import * as notesApi from "../../api/notes";
import { describeError } from "../../api/client";
import { RevisionConflictError } from "../../api/conflict";
import type { NoteOut } from "../../api/types";

export const NOTE_AUTOSAVE_MS = 800;
export type SaveState = "saved" | "saving" | "unsaved" | "error";

export interface NoteDraft {
  base: NoteOut | null;
  title: string;
  content: string;
  conflict: NoteOut | null;
  state: SaveState;
  error: string | null;
  setTitle: (title: string) => void;
  setContent: (content: string) => void;
  // Resolves to whether the draft is clean: true when nothing was dirty, or it
  // was and the save succeeded; false on an error or a conflict. A caller
  // about to leave the editor (close it, or follow a [[link]]) must check this
  // before doing so, or it can discard the user's text (findings round 1).
  flush: () => Promise<boolean>;
  loadLatest: () => void;
  keepMine: () => void;
}

function useLoadedNote(noteId: string) {
  const [base, setBase] = useState<NoteOut | null>(null);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [loadError, setLoadError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    notesApi.getNote(noteId).then((note) => {
      if (!live) return;
      setBase(note);
      setTitle(note.title);
      setContent(note.content);
    }).catch((err: unknown) => {
      if (live) setLoadError(describeError(err));
    });
    return () => { live = false; };
  }, [noteId]);
  return { base, setBase, title, setTitle, content, setContent, loadError };
}

// One note being edited (M2 D4). Title and body autosave a moment after the
// last keystroke, and on flush (blur, leaving the editor), always against the
// revision last seen. A stale revision pauses saving until the user picks
// "Load the latest" or "Keep mine" — and so does an in-flight or failed save,
// until it clears, so leaving never silently drops what was typed.
export function useNoteDraft(noteId: string): NoteDraft {
  const loaded = useLoadedNote(noteId);
  const { base, setBase, title, content } = loaded;
  const [conflict, setConflict] = useState<NoteOut | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const wantedTitle = title.trim() || (base?.title ?? "");
  const dirty = base !== null && (wantedTitle !== base.title || content !== base.content);

  // What flush acts on. Title/content/conflict are always current by the time
  // an event handler runs (any keystroke re-renders before an awaited save
  // round-trips), but `base` changes the instant a save resolves — before
  // React re-renders — so the save itself also writes it here (in saveOnce),
  // to beat a recheck that follows within the same tick.
  const current = useRef({ base, wantedTitle, content, conflict });
  current.current = { base, wantedTitle, content, conflict };

  const inFlight = useRef<Promise<boolean> | null>(null);

  const saveOnce = useCallback((toSave: NoteOut, saveTitle: string, saveContent: string): Promise<boolean> => {
    setSaving(true);
    return notesApi.saveNote(toSave.id, { base_revision: toSave.revision, title: saveTitle, content: saveContent })
      .then((saved) => {
        current.current.base = saved;
        setBase(saved);
        setSaveError(null);
        return true;
      })
      .catch((err: unknown) => {
        if (err instanceof RevisionConflictError) { setConflict(err.current as NoteOut); return false; }
        setSaveError(describeError(err));
        return false;
      })
      .finally(() => setSaving(false));
  }, [setBase]);

  // Saves whatever is dirty against the revision last seen. Resolves true
  // only when there was nothing to save, or there was and it succeeded; false
  // on an error or a conflict, so "leave the editor" can refuse to leave
  // (findings round 1). A save already in flight is awaited first, then
  // whatever is dirty against the revision IT left behind is saved too — so
  // text typed while the request was in the air is never silently dropped.
  const flush = useCallback(async (): Promise<boolean> => {
    if (inFlight.current) {
      const clean = await inFlight.current;
      return clean ? flush() : false;
    }
    const { base: toSave, wantedTitle: saveTitle, content: saveContent, conflict: pending } = current.current;
    if (pending) return false;
    if (!toSave || (saveTitle === toSave.title && saveContent === toSave.content)) return true;
    const run = saveOnce(toSave, saveTitle, saveContent).finally(() => { inFlight.current = null; });
    inFlight.current = run;
    return run;
  }, [saveOnce]);

  useEffect(() => {
    if (!dirty || conflict) return undefined;
    const timer = setTimeout(() => { void flush(); }, NOTE_AUTOSAVE_MS);
    return () => clearTimeout(timer);
  }, [dirty, conflict, flush]);

  const resolve = useConflictChoices(conflict, setConflict, loaded);
  const state: SaveState = saveError ? "error" : saving ? "saving" : dirty ? "unsaved" : "saved";
  return { base, title, content, conflict, state, error: saveError ?? loaded.loadError, setTitle: loaded.setTitle,
           setContent: loaded.setContent, flush, ...resolve };
}

function useConflictChoices(
  conflict: NoteOut | null,
  setConflict: (next: NoteOut | null) => void,
  loaded: ReturnType<typeof useLoadedNote>,
) {
  const { setBase, setTitle, setContent } = loaded;
  // Theirs replaces what is on screen; nothing of mine is saved.
  const loadLatest = useCallback(() => {
    if (!conflict) return;
    setBase(conflict);
    setTitle(conflict.title);
    setContent(conflict.content);
    setConflict(null);
  }, [conflict, setBase, setTitle, setContent, setConflict]);
  // Mine stays on screen and is saved over the latest revision on the next autosave.
  const keepMine = useCallback(() => {
    if (!conflict) return;
    setBase(conflict);
    setConflict(null);
  }, [conflict, setBase, setConflict]);
  return { loadLatest, keepMine };
}
