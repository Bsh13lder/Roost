import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import ExpenseCalendar from "../src/components/board/calendar/ExpenseCalendar";
import type { DayNoteOut } from "../src/api/dayNotes";
import { ToastProvider } from "../src/ui/Toast";
import { makeExpense, makeExpenseLine, makeActions, makeRange } from "./moneyFixtures";
import { onAPhone } from "./phone";

const parseMock = vi.fn();
const createMock = vi.fn();
vi.mock("../src/api/money", () => ({
  parseExpenseLine: (...a: unknown[]) => parseMock(...a),
  createExpense: (...a: unknown[]) => createMock(...a),
  deleteExpense: vi.fn(),
}));
const listDayNotesMock = vi.fn();
vi.mock("../src/api/dayNotes", () => ({
  listDayNotes: (...a: unknown[]) => listDayNotesMock(...a), addDayNote: vi.fn(), deleteDayNote: vi.fn(),
}));
vi.mock("../src/api/projects", () => ({ listProjects: vi.fn().mockResolvedValue([]) }));
vi.mock("../src/hooks/useLiveStore", () => ({
  useLiveState: () => ({ bots: {}, boardVersion: { tasks: 0, money: 0, dayNotes: 0 } }),
}));

const NOTE: DayNoteOut = {
  id: "n1", day: "2026-10-19", author_kind: "user", bot_id: null, bot_name: null, text: "Rent day", created_at: "2026-10-18T08:00:00Z",
  tainted: false,
};

function agenda(range = makeRange()) {
  return render(
    <MemoryRouter>
      <ToastProvider>
        <ExpenseCalendar range={range} month="2026-10" actions={makeActions()} onChanged={vi.fn()} />
      </ToastProvider>
    </MemoryRouter>,
  );
}
const days = () => screen.getAllByRole("heading", { level: 3 }).map((heading) => heading.textContent);

onAPhone();
beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-20T10:00:00Z"));
  listDayNotesMock.mockReset().mockResolvedValue([NOTE]);
  parseMock.mockReset().mockImplementation(async ({ default_day: day }: { default_day?: string }) =>
    makeExpenseLine({ note: "lunch", amount: "12.00", amount_words: "€12", spent_at: day ?? "2026-10-21", ready: true }));
  createMock.mockReset().mockResolvedValue(makeExpense({ id: "new1" }));
});
afterEach(() => { cleanup(); vi.useRealTimers(); });

describe("the expense agenda (G14)", () => {
  it("on a phone the money calendar is an agenda with the server's day totals", async () => {
    agenda();
    expect(await screen.findByRole("group", { name: "Days of the month" })).toBeInTheDocument();
    expect(screen.queryByRole("grid")).toBeNull();
    // newest first; the void-only day (18 Oct) has nothing counted but its row is listed
    await waitFor(() => expect(days()).toEqual(["Today", "Mon 19 Oct", "Sun 18 Oct"]));
    const today = screen.getByRole("region", { name: "Today" });
    expect(today.querySelector(".agenda__total")).toHaveTextContent("€84.20 · US$12");
    expect(within(today).getByText("Paint")).toBeInTheDocument();
    expect(within(today).queryByText(/96\.20/)).toBeNull();
    const monday = screen.getByRole("region", { name: "Mon 19 Oct" });
    expect(monday.querySelector(".agenda__total")).toHaveTextContent("€9.99");
    expect(within(monday).getByText("Rent day")).toBeInTheDocument(); // the note, under the header
    expect(within(monday).getByRole("button", { name: "Day note for Mon 19 Oct" })).toBeInTheDocument();
  });

  it("a picked strip day filters, and an empty month says No expenses.", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    agenda();
    await screen.findByText("Paint");
    await user.click(screen.getByRole("button", { name: "Mon 19 Oct" }));
    expect(days()).toEqual(["Mon 19 Oct"]);
    await user.click(screen.getByRole("button", { name: "Clear" }));
    expect(days()).toHaveLength(3);
    cleanup();
    listDayNotesMock.mockResolvedValue([]);
    agenda(makeRange({ expenses: [], days: [] }));
    expect(await screen.findByText("No expenses.")).toBeInTheDocument();
  });

  it("+ on a day opens the expense line for it", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    agenda();
    await user.click(await screen.findByRole("button", { name: "Add on Mon 19 Oct" }));
    const popover = await screen.findByRole("dialog", { name: "Add expense on Mon 19 Oct" });
    expect(within(popover).getByText("On Mon 19 Oct")).toBeInTheDocument();
    await user.type(within(popover).getByRole("combobox", { name: "New expense" }), "€12 lunch", { delay: null });
    await waitFor(() => expect(parseMock).toHaveBeenCalledWith(expect.objectContaining({ default_day: "2026-10-19" })));
  });
});
