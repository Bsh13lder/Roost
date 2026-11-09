import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { TasksArea } from "../src/components/board/TasksArea";
import { TASK_SCOPE_STORAGE_KEY } from "../src/components/board/taskScope";
import type { TaskRowOut } from "../src/api/tasks";
import { ToastProvider } from "../src/ui/Toast";
import { makeProject, makeProjectDetail } from "./projectFixtures";
import { makeRow as task } from "./taskFixtures";
import { ApiError } from "../src/api/client";

const listTasksMock = vi.fn();
const countsMock = vi.fn();
const updateTaskMock = vi.fn();
const deleteTaskMock = vi.fn();
const restoreTaskMock = vi.fn();
vi.mock("../src/api/tasks", () => ({
  listTasks: (...a: unknown[]) => listTasksMock(...a),
  getTaskCounts: (...a: unknown[]) => countsMock(...a),
  updateTask: (...a: unknown[]) => updateTaskMock(...a),
  deleteTask: (...a: unknown[]) => deleteTaskMock(...a),
  restoreTask: (...a: unknown[]) => restoreTaskMock(...a),
  parseQuickLine: vi.fn(), createTask: vi.fn(), completeTask: vi.fn(), getTask: vi.fn(), failTask: vi.fn(),
  keepTask: vi.fn(), moveOverdue: vi.fn(), restoreDues: vi.fn(), updateStep: vi.fn(), reopenTask: vi.fn(),
}));
const listProjectsMock = vi.fn();
const createProjectMock = vi.fn();
const getProjectMock = vi.fn();
vi.mock("../src/api/projects", () => ({
  listProjects: (...a: unknown[]) => listProjectsMock(...a),
  createProject: (...a: unknown[]) => createProjectMock(...a),
  getProject: (...a: unknown[]) => getProjectMock(...a),
}));
let live = { bots: {}, boardVersion: { tasks: 0, money: 0 } };
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => live }));
vi.mock("../src/api/dates", () => ({ parseDate: vi.fn().mockResolvedValue({ due_date: null }) }));

const progress = (open: number) => ({ done: 0, failed: 0, total: open, open, overdue: 0, steps_done: 0, steps_total: 0, planned_total: "0.00" });
const GARDEN = { ...makeProject({ id: "p1", name: "Garden", progress: progress(2) }), pinned: true };
const KITCHEN = makeProject({ id: "p2", name: "Kitchen", color: "#3b82f6", progress: progress(0) });
const SHED = makeProject({ id: "p3", name: "Old shed", status: "archived" });
const SOW = task({ id: "t1", title: "Sow the beans", project_id: "p1", due_date: "2026-10-20", due_bucket: "today", steps: [] });
const TILES = task({ id: "t2", title: "Pick the tiles", project_id: "p2", due_date: "2026-10-20", due_bucket: "today", steps: [] });
const POST = task({ id: "t3", title: "Post the letter", project_id: null, due_date: "2026-10-20", due_bucket: "today", steps: [] });
const RING = task({ id: "t4", title: "Ring Grandma", project_id: null, due_date: null, due_bucket: "none", steps: [] });

function Where() {
  return <output aria-label="Address">{useLocation().search}</output>;
}

function area(start = "/board?tab=tasks") {
  return render(
    <MemoryRouter initialEntries={[start]}>
      <ToastProvider>
        <TasksArea />
        <Where />
      </ToastProvider>
    </MemoryRouter>,
  );
}

const address = () => screen.getByRole("status", { name: "Address" });
const asked = () => listTasksMock.mock.calls.map((call) => call[0]) as Array<Record<string, unknown>>;
const views = () => screen.getByRole("group", { name: "Task views" });
const chips = () => screen.getByRole("group", { name: "Filter by project" });
const serverFilter = (rows: TaskRowOut[], projectId?: string) =>
  !projectId ? rows : rows.filter((row) => row.project_id === (projectId === "none" ? null : projectId));

