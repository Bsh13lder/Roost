import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ToastProvider } from "../src/ui/Toast";
import { makeRow } from "./taskFixtures";
import { FromLazyClawMark } from "../src/components/board/FromLazyClawMark";
import { TaskRow } from "../src/components/board/TaskRow";
import { ExpenseList } from "../src/components/board/ExpenseList";
import type { ExpenseOut, TaskOut } from "../src/api/types";

afterEach(() => cleanup());

const TASK: TaskOut = {
  id: "t1", title: "Buy tiles", description: null, category: null, priority: "medium", status: "todo",
  owner: "user", due_date: null, reminder_at: null, pre_reminders: [], recurring: null, recur_until: null,
  tags: [], steps: [], created_at: "2026-03-01T09:00:00+00:00", updated_at: "2026-03-01T09:00:00+00:00",
  completed_at: null, created_by_bot: null, tainted: false, project_id: null, allocated_budget: null,
};
const EXPENSE: ExpenseOut = {
  id: "e1", project: "Kitchen", project_id: "p1", task_id: null, step_id: null, amount: "25.50", currency: "EUR",
  description: "Tiles", vendor: null, spent_at: "2026-03-05", status: "posted", is_favorite: false,
  created_at: "2026-03-05T08:00:00+00:00", created_by_bot: null, tainted: false,
};

describe("FromLazyClawMark", () => {
  it("shows a small mark for a LazyClaw row", () => {
    render(<FromLazyClawMark from="lazyclaw" />);
    expect(screen.getByText("from LazyClaw")).toBeInTheDocument();
  });

  it.each([null, undefined])("shows nothing when the row was not imported (%s)", (value) => {
    const { container } = render(<FromLazyClawMark from={value} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("is on an imported task's row and not on another", () => {
    const noop = () => undefined;
    const props = { showProject: true, stepsOpen: false, onToggleSteps: noop, cursor: false, onComplete: noop,
      onOpen: noop, onFail: noop, onKeep: noop, onReschedule: noop };
    const tree = (from: "lazyclaw" | null) => (
      <MemoryRouter><ToastProvider><TaskRow task={makeRow({ ...TASK, imported_from: from })} {...props} /></ToastProvider></MemoryRouter>
    );
    const { rerender } = render(tree("lazyclaw"));
    expect(screen.getByText("from LazyClaw")).toBeInTheDocument();
    rerender(tree(null));
    expect(screen.queryByText("from LazyClaw")).toBeNull();
  });

  it("is on an imported expense's row", () => {
    const noop = () => undefined;
    render(<ExpenseList expenses={[{ ...EXPENSE, imported_from: "lazyclaw" }, { ...EXPENSE, id: "e2" }]} showProject
      currency="EUR" onKeep={noop} />);
    expect(screen.getAllByText("from LazyClaw")).toHaveLength(1);
  });
});

vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => ({ bots: {}, boardVersion: { tasks: 0, money: 0 } }) }));
