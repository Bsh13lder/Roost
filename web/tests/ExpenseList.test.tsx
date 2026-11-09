import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ExpenseDays } from "../src/components/board/ExpenseDays";
import { useExpenseActions } from "../src/components/board/useExpenseActions";
import { ApiError } from "../src/api/client";
import { ToastProvider } from "../src/ui/Toast";
import { makeRange } from "./moneyFixtures";

const deleteMock = vi.fn();
const restoreMock = vi.fn();
const voidMock = vi.fn();
const starMock = vi.fn();
const keepMock = vi.fn();
const updateMock = vi.fn();
vi.mock("../src/api/money", () => ({
  deleteExpense: (...a: unknown[]) => deleteMock(...a), restoreExpense: (...a: unknown[]) => restoreMock(...a),
  voidExpense: (...a: unknown[]) => voidMock(...a), starExpense: (...a: unknown[]) => starMock(...a),
  keepExpense: (...a: unknown[]) => keepMock(...a), updateExpense: (...a: unknown[]) => updateMock(...a),
}));
vi.mock("../src/api/projects", () => ({ listProjects: () => Promise.resolve([]) }));
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => ({ bots: {}, boardVersion: { tasks: 0, money: 0 } }) }));
vi.mock("../src/api/dates", () => ({ parseDate: vi.fn() }));

const reload = vi.fn();
const onError = vi.fn();

function Harness() {
  const actions = useExpenseActions(reload, onError);
  return <ExpenseDays data={makeRange()} showProject actions={actions} today="2026-10-20" />;
}
const renderList = () => render(<ToastProvider><Harness /></ToastProvider>);
const rowOf = (note: string) => screen.getByText(note).closest("li") as HTMLElement;

beforeEach(() => {
  for (const mock of [deleteMock, restoreMock, voidMock, starMock, keepMock, updateMock, reload, onError]) mock.mockReset();
  for (const mock of [deleteMock, restoreMock, voidMock, starMock, keepMock, updateMock]) mock.mockResolvedValue({});
});
afterEach(() => cleanup());

async function chooseFromMenu(user: ReturnType<typeof userEvent.setup>, note: string, item: string) {
  await user.click(within(rowOf(note)).getByRole("button", { name: /^More for/ }));
  await user.click(await screen.findByRole("menuitem", { name: item }));
}

describe("expense rows: delete, void, star", () => {
  it("delete shows Undo, which restores", async () => {
    const user = userEvent.setup();
    renderList();
    await chooseFromMenu(user, "Paint", "Delete");
    expect(deleteMock).toHaveBeenCalledWith("e1");
    const toast = await screen.findByText("Expense deleted");
    await user.click(within(toast.parentElement as HTMLElement).getByRole("button", { name: "Undo" }));
    expect(restoreMock).toHaveBeenCalledWith("e1");
    await waitFor(() => expect(reload).toHaveBeenCalledTimes(2));
  });

  it("void shows Undo", async () => {
    const user = userEvent.setup();
    renderList();
    await chooseFromMenu(user, "Paint", "Void");
    expect(voidMock).toHaveBeenCalledWith("e1", true);
    const toast = await screen.findByText("Expense voided");
    await user.click(within(toast.parentElement as HTMLElement).getByRole("button", { name: "Undo" }));
    expect(voidMock).toHaveBeenLastCalledWith("e1", false);
  });

  it("a void row offers Restore", async () => {
    const user = userEvent.setup();
    renderList();
    await chooseFromMenu(user, "Old lamp", "Restore");
    expect(voidMock).toHaveBeenCalledWith("e4", false);
  });

  it("a restore into a gone project says why", async () => {
    restoreMock.mockRejectedValue(new ApiError(422, "Its project is gone; restore it into another project."));
    const user = userEvent.setup();
    renderList();
    await chooseFromMenu(user, "Paint", "Delete");
    const toast = await screen.findByText("Expense deleted");
    await user.click(within(toast.parentElement as HTMLElement).getByRole("button", { name: "Undo" }));
    expect(await screen.findByText("Its project is gone; restore it into another project.")).toBeInTheDocument();
  });

  it("the star shows on hover and toggles", async () => {
    const user = userEvent.setup();
    renderList();
    const star = within(rowOf("Paint")).getByRole("button", { name: "Star the Casa Nueva expense" });
    expect(star).toHaveAttribute("aria-pressed", "false");
    await user.click(star);
    expect(starMock).toHaveBeenCalledWith("e1", true);
    await waitFor(() => expect(reload).toHaveBeenCalled());
  });

  it("a failed write is told in plain words", async () => {
    deleteMock.mockRejectedValue(new ApiError(404, "Expense not found"));
    const user = userEvent.setup();
    renderList();
    await chooseFromMenu(user, "Paint", "Delete");
    await waitFor(() => expect(onError).toHaveBeenCalledWith("Expense not found"));
  });

  it("editing opens the row in place and saves through the gateway", async () => {
    const user = userEvent.setup();
    renderList();
    await user.click(within(rowOf("Paint")).getByRole("button", { name: "Edit the Casa Nueva expense" }));
    const note = screen.getByLabelText("Note");
    await user.clear(note);
    await user.type(note, "Rollers{Enter}");
    expect(updateMock).toHaveBeenCalledWith("e1", { note: "Rollers" });
    await waitFor(() => expect(reload).toHaveBeenCalled());
    await waitFor(() => expect(screen.queryByLabelText("Note")).not.toBeInTheDocument());
  });

  it("a web-made row offers Keep", async () => {
    const range = makeRange();
    range.expenses[0] = { ...range.expenses[0], tainted: true };
    const user = userEvent.setup();
    function Tainted() {
      const actions = useExpenseActions(reload, onError);
      return <ExpenseDays data={range} showProject actions={actions} today="2026-10-20" />;
    }
    render(<ToastProvider><Tainted /></ToastProvider>);
    expect(within(rowOf("Paint")).getByText("from web content")).toBeInTheDocument();
    await user.click(within(rowOf("Paint")).getByRole("button", { name: "Keep the Casa Nueva expense as yours" }));
    expect(keepMock).toHaveBeenCalledWith("e1");
  });
});
