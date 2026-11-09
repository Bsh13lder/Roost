import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StepList } from "../src/components/tasks/StepList";
import { ApiError } from "../src/api/client";
import type { StepMoneyOut } from "../src/api/types";
import { makeTask } from "./taskFixtures";

const updateStepMock = vi.fn();
vi.mock("../src/api/tasks", () => ({
  addStep: vi.fn(),
  updateStep: (...a: unknown[]) => updateStepMock(...a),
  moveStep: vi.fn(),
  deleteStep: vi.fn(),
}));

const onChanged = vi.fn();
const task = makeTask({
  steps: [{ id: "s-1", title: "Buy a washer", done: false }, { id: "s-2", title: "Fit it", done: false }],
});
const none: StepMoneyOut = { planned: null, spent: "0.00", left: null, used_percent: null, tone: null };
const money: Record<string, StepMoneyOut> = {
  "s-1": { planned: "20.00", spent: "25.00", left: "-5.00", used_percent: 125, tone: "over" },
  "s-2": none,
};
const stepRow = (title: string) => screen.getByText(title).closest("li") as HTMLElement;

beforeEach(() => {
  updateStepMock.mockReset();
  onChanged.mockReset();
  updateStepMock.mockResolvedValue(task);
});
afterEach(() => cleanup());

describe("a step's own budget (owner, 2026-10-26)", () => {
  it("shows spent of planned and what is over, in the server's numbers", () => {
    render(<StepList task={task} money={money} currency="EUR" onChanged={onChanged} />);
    const row = within(stepRow("Buy a washer"));
    expect(row.getByText("€25.00 of €20.00")).toBeInTheDocument();
    expect(row.getByText("€5.00 over").closest(".badge")).toHaveClass("badge--danger");
    expect(within(stepRow("Fit it")).queryByText(/ of /)).not.toBeInTheDocument();
  });

  it("sets a budget on a step and the drawer reloads", async () => {
    const user = userEvent.setup();
    render(<StepList task={task} money={money} currency="EUR" onChanged={onChanged} />);
    await user.click(screen.getByRole("button", { name: "Budget for Fit it" }));
    await user.type(screen.getByLabelText("Budget for Fit it, in EUR"), "12,50{Enter}");
    expect(updateStepMock).toHaveBeenCalledWith("t1", "s-2", { budget: "12,50" });
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it("clears a step's budget", async () => {
    const user = userEvent.setup();
    render(<StepList task={task} money={money} currency="EUR" onChanged={onChanged} />);
    await user.click(screen.getByRole("button", { name: "Budget for Buy a washer" }));
    expect(screen.getByLabelText("Budget for Buy a washer, in EUR")).toHaveValue("20.00");
    await user.click(screen.getByRole("button", { name: "Clear budget" }));
    expect(updateStepMock).toHaveBeenCalledWith("t1", "s-1", { budget: null });
  });

  it("says why when the server refuses the amount", async () => {
    updateStepMock.mockRejectedValue(new ApiError(422, "An amount must be more than 0 and at most 1,000,000."));
    const user = userEvent.setup();
    render(<StepList task={task} money={money} currency="EUR" onChanged={onChanged} />);
    await user.click(screen.getByRole("button", { name: "Budget for Fit it" }));
    await user.type(screen.getByLabelText("Budget for Fit it, in EUR"), "0{Enter}");
    expect(await screen.findByText(/more than 0/)).toBeInTheDocument();
    expect(onChanged).not.toHaveBeenCalled();
  });
});
