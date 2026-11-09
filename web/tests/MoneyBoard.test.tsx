import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { MoneyBoard } from "../src/components/board/MoneyBoard";
import { zoneMonth } from "../src/components/board/money";
import { ToastProvider } from "../src/ui/Toast";
import { makeExpenseLine, makeRange, makeRangeExpense, makeSummary } from "./moneyFixtures";

const getSummaryMock = vi.fn();
const getRangeMock = vi.fn();
const createExpenseMock = vi.fn();
const keepExpenseMock = vi.fn();
const starExpenseMock = vi.fn();
const voidExpenseMock = vi.fn();
const deleteExpenseMock = vi.fn();
const restoreExpenseMock = vi.fn();
const parseExpenseLineMock = vi.fn();
const getInboxMock = vi.fn();
vi.mock("../src/api/money", () => ({
  starExpense: (...a: unknown[]) => starExpenseMock(...a),
  voidExpense: (...a: unknown[]) => voidExpenseMock(...a),
  keepExpense: (...a: unknown[]) => keepExpenseMock(...a),
  deleteExpense: (...a: unknown[]) => deleteExpenseMock(...a),
  restoreExpense: (...a: unknown[]) => restoreExpenseMock(...a),
  updateExpense: vi.fn(),
  getSummary: (...a: unknown[]) => getSummaryMock(...a),
  getRange: (...a: unknown[]) => getRangeMock(...a),
  createExpense: (...a: unknown[]) => createExpenseMock(...a),
  parseExpenseLine: (...a: unknown[]) => parseExpenseLineMock(...a),
  getTrend: () => Promise.resolve({ months: [] }),
  getGeneralInbox: (...a: unknown[]) => getInboxMock(...a),
  exportCsvUrl: (month: string) => `/api/money/export.csv?from=${month}&to=${month}`,
}));
vi.mock("../src/api/dayNotes", () => ({ listDayNotes: () => Promise.resolve([]), addDayNote: vi.fn(), deleteDayNote: vi.fn() }));
vi.mock("../src/api/projects", () => ({ pinProject: vi.fn(), listProjects: () => Promise.resolve([]) }));
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => ({ bots: {}, boardVersion: { tasks: 0, money: 0 } }) }));

const SUMMARY = makeSummary();
const FOOD = makeRangeExpense({ id: "e1", project: "food", project_id: "p-food", amount: "12.50", description: "lunch",
  spent_at: "2026-10-13", created_by_bot: "bot-1" });
const TAXI = makeRangeExpense({ id: "e2", project: "travel", project_id: "p-travel", amount: "20.00", currency: "USD",
  description: "taxi", spent_at: "2026-10-12", tainted: true });
const RANGE = makeRange({
  expenses: [FOOD, TAXI],
  days: [{ day: "2026-10-13", count: 1, totals: { EUR: "12.50" }, bar_percent: 100 },
    { day: "2026-10-12", count: 1, totals: { USD: "20.00" }, bar_percent: 0 }],
  summary: { count: 2, totals: { EUR: "12.50", USD: "20.00" } },
});
const EMPTY = makeRange({ expenses: [], days: [], summary: { count: 0, totals: {} } });

const renderBoard = (ui: ReactElement) => render(
  <MemoryRouter initialEntries={["/board?tab=money"]}><ToastProvider>{ui}</ToastProvider></MemoryRouter>);

beforeEach(() => {
  for (const mock of [getSummaryMock, getRangeMock, createExpenseMock, keepExpenseMock, starExpenseMock,
    voidExpenseMock, deleteExpenseMock, restoreExpenseMock, parseExpenseLineMock]) mock.mockReset();
  parseExpenseLineMock.mockImplementation(({ text }: { text: string }) => Promise.resolve(
    makeExpenseLine({ note: "lunch", amount: text.includes("12") ? "12.50" : null, ready: text.includes("12") })));
  getSummaryMock.mockResolvedValue(SUMMARY);
  getRangeMock.mockResolvedValue(RANGE);
  getInboxMock.mockReset().mockResolvedValue({ expenses: [], next: null });
});
afterEach(() => cleanup());

const rowOf = (note: string) => screen.getByText(note).closest("li") as HTMLElement;

