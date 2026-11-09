import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { TasksBoard } from "../src/components/board/TasksBoard";
import type { TaskRowOut } from "../src/api/tasks";
import type { BotOut } from "../src/api/types";
import { ToastProvider } from "../src/ui/Toast";
import { makeBot } from "./fixtures";
import { makeProject } from "./projectFixtures";
import { makeQuickLine, makeRow as task } from "./taskFixtures";

const listTasksMock = vi.fn();
const createTaskMock = vi.fn();
const completeTaskMock = vi.fn();
const parseQuickLineMock = vi.fn();
const reopenTaskMock = vi.fn();
const deleteTaskMock = vi.fn();
const restoreDuesMock = vi.fn();
const updateTaskMock = vi.fn();
vi.mock("../src/api/tasks", () => ({
  parseQuickLine: (...a: unknown[]) => parseQuickLineMock(...a),
  failTask: vi.fn(),
  keepTask: vi.fn(),
  listTasks: (...a: unknown[]) => listTasksMock(...a),
  createTask: (...a: unknown[]) => createTaskMock(...a),
  completeTask: (...a: unknown[]) => completeTaskMock(...a),
  getTask: vi.fn().mockResolvedValue({}),
  getTaskCounts: vi.fn().mockResolvedValue({ overdue: 0, today: 0, upcoming_14: 0, someday: 0, done_week: 0 }),
  moveOverdue: vi.fn(),
  restoreDues: (...a: unknown[]) => restoreDuesMock(...a),
  updateTask: (...a: unknown[]) => updateTaskMock(...a),
  updateStep: vi.fn(),
  reopenTask: (...a: unknown[]) => reopenTaskMock(...a),
  deleteTask: (...a: unknown[]) => deleteTaskMock(...a),
}));
const listProjectsMock = vi.fn();
vi.mock("../src/api/projects", () => ({ listProjects: (...a: unknown[]) => listProjectsMock(...a) }));
const BOTS: Record<string, BotOut> = { "bot-1": makeBot({ id: "bot-1", name: "Helper" }) };
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => ({ bots: BOTS, boardVersion: { tasks: 0, money: 0 } }) }));
vi.mock("../src/api/dates", () => ({ parseDate: vi.fn().mockResolvedValue({ due_date: null }) }));

// Tue 20 Oct 2026 in Madrid.
const SINK = task({ id: "t1", title: "Fix the sink", project_id: "p1", due_date: "2026-10-21", due_bucket: "tomorrow",
  priority: "high", created_by_bot: "bot-1" });
const CALL = task({ id: "t2", title: "Call plumber", status: "in_progress", steps: [], due_date: null, due_bucket: "none" });
const PAINT = task({ id: "t3", title: "Paint walls", status: "done", steps: [], due_date: "2026-10-19", due_bucket: "overdue",
  completed_at: "2026-10-20T08:00:00Z" });
const DATA: TaskRowOut[] = [SINK, CALL, PAINT];

function Where() {
  const location = useLocation();
  return <output aria-label="Address">{location.search}</output>;
}

function board(start = "/board?tab=tasks&layout=kanban") {
  return render(
    <MemoryRouter initialEntries={[start]}>
      <ToastProvider>
        <TasksBoard />
        <Where />
      </ToastProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-20T10:00:00Z"));
  for (const mock of [reopenTaskMock, deleteTaskMock, createTaskMock, completeTaskMock, restoreDuesMock, updateTaskMock]) mock.mockReset();
  updateTaskMock.mockImplementation(async (id: string, patch: object) => ({ ...DATA.find((t) => t.id === id), ...patch }));
  listProjectsMock.mockReset().mockResolvedValue([makeProject({ id: "p1", name: "Casa Nueva", color: "#22c55e" })]);
  listTasksMock.mockReset().mockImplementation(async () => DATA);
  parseQuickLineMock.mockReset().mockImplementation(async ({ text, default_due: day }: { text: string; default_due?: string }) =>
    makeQuickLine({ title: text.replace(/\/Casa Nueva\s*/, "").trim(), ready: true, due_date: day ?? null,
      project: /\/Casa Nueva/.test(text) ? { id: "p1", name: "Casa Nueva", currency: "EUR", color: "#22c55e" } : null }));
});
afterEach(() => { cleanup(); vi.useRealTimers(); window.localStorage.clear(); });

