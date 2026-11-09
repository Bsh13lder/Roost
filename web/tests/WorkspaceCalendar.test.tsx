import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import WorkspaceCalendar from "../src/components/workspace/calendar/WorkspaceCalendar";
import { ToastProvider } from "../src/ui/Toast";
import { makeProject } from "./projectFixtures";
import { makeRow as task } from "./taskFixtures";
vi.mock("../src/api/routines", async (real) => ({ ...(await real<object>()), listRoutineOccurrences: vi.fn().mockResolvedValue({ occurrences: [], truncated: false }) }));

const listTasksMock = vi.fn();
vi.mock("../src/api/tasks", () => ({ listTasks: (...a: unknown[]) => listTasksMock(...a), getTask: vi.fn() }));
const listDayNotesMock = vi.fn();
const addDayNoteMock = vi.fn();
vi.mock("../src/api/dayNotes", () => ({
  listDayNotes: (...a: unknown[]) => listDayNotesMock(...a), addDayNote: (...a: unknown[]) => addDayNoteMock(...a),
  deleteDayNote: vi.fn(),
}));
const listProjectsMock = vi.fn();
vi.mock("../src/api/projects", () => ({ listProjects: (...a: unknown[]) => listProjectsMock(...a) }));
vi.mock("../src/hooks/useLiveStore", () => ({
  useLiveState: () => ({ bots: {}, boardVersion: { tasks: 0, money: 0, dayNotes: 0 } }),
}));
vi.mock("../src/components/board/calendar/TaskCalendar", () => ({ default: () => <p>The week grid</p> }));
vi.mock("../src/components/tasks/TaskDrawer", () => ({ default: ({ taskId }: { taskId: string }) => <p>Drawer of {taskId}</p> }));

// Fri 23 Oct 2026, 14:48 in Madrid.
const TEST = task({ id: "t1", title: "test", status: "done", due_date: "2026-10-23T13:30:00+02:00", steps: [] });
const LATER = task({ id: "t2", title: "Call the club", project_id: "p1", due_date: "2026-10-23T17:00:00+02:00", steps: [] });
const ALL_DAY = task({ id: "t3", title: "Water plants", due_date: "2026-10-23", steps: [] });
const MONDAY = ["a", "b", "c", "d"].map((id) => task({ id, title: `Errand ${id}`, due_date: "2026-10-19T10:00:00+02:00", status: "done", steps: [] }));
const SATURDAY = task({ id: "t4", title: "Market", due_date: "2026-10-24T09:00:00+02:00", steps: [] });

function Where() {
  return <output aria-label="Address">{useLocation().search}</output>;
}

function calendar(start = "/board?tab=calendar") {
  return render(
    <MemoryRouter initialEntries={[start]}>
      <ToastProvider><WorkspaceCalendar /><Where /></ToastProvider>
    </MemoryRouter>,
  );
}

const month = () => screen.getByRole("grid", { name: "October 2026" });
const dayButton = (name: RegExp) => within(month()).getByRole("button", { name });
const agenda = () => screen.getByRole("region", { name: /^Agenda/ });

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-23T12:48:00Z"));
  listTasksMock.mockReset().mockResolvedValue([TEST, LATER, ALL_DAY, ...MONDAY, SATURDAY]);
  listDayNotesMock.mockReset().mockResolvedValue([
    { id: "n1", day: "2026-10-23", author_kind: "user", bot_id: null, bot_name: null, text: "Club opens late", created_at: "", tainted: false },
  ]);
  addDayNoteMock.mockReset().mockResolvedValue({});
  listProjectsMock.mockReset().mockResolvedValue([makeProject({ id: "p1", name: "Club", color: "#22c55e" })]);
});
afterEach(() => { cleanup(); vi.useRealTimers(); });

describe("the Workspace's Calendar", () => {
  it("draws the month with today boxed and picked, and asks for the month's tasks", async () => {
    calendar();
    const today = dayButton(/^Fri 23 Oct/);
    expect(today).toHaveClass("is-today");
    expect(today).toHaveAttribute("aria-pressed", "true");
    await waitFor(() => expect(listTasksMock).toHaveBeenCalledWith(expect.objectContaining({ from: "2026-09-28", to: "2026-11-01" })));
  });

  it("shows up to three dots a day, then +N", async () => {
    calendar();
    await waitFor(() => expect(dayButton(/^Mon 19 Oct/).querySelectorAll(".wcal__dot")).toHaveLength(3));
    expect(dayButton(/^Mon 19 Oct/)).toHaveTextContent("+1");
    expect(dayButton(/^Mon 19 Oct/)).toHaveAccessibleName("Mon 19 Oct, 4 tasks");
  });

  it("lists the picked day below: notes, all-day tasks, then by time, with a now line on today", async () => {
    calendar();
    expect(await within(agenda()).findByText("Call the club")).toBeInTheDocument();
    expect(within(agenda()).getByRole("heading", { name: "Today · Fri 23 Oct" })).toBeInTheDocument();
    expect(within(agenda()).getByText("Club opens late")).toBeInTheDocument();
    const lines = Array.from(agenda().querySelectorAll(".wcal__item, .wcal__now")).map((node) => node.textContent);
    expect(lines).toEqual(["All dayWater plants", "13:30test", "14:48 now", "17:00Call the club"]);
  });

  it("picking another day puts it in the address and lists it, with no now line", async () => {
    calendar();
    await userEvent.click(dayButton(/^Sat 24 Oct/));
    expect(screen.getByRole("status", { name: "Address" })).toHaveTextContent("day=2026-10-24");
    expect(await within(agenda()).findByText("Market")).toBeInTheDocument();
    expect(agenda().querySelector(".wcal__now")).toBeNull();
    expect(within(agenda()).getByRole("heading", { name: "Sat 24 Oct" })).toBeInTheDocument();
  });

  it("a task opens its drawer", async () => {
    calendar();
    await userEvent.click(await within(agenda()).findByRole("button", { name: /Call the club/ }));
    expect(screen.getByRole("status", { name: "Address" })).toHaveTextContent("task=t2");
    expect(await screen.findByText("Drawer of t2")).toBeInTheDocument();
  });

  it("adds a day note to the picked day", async () => {
    calendar();
    await userEvent.type(within(agenda()).getByRole("textbox", { name: "Add a day note" }), "Bring keys{Enter}");
    await waitFor(() => expect(addDayNoteMock).toHaveBeenCalledWith("2026-10-23", "Bring keys"));
  });

  it("keeps the week grid as an option", async () => {
    calendar();
    await userEvent.click(within(screen.getByRole("group", { name: "Calendar span" })).getByRole("button", { name: "Week" }));
    expect(await screen.findByText("The week grid")).toBeInTheDocument();
    await act(async () => undefined);
  });
});