describe("MoneyBoard", () => {
  it("opens on four summary cards, the budgets side and the month's list", async () => {
    renderBoard(<MoneyBoard />);
    expect(await screen.findByRole("group", { name: "Spent this month" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Monthly limits" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Budgets this month" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Pinned" })).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "Expenses" })).getAllByRole("listitem")).toHaveLength(2);
  });

  it("lists the month by day from the range route", async () => {
    renderBoard(<MoneyBoard initialMonth="2026-10" />);
    await screen.findByRole("list", { name: "Expenses" });
    expect(getRangeMock).toHaveBeenCalledWith("2026-10-01", "2026-10-31", undefined);
    expect(screen.getAllByTestId("xp-day").map((head) => head.textContent)).toEqual(["Tue 13 Oct€12.50", "Mon 12 Oct" + "US$20"]);
  });

  it("shows the view switcher, and Today's totals on the Spent card", async () => {
    renderBoard(<MoneyBoard />);
    const spent = await screen.findByRole("group", { name: "Spent this month" });
    expect(within(spent).getByText("€84.20 · US$12")).toBeInTheDocument();
    const views = screen.getByRole("group", { name: "Expenses view" });
    expect([...views.querySelectorAll("button")].map((button) => button.textContent)).toEqual(["List", "By days", "Calendar"]);
  });

  it("the Calendar view shows the month's grid and leaves out the period dropdown and its summary", async () => {
    const user = userEvent.setup();
    renderBoard(<MoneyBoard initialMonth="2026-10" />);
    await screen.findByRole("list", { name: "Expenses" });
    expect(screen.getByRole("button", { name: /^Period: / })).toBeInTheDocument();
    await user.click(within(screen.getByRole("group", { name: "Expenses view" })).getByRole("button", { name: "Calendar" }));
    expect(await screen.findByRole("grid", { name: "Expenses 2026-10" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Period: / })).not.toBeInTheDocument();
    const day = await screen.findByRole("gridcell", { name: "Tue 13 Oct" });
    expect(within(day).getByText("€12.50")).toBeInTheDocument();
    expect(getRangeMock).toHaveBeenCalledTimes(1); // the calendar reuses the month's rows
  });

  it("Export CSV links to the shown month", async () => {
    renderBoard(<MoneyBoard initialMonth="2026-09" />);
    const link = await screen.findByRole("link", { name: "Export CSV" });
    expect(link).toHaveAttribute("href", "/api/money/export.csv?from=2026-09&to=2026-09");
    expect(link).toHaveAttribute("download");
  });

  it("the month nav stops at this month", async () => {
    const user = userEvent.setup();
    renderBoard(<MoneyBoard />);
    await screen.findByRole("group", { name: "Spent this month" });
    expect(screen.getByRole("button", { name: "Next month" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Previous month" }));
    await waitFor(() => expect(getSummaryMock).toHaveBeenLastCalledWith(expect.stringMatching(/^\d{4}-\d{2}$/)));
    expect(screen.getByRole("button", { name: "Next month" })).toBeEnabled();
  });

  it("marks web content, and keeping it reloads", async () => {
    keepExpenseMock.mockResolvedValue({ ...TAXI, tainted: false });
    const user = userEvent.setup();
    renderBoard(<MoneyBoard />);
    const list = await screen.findByRole("list", { name: "Expenses" });
    expect(within(list).getByText("from web content")).toBeInTheDocument();
    expect(within(list).getAllByRole("button", { name: /^Keep/ })).toHaveLength(1);
    await user.click(within(list).getByRole("button", { name: "Keep the travel expense as yours" }));
    expect(keepExpenseMock).toHaveBeenCalledWith("e2");
    await waitFor(() => expect(getSummaryMock).toHaveBeenCalledTimes(2));
  });

  it("unstarring a Pinned card stars it off and reloads", async () => {
    starExpenseMock.mockResolvedValue({});
    const user = userEvent.setup();
    renderBoard(<MoneyBoard />);
    await user.click(await screen.findByRole("button", { name: "Unstar Sofa" }));
    expect(starExpenseMock).toHaveBeenCalledWith("s1", false);
    await waitFor(() => expect(getSummaryMock).toHaveBeenCalledTimes(2));
  });

  it("says so when the month has no expenses", async () => {
    getSummaryMock.mockResolvedValue(makeSummary({ total: "0.00", expense_count: 0, by_project: [],
      other_currencies: {}, pinned_projects: [], pinned_expenses: [] }));
    getRangeMock.mockResolvedValue(EMPTY);
    renderBoard(<MoneyBoard initialMonth="2026-09" />);
    expect(await screen.findByText("Nothing spent in September 2026.")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Expenses" })).not.toBeInTheDocument();
  });

  it("adds what the line reads and reloads", async () => {
    createExpenseMock.mockResolvedValue(FOOD);
    const user = userEvent.setup();
    renderBoard(<MoneyBoard />);
    await user.type(await screen.findByLabelText("New expense"), "€12.50 lunch{Enter}", { delay: null });
    await waitFor(() => expect(createExpenseMock).toHaveBeenCalledWith(
      expect.objectContaining({ amount: "12.50", note: "lunch" })));
    await waitFor(() => expect(getSummaryMock).toHaveBeenCalledTimes(2));
  });

  it("says what went wrong when the month can't load", async () => {
    getSummaryMock.mockRejectedValue(new Error("down"));
    renderBoard(<MoneyBoard />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong");
  });

  it("goes to the previous month", async () => {
    const user = userEvent.setup();
    renderBoard(<MoneyBoard initialMonth="2026-10" />);
    await screen.findByRole("group", { name: "Spent this month" });
    await user.click(screen.getByRole("button", { name: "Previous month" }));
    await waitFor(() => expect(getSummaryMock).toHaveBeenLastCalledWith("2026-09"));
    expect(getRangeMock).toHaveBeenLastCalledWith("2026-09-01", "2026-09-30", undefined);
  });

  it("a past month keeps the line and offers the way back", async () => {
    const user = userEvent.setup();
    renderBoard(<MoneyBoard initialMonth="2020-01" />);
    await screen.findByRole("group", { name: "Spent this month" });
    expect(screen.getByLabelText("New expense")).toBeInTheDocument();
    expect(screen.getByText(/Type a day in the line, like ‘yesterday’ or ‘3\/10’/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next month" })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: /^Back to / }));
    expect(screen.getByRole("button", { name: "Next month" })).toBeDisabled();
    expect(getSummaryMock).toHaveBeenLastCalledWith(zoneMonth(new Date()));
  });
});

describe("MoneyBoard stars, voids and one project's month", () => {
  it("stars from the list and voids from the menu, reloading after each", async () => {
    starExpenseMock.mockResolvedValue({});
    voidExpenseMock.mockResolvedValue({});
    const user = userEvent.setup();
    renderBoard(<MoneyBoard />);
    await screen.findByRole("list", { name: "Expenses" });
    await user.click(within(rowOf("lunch")).getByRole("button", { name: "Star the food expense" }));
    expect(starExpenseMock).toHaveBeenCalledWith("e1", true);
    await waitFor(() => expect(getSummaryMock).toHaveBeenCalledTimes(2));
    await user.click(within(rowOf("lunch")).getByRole("button", { name: "More for the food expense" }));
    await user.click(await screen.findByRole("menuitem", { name: "Void" }));
    expect(voidExpenseMock).toHaveBeenCalledWith("e1", true);
    await waitFor(() => expect(getSummaryMock).toHaveBeenCalledTimes(3));
    expect(await screen.findByText("Expense voided")).toBeInTheDocument();
  });

  it("a project's month asks for its own rows and adds to it", async () => {
    getSummaryMock.mockResolvedValue(makeSummary({ by_project: [{
      ...SUMMARY.by_project[3], project: "food", project_id: "p-food", spent: "12.50",
    }] }));
    getRangeMock.mockResolvedValue(makeRange({ expenses: [FOOD], days: [RANGE.days[0]] }));
    createExpenseMock.mockResolvedValue(FOOD);
    const user = userEvent.setup();
    renderBoard(<MoneyBoard initialMonth="2026-10" project={{ id: "p-food", name: "food", currency: "EUR" }} />);
    const list = await screen.findByRole("list", { name: "Expenses" });
    expect(getRangeMock).toHaveBeenCalledWith("2026-10-01", "2026-10-31", "p-food");
    expect(within(list).getAllByRole("listitem")).toHaveLength(1);
    expect(within(list).getByText("lunch")).toBeInTheDocument();
    expect(document.querySelector(".xp__tag")).toBeNull(); // every row is this project
    expect(screen.getByText(/12\.50/, { selector: ".money-board__total strong" })).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Spent this month" })).not.toBeInTheDocument();
    parseExpenseLineMock.mockResolvedValue(makeExpenseLine({ note: "", amount: "5.00", ready: true }));
    await user.type(screen.getByLabelText("New expense"), "€5{Enter}", { delay: null });
    // By id, so the gateway files it in this project and in its currency (H7), never by a name.
    await waitFor(() => expect(createExpenseMock).toHaveBeenCalledWith(
      expect.objectContaining({ amount: "5.00", project_id: "p-food" })));
  });

  it("says when a project spent nothing that month", async () => {
    getSummaryMock.mockResolvedValue(makeSummary({ by_project: [] }));
    getRangeMock.mockResolvedValue(EMPTY);
    renderBoard(<MoneyBoard initialMonth="2026-09" project={{ id: "p-garden", name: "Garden", currency: "EUR" }} />);
    expect(await screen.findByText("Nothing spent on this project in September 2026.")).toBeInTheDocument();
  });
});

describe("the thinner side column", () => {
  it("holds the budgets only; Reports sits by Export CSV", async () => {
    renderBoard(<MoneyBoard />);
    const side = await screen.findByRole("complementary", { name: "Budgets" });
    expect(within(side).getByRole("region", { name: "Budgets this month" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Last 6 months" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "No project" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reports" }).closest(".month-nav")).not.toBeNull();
  });

  it("No project is a chip on the list that opens and closes the inbox", async () => {
    getInboxMock.mockResolvedValue({ expenses: [FOOD, TAXI], next: null });
    const user = userEvent.setup();
    renderBoard(<MoneyBoard />);
    const chip = await screen.findByRole("button", { name: "No project · 2" });
    expect(chip.closest(".mtools")).not.toBeNull();
    await user.click(chip);
    expect(await screen.findByRole("list", { name: "Expenses without a project" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "No project · 2" })).toHaveAttribute("aria-pressed", "true");
    await user.click(screen.getByRole("button", { name: "No project · 2" }));
    expect(await screen.findByRole("list", { name: "Expenses" })).toBeInTheDocument();
  });

  it("with every expense in a project there is no chip", async () => {
    renderBoard(<MoneyBoard />);
    await screen.findByRole("list", { name: "Expenses" });
    expect(screen.queryByRole("button", { name: /^No project/ })).not.toBeInTheDocument();
  });
});
