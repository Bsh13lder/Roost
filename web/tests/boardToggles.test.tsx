// Board toggles (2026-10-26): routine runs on the calendars, the show / hide switches per screen, and the bot's
// name on a task it made.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, renderHook, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { RoutineOccurrenceOut } from "../src/api/routines";
import { ShowToggles } from "../src/components/board/ShowToggles";
import { TaskPill } from "../src/components/board/calendar/TaskPill";
import { RoutineLines } from "../src/components/board/calendar/RoutineChip";
import { boardScreen } from "../src/components/board/useBoardList";
import { PlanCalendar } from "../src/components/plan/PlanCalendar";
import WorkspaceCalendar from "../src/components/workspace/calendar/WorkspaceCalendar";
import { agendaItems } from "../src/components/workspace/calendar/agendaItems";
import { screenToggleKey, useScreenToggle } from "../src/hooks/useScreenToggle";
import { botMadeCount, isBotMade, keepMade } from "../src/lib/madeBy";
import { groupRoutineDays, routineLink, routineTimeWords, routineWords } from "../src/lib/routineDays";
import { ToastProvider } from "../src/ui/Toast";
import { item } from "./planFixtures";
import { makeRow as task } from "./taskFixtures";

const listTasksMock = vi.fn();
vi.mock("../src/api/tasks", () => ({ listTasks: (...a: unknown[]) => listTasksMock(...a), getTask: vi.fn() }));
vi.mock("../src/api/dayNotes", () => ({ listDayNotes: vi.fn().mockResolvedValue([]), addDayNote: vi.fn(), deleteDayNote: vi.fn() }));
vi.mock("../src/api/projects", () => ({ listProjects: vi.fn().mockResolvedValue([]) }));
const occurrencesMock = vi.fn();
vi.mock("../src/api/routines", () => ({ listRoutineOccurrences: (...a: unknown[]) => occurrencesMock(...a) }));
const live = { bots: { gela: { id: "gela", name: "Gela" } }, boardVersion: { tasks: 0, money: 0, dayNotes: 0 }, routineVersion: { routines: 0 } };
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => live }));
vi.mock("../src/components/board/calendar/TaskCalendar", () => ({ default: () => <p>The week grid</p> }));
vi.mock("../src/components/tasks/TaskDrawer", () => ({ default: () => null }));

const occ = (over: Partial<RoutineOccurrenceOut> = {}): RoutineOccurrenceOut => ({
  routine_id: "r1", routine_name: "Morning news", bot_id: "gela", bot_name: "Gela", at: "2026-10-23T07:00:00Z",
  day: "2026-10-23", time: "09:00", log_thread_id: "t-log", ...over,
});

// Fri 23 Oct 2026, 14:48 in Madrid.
const MINE = task({ id: "t1", title: "Call the club", due_date: "2026-10-23T17:00:00+02:00", steps: [] });
const BOTS = task({ id: "t2", title: "Draft the post", due_date: "2026-10-23T18:00:00+02:00", created_by_bot: "gela", steps: [] });
const DONE = task({ id: "t3", title: "Old chore", status: "done", due_date: "2026-10-23T08:00:00+02:00", steps: [] });

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-23T12:48:00Z"));
  listTasksMock.mockReset().mockResolvedValue([MINE, BOTS, DONE]);
  occurrencesMock.mockReset().mockResolvedValue({
    occurrences: [occ(), occ({ at: "2026-10-23T13:00:00Z", time: "15:00" }), occ({ routine_id: "r2", routine_name: "Gym", day: "2026-10-24", at: "2026-10-24T06:00:00Z", time: "08:00" })],
    truncated: false,
  });
});
afterEach(() => { cleanup(); vi.useRealTimers(); window.localStorage.clear(); vi.restoreAllMocks(); });

describe("routine days", () => {
  it("groups each routine once a day with its times in order", () => {
    const days = groupRoutineDays([occ({ at: "2026-10-23T13:00:00Z", time: "15:00" }), occ(), occ({ routine_id: "r2", routine_name: "Gym", at: "2026-10-23T06:00:00Z", time: "08:00" })]);
    const friday = days.get("2026-10-23") ?? [];
    expect(friday.map((entry) => [entry.routineName, entry.times])).toEqual([["Gym", ["08:00"]], ["Morning news", ["09:00", "15:00"]]]);
    expect(routineTimeWords(friday[1])).toBe("09:00 +1");
    expect(routineWords(friday[1])).toBe("Routine: Morning news · 09:00 and 15:00 · Gela");
    expect(routineWords({ ...friday[0], botName: "" })).toBe("Routine: Gym · 08:00");
    expect(routineLink(friday[0])).toBe("/bots/gela/routines/r2/log");
  });

  it("an empty list is an empty map", () => {
    expect(groupRoutineDays([]).size).toBe(0);
  });
});

