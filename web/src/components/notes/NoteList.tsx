import { MadeByChip } from "../board/MadeByChip";
import { WebContentChip } from "../board/WebContentChip";
import { plainSnippet, relativeTimeAgo } from "./noteHelpers";
import type { NoteSummaryOut } from "../../api/types";

export interface NoteListProps {
  notes: NoteSummaryOut[];
  onOpen: (noteId: string) => void;
  onKeep: (noteId: string) => void;
}

export function NoteList({ notes, onOpen, onKeep }: NoteListProps) {
  return (
    <ul className="note-list" aria-label="Your notes">
      {notes.map((note) => (
        <li key={note.id} className="note-row">
          <button type="button" className="note-row__open" onClick={() => onOpen(note.id)}>
            <span className="note-row__title">{note.title}</span>
            {note.snippet ? <span className="note-row__snippet">{plainSnippet(note.snippet)}</span> : null}
          </button>
          <div className="note-row__chips">
            {note.tags.map((tag) => <span key={tag} className="board-chip">#{tag}</span>)}
            <span className="note-row__when">{relativeTimeAgo(note.updated_at)}</span>
            <MadeByChip botId={note.created_by_bot} />
            {note.tainted ? <WebContentChip what={note.title} onKeep={() => onKeep(note.id)} /> : null}
          </div>
        </li>
      ))}
    </ul>
  );
}
