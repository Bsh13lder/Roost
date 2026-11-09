import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import TaskCalendar from "../src/components/board/calendar/TaskCalendar";
import { DayPopover } from "../src/components/board/calendar/DayPopover";
import type { DayNoteOut } from "../src/api/dayNotes";
import { ToastProvider } from "../src/ui/Toast";
import { makeBot } from "./fixtures";
import { makeRow as task } from "./taskFixtures";

const listTasksMock = vi.fn();
const updateTaskMock = vi.fn();
vi.mock("../src/api/tasks", () => ({
  listTasks: (...a: unknown[]) => listTasksMock(...a),
  updateTask: (...a: unknown[]) => updateTaskMock(...a),
  restoreDues: vi.fn(),
  moveOverdue: vi.fn(),
  parseQuickLine: vi.fn(),
  createTask: vi.fn(),
}));
vi.mock("../src/api/money", () => ({
  getRange: vi.fn().mockResolvedValue({ from: "", to: "", currency: "EUR", general_project_id: null, expenses: [], days: [], summary: { count: 0, totals: {} } }),
}));
const listDayNotesMock = vi.fn();
const addDayNoteMock = vi.fn();
const deleteDayNoteMock = vi.fn();
vi.mock("../src/api/dayNotes", () => ({
  listDayNotes: (...a: unknown[]) => listDayNotesMock(...a),
  addDayNote: (...a: unknown[]) => addDayNoteMock(...a),
  deleteDayNote: (...a: unknown[]) => deleteDayNoteMock(...a),
}));
vi.mock("../src/api/projects", () => ({ listProjects: vi.fn().mockResolvedValue([]) }));
vi.mock("../src/hooks/useLiveStore", () => ({
  useLiveState: () => ({ bots: { "bot-1": makeBot({ id: "bot-1", name: "Scout" }) }, boardVersion: { tasks: 0, money: 0, dayNotes: 0 } }),
}));
vi.mock("../src/api/dates", () => ({ parseDate: vi.fn().mockResolvedValue({ due_date: null }) }));

const note = (overrides: Partial<DayNoteOut> = {}): DayNoteOut => ({
  id: "n1", day: "2026-10-21", author_kind: "user", bot_id: null, bot_name: null, text: "Dentist at 5", created_at: "2026-10-20T08:00:00Z",
  tainted: false, ...overrides,
});
const NOTES = [
  note(),
  note({ id: "n2", author_kind: "bot", bot_id: "bot-1", bot_name: "Scout", text: "Rain forecast <b>all day</b>", tainted: true }),
];
const PAINT = task({ id: "t1", title: "Paint walls", due_date: "2026-10-21", due_bucket: "tomorrow", steps: [] });

function panel(onAddNote = vi.fn().mockResolvedValue(null)) {
  const view = render(
    <MemoryRouter>
      <ToastProvider>
        <DayPopover kind="tasks" day="2026-10-21" count={0} notes={NOTES} onAddNote={onAddNote} onDeleteNote={vi.fn()} onClose={vi.fn()} />
      </ToastProvider>
    </MemoryRouter>,
  );
  return { ...view, onAddNote };
}

function calendar() {
  return render(
    <MemoryRouter initialEntries={["/board?tab=tasks&layout=calendar"]}>
      <ToastProvider><TaskCalendar projects={new Map()} onOpen={vi.fn()} /></ToastProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-20T10:00:00Z"));
  listTasksMock.mockReset().mockResolvedValue([PAINT]);
  updateTaskMock.mockReset().mockImplementation(async (id: string, patch: object) => ({ ...PAINT, ...patch, id }));
  listDayNotesMock.mockReset().mockResolvedValue(NOTES);
  addDayNoteMock.mockReset().mockResolvedValue(note({ id: "n3" }));
  deleteDayNoteMock.mockReset().mockResolvedValue(undefined);
});
afterEach(() => { cleanup(); vi.useRealTimers(); });

