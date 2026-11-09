import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { todayCount } from "../src/components/board/todayCount";
import { TasksBoard, type TasksBoardProps } from "../src/components/board/TasksBoard";
import type { TaskRowOut } from "../src/api/tasks";
import type { BotOut } from "../src/api/types";
import { ToastProvider } from "../src/ui/Toast";
import { makeBot } from "./fixtures";
import { makeProject } from "./projectFixtures";
import { makeQuickLine, makeRow as task, makeTaskDetail } from "./taskFixtures";

const listTasksMock = vi.fn();
const createTaskMock = vi.fn();
const completeTaskMock = vi.fn();
const keepTaskMock = vi.fn();
const failTaskMock = vi.fn();
const getTaskMock = vi.fn();
const parseQuickLineMock = vi.fn();
const reopenTaskMock = vi.fn();
const deleteTaskMock = vi.fn();
const moveOverdueMock = vi.fn();
const restoreDuesMock = vi.fn();
const updateTaskMock = vi.fn();
const countsMock = vi.fn();
vi.mock("../src/api/tasks", () => ({
  parseQuickLine: (...a: unknown[]) => parseQuickLineMock(...a),
  failTask: (...a: unknown[]) => failTaskMock(...a),
  keepTask: (...a: unknown[]) => keepTaskMock(...a),
  listTasks: (...a: unknown[]) => listTasksMock(...a),
  createTask: (...a: unknown[]) => createTaskMock(...a),
  completeTask: (...a: unknown[]) => completeTaskMock(...a),
  getTask: (...a: unknown[]) => getTaskMock(...a),
  getTaskCounts: (...a: unknown[]) => countsMock(...a),
  moveOverdue: (...a: unknown[]) => moveOverdueMock(...a),
  restoreDues: (...a: unknown[]) => restoreDuesMock(...a),
  updateTask: (...a: unknown[]) => updateTaskMock(...a),
  updateStep: vi.fn(),
  reopenTask: (...a: unknown[]) => reopenTaskMock(...a),
  deleteTask: (...a: unknown[]) => deleteTaskMock(...a),
}));
const listProjectsMock = vi.fn();
vi.mock("../src/api/projects", () => ({ listProjects: (...a: unknown[]) => listProjectsMock(...a) }));
const BOTS: Record<string, BotOut> = { "bot-1": makeBot({ id: "bot-1", name: "Helper" }) };
let live = { bots: BOTS, boardVersion: { tasks: 0, money: 0 } };
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => live }));
const parseDateMock = vi.fn().mockResolvedValue({ due_date: null });
vi.mock("../src/api/dates", () => ({ parseDate: (text: string) => parseDateMock(text) }));

// Tue 20 Oct 2026 in Madrid.
const SINK = task({ project_id: "p1", created_by_bot: "bot-1", due_date: "2026-10-16T09:00:00+02:00", priority: "urgent" });
const GADGET = task({ id: "t2", title: "Buy the gadget", due_date: "2026-10-20", steps: [], tainted: true, due_bucket: "today" });
const TOMORROW = task({ id: "t3", title: "Call plumber", due_date: "2026-10-21", steps: [], due_bucket: "tomorrow", priority: "low" });
const LATER = task({ id: "t4", title: "Book flights", due_date: "2026-10-22", steps: [], due_bucket: "week", priority: "high" });
const DATA: Record<string, TaskRowOut[]> = {
  overdue: [SINK], today: [GADGET], upcoming: [TOMORROW, LATER], someday: [], done: [],
};

function Where() {
  const location = useLocation();
  return <output aria-label="Address">{location.search}</output>;
}

