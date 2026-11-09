import type { NoteLinkOut } from "../../api/types";

export interface WikilinkChipsProps {
  links: NoteLinkOut[];
  onOpen: (noteId: string) => void;
  onCreate: (title: string) => void;
}

// The notes this one links to: open one, or create the note a link names.
export function WikilinkChips({ links, onOpen, onCreate }: WikilinkChipsProps) {
  if (links.length === 0) return null;
  return (
    <ul className="wikilink-chips" aria-label="Links">
      {links.map((link) => (
        <li key={link.target}>
          {link.note_id ? (
            <button type="button" className="wikilink-chip" onClick={() => onOpen(link.note_id as string)}>
              {link.title}
            </button>
          ) : (
            <button type="button" className="wikilink-chip wikilink-chip--new" aria-label={`Create note ${link.title}`}
              onClick={() => onCreate(link.title)}>
              + {link.title}
            </button>
          )}
        </li>
      ))}
    </ul>
  );
}
