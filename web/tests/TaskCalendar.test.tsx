import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import TaskCalendar from "../src/components/board/calendar/TaskCalendar";
import type { TaskRowOut } from "../src/api/tasks";
import { ToastProvider } from "../src/ui/Toast";
import { makeProject } from "./projectFixtures";
import { makeQuickLine, makeRow as task } from "./taskFixtures";

const listTasksMock = vi.fn();
const updateTaskMock = vi.fn();
const restoreDuesMock = vi.fn();
const parseQuickLineMock = vi.fn();
vi.mock("../src/api/tasks", () => ({
  listTasks: (...a: unknown[]) => listTasksMock(...a),
  updateTask: (...a: unknown[]) => updateTaskMock(...a),
  restoreDues: (...a: unknown[]) => restoreDuesMock(...a),
  moveOverdue: vi.fn(),
  parseQuickLine: (...a: unknown[]) => parseQuickLineMock(...a),
  createTask: vi.fn(),
  parseQuickLines: vi.fn(),
}));
const getRangeMock = vi.fn();
vi.mock("../src/api/money", () => ({ getRange: (...a: unknown[]) => getRangeMock(...a) }));
const listDayNotesMock = vi.fn();
vi.mock("../src/api/dayNotes", () => ({
  listDayNotes: (...a: unknown[]) => listDayNotesMock(...a), addDayNote: vi.fn(), deleteDayNote: vi.fn(),
}));
vi.mock("../src/api/projects", () => ({ listProjects: vi.fn().mockResolvedValue([]) }));
const occurrencesMock = vi.fn();
vi.mock("../src/api/routines", () => ({ listRoutineOccurrences: (...a: unknown[]) => occurrencesMock(...a) }));
vi.mock("../src/hooks/useLiveStore", () => ({
  useLiveState: () => ({ bots: {}, boardVersion: { tasks: 0, money: 0, dayNotes: 0 } }),
}));
vi.mock("../src/api/dates", () => ({ parseDate: vi.fn().mockResolvedValue({ due_date: null }) }));

// Tue 20 Oct 2026 in Madrid.
const SINK = task({ id: "t1", title: "Fix the sink", project_id: "p1", due_date: "2026-10-21", due_bucket: "tomorrow", priority: "urgent", steps: [] });
const CALL = task({ id: "t2", title: "Call plumber", due_date: "2026-10-21T09:30:00+02:00", due_bucket: "tomorrow", steps: [] });
const LATE = task({ id: "t3", title: "Pay the deposit", due_date: "2026-10-16", due_bucket: "overdue", steps: [] });
const THURSDAY = ["t4", "t5", "t6", "t7"].map((id, index) =>
  task({ id, title: `Errand ${index + 1}`, due_date: `2026-10-22T1${index}:00:00+02:00`, due_bucket: "week", steps: [] }));
const DATA: TaskRowOut[] = [SINK, CALL, LATE, ...THURSDAY];

function calendar(start = "/board?tab=tasks&layout=calendar") {
  return render(
    <MemoryRouter initialEntries={[start]}>
      <ToastProvider>
        <TaskCalendar projects={new Map([["p1", { name: "Casa Nueva", color: "#22c55e" }]])} onOpen={vi.fn()} />
      </ToastProvider>
    </MemoryRouter>,
  );
}

const cell = async (name: string) => (await screen.findByRole("gridcell", { name })) as HTMLElement;
const dataTransfer = () => {
  const store = new Map<string, string>();
  return { setData: (k: string, v: string) => store.set(k, v), getData: (k: string) => store.get(k) ?? "", effectAllowed: "", dropEffect: "" };
};

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-20T10:00:00Z"));
  for (const mock of [updateTaskMock, restoreDuesMock]) mock.mockReset();
  updateTaskMock.mockImplementation(async (id: string, patch: object) => ({ ...DATA.find((t) => t.id === id), ...patch }));
  restoreDuesMock.mockReset().mockResolvedValue({ restored: 1 });
  listTasksMock.mockReset().mockResolvedValue(DATA);
  getRangeMock.mockReset().mockResolvedValue({
    from: "2026-09-28", to: "2026-10-20", currency: "EUR", general_project_id: null, expenses: [],
    days: [{ day: "2026-10-19", count: 1, totals: { EUR: "84.20", USD: "12.00" }, bar_percent: 100 }],
    summary: { count: 1, totals: { EUR: "84.20" } },
  });
  listDayNotesMock.mockReset().mockResolvedValue([]);
  occurrencesMock.mockReset().mockResolvedValue({ occurrences: [], truncated: false });
  parseQuickLineMock.mockReset().mockImplementation(async ({ text, default_due: day }: { text: string; default_due?: string }) =>
    makeQuickLine({ title: text, ready: true, due_date: day ?? null }));
});
afterEach(() => { cleanup(); vi.useRealTimers(); window.localStorage.clear(); });

