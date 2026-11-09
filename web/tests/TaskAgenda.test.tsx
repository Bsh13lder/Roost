import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import TaskCalendar from "../src/components/board/calendar/TaskCalendar";
import type { DayNoteOut } from "../src/api/dayNotes";
import { screenToggleKey } from "../src/hooks/useScreenToggle";
import { SCREEN_BOARD_CALENDAR } from "../src/components/board/constants";
import { ToastProvider } from "../src/ui/Toast";
import { makeRow as task } from "./taskFixtures";
import { onAPhone } from "./phone";

const occurrencesMock = vi.fn();
vi.mock("../src/api/routines", async (real) => ({ ...(await real<object>()), listRoutineOccurrences: (...a: unknown[]) => occurrencesMock(...a) }));
const listTasksMock = vi.fn();
vi.mock("../src/api/tasks", () => ({
  listTasks: (...a: unknown[]) => listTasksMock(...a),
  updateTask: vi.fn(), restoreDues: vi.fn(), moveOverdue: vi.fn(), parseQuickLine: vi.fn(), createTask: vi.fn(), parseQuickLines: vi.fn(),
}));
const getRangeMock = vi.fn();
vi.mock("../src/api/money", () => ({ getRange: (...a: unknown[]) => getRangeMock(...a) }));
const listDayNotesMock = vi.fn();
vi.mock("../src/api/dayNotes", () => ({
  listDayNotes: (...a: unknown[]) => listDayNotesMock(...a), addDayNote: vi.fn(), deleteDayNote: vi.fn(),
}));
vi.mock("../src/api/projects", () => ({ listProjects: vi.fn().mockResolvedValue([]) }));
const BOT = (id: string, name: string, color: string) => ({ id, name, avatar: { shape: "mochi", color, badge: "none" } });
vi.mock("../src/hooks/useLiveStore", () => ({
  useLiveState: () => ({
    bots: { b1: BOT("b1", "Gela", "#e11d48") },
    boardVersion: { tasks: 0, money: 0, dayNotes: 0 },
  }),
}));
vi.mock("../src/api/dates", () => ({ parseDate: vi.fn().mockResolvedValue({ due_date: null }) }));

const none = { reminder_at: null, pre_reminders: [] };
// Tue 20 Oct 2026 in Madrid.
const SINK = task({ id: "t1", title: "Fix the sink", project_id: "p1", due_date: "2026-10-21", due_bucket: "tomorrow", steps: [], ...none });
const CALL = task({
  id: "t2", title: "Call plumber", due_date: "2026-10-22T09:30:00+02:00", due_bucket: "week", steps: [],
  reminder_at: "2026-10-22T07:30:00Z", pre_reminders: ["2026-10-22T07:00:00Z"],
});
const LATE = task({ id: "t3", title: "Pay the deposit", due_date: "2026-10-16", due_bucket: "overdue", steps: [], ...none });
const DRAFT = task({ id: "t4", title: "Draft the post", due_date: "2026-10-22", created_by_bot: "b1", steps: [], ...none });
const FILED = task({ id: "t5", title: "Filed taxes", due_date: "2026-10-22", status: "done", completed_at: "2026-10-19T08:00:00Z", steps: [], ...none });
const BUSY = ["a", "b", "c", "d", "e"].map((id) => task({ id, title: `Busy ${id}`, due_date: "2026-10-27", steps: [], ...none }));
const NOTE: DayNoteOut = {
  id: "n1", day: "2026-10-21", author_kind: "user", bot_id: null, bot_name: null, text: "Plumber comes at ten",
  created_at: "2026-10-19T08:00:00Z", tainted: false,
};
const NEWS = {
  routine_id: "r1", routine_name: "Morning news", bot_id: "b1", bot_name: "Gela", at: "2026-10-22T07:00:00Z",
  day: "2026-10-22", time: "09:00", log_thread_id: "t-r1",
};

const onOpen = vi.fn();
function calendar() {
  return render(
    <MemoryRouter initialEntries={["/board?tab=tasks&layout=calendar"]}>
      <ToastProvider>
        <TaskCalendar projects={new Map([["p1", { name: "Casa Nueva", color: "#22c55e" }]])} onOpen={onOpen} ownDone />
      </ToastProvider>
    </MemoryRouter>,
  );
}
const cell = (name: RegExp) => screen.getByRole("button", { name });
const panel = () => screen.getByRole("region", { name: /^Day: / });

onAPhone();
beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-20T10:00:00Z"));
  window.localStorage.clear();
  onOpen.mockReset();
  listTasksMock.mockReset().mockResolvedValue([SINK, CALL, LATE, DRAFT, FILED, ...BUSY]);
  occurrencesMock.mockReset().mockResolvedValue({ occurrences: [NEWS], truncated: false });
  getRangeMock.mockReset().mockResolvedValue({ from: "", to: "", currency: "EUR", general_project_id: null, expenses: [], days: [], summary: { count: 0, totals: {} } });
  listDayNotesMock.mockReset().mockResolvedValue([NOTE]);
});
afterEach(() => { cleanup(); vi.useRealTimers(); });