beforeEach(() => {
  live = { bots: {}, boardVersion: { tasks: 0, money: 0 } };
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-20T10:00:00Z"));
  listProjectsMock.mockReset().mockResolvedValue([KITCHEN, GARDEN, SHED]);
  createProjectMock.mockReset();
  updateTaskMock.mockReset().mockResolvedValue(SOW);
  deleteTaskMock.mockReset().mockResolvedValue(undefined);
  restoreTaskMock.mockReset().mockResolvedValue(SOW);
  getProjectMock.mockReset().mockImplementation(async (id: string) => makeProjectDetail({ id }));
  countsMock.mockReset().mockImplementation(async (projectId?: string) => (
    projectId === "none" ? { overdue: 0, today: 1, upcoming_14: 0, someday: 1, done_week: 2, open: 2 }
      : { overdue: 1, today: 2, upcoming_14: 4, someday: 0, done_week: 0, open: 4 }));
  listTasksMock.mockReset().mockImplementation(async (filter: { view?: string; status?: string; projectId?: string }) => {
    const byView: Record<string, TaskRowOut[]> = { today: [SOW, TILES, POST], board: [SOW, TILES, POST] };
    if (filter.status === "open" && !filter.view) return serverFilter([POST, RING], filter.projectId);
    return serverFilter(byView[filter.view ?? ""] ?? [], filter.projectId);
  });
});
afterEach(() => { cleanup(); vi.useRealTimers(); window.localStorage.clear(); });

