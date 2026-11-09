import { useState } from "react";
import { ConflictNotice } from "../board/ConflictNotice";
import { ErrorNotice } from "../ErrorNotice";
import { NotePreview } from "./NotePreview";
import { WikilinkChips } from "./WikilinkChips";
import { MAX_NOTE_CONTENT_LENGTH, MAX_NOTE_TITLE_LENGTH, normalizePage } from "./noteHelpers";
import { useNoteDraft, type SaveState } from "./useNoteDraft";

const SAVE_LABEL: Record<SaveState, string> = {
  saved: "Saved", saving: "Saving…", unsaved: "Unsaved changes", error: "Not saved",
};

export interface NoteEditorProps {
  noteId: string;
  onClose: () => void;
  onOpenNote: (noteId: string) => void;
  onCreateNote: (title: string) => void;
}

interface EditorBarProps {
  label: string;
  preview: boolean;
  onPreview: (preview: boolean) => void;
  onClose: () => void;
}

function EditorBar({ label, preview, onPreview, onClose }: EditorBarProps) {
  return (
    <div className="note-editor__bar">
      <button type="button" className="btn btn--quiet btn--small" onClick={onClose}>← Notes</button>
      <span className="note-editor__state" aria-live="polite">{label}</span>
      <div className="note-editor__modes" role="group" aria-label="View">
        <button type="button" className="btn btn--quiet btn--small" aria-pressed={!preview} onClick={() => onPreview(false)}>Edit</button>
        <button type="button" className="btn btn--quiet btn--small" aria-pressed={preview} onClick={() => onPreview(true)}>Preview</button>
      </div>
    </div>
  );
}

// One note: title, markdown body (or its preview), [[link]] chips, autosave.
export function NoteEditor({ noteId, onClose, onOpenNote, onCreateNote }: NoteEditorProps) {
  const draft = useNoteDraft(noteId);
  const [preview, setPreview] = useState(false);
  // Only leaves once the draft is clean (findings round 1): flush() returns
  // false on an error or a conflict, and `then` must not run then — the
  // editor stays open with "Not saved" or the ConflictNotice showing, instead
  // of discarding the user's text.
  const leave = async (then: () => void) => { if (await draft.flush()) then(); };
  const openTarget = (target: string) => {
    const link = draft.base?.links.find((candidate) => candidate.target === normalizePage(target));
    void leave(() => (link?.note_id ? onOpenNote(link.note_id) : onCreateNote(target)));
  };

  if (!draft.base) return draft.error ? <ErrorNotice message={draft.error} /> : <p className="board-loading">Loading&hellip;</p>;
  const label = SAVE_LABEL[draft.state] + (draft.state === "error" && draft.error ? `: ${draft.error}` : "");
  return (
    <article className="note-editor" aria-label={`Note ${draft.base.title}`}>
      <EditorBar label={label} preview={preview} onPreview={setPreview} onClose={() => void leave(onClose)} />
      {draft.conflict ? <ConflictNotice what="note" onLoad={draft.loadLatest} onKeep={draft.keepMine} /> : null}
      <input className="note-editor__title" aria-label="Title" value={draft.title} maxLength={MAX_NOTE_TITLE_LENGTH}
        onChange={(event) => draft.setTitle(event.target.value)} onBlur={() => void draft.flush()} />
      {preview ? <NotePreview content={draft.content} onWikilink={openTarget} /> : (
        <>
          <textarea className="note-editor__body" aria-label="Note text" value={draft.content}
            maxLength={MAX_NOTE_CONTENT_LENGTH} onChange={(event) => draft.setContent(event.target.value)}
            onBlur={() => void draft.flush()} />
          <WikilinkChips links={draft.base.links} onOpen={(id) => void leave(() => onOpenNote(id))}
            onCreate={(title) => void leave(() => onCreateNote(title))} />
        </>
      )}
    </article>
  );
}
