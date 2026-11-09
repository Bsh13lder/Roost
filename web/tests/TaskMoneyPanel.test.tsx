import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactElement } from "react";
import { cleanup, render as renderPlain, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TaskMoneyPanel } from "../src/components/tasks/TaskMoneyPanel";
import { makeExpense } from "./projectFixtures";
import { makeExpenseLine } from "./moneyFixtures";
import { makeTaskDetail } from "./taskFixtures";
import { ToastProvider } from "../src/ui/Toast";

const createExpenseMock = vi.fn();
const parseMock = vi.fn();
const voidExpenseMock = vi.fn();
const deleteExpenseMock = vi.fn();
vi.mock("../src/api/money", () => ({
  deleteExpense: (...a: unknown[]) => deleteExpenseMock(...a),
  restoreExpense: vi.fn().mockResolvedValue({}),
  createExpense: (...a: unknown[]) => createExpenseMock(...a),
  parseExpenseLine: (...a: unknown[]) => parseMock(...a),
  voidExpense: (...a: unknown[]) => voidExpenseMock(...a),
  starExpense: vi.fn(),
  keepExpense: vi.fn(),
}));
vi.mock("../src/api/dates", () => ({ parseDate: vi.fn() }));
vi.mock("../src/api/projects", () => ({ listProjects: vi.fn().mockResolvedValue([]) }));
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => ({ bots: {}, boardVersion: { tasks: 0, money: 0 } }) }));

const onChanged = vi.fn();
const render = (ui: ReactElement) => renderPlain(<ToastProvider>{ui}</ToastProvider>);
const inProject = makeTaskDetail({
  project_id: "p1", allocated_budget: "50.00",
  money: { planned: "50.00", spent: "62.50", left: "-12.50", currency: "EUR", steps: { "s-1": "12.50", "s-2": "0.00" },
    other_currencies: { USD: "7.00" }, steps_other_currencies: {}, used_percent: 125, tone: "over" },
  expenses: [makeExpense({ id: "e1", task_id: "t1", step_id: "s-1", amount: "12.50", description: "washers" })],
});

beforeEach(() => {
  for (const mock of [createExpenseMock, voidExpenseMock, deleteExpenseMock, onChanged, parseMock]) mock.mockReset();
  deleteExpenseMock.mockResolvedValue(undefined);
  parseMock.mockResolvedValue(makeExpenseLine({ note: "washer", amount: "8.40", ready: true }));
  createExpenseMock.mockResolvedValue({});
  voidExpenseMock.mockResolvedValue({});
});
afterEach(() => cleanup());

describe("the drawer's money (redesign P3)", () => {
  it("shows Planned, Spent, Left and a meter in the server's tone", () => {
    render(<TaskMoneyPanel task={inProject} onChanged={onChanged} />);
    const figures = screen.getByRole("group", { name: "Planned, spent and left" });
    expect(figures).toHaveTextContent("Planned€50.00");
    expect(figures).toHaveTextContent("Spent€62.50");
    expect(figures).toHaveTextContent("Left-€12.50");
    expect(screen.getByText("€12.50 over").closest(".badge")).toHaveClass("badge--danger");
    const meter = screen.getByRole("meter", { name: "Budget used" });
    expect(meter).toHaveAttribute("aria-valuenow", "100");
    expect(meter.firstElementChild).toHaveClass("meter__fill--over");
    expect(screen.getByText("washers")).toBeInTheDocument();
  });

  it("says No budget yet without one", () => {
    const noSlice = makeTaskDetail({ project_id: "p1", money: { ...inProject.money!, planned: null, left: null, used_percent: null, tone: null } });
    render(<TaskMoneyPanel task={noSlice} onChanged={onChanged} />);
    expect(screen.getByText(/^No budget yet\./)).toBeInTheDocument();
    expect(screen.queryByRole("meter")).not.toBeInTheDocument();
  });

  it("shows spending in another currency apart, never added in", () => {
    render(<TaskMoneyPanel task={inProject} onChanged={onChanged} />);
    expect(screen.getByText("Also spent: US$7.00")).toBeInTheDocument();
  });

  it("adds an expense with the expense line, for one of the task's steps, in the task's project", async () => {
    const user = userEvent.setup();
    render(<TaskMoneyPanel task={inProject} onChanged={onChanged} />);
    expect(screen.queryByLabelText("Amount")).not.toBeInTheDocument(); // the old form is gone
    await user.click(screen.getByRole("combobox", { name: "For" }));
    await user.click(await screen.findByRole("option", { name: "Fit it" }));
    await user.type(screen.getByLabelText("New expense"), "€8,40 washer{Enter}", { delay: null });
    await waitFor(() => expect(createExpenseMock).toHaveBeenCalled());
    expect(createExpenseMock).toHaveBeenCalledWith(expect.objectContaining({
      amount: "8.40", project_id: "p1", note: "washer", task_id: "t1", step_id: "s-2",
    }));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(screen.getByLabelText("New expense")).toHaveValue("");
  });

  it("voids an expense and the drawer reloads", async () => {
    const user = userEvent.setup();
    render(<TaskMoneyPanel task={inProject} onChanged={onChanged} />);
    await user.click(screen.getByRole("button", { name: /^More for / }));
    await user.click(await screen.findByRole("menuitem", { name: "Void" }));
    expect(voidExpenseMock).toHaveBeenCalledWith("e1", true);
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it("deletes an expense from the drawer, with Undo, and the drawer reloads", async () => {
    const user = userEvent.setup();
    render(<TaskMoneyPanel task={inProject} onChanged={onChanged} />);
    await user.click(screen.getByRole("button", { name: /^More for / }));
    await user.click(await screen.findByRole("menuitem", { name: "Delete" }));
    expect(deleteExpenseMock).toHaveBeenCalledWith("e1");
    expect(await screen.findByText("Expense deleted")).toBeInTheDocument();
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it("a task in no project shows its money in General's currency, with a budget of its own", () => {
    const loose = makeTaskDetail({
      project_id: null, allocated_budget: "40.00",
      money: { planned: "40.00", spent: "10.00", left: "30.00", currency: "EUR", steps: {}, other_currencies: {},
        steps_other_currencies: {}, used_percent: 25, tone: "ok" },
    });
    render(<TaskMoneyPanel task={loose} onChanged={onChanged} />);
    expect(screen.getByText("In no project, so its money counts in General, in EUR.")).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Planned, spent and left" })).toHaveTextContent("Left€30.00");
  });

  it("a task in no project files its expense under the whole task", async () => {
    const user = userEvent.setup();
    render(<TaskMoneyPanel task={makeTaskDetail({ steps: [] })} onChanged={onChanged} />);
    expect(screen.queryByRole("combobox", { name: "For" })).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("New expense"), "€8,40 washer{Enter}", { delay: null });
    await waitFor(() => expect(createExpenseMock).toHaveBeenCalled());
    const sent = createExpenseMock.mock.calls[0][0] as Record<string, unknown>;
    expect(sent).toMatchObject({ amount: "8.40", task_id: "t1" });
    expect(sent).not.toHaveProperty("project_id");
    expect(sent).not.toHaveProperty("step_id");
  });
});