describe("TaskCalendar", () => {
  it("puts tasks on their due day, overdue ones on today with Nd", async () => {
    calendar();
    expect(within(await cell("Wed 21 Oct")).getByText("Fix the sink")).toBeInTheDocument();
    const today = await cell("Tue 20 Oct");
    expect(await within(today).findByText("Pay the deposit")).toBeInTheDocument();
    expect(within(today).getByText("4d")).toBeInTheDocument();
    expect(listTasksMock).toHaveBeenCalledWith({ from: "2026-09-28", to: "2026-11-01" });
  });

  it("shows +N more past three and opens the day popover", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    calendar();
    const thursday = await cell("Thu 22 Oct");
    await within(thursday).findByText("Errand 1");
    expect(within(thursday).queryByText("Errand 4")).not.toBeInTheDocument();
    await user.click(within(thursday).getByRole("button", { name: "+1 more" }));
    const popover = await screen.findByRole("dialog", { name: "Thu 22 Oct" });
    expect(within(popover).getByText("Tasks · 4")).toBeInTheDocument();
    expect(within(popover).getByText("Errand 4")).toBeInTheDocument();
    expect(within(popover).getByText("Day note")).toBeInTheDocument();
  });

  it("the corner shows the day's spending from the server", async () => {
    calendar();
    const monday = await cell("Mon 19 Oct");
    expect(await within(monday).findByText("€84.20")).toBeInTheDocument();
    expect(within(monday).queryByText(/12\.00/)).not.toBeInTheDocument();
    expect(getRangeMock).toHaveBeenCalledWith("2026-09-28", "2026-11-01");
  });

  it("a click on an empty day opens quick add with the date", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    calendar();
    await user.click(await cell("Fri 23 Oct"));
    const popover = await screen.findByRole("dialog", { name: "Add task on Fri 23 Oct" });
    expect(within(popover).getByText("Due Fri 23 Oct")).toBeInTheDocument(); // the first chip, before anything is typed
    const line = within(popover).getByRole("combobox", { name: "New task" });
    expect(line).toHaveAttribute("placeholder", "Call plumber /Casa Nueva €200 !!");
    await user.type(line, "Call the bank");
    await waitFor(() => expect(parseQuickLineMock).toHaveBeenCalledWith(expect.objectContaining({ default_due: "2026-10-23" })));
    expect(await within(popover).findByText(/Fri 23 Oct/, { selector: ".quick-chip" })).toBeInTheDocument();
  });

  it("the + on a day opens the same quick add", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    calendar();
    await user.click(await screen.findByRole("button", { name: "Add on Sat 24 Oct" }));
    expect(await screen.findByRole("dialog", { name: "Add task on Sat 24 Oct" })).toBeInTheDocument();
  });

  it("dragging a pill to another day reschedules it, with Undo", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    calendar();
    const pill = (await within(await cell("Wed 21 Oct")).findByText("Fix the sink")).closest(".tchip") as HTMLElement;
    const transfer = dataTransfer();
    fireEvent.dragStart(pill, { dataTransfer: transfer });
    const target = await cell("Fri 23 Oct");
    fireEvent.dragOver(target, { dataTransfer: transfer });
    expect(target).toHaveClass("is-over");
    fireEvent.drop(target, { dataTransfer: transfer });
    await waitFor(() => expect(updateTaskMock).toHaveBeenCalledWith("t1", { due_date: "2026-10-23" }));
    expect(await screen.findByText("“Fix the sink” moved to Fri 23 Oct")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Undo" }));
    await waitFor(() => expect(restoreDuesMock).toHaveBeenCalledWith([expect.objectContaining({ id: "t1", due_date: "2026-10-21" })]));
  });

  it("dropping a timed task keeps its time", async () => {
    calendar();
    const pill = (await within(await cell("Wed 21 Oct")).findByText("Call plumber")).closest(".tchip") as HTMLElement;
    const transfer = dataTransfer();
    fireEvent.dragStart(pill, { dataTransfer: transfer });
    fireEvent.drop(await cell("Thu 22 Oct"), { dataTransfer: transfer });
    await waitFor(() => expect(updateTaskMock).toHaveBeenCalledWith("t2", { due_date: "2026-10-22T09:30" }));
  });

  it("week view puts timed tasks in their hour and the rest in All day", async () => {
    calendar("/board?tab=tasks&layout=calendar&cmode=week&week=2026-10-19");
    expect(await screen.findByRole("heading", { name: "19–25 Oct" })).toBeInTheDocument();
    const slot = (await screen.findByText("Call plumber")).closest(".slot") as HTMLElement;
    expect(slot.style.top).toBe("100px"); // (9.5 - 7) * 40
    const allDay = screen.getByRole("row", { name: "All day" });
    expect(within(allDay).getByText("Fix the sink")).toBeInTheDocument();
    expect(within(allDay).getByText("Pay the deposit")).toBeInTheDocument(); // late: on today, all day
    expect(within(allDay).queryByText("Call plumber")).not.toBeInTheDocument();
    expect(listTasksMock).toHaveBeenCalledWith({ from: "2026-10-19", to: "2026-10-25" });
  });

  it("a pill carries its project's colour edge and the urgent flag", async () => {
    calendar();
    const pill = (await within(await cell("Wed 21 Oct")).findByText("Fix the sink")).closest(".tchip") as HTMLElement;
    expect(pill.style.getPropertyValue("--pc")).toBe("#22c55e");
    expect(within(pill).getByTitle("Urgent")).toBeInTheDocument();
    expect(makeProject).toBeDefined();
  });

  it("the arrows move by a month, and › keeps going into the future", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    calendar();
    await user.click(await screen.findByRole("button", { name: "Next month" }));
    expect(await screen.findByRole("heading", { name: "November 2026" })).toBeInTheDocument();
    await waitFor(() => expect(listTasksMock).toHaveBeenLastCalledWith({ from: "2026-10-26", to: "2026-12-06" }));
  });
});