describe("DayPopover", () => {
  it("lists the day's notes with who wrote them", () => {
    panel();
    const section = screen.getByRole("region", { name: "Day note" });
    expect(within(section).getByText("You")).toHaveClass("dwho--you");
    expect(within(section).getByText("Scout")).toBeInTheDocument();
    // a bot's line from a web page carries the mark, and its text is text, never markup
    expect(within(section).getAllByText("from web content")).toHaveLength(1);
    expect(within(section).getByText("Rain forecast <b>all day</b>")).toBeInTheDocument();
    expect(section.querySelector("b")).toBeNull();
    expect(screen.getByRole("heading", { name: "Wed 21 Oct" })).toBeInTheDocument();
  });

  it("adds a note for this day, with Enter or Add, and shows a refusal in a sentence", async () => {
    const user = userEvent.setup();
    const { onAddNote } = panel(vi.fn().mockResolvedValueOnce("A day can hold 20 notes.").mockResolvedValue(null));
    const field = screen.getByRole("textbox", { name: "Add a note for this day" });
    expect(screen.getByRole("button", { name: "Add" })).toBeDisabled();
    await user.type(field, "Bring the keys{Enter}");
    expect(onAddNote).toHaveBeenCalledWith("Bring the keys");
    expect(await screen.findByRole("alert")).toHaveTextContent("A day can hold 20 notes.");
    expect(field).toHaveValue("Bring the keys");
    await user.click(screen.getByRole("button", { name: "Add" }));
    await waitFor(() => expect(field).toHaveValue(""));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("a day with a note shows the note mark", async () => {
    calendar();
    const wednesday = await screen.findByRole("gridcell", { name: "Wed 21 Oct" });
    const mark = await within(wednesday).findByRole("button", { name: "Day note for Wed 21 Oct" });
    expect(mark).toHaveAttribute("title", "Day note · 2 lines");
    expect(within(await screen.findByRole("gridcell", { name: "Thu 22 Oct" })).queryByRole("button", { name: /Day note/ })).toBeNull();
  });

  it("deletes a note with Undo", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    calendar();
    const wednesday = await screen.findByRole("gridcell", { name: "Wed 21 Oct" });
    await user.click(await within(wednesday).findByRole("button", { name: "Day note for Wed 21 Oct" }));
    const popover = await screen.findByRole("dialog", { name: "Wed 21 Oct" });
    const lines = within(popover).getAllByRole("button", { name: "Delete note" });
    await user.click(lines[0]);
    await waitFor(() => expect(deleteDayNoteMock).toHaveBeenCalledWith("n1"));
    expect(await screen.findByText("Note deleted")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Undo" }));
    await waitFor(() => expect(addDayNoteMock).toHaveBeenCalledWith("2026-10-21", "Dentist at 5"));
  });

  it("adds a note from the popover through the API", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    calendar();
    await user.click(await screen.findByRole("button", { name: "Day note for Wed 21 Oct" }));
    await user.type(await screen.findByRole("textbox", { name: "Add a note for this day" }), "Call mum{Enter}");
    await waitFor(() => expect(addDayNoteMock).toHaveBeenCalledWith("2026-10-21", "Call mum"));
  });

  it("pills in the popover reschedule through →", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    calendar();
    await user.click(await screen.findByRole("button", { name: "Day note for Wed 21 Oct" }));
    const popover = await screen.findByRole("dialog", { name: "Wed 21 Oct" });
    expect(within(popover).getByText("Tasks · 1")).toBeInTheDocument();
    const pill = within(popover).getByText("Paint walls").closest(".tchip") as HTMLElement;
    expect(pill).not.toHaveAttribute("draggable");
    await user.click(within(pill).getByRole("button", { name: "Reschedule Paint walls" }));
    await user.click(await screen.findByRole("button", { name: /^Tomorrow/ }));
    await waitFor(() => expect(updateTaskMock).toHaveBeenCalledWith("t1", { due_date: "2026-10-21" }));
  });
});
