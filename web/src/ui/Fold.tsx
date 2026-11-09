import { useId, useState, type ReactNode } from "react";
import { ChevronIcon } from "../components/icons";

export const FOLD_STORAGE_PREFIX = "roost.fold.";

export interface FoldProps {
  id: string; // what this browser remembers it by
  title: string;
  summary?: string; // a short value shown while it is closed, such as the current mode
  children: ReactNode;
}

function readOpen(id: string): boolean {
  try {
    return window.localStorage.getItem(FOLD_STORAGE_PREFIX + id) === "1";
  } catch (error) {
    console.warn("This browser keeps no site data here: sections start closed.", error);
    return false;
  }
}

function writeOpen(id: string, open: boolean): void {
  try {
    if (open) window.localStorage.setItem(FOLD_STORAGE_PREFIX + id, "1");
    else window.localStorage.removeItem(FOLD_STORAGE_PREFIX + id);
  } catch (error) {
    console.warn("Could not remember this section's state.", error);
  }
}

// A section that folds away (the quiet Info tab): closed until you open it, and this browser remembers.
// Its body is not rendered while closed, so a lazy section loads only when opened.
export function Fold({ id, title, summary, children }: FoldProps) {
  const [open, setOpen] = useState(() => readOpen(id));
  const bodyId = useId();
  const toggle = () => {
    writeOpen(id, !open);
    setOpen(!open);
  };
  return (
    <section className="fold" data-open={open}>
      <button type="button" className="fold__head" aria-expanded={open} aria-controls={bodyId} onClick={toggle}>
        <span className="fold__title">{title}</span>
        {summary ? <span className="fold__summary">{summary}</span> : null}
        <span className="fold__chevron" aria-hidden="true"><ChevronIcon /></span>
      </button>
      {open ? <div className="fold__body" id={bodyId}>{children}</div> : null}
    </section>
  );
}