describe("TaskCalendar, friendlier (lead task 02)", () => {
  it("today is marked in words and for screen readers", async () => {
    calendar();
    const today = await cell("Tue 20 Oct");
    expect(today).toHaveAttribute("aria-current", "date");
    expect(within(today).getByText("Today")).toBeInTheDocument();
    expect(await cell("Wed 21 Oct")).not.toHaveAttribute("aria-current");
  });

  it("a Today button brings you back once you have moved away", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    calendar();
    await cell("Tue 20 Oct");
    expect(screen.queryByRole("button", { name: "Today" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Next month" }));
    await user.click(await screen.findByRole("button", { name: "Today" }));
    expect(await screen.findByRole("heading", { name: "October 2026" })).toBeInTheDocument();
  });

  it("done tasks sit after the open ones and read as done", async () => {
    window.localStorage.setItem("roost.show-finished.v1", "1"); // finished tasks shown (lead task 14)
    const errands = THURSDAY.map((one, index) => (index === 0 ? { ...one, status: "done" as const } : one));
    listTasksMock.mockResolvedValue(errands);
    calendar();
    const thursday = await cell("Thu 22 Oct");
    await within(thursday).findByText("Errand 2");
    expect(within(thursday).queryByText("Errand 1")).not.toBeInTheDocument(); // behind "+1 more"
    expect(within(thursday).getByText("Errand 4")).toBeInTheDocument();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    await user.click(within(thursday).getByRole("button", { name: "+1 more" }));
    const done = within(await screen.findByRole("dialog", { name: "Thu 22 Oct" })).getByText("Errand 1").closest(".tchip") as HTMLElement;
    expect(done).toHaveClass("is-done");
    expect(done).toHaveAttribute("title", expect.stringContaining("done"));
  });

  it("a pill names its project as well as wearing its colour", async () => {
    calendar();
    const pill = (await within(await cell("Wed 21 Oct")).findByText("Fix the sink")).closest(".tchip") as HTMLElement;
    expect(pill).toHaveAccessibleName(expect.stringContaining("Casa Nueva"));
    expect(pill).toHaveClass("has-project");
  });

  it("an empty day says it can take a task; a busy one does not", async () => {
    calendar();
    const friday = await cell("Fri 23 Oct");
    expect(within(friday).getByText("Add task")).toBeInTheDocument();
    const wednesday = await cell("Wed 21 Oct");
    await within(wednesday).findByText("Fix the sink");
    expect(within(wednesday).queryByText("Add task")).not.toBeInTheDocument();
  });
});

// Lead task 14: the calendar follows Show finished.
describe("Show finished on the calendar", () => {
  afterEach(() => window.localStorage.clear());
  const finished = [task({ id: "t8", title: "Water plants", status: "done", due_date: "2026-10-23", due_bucket: "week", steps: [] }),
    task({ id: "t9", title: "Fix the gate", status: "failed", due_date: "2026-10-23", due_bucket: "week", steps: [] })];

  it("off: finished tasks are not on the grid", async () => {
    listTasksMock.mockResolvedValue([...DATA, ...finished]);
    calendar();
    await screen.findByText("Fix the sink");
    expect(screen.queryByText("Water plants")).toBeNull();
    expect(screen.queryByText("Fix the gate")).toBeNull();
  });

  it("on: they are, quiet", async () => {
    window.localStorage.setItem("roost.show-finished.v1", "1");
    listTasksMock.mockResolvedValue([...DATA, ...finished]);
    calendar();
    expect((await screen.findByText("Water plants")).closest(".tchip")).toHaveClass("is-closed");
    expect(screen.getByText("Fix the gate").closest(".tchip")).toHaveClass("is-closed");
  });
});

describe("TaskCalendar within a selection (lead task 15)", () => {
  it("asks for the span's tasks of the selected project only", async () => {
    render(
      <MemoryRouter initialEntries={["/board?tab=tasks&layout=calendar&project=p1"]}>
        <ToastProvider>
          <TaskCalendar projects={new Map()} onOpen={vi.fn()} scope={{ kind: "project", id: "p1" }} />
        </ToastProvider>
      </MemoryRouter>,
    );
    await waitFor(() => expect(listTasksMock).toHaveBeenCalledWith(expect.objectContaining({ projectId: "p1" })));
    expect(listTasksMock.mock.calls[0][0]).toEqual(expect.objectContaining({ from: expect.any(String), to: expect.any(String) }));
  });
});

describe("TaskCalendar on the Inbox (lead task 15)", () => {
  it("asks the server for the span with project_id=none", async () => {
    render(
      <MemoryRouter initialEntries={["/board?tab=tasks&layout=calendar&project=inbox"]}>
        <ToastProvider>
          <TaskCalendar projects={new Map()} onOpen={vi.fn()} scope={{ kind: "inbox" }} />
        </ToastProvider>
      </MemoryRouter>,
    );
    await waitFor(() => expect(listTasksMock).toHaveBeenCalledWith(expect.objectContaining({ projectId: "none" })));
    expect(await screen.findByText("Fix the sink")).toBeInTheDocument(); // the server's answer, not filtered again
  });
});

// Board toggles: routine runs on the month and the week, and the Routines switch.
describe("TaskCalendar's routines", () => {
  const runs = (count: number) => Array.from({ length: count }, (_, index) => ({
    routine_id: `r${index}`, routine_name: `Routine ${index + 1}`, bot_id: "b1", bot_name: "Gela",
    at: `2026-10-22T0${index}:00:00Z`, day: "2026-10-22", time: `0${index + 2}:00`, log_thread_id: "t",
  }));

  it("a month cell lists two routine lines, then +N routines", async () => {
    occurrencesMock.mockResolvedValue({ occurrences: runs(3), truncated: false });
    calendar();
    const thursday = await cell("Thu 22 Oct");
    expect(await within(thursday).findByRole("link", { name: /Routine 1 · 02:00 · Gela/ })).toBeInTheDocument();
    expect(within(thursday).getAllByRole("link")).toHaveLength(2);
    expect(within(thursday).getByText("+1 routine")).toBeInTheDocument();
    expect(occurrencesMock).toHaveBeenCalledWith("2026-09-28", "2026-11-01", undefined);
  });

  it("the week lists them in All day, and Routines off asks for none", async () => {
    occurrencesMock.mockResolvedValue({ occurrences: runs(1), truncated: false });
    calendar("/board?tab=tasks&layout=calendar&cmode=week&week=2026-10-19");
    const allDay = await screen.findByRole("row", { name: "All day" });
    expect(await within(allDay).findByRole("link", { name: /Routine 1/ })).toBeInTheDocument();
    cleanup();
    occurrencesMock.mockClear();
    window.localStorage.setItem("roost.show.v1.board-calendar.routines", "0");
    calendar("/board?tab=tasks&layout=calendar&cmode=week&week=2026-10-19");
    expect(await screen.findByText("Fix the sink")).toBeInTheDocument();
    expect(occurrencesMock).not.toHaveBeenCalled();
    expect(screen.queryByRole("link", { name: /Routine 1/ })).toBeNull();
  });

  it("Made by bots off leaves a bot's tasks off the grid", async () => {
    listTasksMock.mockResolvedValue([...DATA, task({ id: "t9", title: "Bot errand", due_date: "2026-10-21", due_bucket: "tomorrow", created_by_bot: "b1", steps: [] })]);
    window.localStorage.setItem("roost.show.v1.board-calendar.botMade", "0");
    calendar();
    expect(await within(await cell("Wed 21 Oct")).findByText("Fix the sink")).toBeInTheDocument();
    expect(screen.queryByText("Bot errand")).toBeNull();
  });
});
