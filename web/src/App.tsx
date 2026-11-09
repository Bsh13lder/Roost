import { Suspense, lazy, type ReactNode } from "react";
import { Navigate, Route, Routes, useParams, useSearchParams } from "react-router-dom";
import { AuthProvider, useAuth } from "./hooks/useAuth";
import { ToastProvider } from "./ui/Toast";
import { Layout } from "./components/Layout";
import { Login } from "./pages/Login";
import { PickAChat } from "./pages/PickAChat";
import { Chat } from "./pages/Chat";
import { ALL_TASKS_HREF } from "./pages/boardPaths";
import { PageLoading } from "./components/PageLoading";
import { panelPage, type PanelPage } from "./components/panel/panelTabs";

// Pages that are their own chunks: a routine's run log (routines plan), and the Board, a project, the new-bot
// form, a room and a bot's instructions (lead task 03), so the entry holds only the shell and the chat.
const RoutineLog = lazy(() => import("./pages/RoutineLog").then((module) => ({ default: module.RoutineLog })));
const Board = lazy(() => import("./pages/Board").then((module) => ({ default: module.Board })));
const Project = lazy(() => import("./pages/Project").then((module) => ({ default: module.Project })));
const NewBot = lazy(() => import("./pages/NewBot").then((module) => ({ default: module.NewBot })));
const Room = lazy(() => import("./pages/Room").then((module) => ({ default: module.Room })));
const Routines = lazy(() => import("./pages/Routines").then((module) => ({ default: module.Routines })));
const Instructions = lazy(() => import("./pages/Instructions").then((module) => ({ default: module.Instructions })));

// A lazy page with the calm loading line while its chunk arrives.
const lazyPage = (page: ReactNode) => <Suspense fallback={<PageLoading />}>{page}</Suspense>;

function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <p className="app-loading">Loading&hellip;</p>;
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

// The old Profile and Desk addresses open the bot panel on the page ?tab= names (an old tab maps to its new page;
// a missing one opens `fallback`).
function ToPanel({ fallback }: { fallback: PanelPage }) {
  const { botId } = useParams<{ botId: string }>();
  const [params] = useSearchParams();
  const tab = panelPage(params.get("tab")) ?? fallback;
  return <Navigate to={`/bots/${botId}?panel=${tab}`} replace />;
}

// /board/projects, the old list of projects, opens the Tasks area on All tasks: its rail lists them now.
function ToProjectsTab() {
  return <Navigate to={ALL_TASKS_HREF} replace />;
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route path="/" element={<PickAChat />} />
        <Route path="/bots/new" element={lazyPage(<NewBot />)} />
        <Route path="/bots/:botId" element={<Chat />} />
        <Route path="/bots/:botId/profile" element={<ToPanel fallback="profile" />} />
        <Route path="/bots/:botId/instructions" element={lazyPage(<Instructions />)} />
        <Route path="/bots/:botId/routines/:routineId/log" element={lazyPage(<RoutineLog />)} />
        <Route path="/board" element={lazyPage(<Board />)} />
        <Route path="/routines" element={lazyPage(<Routines />)} />
        <Route path="/board/projects" element={<ToProjectsTab />} />
        <Route path="/board/projects/:projectId" element={lazyPage(<Project />)} />
        <Route path="/bots/:botId/desk" element={<ToPanel fallback="computer" />} />
        <Route path="/bots/:botId/board" element={<Navigate to="/board" replace />} />
        <Route path="/rooms/:roomId" element={lazyPage(<Room />)} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export function App() {
  return (
    <AuthProvider>
      <ToastProvider>
        <AppRoutes />
      </ToastProvider>
    </AuthProvider>
  );
}
