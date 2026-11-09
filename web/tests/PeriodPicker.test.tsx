import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { MoneyBoard } from "../src/components/board/MoneyBoard";
import { ToastProvider } from "../src/ui/Toast";
import { makeRange, makeSummary } from "./moneyFixtures";

const getSummaryMock = vi.fn();
const getRangeMock = vi.fn();
vi.mock("../src/api/money", () => ({
  getSummary: (...a: unknown[]) => getSummaryMock(...a),
  getRange: (...a: unknown[]) => getRangeMock(...a),
  parseExpenseLine: vi.fn(), createExpense: vi.fn(), starExpense: vi.fn(), voidExpense: vi.fn(), keepExpense: vi.fn(),
  deleteExpense: vi.fn(), restoreExpense: vi.fn(), updateExpense: vi.fn(),
  getTrend: () => Promise.resolve({ months: [] }),
  getGeneralInbox: () => Promise.resolve({ expenses: [], next: null }),
  exportCsvUrl: (month: string) => `/api/money/export.csv?from=${month}&to=${month}`,
}));
vi.mock("../src/api/projects", () => ({ pinProject: vi.fn(), listProjects: () => Promise.resolve([]) }));
vi.mock("../src/api/dates", () => ({ parseDate: vi.fn() }));
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => ({ bots: {}, boardVersion: { tasks: 0, money: 0 } }) }));

const MONTH = makeRange({ from: "2026-10-01", to: "2026-10-21" });
const WEEK = makeRange({
  from: "2026-10-19", to: "2026-10-21", expenses: [MONTH.expenses[0]],
  days: [MONTH.days[0]], summary: { count: 12, totals: { EUR: "340.20", USD: "12.00" } },
});

function renderBoard(entry = "/board?tab=money") {
  return render(
    <MemoryRouter initialEntries={[entry]}><ToastProvider><MoneyBoard /></ToastProvider></MemoryRouter>);
}
const period = () => screen.getByRole("button", { name: /^Period: / });
async function pick(user: ReturnType<typeof userEvent.setup>, name: string) {
  await user.click(period());
  const panel = await screen.findByRole("dialog", { name: "Pick a period" });
  await user.click(within(panel).getByRole("button", { name }));
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-21T10:00:00Z")); // Wednesday the 21st in Madrid
  getSummaryMock.mockReset().mockResolvedValue(makeSummary());
  getRangeMock.mockReset().mockImplementation((from: string) => Promise.resolve(from === "2026-10-19" ? WEEK : MONTH));
});
afterEach(() => { cleanup(); vi.useRealTimers(); });

