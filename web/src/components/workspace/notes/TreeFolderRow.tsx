import { useId } from "react";
import { filesText, type TreeFolder, type TreeItem } from "./treeFolders";
import { KindIcon } from "../../documents/KindIcon";
import { ChevronIcon, FileIcon } from "../../icons";
import { cx } from "../../../ui/cx";

export interface TreeFolderRowProps {
  folder: TreeFolder;
  open: boolean;
  onToggle: () => void;
  onOpenNote: (id: string) => void;
  onOpenDocument: (id: string) => void;
}

const KIND_WORD: Record<TreeItem["kind"], string> = { note: "Note", doc: "Doc", sheet: "Sheet", pdf: "PDF" };

function ItemRow({ item, onOpenNote, onOpenDocument }: { item: TreeItem } & Pick<TreeFolderRowProps, "onOpenNote" | "onOpenDocument">) {
  const open = () => (item.kind === "note" ? onOpenNote(item.id) : onOpenDocument(item.id));
  return (
    <li>
      <button type="button" className="ntree__item" aria-label={`${KIND_WORD[item.kind]}: ${item.title}`} onClick={open}>
        <span className="ntree__icon" aria-hidden="true">{item.kind === "note" ? <FileIcon /> : <KindIcon kind={item.kind} />}</span>
        <span className="ntree__name">{item.title}</span>
      </button>
    </li>
  );
}

// One folder of the Notes tree: a project (its colour) or No project, with its count; open, its notes and documents.
export function TreeFolderRow({ folder, open, onToggle, onOpenNote, onOpenDocument }: TreeFolderRowProps) {
  const listId = useId();
  return (
    <li className="ntree__folder">
      <button type="button" className={cx("ntree__fold", open && "is-open")} aria-expanded={open} aria-controls={listId}
        onClick={onToggle}>
        <span className="ntree__chevron" aria-hidden="true"><ChevronIcon /></span>
        {folder.color ? <span className="project-dot ntree__dot" style={{ background: folder.color }} aria-hidden="true" /> : null}
        <span className="ntree__name">{folder.name}</span>
        <span className="ntree__count">{filesText(folder.items.length)}</span>
      </button>
      {open ? (
        <ul id={listId} role="group" aria-label={folder.name} className="ntree__items">
          {folder.items.map((item) => (
            <ItemRow key={`${item.kind}-${item.id}`} item={item} onOpenNote={onOpenNote} onOpenDocument={onOpenDocument} />
          ))}
        </ul>
      ) : null}
    </li>
  );
}
