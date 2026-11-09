import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import ExpenseCalendar from "../src/components/board/calendar/ExpenseCalendar";
import type { DayNoteOut } from "../src/api/dayNotes";
import { ToastProvider } from "../src/ui/Toast";
import { makeExpense, makeExpenseLine, makeActions, makeRange } from "./moneyFixtures";

const parseMock = vi.fn();
const createMock = vi.fn();
const deleteMock = vi.fn();
vi.mock("../src/api/money", () => ({
  parseExpenseLine: (...a: unknown[]) => parseMock(...a),
  createExpense: (...a: unknown[]) => createMock(...a),
  deleteExpense: (...a: unknown[]) => deleteMock(...a),
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
  id: "n1", day: "2026-10-20", author_kind: "user", bot_id: null, bot_name: null, text: "Rent day", created_at: "2026-10-19T08:00:00Z",
  tainted: false,
};
const onChanged = vi.fn();
let actions = makeActions();

function calendar() {
  return render(
    <MemoryRouter>
      <ToastProvider>
        <ExpenseCalendar range={makeRange()} month="2026-10" actions={actions} onChanged={onChanged} />
      </ToastProvider>
    </MemoryRouter>,
  );
}
const cell = async (name: string) => (await screen.findByRole("gridcell", { name })) as HTMLElement;

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-20T10:00:00Z"));
  actions = makeActions();
  onChanged.mockReset();
  listDayNotesMock.mockReset().mockResolvedValue([NOTE]);
  parseMock.mockReset().mockImplementation(async ({ text, default_day: day }: { text: string; default_day?: string }) =>
    makeExpenseLine({ note: "lunch", amount: "12.00", amount_words: "€12", spent_at: day ?? "2026-10-21", ready: text.includes("12") }));
  createMock.mockReset().mockResolvedValue(makeExpense({ id: "new1" }));
  deleteMock.mockReset().mockResolvedValue(undefined);
});
afterEach(() => { cleanup(); vi.useRealTimers(); });

describe("ExpenseCalendar", () => {
  it("each day shows its totals per currency from the server, never summed", async () => {
    calendar();
    const today = await cell("Tue 20 Oct");
    expect(within(today).getByText("€84.20")).toBeInTheDocument();
    const usd = within(today).getByText("US$12.00");
    expect(usd).toHaveClass("ccell__tot", "usd");
    expect(within(today).queryByText(/96\.20/)).not.toBeInTheDocument();
    expect(within(await cell("Mon 19 Oct")).getByText("€9.99")).toBeInTheDocument();
    // days of other months show nothing
    expect(within(await cell("Mon 28 Sep")).queryByText(/€/)).not.toBeInTheDocument();
    expect(screen.getByText("Other currencies are shown apart (blue), never added together.")).toBeInTheDocument();
  });

  it("void expenses are not in a day's count", async () => {
    calendar();
    expect(within(await cell("Tue 20 Oct")).getByTitle("2 expenses")).toBeInTheDocument();
    expect(within(await cell("Mon 19 Oct")).getByTitle("1 expense")).toBeInTheDocument();
    const sunday = await cell("Sun 18 Oct"); // only a void expense: the server counts none
    expect(within(sunday).queryByTitle(/expense/)).not.toBeInTheDocument();
    expect(within(sunday).queryByText(/€/)).not.toBeInTheDocument();
  });

  it("clicking a day lists its expenses beside the grid, with Clear", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    calendar();
    const side = screen.getByRole("complementary", { name: "Selected day" });
    expect(within(side).getByText("Click a day to see its expenses.")).toBeInTheDocument();
    await user.click(await cell("Tue 20 Oct"));
    expect(within(side).getByText("Paint")).toBeInTheDocument();
    expect(within(side).getByText("Taxi")).toBeInTheDocument();
    expect(within(side).getByText("Tue 20 Oct")).toBeInTheDocument();
    expect(within(side).getByText("€84.20 · US$12")).toBeInTheDocument();
    expect(within(side).getByText("Rent day")).toBeInTheDocument();
    expect(await cell("Tue 20 Oct")).toHaveClass("is-sel");
    await user.click(within(side).getByRole("button", { name: "Clear" }));
    expect(within(side).getByText("Click a day to see its expenses.")).toBeInTheDocument();
    expect(await cell("Tue 20 Oct")).not.toHaveClass("is-sel");
  });

  it("a day with nothing says so, and a void expense is listed there", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    calendar();
    await user.click(await cell("Sat 17 Oct"));
    expect(screen.getByText("No expenses.")).toBeInTheDocument();
    await user.click(await cell("Sun 18 Oct"));
    expect(within(screen.getByRole("complementary", { name: "Selected day" })).getByText("Old lamp")).toBeInTheDocument();
  });

  it("+ opens the expense line with the day filled", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    calendar();
    await user.click(await screen.findByRole("button", { name: "Add on Mon 19 Oct" }));
    const popover = await screen.findByRole("dialog", { name: "Add expense on Mon 19 Oct" });
    expect(within(popover).getByText("On Mon 19 Oct")).toBeInTheDocument();
    const line = within(popover).getByRole("combobox", { name: "New expense" });
    expect(line).toHaveAttribute("placeholder", "€12 lunch /Trip");
    expect(popover.querySelector(".quick-box__glyph")).toHaveTextContent("€");
    await user.type(line, "€12 lunch", { delay: null });
    await waitFor(() => expect(parseMock).toHaveBeenCalledWith(expect.objectContaining({ default_day: "2026-10-19" })));
    await user.click(within(popover).getByRole("button", { name: "Add expense" }));
    await waitFor(() => expect(createMock).toHaveBeenCalledWith(expect.objectContaining({ spent_at: "2026-10-19", amount: "12.00" })));
    expect(await screen.findByText("Added €12 lunch on Mon 19 Oct")).toBeInTheDocument();
    expect(onChanged).toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Undo" }));
    await waitFor(() => expect(deleteMock).toHaveBeenCalledWith("new1"));
  });

  it("a day with a note shows the note mark and opens the day popover", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    calendar();
    const today = await cell("Tue 20 Oct");
    await user.click(await within(today).findByRole("button", { name: "Day note for Tue 20 Oct" }));
    const popover = await screen.findByRole("dialog", { name: "Tue 20 Oct" });
    expect(within(popover).getByText("Expenses · 2")).toBeInTheDocument();
    expect(within(popover).getByText("Paint")).toBeInTheDocument();
    expect(within(popover).getByText("€84.20 · US$12")).toBeInTheDocument();
    expect(within(popover).getByText("Rent day")).toBeInTheDocument();
    expect(within(await cell("Mon 19 Oct")).queryByRole("button", { name: /Day note/ })).not.toBeInTheDocument();
    await user.click(within(popover).getByRole("button", { name: "Add expense" }));
    expect(await screen.findByRole("dialog", { name: "Add expense on Tue 20 Oct" })).toBeInTheDocument();
  });
});