describe("made by bots", () => {
  it("is a task with a bot's id; keepMade drops them only when hidden", () => {
    const rows = [MINE, BOTS];
    expect(rows.map(isBotMade)).toEqual([false, true]);
    expect(keepMade(rows, true)).toBe(rows);
    expect(keepMade(rows, false).map((row) => row.id)).toEqual(["t1"]);
    expect(botMadeCount(rows)).toBe(1);
  });
});

describe("useScreenToggle", () => {
  it("defaults, remembers per screen, and survives a browser that refuses storage", () => {
    const list = renderHook(() => useScreenToggle("board-list", "botMade"));
    const calendar = renderHook(() => useScreenToggle("board-calendar", "botMade"));
    expect(list.result.current[0]).toBe(true);
    act(() => list.result.current[1](false));
    expect(list.result.current[0]).toBe(false);
    expect(calendar.result.current[0]).toBe(true);
    expect(window.localStorage.getItem(screenToggleKey("board-list", "botMade"))).toBe("0");
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("full"); });
    vi.spyOn(console, "warn").mockImplementation(() => undefined);
    act(() => calendar.result.current[1](false));
    expect(calendar.result.current[0]).toBe(false);
  });

  it("follows another tab", () => {
    const hook = renderHook(() => useScreenToggle("plan-calendar", "done"));
    act(() => {
      window.localStorage.setItem(screenToggleKey("plan-calendar", "done"), "0");
      window.dispatchEvent(new StorageEvent("storage", { key: screenToggleKey("plan-calendar", "done") }));
    });
    expect(hook.result.current[0]).toBe(false);
  });

  it("each board layout and a project page keep their own choices", () => {
    expect([boardScreen(undefined, "list"), boardScreen(undefined, "kanban"), boardScreen(undefined, "calendar"), boardScreen("p1", "list")])
      .toEqual(["board-list", "board-kanban", "board-calendar", "project"]);
  });
});

describe("ShowToggles", () => {
  it("shows the switches a screen has and says how many bot tasks it hides", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const { rerender } = render(<ShowToggles screen="board-calendar" routines ownDone botMadeHidden={2} />);
    const group = screen.getByRole("group", { name: "Show" });
    expect(within(group).getAllByRole("switch").map((one) => one.textContent)).toEqual(["Routines", "Done", "Made by bots"]);
    await user.click(within(group).getByRole("switch", { name: "Made by bots" }));
    expect(within(group).getByRole("switch", { name: "Made by bots" })).toHaveAttribute("aria-checked", "false");
    expect(screen.getByText("2 by bots hidden")).toBeInTheDocument();
    rerender(<ShowToggles screen="board-list" botMade={false} done={<span>Show finished here</span>} />);
    expect(screen.queryByRole("switch")).toBeNull();
    expect(screen.getByText("Show finished here")).toBeInTheDocument();
  });
});

describe("the bot's name on its task", () => {
  it("a calendar pill ends with the bot's name; the user's own has none", () => {
    render(<><TaskPill task={BOTS} today="2026-10-23" onOpen={vi.fn()} /><TaskPill task={MINE} today="2026-10-23" onOpen={vi.fn()} /></>);
    const pill = screen.getByRole("button", { name: /Draft the post/ });
    expect(pill).toHaveAccessibleName(expect.stringContaining("by Gela"));
    expect(within(pill).getByText("Gela")).toHaveClass("tchip__by");
    expect(screen.getByRole("button", { name: /Call the club/ })).not.toHaveAccessibleName(expect.stringContaining("by"));
  });
});

describe("RoutineLines", () => {
  it("shows at most max lines, then +N routines, and a tap opens the run log", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const entries = groupRoutineDays([occ(), occ({ routine_id: "r2", routine_name: "Gym" }), occ({ routine_id: "r3", routine_name: "Inbox" })]).get("2026-10-23") ?? [];
    render(
      <MemoryRouter>
        <Routes>
          <Route path="/" element={<RoutineLines entries={entries} max={2} />} />
          <Route path="/bots/:botId/routines/:routineId/log" element={<p>Run log</p>} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getAllByRole("link")).toHaveLength(2);
    expect(screen.getByText("+1 routine")).toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: /Morning news/ }));
    expect(screen.getByText("Run log")).toBeInTheDocument();
  });
});

