import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { TaskRow, type TaskRowProps } from "../src/components/board/TaskRow";
import { ToastProvider } from "../src/ui/Toast";
import { LONG_PRESS_MS } from "../src/components/board/constants";
import { makeRow } from "./taskFixtures";

const updateStepMock = vi.fn();
vi.mock("../src/api/tasks", () => ({ updateStep: (...a: unknown[]) => updateStepMock(...a) }));
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => ({ bots: {}, boardVersion: { tasks: 0, money: 0 } }) }));

const noop = () => undefined;

function renderRow(overrides: Partial<TaskRowProps> = {}) {
  const props: TaskRowProps = {
    task: makeRow(), showProject: true, project: { name: "Renovation", color: "#22c55e" }, stepsOpen: false,
    onToggleSteps: noop, cursor: false, onComplete: noop, onOpen: noop, onFail: noop, onKeep: noop,
    onReschedule: noop, ...overrides,
  };
  return render(
    <MemoryRouter><ToastProvider><div role="grid" aria-label="Tasks"><TaskRow {...props} /></div></ToastProvider></MemoryRouter>,
  );
}

beforeEach(() => { updateStepMock.mockReset(); });
afterEach(() => cleanup());

describe("TaskRow (G3)", () => {
  it("marks urgent with a flag pill and a red edge, high with a flag, nothing for medium", () => {
    const { rerender } = renderRow({ task: makeRow({ priority: "urgent" }) });
    expect(screen.getByText("Urgent")).toBeInTheDocument();
    expect(screen.getByRole("row")).toHaveClass("task-row--urgent");
    cleanup();
    renderRow({ task: makeRow({ priority: "high" }) });
    expect(screen.getByTitle("High")).toBeInTheDocument();
    expect(screen.queryByText("Urgent")).toBeNull();
    expect(screen.getByRole("row")).not.toHaveClass("task-row--urgent");
    cleanup();
    renderRow({ task: makeRow({ priority: "medium" }) });
    expect(screen.queryByTitle("High")).toBeNull();
    expect(screen.queryByText("Urgent")).toBeNull();
    void rerender;
  });

  it("a done urgent task has no red edge", () => {
    renderRow({ task: makeRow({ priority: "urgent", status: "done" }) });
    expect(screen.getByRole("row")).not.toHaveClass("task-row--urgent");
  });

  it("shows money left, or over in danger, from the server", () => {
    const money = { planned: "400.00", spent: "320.00", left: "80.00", currency: "EUR", over: false };
    renderRow({ task: makeRow({ money }) });
    const left = screen.getAllByText("€80 left")[0];
    expect(left).toHaveAttribute("title", "€320 spent of €400");
    cleanup();
    renderRow({ task: makeRow({ money: { planned: "100.00", spent: "130.00", left: "-30.00", currency: "EUR", over: true } }) });
    expect(screen.getAllByText("€30 over")[0]).toHaveClass("task-row__money--over");
  });

  it("hides the project column on a project page", () => {
    renderRow();
    expect(screen.getAllByText("Renovation").length).toBeGreaterThan(0);
    cleanup();
    renderRow({ showProject: false, project: undefined });
    expect(screen.queryByText("Renovation")).toBeNull();
  });

  it("puts the actions in the tab order", async () => {
    const user = userEvent.setup();
    renderRow();
    await user.tab(); // the tick
    await user.tab(); // the title
    await user.tab(); // the steps chip
    await user.tab();
    expect(screen.getByRole("button", { name: "Reschedule Fix the sink" })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("button", { name: "More for Fix the sink" })).toHaveFocus();
  });

  it("the steps chip opens and closes this task's steps only", async () => {
    const onToggleSteps = vi.fn();
    const user = userEvent.setup();
    const { rerender } = renderRow({ onToggleSteps });
    const chip = screen.getByRole("button", { name: "Show the 2 steps of Fix the sink" });
    expect(chip).toHaveAttribute("aria-expanded", "false");
    expect(chip).toHaveAttribute("title", "1 of 2 steps · click to show");
    expect(screen.queryByText("Fit it")).toBeNull();
    await user.click(chip);
    expect(onToggleSteps).toHaveBeenCalledWith("t1");
    cleanup();
    renderRow({ stepsOpen: true });
    expect(screen.getByRole("button", { name: "Hide the 2 steps of Fix the sink" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Fit it")).toBeInTheDocument();
    void rerender;
  });

  it("ticking a step calls the step route", async () => {
    const onSteps = vi.fn();
    updateStepMock.mockResolvedValue(makeRow({ steps: [{ id: "s-1", title: "Buy a washer", done: true }, { id: "s-2", title: "Fit it", done: true }] }));
    const user = userEvent.setup();
    renderRow({ stepsOpen: true, onSteps });
    await user.click(screen.getByRole("checkbox", { name: "Complete step Fit it" }));
    expect(updateStepMock).toHaveBeenCalledWith("t1", "s-2", { done: true });
    expect(onSteps).toHaveBeenCalledWith("t1", [{ id: "s-1", title: "Buy a washer", done: true }, { id: "s-2", title: "Fit it", done: true }]);
  });

  it("puts the old step state back when the route fails", async () => {
    const onSteps = vi.fn();
    updateStepMock.mockRejectedValue(new Error("boom"));
    const user = userEvent.setup();
    renderRow({ stepsOpen: true, onSteps });
    await user.click(screen.getByRole("checkbox", { name: "Complete step Fit it" }));
    const calls = onSteps.mock.calls;
    expect(calls[0][1][1].done).toBe(true);
    expect(calls[calls.length - 1][1][1].done).toBe(false);
  });

  it("→ opens the reschedule popover", async () => {
    const user = userEvent.setup();
    renderRow();
    await user.click(screen.getByRole("button", { name: "Reschedule Fix the sink" }));
    expect(await screen.findByRole("dialog", { name: /Reschedule/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Tomorrow/ })).toBeInTheDocument();
  });

  it("completes from the tick, opens from the title and shows the repeat and star quietly", async () => {
    const onComplete = vi.fn();
    const onOpen = vi.fn();
    const user = userEvent.setup();
    const task = makeRow({ recurring: "0 9 * * *", repeat_text: "every day 09:00", starred: true });
    renderRow({ task, onComplete, onOpen });
    expect(screen.getByTitle("every day 09:00")).toBeInTheDocument();
    expect(screen.getByLabelText("Starred")).toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: "Complete Fix the sink" }));
    expect(onComplete).toHaveBeenCalledWith(task);
    await user.click(screen.getByRole("button", { name: "Fix the sink" }));
    expect(onOpen).toHaveBeenCalledWith("t1");
    await user.click(within(screen.getByRole("row")).getByText("Fix the sink").closest("[role=row]")!);
  });
});