describe("the Money period picker", () => {
  it("is the month arrows and one dropdown: Whole month, Today, This week, Custom range", async () => {
    const user = userEvent.setup();
    renderBoard();
    await screen.findByRole("list", { name: "Expenses" });
    expect(screen.getByRole("button", { name: "Previous month" })).toBeInTheDocument();
    expect(period()).toHaveAccessibleName("Period: Whole month");
    expect(screen.queryByRole("group", { name: "Filter by date" })).not.toBeInTheDocument(); // the chip row is gone
    await user.click(period());
    const panel = await screen.findByRole("dialog", { name: "Pick a period" });
    expect(within(panel).getAllByRole("button").map((option) => option.textContent))
      .toEqual(["Whole month", "Today", "This week", "Custom range…"]);
    expect(within(panel).getByRole("button", { name: "Whole month" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByText(/expenses? ·/)).not.toBeInTheDocument();
  });

  it("a period asks the server for its range, shows the summary and closes", async () => {
    const user = userEvent.setup();
    renderBoard();
    await screen.findByRole("list", { name: "Expenses" });
    await pick(user, "This week");
    await waitFor(() => expect(getRangeMock).toHaveBeenCalledWith("2026-10-19", "2026-10-21", undefined));
    const summary = await screen.findByText("12 expenses · €340.20 · US$12.00");
    expect(summary.closest(".rsum")).toHaveTextContent("this week; other currencies apart");
    expect(period()).toHaveAccessibleName("Period: This week");
    expect(screen.queryByRole("dialog", { name: "Pick a period" })).not.toBeInTheDocument();
    expect(getSummaryMock).toHaveBeenCalledTimes(1); // the cards stay on the month
  });

  it("Whole month goes back to the month", async () => {
    const user = userEvent.setup();
    renderBoard("/board?tab=money&range=week");
    await screen.findByText(/12 expenses/);
    await pick(user, "Whole month");
    await waitFor(() => expect(screen.queryByText(/12 expenses/)).not.toBeInTheDocument());
    expect(period()).toHaveAccessibleName("Period: Whole month");
  });

  it("the month arrows always show a whole month", async () => {
    const user = userEvent.setup();
    renderBoard("/board?tab=money&range=week");
    await screen.findByText(/12 expenses/);
    await user.click(screen.getByRole("button", { name: "Previous month" }));
    await waitFor(() => expect(getSummaryMock).toHaveBeenLastCalledWith("2026-09"));
    expect(screen.queryByText(/12 expenses/)).not.toBeInTheDocument();
    expect(period()).toHaveAccessibleName("Period: Whole month");
  });

  it("Today from a past month comes back to this month", async () => {
    const user = userEvent.setup();
    renderBoard();
    await screen.findByRole("list", { name: "Expenses" });
    await user.click(screen.getByRole("button", { name: "Previous month" }));
    await waitFor(() => expect(getSummaryMock).toHaveBeenLastCalledWith("2026-09"));
    await pick(user, "Today");
    await waitFor(() => expect(getSummaryMock).toHaveBeenLastCalledWith("2026-10"));
    expect(getRangeMock).toHaveBeenCalledWith("2026-10-21", "2026-10-21", undefined);
    expect(screen.getByRole("heading", { name: "October 2026" })).toBeInTheDocument();
  });

  it("custom range: pick From and To, then Apply", async () => {
    const user = userEvent.setup();
    renderBoard();
    await screen.findByRole("list", { name: "Expenses" });
    await pick(user, "Custom range…");
    const dialog = await screen.findByRole("dialog", { name: "Pick a period" });
    const apply = within(dialog).getByRole("button", { name: "Apply" });
    expect(apply).toBeDisabled();
    await user.click(await within(dialog).findByRole("button", { name: /October 12th, 2026/ }));
    expect(within(dialog).getByText("From Mon 12 Oct")).toBeInTheDocument();
    expect(apply).toBeEnabled();
    await user.click(within(dialog).getByRole("button", { name: /October 14th, 2026/ }));
    expect(within(dialog).getByText("To Wed 14 Oct")).toBeInTheDocument();
    await user.click(apply);
    await waitFor(() => expect(getRangeMock).toHaveBeenCalledWith("2026-10-12", "2026-10-14", undefined));
    expect(period()).toHaveAccessibleName("Period: 12 Oct–14 Oct");
  });

  it("future days can't be picked", async () => {
    const user = userEvent.setup();
    renderBoard();
    await screen.findByRole("list", { name: "Expenses" });
    await pick(user, "Custom range…");
    expect(await screen.findByRole("button", { name: /October 22nd, 2026/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /October 21st, 2026/ })).toBeEnabled();
  });

  it("Cancel closes the picker without a range", async () => {
    const user = userEvent.setup();
    renderBoard();
    await screen.findByRole("list", { name: "Expenses" });
    await pick(user, "Custom range…");
    await user.click(await screen.findByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog", { name: "Pick a period" })).not.toBeInTheDocument();
    expect(getRangeMock).toHaveBeenCalledTimes(1);
    expect(period()).toHaveAccessibleName("Period: Whole month");
  });

  it("the address keeps the range, the view and the day", async () => {
    renderBoard("/board?tab=money&mview=days&range=custom&from=2026-10-12&to=2026-10-14&day=2026-10-12");
    await waitFor(() => expect(getRangeMock).toHaveBeenCalledWith("2026-10-12", "2026-10-14", undefined));
    expect(period()).toHaveAccessibleName("Period: 12 Oct–14 Oct");
    expect(await screen.findByRole("button", { name: "Mon 12 Oct ✕ Clear" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Expenses view" }).querySelector("[aria-pressed='true']")).toHaveTextContent("By days");
  });

  it("picking a day in By days filters to it, with a chip that clears it", async () => {
    const user = userEvent.setup();
    renderBoard("/board?tab=money&mview=days");
    const strip = await screen.findByRole("group", { name: "Spending per day" });
    expect(screen.getByText("Pick a bar or a day to see its expenses.")).toBeInTheDocument();
    await user.click(within(strip).getByRole("button", { name: /^Tue 20 Oct/ }));
    expect(screen.getByRole("button", { name: "Tue 20 Oct ✕ Clear" })).toBeInTheDocument();
    expect(screen.getByText(/2 expenses|1 expense/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Tue 20 Oct ✕ Clear" }));
    expect(screen.getByText("Pick a bar or a day to see its expenses.")).toBeInTheDocument();
  });

  it("the list view filtered to a day shows only that day", async () => {
    const user = userEvent.setup();
    renderBoard("/board?tab=money&day=2026-10-19");
    const list = await screen.findByRole("list", { name: "Expenses" });
    expect(within(list).getByText("Netflix")).toBeInTheDocument();
    expect(within(list).queryByText("Paint")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Mon 19 Oct ✕ Clear" }));
    expect(await within(screen.getByRole("list", { name: "Expenses" })).findByText("Paint")).toBeInTheDocument();
  });
});

describe("Today on the Spent card", () => {
  it("is the Spent card's sub-line this month, and not a figure of its own", async () => {
    renderBoard();
    const spent = await screen.findByRole("group", { name: "Spent this month" });
    expect(within(spent).getByText("Today:")).toBeInTheDocument();
    expect(within(spent).getByText("€84.20 · US$12")).toBeInTheDocument();
    expect(screen.getAllByText("Today:")).toHaveLength(1);
  });

  it("is left out on a past month", async () => {
    const user = userEvent.setup();
    renderBoard();
    await screen.findByRole("group", { name: "Spent this month" });
    await user.click(screen.getByRole("button", { name: "Previous month" }));
    await waitFor(() => expect(getSummaryMock).toHaveBeenLastCalledWith("2026-09"));
    await screen.findByRole("group", { name: "Spent this month" });
    expect(screen.queryByText("Today:")).not.toBeInTheDocument();
  });
});
