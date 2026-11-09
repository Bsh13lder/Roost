import { lazy, Suspense, type ReactNode } from "react";
import { Link, Navigate, useSearchParams } from "react-router-dom";
import { BackIcon } from "../components/icons";
import { INBOX_VIEW } from "../components/board/constants";
import { MoneyBoard } from "../components/board/MoneyBoard";
import { TasksArea } from "../components/board/TasksArea";
import { parseScope, scopeProjectId, TASK_SCOPE_PARAM } from "../components/board/taskScope";
import { WorkspaceBar } from "../components/workspace/WorkspaceBar";
import {
  OLD_PROJECTS_TAB, SEARCH_PARAM, SECTION_PARAM, sectionOf, WORKSPACE_HREF, type WorkspaceSection,
} from "../components/workspace/sections";
import { ALL_TASKS_HREF, DOCUMENT_PARAM, NOTE_PARAM } from "./boardPaths";

// The heavier sections are their own chunks (M2 D4): the Workspace's entry stays small.
const NotesTree = lazy(() => import("../components/workspace/notes/NotesTree"));
const WorkspaceCalendar = lazy(() => import("../components/workspace/calendar/WorkspaceCalendar"));

const LOADING = <p className="board-loading">Loading&hellip;</p>;
const KEPT_ON_SWITCH = [SEARCH_PARAM, TASK_SCOPE_PARAM] as const; // the pill's words and the project chip

function sectionPanel(section: WorkspaceSection, params: URLSearchParams): ReactNode {
  if (section === "tasks") return <TasksArea />;
  if (section === "calendar") return <Suspense fallback={LOADING}><WorkspaceCalendar /></Suspense>;
  return (
    <Suspense fallback={LOADING}>
      <NotesTree openNote={params.get(NOTE_PARAM)} openDocument={params.get(DOCUMENT_PARAM)} />
    </Suspense>
  );
}

function Head({ title, back, backLabel }: { title: string; back: string; backLabel: string }) {
  return (
    <header className="board-head workspace-head">
      <div className="board-head__row">
        <Link to={back} className="icon-btn" aria-label={backLabel}><BackIcon /></Link>
        <h1 className="board-head__title">{title}</h1>
      </div>
    </header>
  );
}

// All money: the old Money tab's whole page (List · By days · Calendar, the date filter, reports), reached from
// the project chips' menu.
function AllMoney() {
  return (
    <div className="board-page">
      <div className="board-scroll">
        <Head title="All money" back={WORKSPACE_HREF} backLabel="Back to the Workspace" />
        <div className="board-wrap"><MoneyBoard /></div>
      </div>
    </div>
  );
}

// The user's Workspace (app restructure, R2), one for every bot, opened from Home: Tasks · Notes · Calendar with
// the "Add or find anything…" pill. It keeps the Board's /board address and every old link.
export function Board() {
  const [params, setParams] = useSearchParams();
  if (params.get(SECTION_PARAM) === OLD_PROJECTS_TAB) return <Navigate to={ALL_TASKS_HREF} replace />;
  const place = sectionOf(params);
  if (place === "money") return <AllMoney />;
  const choose = (section: WorkspaceSection) => {
    const next = new URLSearchParams({ [SECTION_PARAM]: section });
    for (const key of KEPT_ON_SWITCH) { const value = params.get(key); if (value) next.set(key, value); }
    setParams(next, { replace: true });
  };
  // A new task joins the project chip picked, except on the Inbox tab (every task with no project).
  const inInbox = place === "tasks" && params.get("view") === INBOX_VIEW;
  const projectId = inInbox ? undefined : scopeProjectId(parseScope(params.get(TASK_SCOPE_PARAM)));
  return (
    <div className="board-page workspace">
      <div className="board-scroll">
        <Head title="Workspace" back="/" backLabel="Back to chats" />
        <WorkspaceBar section={place} onSection={choose} projectId={projectId} />
        <div className="board-wrap workspace-panel">{sectionPanel(place, params)}</div>
      </div>
    </div>
  );
}
