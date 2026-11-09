import Markdown from "../markdown/Markdown";
import { stripFrontMatter } from "./noteHelpers";

export interface NotePreviewProps {
  content: string;
  onWikilink: (target: string) => void;
}

// A note's markdown, drawn by the shared renderer (redesign P2), where a [[link]] opens its note.
export function NotePreview({ content, onWikilink }: NotePreviewProps) {
  return <Markdown className="note-preview" text={stripFrontMatter(content)} onWikilink={onWikilink} />;
}