function board(props: TasksBoardProps = {}, start = "/board?tab=tasks") {
  const tree = () => (
    <MemoryRouter initialEntries={[start]}>
      <ToastProvider>
        <TasksBoard {...props} />
        <Where />
      </ToastProvider>
    </MemoryRouter>
  );
  const view = render(tree());
  return { ...view, again: () => view.rerender(tree()) };
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-20T10:00:00Z"));
  live = { bots: BOTS, boardVersion: { tasks: 0, money: 0 } };
  for (const mock of [reopenTaskMock, deleteTaskMock, listTasksMock, createTaskMock, completeTaskMock, keepTaskMock,
    failTaskMock, getTaskMock, moveOverdueMock, restoreDuesMock, updateTaskMock]) mock.mockReset();
  listProjectsMock.mockReset().mockResolvedValue([makeProject({ id: "p1", name: "Renovation" })]);
  countsMock.mockReset().mockResolvedValue({ overdue: 1, today: 1, upcoming_14: 2, someday: 0, done_week: 3 });
  listTasksMock.mockImplementation(async (first: unknown, second?: { projectId?: string }) => {
    if (typeof first === "object" && first !== null) return DATA[(first as { view: string }).view] ?? [];
    return second?.projectId ? [GADGET, SINK] : [];
  });
  getTaskMock.mockResolvedValue(makeTaskDetail());
  parseQuickLineMock.mockReset().mockImplementation(async ({ text, project_id: projectId }: { text: string; project_id?: string }) =>
    makeQuickLine({ title: text, ready: true, project: projectId ? { id: projectId, name: "Garden", currency: "EUR", color: "#22c55e" } : null }));
});
afterEach(() => { cleanup(); vi.useRealTimers(); window.localStorage.clear(); });

const rowOf = async (title: string) => (await screen.findByText(title)).closest("[role=row]") as HTMLElement;
const address = () => screen.getByRole("status", { name: "Address" });
const lastCall = () => listTasksMock.mock.calls[listTasksMock.mock.calls.length - 1][0];