// jsdom has no PointerEvent: a stand-in that keeps the pointer type and the coordinates.
class FakePointerEvent extends MouseEvent {
  readonly pointerType: string;
  constructor(type: string, init: MouseEventInit & { pointerType?: string } = {}) {
    super(type, init);
    this.pointerType = init.pointerType ?? "";
  }
}

describe("TaskRow on a phone (G14)", () => {
  beforeEach(() => { vi.stubGlobal("PointerEvent", FakePointerEvent); });
  afterEach(() => { vi.unstubAllGlobals(); });

  it("a long-press opens the row's menu", async () => {
    vi.useFakeTimers();
    try {
      const onOpen = vi.fn();
      renderRow({ task: makeRow({ title: "Fix the sink" }), onOpen });
      const row = screen.getByRole("row");
      fireEvent.pointerDown(row, { pointerType: "touch", clientX: 10, clientY: 10 });
      act(() => { vi.advanceTimersByTime(LONG_PRESS_MS - 1); });
      expect(screen.queryByRole("menu")).toBeNull();
      act(() => { vi.advanceTimersByTime(2); });
      expect(screen.getByRole("menuitem", { name: "Mark done" })).toBeInTheDocument();
      fireEvent.pointerUp(row, { pointerType: "touch" });
      fireEvent.click(row); // the click after a long press does not also open the drawer
      expect(onOpen).not.toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });

  it("a short press, a mouse press and a press that moves do not open it", () => {
    vi.useFakeTimers();
    try {
      renderRow();
      const row = screen.getByRole("row");
      fireEvent.pointerDown(row, { pointerType: "touch", clientX: 10, clientY: 10 });
      act(() => { vi.advanceTimersByTime(LONG_PRESS_MS - 100); });
      fireEvent.pointerUp(row, { pointerType: "touch" });
      act(() => { vi.advanceTimersByTime(500); });
      fireEvent.pointerDown(row, { pointerType: "mouse" });
      act(() => { vi.advanceTimersByTime(LONG_PRESS_MS + 10); });
      fireEvent.pointerDown(row, { pointerType: "touch", clientX: 10, clientY: 10 });
      fireEvent.pointerMove(row, { pointerType: "touch", clientX: 10, clientY: 60 });
      act(() => { vi.advanceTimersByTime(LONG_PRESS_MS + 10); });
      expect(screen.queryByRole("menu")).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });
});