function workspace() {
  return render(<MemoryRouter initialEntries={["/board?tab=calendar"]}><ToastProvider><WorkspaceCalendar /></ToastProvider></MemoryRouter>);
}
const agenda = () => screen.getByRole("region", { name: /^Agenda/ });
const agendaLines = () => Array.from(agenda().querySelectorAll(".wcal__item, .wcal__now")).map((node) => node.textContent);

describe("the Workspace's Calendar with toggles", () => {
  it("lists the day's routine runs among the tasks, with each bot's name", async () => {
    workspace();
    expect(await within(agenda()).findByRole("link", { name: /Morning news/ })).toBeInTheDocument();
    expect(occurrencesMock).toHaveBeenCalledWith("2026-09-28", "2026-11-01", undefined);
    expect(agendaLines()).toEqual([
      "08:00Old chore", "09:00 +1Morning newsGela", "14:48 now", "17:00Call the club", "18:00 · by GelaDraft the post",
    ]);
    const saturday = screen.getByRole("button", { name: /^Sat 24 Oct/ });
    expect(saturday).toHaveAccessibleName("Sat 24 Oct, 1 routine");
    expect(saturday.querySelector(".wcal__rdot")).not.toBeNull();
  });

  it("Routines, Done and Made by bots hide what they name, and are remembered", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    workspace();
    await within(agenda()).findByRole("link", { name: /Morning news/ });
    await user.click(screen.getByRole("switch", { name: "Routines" }));
    await user.click(screen.getByRole("switch", { name: "Done" }));
    await user.click(screen.getByRole("switch", { name: "Made by bots" }));
    await waitFor(() => expect(agendaLines()).toEqual(["14:48 now", "17:00Call the club"]));
    cleanup();
    workspace();
    expect(await within(agenda()).findByText("Call the club")).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Routines" })).toHaveAttribute("aria-checked", "false");
    expect(within(agenda()).queryByText("Draft the post")).toBeNull();
  });

  it("a failed routines load leaves the tasks alone", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    occurrencesMock.mockRejectedValue(new Error("down"));
    workspace();
    expect(await within(agenda()).findByText("Call the club")).toBeInTheDocument();
    await waitFor(() => expect(warn).toHaveBeenCalled());
    expect(within(agenda()).queryByRole("link")).toBeNull();
  });
});

describe("the Plan calendar's routines", () => {
  const plan = (botId?: string) => render(
    <MemoryRouter initialEntries={["/?month=2026-10"]}>
      <PlanCalendar items={[item({ id: "a", text: "Dentist", date: "2026-10-23", time: "10:00" }),
        item({ id: "b", text: "Filed taxes", date: "2026-10-23", status: "done" })]} today="2026-10-23" botId={botId} />
    </MemoryRouter>,
  );

  it("shows only that bot's routines under the day, and Done and Routines hide", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    plan("gela");
    const runs = await screen.findByRole("list", { name: "Routines on Fri 23 Oct" });
    expect(occurrencesMock).toHaveBeenCalledWith("2026-09-28", "2026-11-01", "gela");
    expect(within(runs).getByRole("link", { name: /Morning news/ })).not.toHaveTextContent("Gela"); // its own Plan: no name
    expect(screen.getByText("Filed taxes")).toBeInTheDocument();
    await user.click(screen.getByRole("switch", { name: "Done" }));
    expect(screen.queryByText("Filed taxes")).toBeNull();
    await user.click(screen.getByRole("switch", { name: "Routines" }));
    await waitFor(() => expect(screen.queryByRole("list", { name: "Routines on Fri 23 Oct" })).toBeNull());
    expect(screen.queryByRole("switch", { name: "Made by bots" })).toBeNull();
  });

  it("without a bot it asks for no routines", () => {
    plan();
    expect(occurrencesMock).not.toHaveBeenCalled();
    expect(screen.queryByRole("switch", { name: "Routines" })).toBeNull();
  });
});

describe("agendaItems", () => {
  it("puts a routine at its first time, after a task at the same time", () => {
    const entry = groupRoutineDays([occ({ time: "17:00" })]).get("2026-10-23") ?? [];
    expect(agendaItems([MINE], null, entry).map((line) => line.kind)).toEqual(["task", "routine"]);
  });
});