describe("TasksBoard rows", () => {
  it("shows each task's project, steps and maker on one line, and marks web content", async () => {
    board();
    const sink = await rowOf("Fix the sink");
    expect(await within(sink).findAllByText("Renovation")).not.toHaveLength(0);
    expect(within(sink).getByTitle("1 of 2 steps · click to show")).toHaveTextContent("1/2");
    expect(within(sink).getByText("by Helper")).toBeInTheDocument();
    expect(within(sink).getByText("4d overdue")).toBeInTheDocument();
    expect(within(await rowOf("Buy the gadget")).getByText("from web content")).toBeInTheDocument();
    expect(listProjectsMock).toHaveBeenCalledWith(true);
  });

  it("opens one task's steps from its chip and leaves the others closed", async () => {
    DATA.today = [task({ id: "t2", title: "Second", due_date: "2026-10-20", steps: [{ id: "x", title: "Other step", done: false }] })];
    const user = userEvent.setup();
    board();
    await user.click(await screen.findByRole("button", { name: "Show the 2 steps of Fix the sink" }));
    expect(screen.getByText("Fit it")).toBeInTheDocument();
    expect(screen.queryByText("Other step")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Hide the 2 steps of Fix the sink" }));
    expect(screen.queryByText("Fit it")).toBeNull();
    DATA.today = [GADGET];
  });

  it("a click on the title opens the task's drawer at ?task=, and Close puts the address back", async () => {
    const user = userEvent.setup();
    board();
    await user.click(await screen.findByRole("button", { name: "Fix the sink" }));
    expect(address()).toHaveTextContent("?tab=tasks&task=t1");
    expect(await screen.findByRole("dialog", { name: "Fix the sink" })).toBeInTheDocument();
    expect(getTaskMock).toHaveBeenCalledWith("t1");
    await user.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(address()).toHaveTextContent(/^\?tab=tasks$/);
  });

  it("Esc closes the drawer", async () => {
    const user = userEvent.setup();
    board();
    await user.click(await screen.findByRole("button", { name: "Fix the sink" }));
    expect(await screen.findByRole("dialog", { name: "Fix the sink" })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("the row's menu opens the drawer or marks the task failed", async () => {
    failTaskMock.mockResolvedValue(task({ status: "failed" }));
    const user = userEvent.setup();
    board();
    await user.click(await screen.findByRole("button", { name: "More for Fix the sink" }));
    await user.click(await screen.findByRole("menuitem", { name: "Mark failed" }));
    expect(failTaskMock).toHaveBeenCalledWith("t1");
    await waitFor(() => expect(listTasksMock.mock.calls.length).toBeGreaterThan(2));
    await user.click(screen.getByRole("button", { name: "More for Fix the sink" }));
    await user.click(await screen.findByRole("menuitem", { name: "Open" }));
    expect(await screen.findByRole("dialog", { name: "Fix the sink" })).toBeInTheDocument();
  });

  it("completes a task, and offers Keep only on a web-made one", async () => {
    completeTaskMock.mockResolvedValue(task({ status: "done" }));
    keepTaskMock.mockResolvedValue(task({ id: "t2", tainted: false }));
    const user = userEvent.setup();
    board();
    expect(within(await rowOf("Fix the sink")).queryByRole("button", { name: /^Keep/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: "Complete Fix the sink" }));
    expect(completeTaskMock).toHaveBeenCalledWith("t1");
    await user.click(within(await rowOf("Buy the gadget")).getByRole("button", { name: "Keep Buy the gadget as yours" }));
    expect(keepTaskMock).toHaveBeenCalledWith("t2");
  });

  it("completing shows Undo, which reopens and removes the next repeat", async () => {
    completeTaskMock.mockResolvedValue({ ...task({ status: "done" }), next_id: "t9" });
    reopenTaskMock.mockResolvedValue(task());
    deleteTaskMock.mockResolvedValue(undefined);
    const user = userEvent.setup();
    board();
    await user.click(await screen.findByRole("checkbox", { name: "Complete Fix the sink" }));
    expect(await screen.findByText("“Fix the sink” done")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Undo" }));
    await waitFor(() => expect(reopenTaskMock).toHaveBeenCalledWith("t1"));
    await waitFor(() => expect(deleteTaskMock).toHaveBeenCalledWith("t9"));
  });

  it("Undo of a plain complete only reopens", async () => {
    completeTaskMock.mockResolvedValue({ ...task({ status: "done" }), next_id: null });
    reopenTaskMock.mockResolvedValue(task());
    const user = userEvent.setup();
    board();
    await user.click(await screen.findByRole("checkbox", { name: "Complete Fix the sink" }));
    await user.click(await screen.findByRole("button", { name: "Undo" }));
    await waitFor(() => expect(reopenTaskMock).toHaveBeenCalledWith("t1"));
    expect(deleteTaskMock).not.toHaveBeenCalled();
  });

  it("reloads when a tasks_changed frame arrives", async () => {
    const view = board();
    await screen.findByText("Fix the sink");
    const before = listTasksMock.mock.calls.length;
    live = { bots: BOTS, boardVersion: { tasks: 1, money: 0 } };
    view.again();
    await waitFor(() => expect(listTasksMock.mock.calls.length).toBeGreaterThan(before));
  });

  it("says there is nothing here in the shared words", async () => {
    DATA.overdue = [];
    DATA.today = [];
    board();
    expect(await screen.findByText("Nothing here. Nice.")).toBeInTheDocument();
    DATA.overdue = [SINK];
    DATA.today = [GADGET];
  });

  it("has no quick-add line of its own in the Workspace: the pill adds", async () => {
    board();
    await screen.findByText("Fix the sink");
    expect(screen.queryByLabelText("New task")).toBeNull();
  });
});

describe("TasksBoard views", () => {
  it("switches views and keeps the view in the URL", async () => {
    const user = userEvent.setup();
    board();
    const today = await screen.findByRole("button", { name: /^Today/ });
    expect(today).toHaveAttribute("aria-pressed", "true");
    expect(within(today).getByText("2")).toBeInTheDocument(); // overdue + today
    await user.click(screen.getByRole("button", { name: "More views" }));
    await user.click(await screen.findByRole("menuitem", { name: "Someday" }));
    expect(address()).toHaveTextContent("view=someday");
    await waitFor(() => expect(lastCall()).toMatchObject({ view: "someday", sort: "due" }));
    await user.click(screen.getByRole("button", { name: /^Today/ }));
    expect(address()).not.toHaveTextContent("view=");
  });

  it("starts on the view in the address", async () => {
    board({}, "/board?tab=tasks&view=done&q=sink&sort=priority");
    await waitFor(() => expect(lastCall()).toMatchObject({ view: "done", q: "sink", sort: "priority" }));
    expect(screen.getByRole("button", { name: "More views" })).toHaveTextContent("Done");
  });

  it("sorts by priority", async () => {
    const user = userEvent.setup();
    board();
    await user.click(await screen.findByRole("combobox", { name: "Sort" }));
    await user.click(await screen.findByRole("option", { name: "Sort: Priority" }));
    expect(address()).toHaveTextContent("sort=priority");
    await waitFor(() => expect(lastCall()).toMatchObject({ sort: "priority" }));
  });

  it("groups Today as Overdue then Today", async () => {
    board();
    const headings = await screen.findAllByRole("heading", { level: 3 });
    expect(headings.map((h) => h.textContent)).toEqual(["Overdue", "Due today · Tue 20 Oct"]);
    expect(within(screen.getByRole("region", { name: "Overdue" })).getByText("Fix the sink")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Due today · Tue 20 Oct" })).getByText("Buy the gadget")).toBeInTheDocument();
  });

  it("Upcoming groups by day", async () => {
    board({}, "/board?tab=tasks&view=upcoming");
    const headings = await screen.findAllByRole("heading", { level: 3 });
    expect(headings.map((h) => h.textContent)).toEqual(["Tomorrow · Wed 21 Oct", "Thu 22 Oct"]);
  });

  it("Reschedule all opens the popover for every overdue task, with Undo", async () => {
    moveOverdueMock.mockResolvedValue({ moved: [{ id: "t1", due_date: "2026-10-16", reminder_at: null, pre_reminders: [] }] });
    restoreDuesMock.mockResolvedValue({ restored: 1 });
    const user = userEvent.setup();
    board();
    await user.click(await screen.findByRole("button", { name: "Reschedule all" }));
    expect(await screen.findByRole("dialog", { name: "Reschedule 1 overdue task" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^Tomorrow/ }));
    await waitFor(() => expect(moveOverdueMock).toHaveBeenCalledWith("2026-10-21"));
    await user.click(await screen.findByRole("button", { name: "Undo" }));
    await waitFor(() => expect(restoreDuesMock).toHaveBeenCalledWith([{ id: "t1", due_date: "2026-10-16", reminder_at: null, pre_reminders: [] }]));
  });

  it("Expand all opens every task's steps; Collapse all closes them", async () => {
    DATA.today = [task({ id: "t2", title: "Second", due_date: "2026-10-20", steps: [{ id: "x", title: "Other step", done: false }] })];
    const user = userEvent.setup();
    board();
    await screen.findByText("Fix the sink");
    await user.click(screen.getByRole("button", { name: "More options" }));
    await user.click(await screen.findByRole("menuitem", { name: "Expand all subtasks" }));
    expect(screen.getByText("Fit it")).toBeInTheDocument();
    expect(screen.getByText("Other step")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "More options" }));
    await user.click(await screen.findByRole("menuitem", { name: "Collapse all subtasks" }));
    expect(screen.queryByText("Fit it")).toBeNull();
    expect(screen.queryByText("Other step")).toBeNull();
    DATA.today = [GADGET];
  });

  it("keys move a cursor, complete, and switch views", async () => {
    completeTaskMock.mockResolvedValue(task({ status: "done" }));
    const user = userEvent.setup();
    board();
    const sink = await rowOf("Fix the sink");
    expect(sink).toHaveClass("is-cursor");
    await user.keyboard("j");
    expect(await rowOf("Buy the gadget")).toHaveClass("is-cursor");
    await user.keyboard("x");
    await waitFor(() => expect(completeTaskMock).toHaveBeenCalledWith("t2"));
    await user.keyboard("2");
    expect(address()).toHaveTextContent("view=upcoming");
  });

  it("t moves the task at the cursor to tomorrow", async () => {
    updateTaskMock.mockResolvedValue(task());
    const user = userEvent.setup();
    board();
    await screen.findByText("Fix the sink");
    await user.keyboard("t");
    await waitFor(() => expect(updateTaskMock).toHaveBeenCalledWith("t1", { due_date: "2026-10-21T09:00" }));
  });
});

describe("TasksBoard on a project's page", () => {
  it("shows Overdue, Next up, Later and Done without the project column", async () => {
    window.localStorage.setItem("roost.show-finished.v1", "1"); // finished tasks shown (lead task 14)
    listTasksMock.mockImplementation(async () => [
      task({ id: "t3", title: "Fix the fence", status: "failed", project_id: "p1", completed_at: "2026-10-14T18:00:00+00:00" }),
      task({ id: "t6", title: "Someday job", due_date: null, steps: [], project_id: "p1" }),
      task({ id: "t7", title: "Soon job", due_date: "2026-10-22", steps: [], project_id: "p1" }),
      SINK,
    ]);
    board({ projectId: "p1" });
    await screen.findByText("Fix the sink");
    expect((await screen.findAllByRole("heading", { level: 3 })).map((h) => h.textContent))
      .toEqual(["Overdue", "Next up", "Later", "Done"]);
    expect(within(await rowOf("Fix the fence")).getByRole("checkbox", { name: "Complete Fix the fence" })).toBeDisabled();
    expect(within(await rowOf("Fix the sink")).queryByText("Renovation")).not.toBeInTheDocument();
    expect(listTasksMock).toHaveBeenCalledWith("all", { projectId: "p1" });
    expect(listProjectsMock).not.toHaveBeenCalled();
    expect(countsMock).not.toHaveBeenCalled();
    expect(screen.queryByLabelText("Search tasks")).toBeNull();
    expect(address()).not.toHaveTextContent("view");
  });

  it("adds a task into the project", async () => {
    createTaskMock.mockResolvedValue(task({ id: "t4", title: "Buy seeds", project_id: "p1" }));
    const user = userEvent.setup();
    board({ projectId: "p1", currency: "EUR" });
    await user.type(await screen.findByLabelText("New task"), "Buy seeds");
    await user.click(screen.getByRole("button", { name: "Add" }));
    expect(parseQuickLineMock).toHaveBeenLastCalledWith({ text: "Buy seeds", project_id: "p1" });
    expect(createTaskMock).toHaveBeenCalledWith({ title: "Buy seeds", project_id: "p1" });
  });

  it("shows a task's money left or over, as the server reckons it", async () => {
    listTasksMock.mockImplementation(async () => [
      task({ project_id: "p1", money: { planned: "100.00", spent: "80.00", left: "20.00", currency: "EUR", over: false } }),
      task({ id: "t2", title: "Fix the fence", project_id: "p1", money: { planned: "100.00", spent: "130.00", left: "-30.00", currency: "EUR", over: true } }),
      task({ id: "t3", title: "Buy seeds", project_id: "p1" }),
    ]);
    board({ projectId: "p1", currency: "EUR" });
    expect(within(await rowOf("Fix the sink")).getAllByText("€20 left")).not.toHaveLength(0);
    expect(within(await rowOf("Fix the fence")).getAllByText("€30 over")).not.toHaveLength(0);
    expect(within(await rowOf("Buy seeds")).queryByText(/^€\d+ (left|over)$/)).toBeNull();
  });
});

// Lead task 04: the Board with nothing in its address lands on Tasks › Today.
describe("the Board's landing view", () => {
  it("with no view in the address, Tasks opens on Today: what is late and what is due today", async () => {
    board({}, "/board");
    const views = await screen.findByRole("group", { name: "Task views" });
    expect(within(views).getByRole("button", { name: /^Today/ })).toHaveAttribute("aria-pressed", "true");
    await waitFor(() => expect(listTasksMock).toHaveBeenCalledWith(expect.objectContaining({ view: "today" })));
    expect(listTasksMock).toHaveBeenCalledWith(expect.objectContaining({ view: "overdue" }));
  });

  it("a view in the address still wins", async () => {
    board({}, "/board?view=upcoming");
    const views = await screen.findByRole("group", { name: "Task views" });
    expect(within(views).getByRole("button", { name: /^Upcoming/ })).toHaveAttribute("aria-pressed", "true");
  });
});

// Lead task 05: one Today number everywhere, the Today list's own set (open tasks overdue or due today).
describe("one Today number", () => {
  it("the Today tab counts overdue plus due today", async () => {
    countsMock.mockResolvedValue({ overdue: 3, today: 2, upcoming_14: 0, someday: 0, done_week: 0 });
    board();
    const views = screen.getByRole("group", { name: "Task views" });
    await waitFor(() => expect(within(views).getByRole("button", { name: /^Today/ })).toHaveTextContent("5"));
  });

  it("todayCount is overdue plus due today, nothing else", () => {
    expect(todayCount({ overdue: 3, today: 2, upcoming_14: 7, someday: 4, done_week: 9 })).toBe(5);
  });
});

// Lead task 14: Show finished, off by default, remembered in this browser.
describe("Show finished on the task list", () => {
  const DONE_TODAY = task({ id: "t8", title: "Water plants", status: "done", due_date: "2026-10-20", steps: [], due_bucket: "today",
    completed_at: "2026-10-20T08:00:00Z" });
  const DONE_YESTERDAY = task({ id: "t9", title: "Post the letter", status: "done", due_date: "2026-10-19", steps: [],
    due_bucket: "overdue", completed_at: "2026-10-19T08:00:00Z" });
  afterEach(() => window.localStorage.clear());

  it("is off: Today asks for open tasks only and shows no finished one", async () => {
    board();
    await rowOf("Buy the gadget");
    expect(screen.getByRole("switch", { name: "Show finished" })).toHaveAttribute("aria-checked", "false");
    expect(listTasksMock.mock.calls.map(([first]) => (first as { view: string }).view)).not.toContain("done");
  });

  it("on: Today asks the server with include_finished and shows its done tasks quiet, after the open ones", async () => {
    DATA.done = [DONE_TODAY, DONE_YESTERDAY];
    listTasksMock.mockImplementation(async (first: { view: string; includeFinished?: boolean }) =>
      (first.view === "today" && first.includeFinished ? [DONE_TODAY, ...(DATA.today ?? [])] : DATA[first.view] ?? []));
    const user = userEvent.setup();
    board();
    await rowOf("Buy the gadget");
    await user.click(screen.getByRole("switch", { name: "Show finished" }));
    const water = await rowOf("Water plants");
    expect(water).toHaveClass("is-done");
    const dueToday = screen.getByRole("heading", { name: /^Due today/ }).closest("section") as HTMLElement;
    expect(within(dueToday).getAllByRole("row").map((row) => row.textContent?.includes("Water plants"))).toEqual([false, true]);
    expect(screen.queryByText("Post the letter")).not.toBeInTheDocument();
    const asked = listTasksMock.mock.calls.map(([filter]) => filter as { view: string; includeFinished?: boolean });
    expect(asked).toContainEqual(expect.objectContaining({ view: "today", includeFinished: true }));
    expect(asked).toContainEqual({ view: "overdue", sort: "due" }); // a finished task is never late
    expect(asked.some((filter) => filter.view === "done")).toBe(false); // no second fetch of the Done view
    expect(window.localStorage.getItem("roost.show-finished.v1")).toBe("1");
    DATA.done = [];
  });

  it("on: Upcoming and Someday ask with include_finished too, within the selection", async () => {
    window.localStorage.setItem("roost.show-finished.v1", "1");
    board({ scope: { kind: "inbox" } }, "/board?tab=tasks&view=someday");
    await waitFor(() => expect(listTasksMock).toHaveBeenCalledWith({ view: "someday", sort: "due", includeFinished: true, projectId: "none" }));
  });

  it("is not offered on the Done view, which is all finished tasks", async () => {
    board({}, "/board?tab=tasks&view=done");
    await screen.findByRole("group", { name: "Task layout" });
    expect(screen.queryByRole("switch", { name: "Show finished" })).not.toBeInTheDocument();
  });

  it("on a project's page hides the Done group while off, and says how many it hides", async () => {
    listTasksMock.mockImplementation(async () => [
      task({ id: "t3", title: "Fix the fence", status: "done", project_id: "p1", completed_at: "2026-10-14T18:00:00+00:00" }),
      SINK,
    ]);
    const user = userEvent.setup();
    board({ projectId: "p1" });
    await rowOf("Fix the sink");
    expect(screen.queryByText("Fix the fence")).not.toBeInTheDocument();
    expect(screen.getByText("1 finished hidden")).toBeInTheDocument();
    await user.click(screen.getByRole("switch", { name: "Show finished" }));
    expect(await rowOf("Fix the fence")).toHaveClass("is-done");
    expect(screen.getByRole("heading", { level: 3, name: "Done" })).toBeInTheDocument();
  });
});

// Board toggles: Made by bots on the list, remembered per screen.
describe("Made by bots on the task list", () => {
  it("off hides the tasks a bot made, says how many, and the Kanban keeps its own choice", async () => {
    const user = userEvent.setup();
    board({}, "/board?tab=tasks&view=overdue");
    await rowOf("Fix the sink");
    const toggle = screen.getByRole("switch", { name: "Made by bots" });
    expect(toggle).toHaveAttribute("aria-checked", "true");
    expect(screen.queryByRole("switch", { name: "Routines" })).not.toBeInTheDocument();
    await user.click(toggle);
    await waitFor(() => expect(screen.queryByText("Fix the sink")).not.toBeInTheDocument());
    expect(screen.getByText("1 by bots hidden")).toBeInTheDocument();
    expect(window.localStorage.getItem("roost.show.v1.board-list.botMade")).toBe("0");
    expect(window.localStorage.getItem("roost.show.v1.board-kanban.botMade")).toBeNull();
  });

  it("is offered on the Done view and on a project's page too", async () => {
    board({}, "/board?tab=tasks&view=done");
    expect(await screen.findByRole("switch", { name: "Made by bots" })).toBeInTheDocument();
    cleanup();
    board({ projectId: "p1" });
    await rowOf("Fix the sink");
    await userEvent.setup().click(screen.getByRole("switch", { name: "Made by bots" }));
    await waitFor(() => expect(screen.queryByText("Fix the sink")).not.toBeInTheDocument());
    expect(window.localStorage.getItem("roost.show.v1.project.botMade")).toBe("0");
  });
});
