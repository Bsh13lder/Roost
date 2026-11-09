import { DeleteConfirm, ProjectMenu, useProjectActions } from "./ProjectActions";
import { ProjectStats } from "./ProjectStats";
import { RepeatingStrip } from "./RepeatingStrip";
import { dateLabel, daysLeftText, isGeneral } from "./projects";
import { WebContentChip } from "../board/WebContentChip";
import { formatMoney } from "../board/money";
import * as projectsApi from "../../api/projects";
import type { ProjectDetailBoardOut } from "../../api/projects";
import { Badge } from "../../ui/Badge";
import { Button } from "../../ui/Button";
import { todayIn } from "../../ui/date/dates";

export interface ProjectHeaderCardProps {
  project: ProjectDetailBoardOut;
  today?: string; // the account's today, "YYYY-MM-DD" (tests pass one)
  onEdit: () => void;
  onChanged: () => void;
  onDeleted: () => void;
}

// "Led by Chief · 10 Sep 2026 → 17 Feb 2027 · 120 days left"; a missing part drops out.
function factsOf(project: ProjectDetailBoardOut, today: string): string {
  const dates = project.start_date && project.due_date
    ? `${dateLabel(project.start_date)} → ${dateLabel(project.due_date)}`
    : project.start_date ? `Starts ${dateLabel(project.start_date)}` : project.due_date ? `Due ${dateLabel(project.due_date)}` : "";
  return [
    project.lead_bot_name ? `Led by ${project.lead_bot_name}` : "", dates,
    project.due_date ? daysLeftText(project.due_date, today) : "",
  ].filter((part) => part !== "").join(" · ");
}

// The top of a project's page (G13): its name and status, Edit and the ⋯ menu, the facts line, the three
// stats, the repeating strip and any other currencies. Every number is the server's.
export function ProjectHeaderCard({ project, today = todayIn(), onEdit, onChanged, onDeleted }: ProjectHeaderCardProps) {
  const actions = useProjectActions({ project, onChanged, onDeleted });
  const general = isGeneral(project);
  const facts = factsOf(project, today);
  return (
    <section className="money-card p-card" aria-label="Summary">
      <div className="p-card__top">
        <span className="project-dot" style={{ background: project.color }} aria-hidden="true" />
        <h1 className="p-card__name">{project.name}</h1>
        <Badge tone={project.status === "archived" ? "neutral" : "ok"}>{project.status === "archived" ? "Archived" : "Active"}</Badge>
        {project.tainted ? (
          <WebContentChip what={project.name} onKeep={() => { void projectsApi.keepProject(project.id).then(onChanged); }} />
        ) : null}
        {general ? null : (
          <div className="p-card__actions">
            <Button size="sm" onClick={onEdit}>Edit</Button>
            <ProjectMenu project={project} actions={actions} />
          </div>
        )}
      </div>
      <DeleteConfirm project={project} actions={actions} />
      {facts ? <p className="p-card__facts">{facts}</p> : null}
      <ProjectStats project={project} today={today} />
      <RepeatingStrip rules={project.repeating} />
      {Object.entries(project.other_currencies).map(([code, total]) => (
        <p key={code} className="p-card__other">Also {formatMoney(total, code)} (not in the total)</p>
      ))}
    </section>
  );
}
