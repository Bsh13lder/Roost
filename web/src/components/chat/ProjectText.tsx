import { Link } from "react-router-dom";
import { FolderIcon } from "../icons";
import { splitProjectTokens } from "../../lib/projectTokens";
import { useChatShared } from "./chatContext";
import { renderBody } from "./PlainText";

// Your own message as written, with each "#Project Name" you picked drawn as a chip that opens that project's page
// (2026-10-26). The server reads the same names (roost/projects/chat_refs.py), so a chip is exactly the project the
// bot was told about; an unknown "#word" stays text.
export function ProjectText({ text, keyPrefix }: { text: string; keyPrefix: string }) {
  const { projects } = useChatShared();
  const segments = splitProjectTokens(text, projects);
  return (
    <span className="message__plain">
      {segments.map((segment, index) => {
        const key = `${keyPrefix}-p${index}`;
        if (!("project" in segment)) return <span key={key}>{renderBody(segment.text, key)}</span>;
        return (
          <Link key={key} to={`/board/projects/${segment.project.id}`} className="project-chip"
            aria-label={`Project ${segment.project.name}`}>
            <FolderIcon />
            <span>{segment.project.name}</span>
          </Link>
        );
      })}
    </span>
  );
}