describe("the phone calendar: a month grid of markers", () => {
  it("draws every day of the month as a cell with markers, not sentences, and a legend", async () => {
    calendar();
    const grid = await screen.findByRole("group", { name: "Month" });
    await waitFor(() => expect(cell(/^Thu 22 Oct: 3 tasks, 1 reminder, 1 routine$/)).toBeInTheDocument());
    expect(within(grid).queryByText("Call plumber")).toBeNull(); // no titles in the grid
    const thu = cell(/^Thu 22 Oct:/);
    expect(thu.querySelectorAll(".mcell__dot")).toHaveLength(3);
    expect(thu.querySelector(".mcell__dot.is-done")).not.toBeNull();
    expect(thu.querySelector(".mcell__bell")).not.toBeNull();
    expect(thu.querySelector(".mcell__repeat")).not.toBeNull();
    expect(within(thu).getByText("G")).toHaveClass("mcell__bot");
    const busy = cell(/^Tue 27 Oct: 5 tasks$/);
    expect(busy.querySelectorAll(".mcell__dot")).toHaveLength(3);
    expect(within(busy).getByText("+2")).toBeInTheDocument();
    const today = cell(/^Tue 20 Oct/);
    expect(today).toHaveClass("is-today");
    expect(today).toHaveAttribute("aria-pressed", "true");
    expect(today.querySelector(".mcell__dot.is-late")).not.toBeNull();
    expect(screen.getByRole("note", { name: "What the marks mean" })).toHaveTextContent(/task.*done.*reminder.*routine.*bot/i);
    expect(screen.queryByRole("group", { name: "Days of the month" })).toBeNull();
  });

  it("today is picked: its panel lists the late task with Late", async () => {
    calendar();
    await screen.findByText("Pay the deposit");
    expect(within(panel()).getByRole("heading", { name: "Today" })).toBeInTheDocument();
    const row = within(panel()).getByRole("button", { name: /Pay the deposit/ });
    expect(within(row).getByText("Late")).toBeInTheDocument();
  });

  it("tapping a day lists its Tasks, Reminders and Routines with time, bot and project", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    calendar();
    await waitFor(() => cell(/^Thu 22 Oct:/));
    await user.click(cell(/^Thu 22 Oct:/));
    const day = panel();
    expect(within(day).getByRole("heading", { name: "Thu 22 Oct" })).toBeInTheDocument();
    const tasks = within(day).getByRole("list", { name: "Tasks" });
    const reminders = within(day).getByRole("list", { name: "Reminders" });
    const routines = within(day).getByRole("list", { name: "Routines" });
    expect(within(tasks).getByText("09:30")).toBeInTheDocument();
    expect(within(tasks).getByText("Draft the post").closest("button")).toHaveTextContent("Gela");
    expect(within(reminders).getByText("09:00 +1")).toBeInTheDocument(); // 30 minutes ahead, then at 09:30
    expect(within(reminders).getByText("Call plumber")).toBeInTheDocument();
    expect(within(routines).getByText("Morning news").closest("a")).toHaveAttribute("href", "/bots/b1/routines/r1/log");
    await user.click(within(tasks).getByText("Call plumber"));
    expect(onOpen).toHaveBeenCalledWith("t2");
    await user.click(cell(/^Wed 21 Oct:/));
    expect(within(panel()).getByText("Plumber comes at ten")).toBeInTheDocument();
    expect(within(panel()).getByText("Casa Nueva")).toBeInTheDocument();
    expect(within(panel()).queryByRole("list", { name: "Reminders" })).toBeNull();
  });

  it("an empty day says so and offers Add a task", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    calendar();
    await waitFor(() => cell(/^Thu 22 Oct:/));
    await user.click(cell(/^Sat 24 Oct$/));
    expect(within(panel()).getByText("Nothing on this day.")).toBeInTheDocument();
    await user.click(within(panel()).getByRole("button", { name: "Add a task on Sat 24 Oct" }));
    expect(await screen.findByRole("dialog", { name: "Add task on Sat 24 Oct" })).toBeInTheDocument();
  });

  it("Show switches hide routines, done and bot-made items from the grid and the panel", async () => {
    window.localStorage.setItem(screenToggleKey(SCREEN_BOARD_CALENDAR, "routines"), "0");
    window.localStorage.setItem(screenToggleKey(SCREEN_BOARD_CALENDAR, "done"), "0");
    window.localStorage.setItem(screenToggleKey(SCREEN_BOARD_CALENDAR, "botMade"), "0");
    calendar();
    await waitFor(() => expect(cell(/^Thu 22 Oct: 1 task, 1 reminder$/)).toBeInTheDocument());
    expect(occurrencesMock).not.toHaveBeenCalled();
    expect(cell(/^Thu 22 Oct:/).querySelector(".mcell__bot")).toBeNull();
  });

  it("months move with the arrows and Today comes back", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    calendar();
    await waitFor(() => cell(/^Thu 22 Oct:/));
    await user.click(screen.getByRole("button", { name: "Next month" }));
    expect(await screen.findByRole("button", { name: /^Sun 1 Nov/ })).toHaveAttribute("aria-pressed", "true");
    await user.click(screen.getByRole("button", { name: "Today" }));
    expect(await screen.findByRole("button", { name: /^Tue 20 Oct/ })).toHaveAttribute("aria-pressed", "true");
  });
});