const column = async (name: string) => (await screen.findByRole("region", { name })) as HTMLElement;
const card = async (title: string) => (await screen.findByText(title)).closest(".kcard") as HTMLElement;
const lastCall = () => listTasksMock.mock.calls[listTasksMock.mock.calls.length - 1][0];
const dataTransfer = () => {
  const store = new Map<string, string>();
  return { setData: (k: string, v: string) => store.set(k, v), getData: (k: string) => store.get(k) ?? "", effectAllowed: "", dropEffect: "" };
};

describe("KanbanBoard", () => {
  it("asks for the board view and puts each task in its status column with counts", async () => {
    window.localStorage.setItem("roost.show-finished.v1", "1"); // finished tasks shown (lead task 14)
    board();
    expect(within(await column("To do")).getByText("Fix the sink")).toBeInTheDocument();
    expect(within(await column("On it")).getByText("Call plumber")).toBeInTheDocument();
    expect(within(await column("Done")).getByText("Paint walls")).toBeInTheDocument();
    expect(lastCall()).toMatchObject({ view: "board", sort: "due" });
  });

  it("columns show counts and collapse", async () => {
    const user = userEvent.setup();
    board();
    const todo = await column("To do");
    expect(within(todo).getByLabelText("1 task")).toHaveTextContent("1");
    await user.click(within(todo).getByRole("button", { name: "Collapse To do" }));
    expect(within(await column("To do")).queryByText("Fix the sink")).toBeNull();
    expect(within(await column("To do")).getByLabelText("1 task")).toBeInTheDocument();
    expect(address()).toHaveTextContent("layout=kanban");
    await user.click(within(await column("To do")).getByRole("button", { name: "Expand To do" }));
    expect(within(await column("To do")).getByText("Fix the sink")).toBeInTheDocument();
  });

  it("+ pre-fills the column's value: Tomorrow sets the due, Casa types /Casa Nueva", async () => {
    const user = userEvent.setup();
    const view = board("/board?tab=tasks&layout=kanban&group=due");
    await user.click(await screen.findByRole("button", { name: "Add a task in Tomorrow" }));
    const dialog = await screen.findByRole("dialog", { name: "Add task in Tomorrow" });
    await user.type(within(dialog).getByRole("combobox", { name: "New task" }), "Buy tiles");
    await waitFor(() => expect(parseQuickLineMock).toHaveBeenCalledWith(expect.objectContaining({ default_due: "2026-10-21" })));
    createTaskMock.mockResolvedValue(task({ id: "n1" }));
    await user.click(within(dialog).getByRole("button", { name: "Add" }));
    await waitFor(() => expect(createTaskMock).toHaveBeenCalledWith(expect.objectContaining({ title: "Buy tiles", due_date: "2026-10-21" })));
    view.unmount();

    board("/board?tab=tasks&layout=kanban&group=project");
    await user.click(await screen.findByRole("button", { name: "Add a task in Casa Nueva" }));
    const second = await screen.findByRole("dialog", { name: "Add task in Casa Nueva" });
    expect(within(second).getByRole("combobox", { name: "New task" })).toHaveValue("/Casa Nueva ");
  });

  it("a Status On it + creates the task, then moves it to On it", async () => {
    const user = userEvent.setup();
    board();
    await user.click(await screen.findByRole("button", { name: "Add a task in On it" }));
    const dialog = await screen.findByRole("dialog", { name: "Add task in On it" });
    createTaskMock.mockResolvedValue(task({ id: "n1", title: "Sand floor" }));
    await user.type(within(dialog).getByRole("combobox", { name: "New task" }), "Sand floor");
    await user.click(within(dialog).getByRole("button", { name: "Add" }));
    await waitFor(() => expect(updateTaskMock).toHaveBeenCalledWith("n1", { status: "in_progress" }));
  });

  it("Done has no +", async () => {
    board();
    await column("Done");
    expect(screen.queryByRole("button", { name: "Add a task in Done" })).toBeNull();
    expect(screen.getByRole("button", { name: "Add a task in To do" })).toBeInTheDocument();
  });

  it("Move to… moves a card, with Undo", async () => {
    const user = userEvent.setup();
    board();
    await user.click(await screen.findByRole("button", { name: "More for Fix the sink" }));
    expect(screen.getByRole("menuitem", { name: "Reschedule…" })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "To do" })).toBeNull();
    await user.click(screen.getByRole("menuitem", { name: "On it" }));
    await waitFor(() => expect(updateTaskMock).toHaveBeenCalledWith("t1", { status: "in_progress" }));
    expect(await screen.findByText("“Fix the sink” moved to On it")).toBeInTheDocument();
    updateTaskMock.mockClear();
    await user.click(screen.getByRole("button", { name: "Undo" }));
    await waitFor(() => expect(updateTaskMock).toHaveBeenCalledWith("t1", { status: "todo" }));
  });

  it("Move to… Done completes the task, and from Done reopens it", async () => {
    window.localStorage.setItem("roost.show-finished.v1", "1"); // finished tasks shown (lead task 14)
    completeTaskMock.mockResolvedValue({ ...SINK, status: "done", next_id: null });
    reopenTaskMock.mockResolvedValue(PAINT);
    const user = userEvent.setup();
    board();
    await user.click(await screen.findByRole("button", { name: "More for Fix the sink" }));
    await user.click(screen.getByRole("menuitem", { name: "Done" }));
    await waitFor(() => expect(completeTaskMock).toHaveBeenCalledWith("t1"));
    await user.click(await screen.findByRole("button", { name: "More for Paint walls" }));
    await user.click(screen.getByRole("menuitem", { name: "On it" }));
    await waitFor(() => expect(reopenTaskMock).toHaveBeenCalledWith("t3"));
    await waitFor(() => expect(updateTaskMock).toHaveBeenCalledWith("t3", { status: "in_progress" }));
  });

  it("drag and drop moves a card", async () => {
    board();
    const source = await card("Fix the sink");
    const transfer = dataTransfer();
    fireEvent.dragStart(source, { dataTransfer: transfer });
    const target = await column("On it");
    fireEvent.dragOver(target, { dataTransfer: transfer });
    expect(target).toHaveClass("is-over");
    fireEvent.drop(target, { dataTransfer: transfer });
    await waitFor(() => expect(updateTaskMock).toHaveBeenCalledWith("t1", { status: "in_progress" }));
    expect(target).not.toHaveClass("is-over");
  });

  it("Bot columns are not drop targets, and Move to… leaves them out", async () => {
    const user = userEvent.setup();
    board("/board?tab=tasks&layout=kanban&group=bot");
    const source = await card("Fix the sink");
    const transfer = dataTransfer();
    fireEvent.dragStart(source, { dataTransfer: transfer });
    const you = await column("You");
    const over = fireEvent.dragOver(you, { dataTransfer: transfer });
    expect(over).toBe(true); // not prevented: the browser shows the not-allowed cursor
    fireEvent.drop(you, { dataTransfer: transfer });
    expect(updateTaskMock).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "More for Fix the sink" }));
    expect(screen.getByRole("menuitem", { name: "Reschedule…" })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "You" })).toBeNull();
  });

  it("dropping on Tomorrow sets the due at once; dropping on This week opens the date picker", async () => {
    board("/board?tab=tasks&layout=kanban&group=due");
    const source = await card("Call plumber");
    const transfer = dataTransfer();
    fireEvent.dragStart(source, { dataTransfer: transfer });
    fireEvent.drop(await column("Tomorrow"), { dataTransfer: transfer });
    await waitFor(() => expect(updateTaskMock).toHaveBeenCalledWith("t2", { due_date: "2026-10-21" }));
    fireEvent.dragStart(await card("Call plumber"), { dataTransfer: transfer });
    fireEvent.drop(await column("This week"), { dataTransfer: transfer });
    expect(await screen.findByRole("dialog", { name: "Reschedule “Call plumber”" })).toBeInTheDocument();
  });

  it("Overdue is not a drop target and finished past tasks are hidden under Due date", async () => {
    board("/board?tab=tasks&layout=kanban&group=due");
    const overdue = await column("Overdue");
    expect(screen.queryByText("Paint walls")).toBeNull();
    const transfer = dataTransfer();
    fireEvent.dragStart(await card("Fix the sink"), { dataTransfer: transfer });
    expect(fireEvent.dragOver(overdue, { dataTransfer: transfer })).toBe(true);
    expect(screen.getByText("Finished tasks from the past are hidden here.")).toBeInTheDocument();
  });

  it("Split by project gives one row per project with status columns", async () => {
    board("/board?tab=tasks&layout=kanban&split=1");
    await waitFor(() => expect(screen.getAllByRole("group", { name: "Kanban board" })).toHaveLength(2)); // Casa Nueva, No project
    const boards = screen.getAllByRole("group", { name: "Kanban board" });
    expect(screen.getByText("Casa Nueva", { selector: ".klane__head *, .klane__head" })).toBeInTheDocument();
    expect(within(boards[0]).getAllByRole("region").map((r) => r.getAttribute("aria-label"))).toEqual(["To do", "On it", "Done"]);
    // a drop into the Casa Nueva row sets that project (it was already On it, so only the project changes)
    const transfer = dataTransfer();
    fireEvent.dragStart(await screen.findByText("Call plumber").then((e) => e.closest(".kcard") as HTMLElement), { dataTransfer: transfer });
    fireEvent.drop(within(boards[0]).getByRole("region", { name: "On it" }), { dataTransfer: transfer });
    await waitFor(() => expect(updateTaskMock).toHaveBeenCalledWith("t2", { project_id: "p1" }));
    // another column in another row changes both in one write
    updateTaskMock.mockClear();
    fireEvent.dragStart(await card("Fix the sink"), { dataTransfer: transfer });
    fireEvent.drop(within(boards[1]).getByRole("region", { name: "On it" }), { dataTransfer: transfer });
    await waitFor(() => expect(updateTaskMock).toHaveBeenCalledWith("t1", { status: "in_progress", project_id: null }));
  });

  it("the Split by project switch is only on while grouping by Status", async () => {
    board("/board?tab=tasks&layout=kanban&group=priority&split=1");
    const toggle = await screen.findByRole("switch", { name: "Split by project" });
    expect(toggle).toBeDisabled();
    expect(toggle).toHaveAttribute("aria-checked", "false");
    expect(screen.getAllByRole("group", { name: "Kanban board" })).toHaveLength(1);
  });

  it("sorting by Money left asks the server", async () => {
    const user = userEvent.setup();
    board();
    await user.click(await screen.findByRole("combobox", { name: "Sort cards by" }));
    await user.click(await screen.findByRole("option", { name: "Sort cards by: Money left" }));
    await waitFor(() => expect(lastCall()).toMatchObject({ view: "board", sort: "money_left" }));
    expect(address()).toHaveTextContent("ksort=money_left");
  });

  it("grouping is kept in the address", async () => {
    const user = userEvent.setup();
    board();
    await user.click(await screen.findByRole("combobox", { name: "Group by" }));
    await user.click(await screen.findByRole("option", { name: "Group by: Priority" }));
    expect(address()).toHaveTextContent("group=priority");
    expect(await column("High")).toBeInTheDocument();
  });

  it("the steps chip expands inside the card", async () => {
    const user = userEvent.setup();
    board();
    await user.click(await screen.findByRole("button", { name: "Show the 2 steps of Fix the sink" }));
    expect(within(await card("Fix the sink")).getByText("Fit it")).toBeInTheDocument();
  });

  it("clicking a card opens the drawer address", async () => {
    const user = userEvent.setup();
    board();
    await user.click(await screen.findByText("Fix the sink"));
    expect(address()).toHaveTextContent("task=t1");
  });
});

const address = () => screen.getByRole("status", { name: "Address" });

// Lead task 14: Show finished on the Kanban.
describe("Show finished on the Kanban", () => {
  afterEach(() => window.localStorage.clear());

  it("off: no finished card; Done stays a place to drop a card and says its cards are hidden", async () => {
    window.localStorage.removeItem("roost.show-finished.v1");
    board();
    const done = await column("Done");
    await screen.findByText("Fix the sink");
    expect(within(done).queryByText("Paint walls")).toBeNull();
    expect(within(done).getByText("Finished tasks are hidden")).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Show finished" })).toHaveAttribute("aria-checked", "false");
    expect(screen.getByText("1 finished hidden")).toBeInTheDocument();
  });

  it("on: Done holds the finished cards, quiet", async () => {
    const user = userEvent.setup();
    board();
    await screen.findByText("Fix the sink");
    await user.click(screen.getByRole("switch", { name: "Show finished" }));
    const paint = within(await column("Done")).getByText("Paint walls");
    expect(paint.closest(".kcard")).toHaveClass("is-done");
  });
});
