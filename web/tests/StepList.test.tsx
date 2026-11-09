import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StepList } from "../src/components/tasks/StepList";
import { ApiError } from "../src/api/client";
import { makeTask } from "./taskFixtures";

const addStepMock = vi.fn();
const updateStepMock = vi.fn();
const moveStepMock = vi.fn();
const deleteStepMock = vi.fn();
vi.mock("../src/api/tasks", () => ({
  addStep: (...a: unknown[]) => addStepMock(...a),
  updateStep: (...a: unknown[]) => updateStepMock(...a),
  moveStep: (...a: unknown[]) => moveStepMock(...a),
  deleteStep: (...a: unknown[]) => deleteStepMock(...a),
}));

const onChanged = vi.fn();
const task = makeTask({
  steps: [
    { id: "s-1", title: "Buy a washer", done: true }, { id: "s-2", title: "Fit it", done: false },
    { id: "s-3", title: "Test for leaks", done: false },
  ],
});
const stepRow = (title: string) => screen.getByText(title).closest("li") as HTMLElement;

beforeEach(() => {
  for (const mock of [addStepMock, updateStepMock, moveStepMock, deleteStepMock, onChanged]) mock.mockReset();
  for (const mock of [addStepMock, updateStepMock, moveStepMock]) mock.mockResolvedValue(task);
  deleteStepMock.mockResolvedValue({ ...task, moved_expenses: 0, moved_comments: 0 });
});
afterEach(() => cleanup());

describe("the drawer's steps (redesign P3)", () => {
  it("shows the progress, each step and what is spent on it", () => {
    render(<StepList task={task} spent={{ "s-1": "12.50", "s-2": "0.00" }} currency="EUR" onChanged={onChanged} />);
    expect(screen.getByRole("meter", { name: "Steps done" })).toHaveAttribute("aria-valuetext", "1 of 3 steps done");
    expect(screen.getByRole("checkbox", { name: "Done: Buy a washer" })).toBeChecked();
    expect(within(stepRow("Buy a washer")).getByText("€12.50 spent")).toBeInTheDocument();
    expect(within(stepRow("Fit it")).queryByText(/spent/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Move Buy a washer up" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Move Test for leaks down" })).toBeDisabled();
  });

  it("ticks and unticks a step, and the drawer reloads", async () => {
    const user = userEvent.setup();
    render(<StepList task={task} onChanged={onChanged} />);
    await user.click(screen.getByRole("checkbox", { name: "Done: Fit it" }));
    expect(updateStepMock).toHaveBeenCalledWith("t1", "s-2", { done: true });
    await user.click(screen.getByRole("checkbox", { name: "Done: Buy a washer" }));
    expect(updateStepMock).toHaveBeenLastCalledWith("t1", "s-1", { done: false });
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(2));
  });

  it("adds a step at the end, and renames one with Enter or keeps it with Cancel", async () => {
    const user = userEvent.setup();
    render(<StepList task={task} onChanged={onChanged} />);
    await user.type(screen.getByLabelText("New step"), "Call the plumber{Enter}");
    expect(addStepMock).toHaveBeenCalledWith("t1", "Call the plumber");
    await waitFor(() => expect(screen.getByLabelText("New step")).toHaveValue(""));
    await user.click(screen.getByRole("button", { name: "Rename Fit it" }));
    const box = screen.getByLabelText("New title for Fit it");
    await user.clear(box);
    await user.type(box, "Fit the washer{Enter}");
    expect(updateStepMock).toHaveBeenCalledWith("t1", "s-2", { title: "Fit the washer" });
    await user.click(screen.getByRole("button", { name: "Rename Test for leaks" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByLabelText("New title for Test for leaks")).not.toBeInTheDocument();
    expect(updateStepMock).toHaveBeenCalledTimes(1);
  });

  it("moves a step up or down by one place", async () => {
    const user = userEvent.setup();
    render(<StepList task={task} onChanged={onChanged} />);
    await user.click(screen.getByRole("button", { name: "Move Test for leaks up" }));
    expect(moveStepMock).toHaveBeenCalledWith("t1", "s-3", 1);
    await user.click(screen.getByRole("button", { name: "Move Buy a washer down" }));
    expect(moveStepMock).toHaveBeenLastCalledWith("t1", "s-1", 1);
  });

  it("deletes a step and says its money and comments stay on the task", async () => {
    deleteStepMock.mockResolvedValue({ ...task, moved_expenses: 1, moved_comments: 2 });
    const user = userEvent.setup();
    render(<StepList task={task} onChanged={onChanged} />);
    await user.click(screen.getByRole("button", { name: "Delete Buy a washer" }));
    expect(deleteStepMock).toHaveBeenCalledWith("t1", "s-1");
    expect(await screen.findByRole("status")).toHaveTextContent("Its 1 expense and 2 comments stay on the task.");
  });

  it("shows the server's reason when a change is refused, and keeps the text typed", async () => {
    addStepMock.mockRejectedValue(new ApiError(409, "This task's steps changed while yours was being saved. Try again."));
    const user = userEvent.setup();
    render(<StepList task={makeTask({ steps: [] })} onChanged={onChanged} />);
    expect(screen.queryByRole("meter")).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("New step"), "Buy a washer");
    await user.click(screen.getByRole("button", { name: "Add step" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Try again.");
    expect(screen.getByLabelText("New step")).toHaveValue("Buy a washer");
    expect(onChanged).not.toHaveBeenCalled();
  });
});
