import { useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { QuickBox } from "../board/QuickBox";
import * as documentsApi from "../../api/documents";
import * as notesApi from "../../api/notes";
import { describeError } from "../../api/client";
import { Input } from "../../ui/Input";

export type NewKind = "note" | "document";

export interface ProjectQuickNewProps {
  kind: NewKind;
  projectId: string;
  projectName: string;
  onCreated: (id: string) => void; // the new item's id: the panel opens it
}

const UNTITLED: Record<NewKind, string> = { note: "Untitled note", document: "Untitled doc" };

function create(kind: NewKind, projectId: string, typed: string): Promise<{ id: string }> {
  const title = typed || UNTITLED[kind];
  if (kind === "note") return notesApi.createNote({ title, content: typed ? `# ${typed}\n\n` : "", project_id: projectId });
  return documentsApi.createDocument({ kind: "doc", title, project_id: projectId });
}

// "New note in Casa Nueva…" (G13): a line on top of the Notes and Docs tabs. Enter creates the item with the
// project set, through the same APIs as the panels, and opens it.
export function ProjectQuickNew({ kind, projectId, projectName, onCreated }: ProjectQuickNewProps) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submit = () => {
    setBusy(true);
    setError(null);
    create(kind, projectId, text.trim())
      .then((made) => { setText(""); onCreated(made.id); })
      .catch((err: unknown) => setError(describeError(err)))
      .finally(() => setBusy(false));
  };
  return (
    <>
      <QuickBox glyph="+" label={`New ${kind} in ${projectName}`}>
        <Input aria-label={`New ${kind}`} placeholder={`New ${kind} in ${projectName}…`} value={text} disabled={busy}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); submit(); } }} />
      </QuickBox>
      {error ? <ErrorNotice message={error} /> : null}
    </>
  );
}
