import { Suspense, lazy, useCallback, useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ErrorNotice } from "../components/ErrorNotice";
import { BackIcon } from "../components/icons";
import { lazyPanel } from "../components/board/lazyPanel";
import { TasksBoard } from "../components/board/TasksBoard";
import { ProjectEditForm } from "../components/projects/ProjectEditForm";
import { ProjectMoney } from "../components/projects/ProjectMoney";
import { ProjectHeaderCard } from "../components/projects/ProjectHeaderCard";
import { ProjectQuickNew } from "../components/projects/ProjectQuickNew";
import { useLiveState } from "../hooks/useLiveStore";
import { Tabs } from "../ui/Tabs";
import * as projectsApi from "../api/projects";
import { ApiError, describeError } from "../api/client";
import type { ProjectDetailBoardOut } from "../api/projects";
import { ALL_TASKS_HREF, projectTasksHref } from "./boardPaths";

// Its tasks and its money are one page (app restructure: Money is no longer a tab); notes and documents stay tabs
// under them. An old ?tab=tasks or ?tab=money opens the page as it is.
export type ProjectTab = "notes" | "docs";
export const TABS: ReadonlyArray<{ id: ProjectTab; label: string }> = [
  { id: "notes", label: "Notes" }, { id: "docs", label: "Documents" },
];
// Which of the server's counts each tab wears.
const COUNT_KEYS = { notes: "notes", docs: "documents" } as const;

// Notes and Documents stay their own chunks here too (M2 D4).
const NotesPanel = lazyPanel(lazy(() => import("../components/notes/NotesBoard")));
const DocumentsPanel = lazyPanel(lazy(() => import("../components/documents/DocumentsBoard")));
// Export to my vault (obsidian track): its own chunk.
const VaultExportCard = lazy(() => import("../components/vaultExport/VaultExportCard"));

interface PanelArgs {
  project: ProjectDetailBoardOut;
  opened: string | null; // the note or document the quick line just made
  onCreated: (id: string) => void;
}
const PANELS: Record<ProjectTab, (args: PanelArgs) => ReactNode> = {
  notes: ({ project, opened, onCreated }) => (
    <>
      <ProjectQuickNew kind="note" projectId={project.id} projectName={project.name} onCreated={onCreated} />
      <NotesPanel projectId={project.id} openId={opened} />
    </>
  ),
  docs: ({ project, opened, onCreated }) => (
    <>
      <ProjectQuickNew kind="document" projectId={project.id} projectName={project.name} onCreated={onCreated} />
      <DocumentsPanel projectId={project.id} openId={opened} />
    </>
  ),
};

// The project and its numbers. It reloads when its tasks, money, notes or documents change anywhere;
// once the project is gone (deleted in another tab) it shows why, with the way back.
function useProjectDetail(projectId: string | undefined) {
  const { tasks, money, notes, documents } = useLiveState().boardVersion;
  const [project, setProject] = useState<ProjectDetailBoardOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef(0);
  const load = useCallback(() => {
    if (!projectId) return;
    const ticket = ++latest.current;
    projectsApi.getProject(projectId)
      .then((found) => { if (ticket === latest.current) { setProject(found); setError(null); } })
      .catch((err: unknown) => {
        if (ticket !== latest.current) return;
        if (err instanceof ApiError && err.status === 404) setProject(null);
        setError(describeError(err));
      });
  }, [projectId]);
  useEffect(() => load(), [load, tasks, money, notes, documents]);
  return { project, error, load };
}

// The sticky head (G13): back to this project's tasks in the Workspace, then "Workspace / Tasks /" and its name.
function ProjectHead({ projectId, project }: { projectId: string; project: ProjectDetailBoardOut | null }) {
  return (
    <header className="board-head project-head">
      <div className="board-head__row">
        <Link to={projectTasksHref(projectId)} className="icon-btn" aria-label="Back to tasks"><BackIcon /></Link>
        <span className="project-head__trail">Workspace / Tasks /</span>
        {project ? <span className="project-head__name">{project.name}</span> : null}
      </div>
    </header>
  );
}

// One part of the page: its title with the server's count, then what it holds.
function PageSection({ title, count, children }: { title: string; count: number; children: ReactNode }) {
  const id = useId();
  return (
    <section className="project-section" aria-labelledby={id}>
      <div className="project-section__head">
        <h2 id={id} className="project-section__title">{title}</h2>
        <span className="count" aria-hidden="true">{count}</span>
      </div>
      {children}
    </section>
  );
}

interface BodyProps {
  project: ProjectDetailBoardOut;
  reload: () => void;
  onDeleted: () => void;
}

function ProjectBody({ project, reload, onDeleted }: BodyProps) {
  const [params, setParams] = useSearchParams();
  const [editing, setEditing] = useState(false);
  const [opened, setOpened] = useState<{ tab: ProjectTab; id: string } | null>(null);
  const current = TABS.find((tab) => tab.id === params.get("tab"))?.id ?? TABS[0].id;
  const doneEditing = () => { setEditing(false); reload(); };
  const counts = project.counts;
  const tabs = TABS.map((tab) => ({ ...tab, count: counts[COUNT_KEYS[tab.id]] }));
  return (
    <>
      {editing
        ? <ProjectEditForm project={project} onDone={doneEditing} />
        : <ProjectHeaderCard project={project} onEdit={() => setEditing(true)} onChanged={reload} onDeleted={onDeleted} />}
      <Suspense fallback={null}><VaultExportCard projectId={project.id} /></Suspense>
      <PageSection title="Tasks" count={counts.tasks_open}>
        <TasksBoard projectId={project.id} leadBotId={project.lead_bot_id} currency={project.currency} money={project.task_money} />
      </PageSection>
      <PageSection title="Money" count={counts.expenses}>
        <ProjectMoney project={project} onChanged={reload} />
      </PageSection>
      <Tabs variant="line" label="Notes and documents" tabs={tabs} value={current} panelClassName="board-panel"
        onChange={(tab) => setParams({ tab }, { replace: true })}>
        {PANELS[current]({
          project, opened: opened?.tab === current ? opened.id : null,
          onCreated: (id) => setOpened({ tab: current, id }),
        })}
      </Tabs>
    </>
  );
}

// A project's page (H14, G13, app restructure): a header card with its numbers, its tasks, its money (expenses
// and income, the money line, top-ups, the budget), then Notes · Documents with counts.
export function Project() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const { project, error, load } = useProjectDetail(projectId);
  const shown = project && project.id === projectId ? project : null;
  return (
    <div className="board-page">
      <div className="board-scroll">
        <ProjectHead projectId={projectId ?? ""} project={shown} />
        <div className="board-wrap project-page">
          {error ? <ErrorNotice message={error} onRetry={load} /> : null}
          {!shown && !error ? <p className="board-loading">Loading&hellip;</p> : null}
          {shown ? <ProjectBody project={shown} reload={load} onDeleted={() => navigate(ALL_TASKS_HREF, { replace: true })} /> : null}
        </div>
      </div>
    </div>
  );
}
