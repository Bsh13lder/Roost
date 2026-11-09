import { useId } from "react";
import { Link } from "react-router-dom";
import { ErrorNotice } from "../../ErrorNotice";
import { BudgetBar } from "../../projects/BudgetBar";
import type { ProjectListState } from "../../tasks/useProjects";
import type { ProjectOut } from "../../../api/types";
import { Badge } from "../../../ui/Badge";
import { Button } from "../../../ui/Button";

export interface ProjectPeekProps {
  projectId: string;
  list: ProjectListState; // the rail's projects list (GET /api/projects): the card reads its project from it
  onAll: () => void; // the project is gone: back to All tasks
  gone?: boolean; // the server said so elsewhere (the counts' 404), whatever the list still holds
}

// The budget the card shows: the total one, else the monthly limit, else none.
function PeekBudget({ project }: { project: ProjectOut }) {
  if (project.total.budget !== null) return <BudgetBar label="Total budget" line={project.total} currency={project.currency} />;
  if (project.month.budget !== null) return <BudgetBar label="This month" line={project.month} currency={project.currency} />;
  return null;
}

function PeekGone({ error, onRetry, onAll }: { error: string | null; onRetry: () => void; onAll: () => void }) {
  return (
    <div className="peek peek--gone">
      {error ? <ErrorNotice message={error} onRetry={onRetry} /> : <p className="peek__counts">This project is gone.</p>}
      <Button size="sm" onClick={onAll}>Show all tasks</Button>
    </div>
  );
}

// Over the tasks of the project the rail picked (lead tasks 15 and 20): its colour and name, its open and overdue
// tasks (progress.open and .overdue), a budget bar when it has a budget, and Open project for everything else
// (money, notes, documents). It reads the rail's list, so it moves when the list reloads; the server counts and
// sums, the card only shows.
export function ProjectPeek({ projectId, list, onAll, gone = false }: ProjectPeekProps) {
  const titleId = useId();
  if (gone) return <PeekGone error={null} onRetry={list.reload} onAll={onAll} />;
  const project = list.projects.find((one) => one.id === projectId);
  if (!project) {
    if (!list.loaded && !list.error) return <div className="peek peek--loading" aria-hidden="true" />;
    return <PeekGone error={list.loaded ? null : list.error} onRetry={list.reload} onAll={onAll} />;
  }
  const { open, overdue } = project.progress;
  return (
    <section className="peek" aria-labelledby={titleId}>
      <div className="peek__top">
        <span className="project-dot peek__dot" style={{ background: project.color }} aria-hidden="true" />
        <h2 id={titleId} className="peek__name">{project.name}</h2>
        {project.status === "archived" ? <Badge tone="neutral">Archived</Badge> : null}
        <Link to={`/board/projects/${encodeURIComponent(project.id)}`} className="peek__open">Open project ›</Link>
      </div>
      <p className="peek__counts">
        <span>{open} open</span>
        {overdue > 0 ? <span className="peek__late">{overdue} overdue</span> : null}
      </p>
      <PeekBudget project={project} />
    </section>
  );
}