describe("the Workspace's Tasks: Today · Inbox · Upcoming", () => {
  it("opens on Today, with Someday, Overdue and Done behind More, and no quick-add line of its own", async () => {
    area();
    const buttons = within(views()).getAllByRole("button").map((button) => button.getAttribute("aria-label") ?? button.textContent);
    expect(buttons.slice(0, 3).map((text) => text?.replace(/\d+$/, ""))).toEqual(["Today", "Inbox", "Upcoming"]);
    expect(within(views()).getByRole("button", { name: /^Today/ })).toHaveAttribute("aria-pressed", "true");
    expect(await screen.findByText("Pick the tiles")).toBeInTheDocument();
    expect(screen.queryByLabelText("New task")).toBeNull();
    await userEvent.click(within(views()).getByRole("button", { name: "More views" }));
    expect(screen.getByRole("menuitem", { name: "Someday" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Overdue" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("menuitem", { name: "Done" }));
    expect(address()).toHaveTextContent("view=done");
  });

  it("wears the server's counts: Today is overdue plus today, Inbox the open tasks with no project", async () => {
    area();
    await waitFor(() => expect(within(views()).getByRole("button", { name: /^Today/ })).toHaveTextContent("3"));
    await waitFor(() => expect(within(views()).getByRole("button", { name: /^Inbox/ })).toHaveTextContent("2"));
    expect(within(views()).getByRole("button", { name: /^Upcoming/ })).toHaveTextContent("4");
    expect(countsMock).toHaveBeenCalledWith("none");
  });

  it("Inbox lists every open task with no project, and hides the project chips", async () => {
    area();
    await userEvent.click(within(views()).getByRole("button", { name: /^Inbox/ }));
    expect(address()).toHaveTextContent("view=inbox");
    expect(await screen.findByText("Ring Grandma")).toBeInTheDocument();
    expect(screen.getByText("Post the letter")).toBeInTheDocument();
    expect(asked()).toContainEqual(expect.objectContaining({ status: "open", projectId: "none" }));
    expect(screen.queryByRole("group", { name: "Filter by project" })).toBeNull();
  });

  it("List · Kanban stays a toggle, and Kanban asks the board view within the chip picked", async () => {
    area("/board?tab=tasks&project=p1");
    await userEvent.click(within(screen.getByRole("group", { name: "Task layout" })).getByRole("button", { name: "Kanban" }));
    expect(address()).toHaveTextContent("layout=kanban");
    await waitFor(() => expect(asked()).toContainEqual(expect.objectContaining({ view: "board", projectId: "p1" })));
  });
});

describe("the project chips", () => {
  it("are All, the pinned projects first, the others, then No project; archived ones are not chips", async () => {
    area();
    await within(chips()).findByRole("button", { name: "Garden" });
    const names = within(chips()).getAllByRole("button").map((button) => button.textContent);
    expect(names).toEqual(["All", "Garden", "Kitchen", "No project"]);
    expect(within(chips()).getByRole("button", { name: "All" })).toHaveAttribute("aria-pressed", "true");
  });

  it("a chip narrows the tasks to its project, shows its card with Open project, and is remembered", async () => {
    area();
    await userEvent.click(await within(chips()).findByRole("button", { name: "Kitchen" }));
    expect(address()).toHaveTextContent("project=p2");
    expect(await screen.findByRole("link", { name: "Open project ›" })).toHaveAttribute("href", "/board/projects/p2");
    await waitFor(() => expect(screen.queryByText("Sow the beans")).toBeNull());
    expect(asked()).toContainEqual(expect.objectContaining({ view: "today", projectId: "p2" }));
    expect(window.localStorage.getItem(TASK_SCOPE_STORAGE_KEY)).toBe("p2");
  });

  it("No project narrows to the tasks with none; All drops the filter", async () => {
    area();
    await userEvent.click(within(chips()).getByRole("button", { name: "No project" }));
    expect(address()).toHaveTextContent("project=inbox");
    expect(await screen.findByText("Post the letter")).toBeInTheDocument();
    await userEvent.click(within(chips()).getByRole("button", { name: "All" }));
    expect(address()).not.toHaveTextContent("project=");
  });

  it("an archived project picked from an old link still shows as a chip", async () => {
    area("/board?tab=tasks&project=p3");
    expect(await within(chips()).findByRole("button", { name: "Old shed" })).toHaveAttribute("aria-pressed", "true");
  });

  it("their menu holds All money (the old Money page) and New project, which makes one and picks it", async () => {
    createProjectMock.mockResolvedValue(makeProject({ id: "p9", name: "Balcony" }));
    area();
    await userEvent.click(screen.getByRole("button", { name: "Projects and money" }));
    expect(screen.getByRole("menuitem", { name: "All money" })).toHaveAttribute("href", "/board?tab=money");
    await userEvent.click(screen.getByRole("menuitem", { name: "New project" }));
    const sheet = await screen.findByRole("dialog", { name: "New project" });
    await userEvent.type(within(sheet).getByLabelText("Name"), "Balcony");
    await userEvent.click(within(sheet).getByRole("button", { name: "Create project" }));
    await waitFor(() => expect(address()).toHaveTextContent("project=p9"));
  });

  it("a project the server no longer knows shows the calm gone state, with Show all tasks", async () => {
    countsMock.mockImplementation(async (projectId?: string) => {
      if (projectId === "p1") throw new ApiError(404, "Project not found");
      return { overdue: 0, today: 0, upcoming_14: 0, someday: 0, done_week: 0, open: 0 };
    });
    area("/board?tab=tasks&project=p1");
    expect(await screen.findByText("This project is gone.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Show all tasks" }));
    expect(within(chips()).getByRole("button", { name: "All" })).toHaveAttribute("aria-pressed", "true");
  });
});

describe("a task row in the Workspace", () => {
  const rowOf = async (title: string) => (await screen.findByText(title)).closest("[role=row]") as HTMLElement;

  it("wears its project as a pill that opens the project's page", async () => {
    area();
    const row = await rowOf("Sow the beans");
    await waitFor(() => expect(within(row).getAllByRole("link", { name: "Garden" })[0]).toHaveAttribute("href", "/board/projects/p1"));
  });

  it("Move to… puts it in another project, with Undo", async () => {
    area();
    const row = await rowOf("Sow the beans");
    await within(row).findAllByRole("link", { name: "Garden" });
    await userEvent.click(within(row).getByRole("button", { name: "More for Sow the beans" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Move to…" }));
    const sheet = await screen.findByRole("dialog", { name: "Move “Sow the beans” to…" });
    await userEvent.click(within(sheet).getByRole("button", { name: "Kitchen" }));
    await waitFor(() => expect(updateTaskMock).toHaveBeenCalledWith("t1", { project_id: "p2" }));
    await userEvent.click(await screen.findByRole("button", { name: "Undo" }));
    await waitFor(() => expect(updateTaskMock).toHaveBeenLastCalledWith("t1", { project_id: "p1" }));
  });

  it("Delete removes it, and Undo brings the same task back", async () => {
    area();
    const row = await rowOf("Post the letter");
    await userEvent.click(within(row).getByRole("button", { name: "More for Post the letter" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Delete" }));
    await waitFor(() => expect(deleteTaskMock).toHaveBeenCalledWith("t3"));
    expect(await screen.findByText("Deleted “Post the letter”")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Undo" }));
    await waitFor(() => expect(restoreTaskMock).toHaveBeenCalledWith("t3"));
  });
});
