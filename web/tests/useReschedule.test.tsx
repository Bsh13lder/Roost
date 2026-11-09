import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { render, screen } from "@testing-library/react";

import { useReschedule } from "../src/components/board/useReschedule";
import { ToastProvider } from "../src/ui/Toast";
import type { TaskOut } from "../src/api/types";

const updateTask = vi.fn();
const moveOverdue = vi.fn();
const restoreDues = vi.fn();
vi.mock("../src/api/tasks", () => ({
  updateTask: (...a: unknown[]) => updateTask(...a),
  moveOverdue: (...a: unknown[]) => moveOverdue(...a),
  restoreDues: (...a: unknown[]) => restoreDues(...a),
}));

const task = { id: "t1", title: "Pay the deposit", due_date: "2026-10-18T09:30:00+02:00", reminder_at: "2026-10-18T07:30:00+00:00",
  pre_reminders: ["2026-10-18T06:00:00+00:00"] } as TaskOut;

beforeEach(() => {
  updateTask.mockReset().mockResolvedValue(task);
  moveOverdue.mockReset();
  restoreDues.mockReset().mockResolvedValue({ restored: 1 });
});
afterEach(cleanup);

function Harness({ run, onChanged }: { run: (api: ReturnType<typeof useReschedule>) => void; onChanged: () => void }) {
  const api = useReschedule(onChanged);
  return <button type="button" onClick={() => run(api)}>go</button>;
}

async function go(run: (api: ReturnType<typeof useReschedule>) => Promise<void> | void, onChanged = vi.fn()) {
  render(<ToastProvider><Harness run={run} onChanged={onChanged} /></ToastProvider>);
  await userEvent.click(screen.getByRole("button", { name: "go" }));
  return onChanged;
}

describe("useReschedule", () => {
  it("one task: PATCH then Undo restores due and reminders", async () => {
    const onChanged = await go((api) => { void api.one(task, { day: "2026-10-21", time: "10:00" }); });
    await waitFor(() => expect(updateTask).toHaveBeenCalledWith("t1", { due_date: "2026-10-21T10:00" }));
    expect(await screen.findByText("“Pay the deposit” moved to Wed 21 Oct, 10:00")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Undo" }));
    expect(restoreDues).toHaveBeenCalledWith([{ id: "t1", due_date: task.due_date, reminder_at: task.reminder_at,
      pre_reminders: task.pre_reminders }]);
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(2));
  });

  it("many overdue: move-overdue then Undo restores them all", async () => {
    const moved = [{ id: "a", due_date: "2026-10-01", reminder_at: null, pre_reminders: [] },
      { id: "b", due_date: "2026-10-02", reminder_at: null, pre_reminders: [] },
      { id: "c", due_date: "2026-10-03", reminder_at: null, pre_reminders: [] }];
    moveOverdue.mockResolvedValue({ moved });
    await go((api) => { void api.overdue({ day: "2026-10-21", time: null }); });
    await waitFor(() => expect(moveOverdue).toHaveBeenCalledWith("2026-10-21"));
    expect(await screen.findByText("3 tasks moved to Wed 21 Oct")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Undo" }));
    expect(restoreDues).toHaveBeenCalledWith(moved);
  });

  it("keeps the task's time when none is typed", async () => {
    await go((api) => { void api.one(task, { day: "2026-10-22", time: null }); });
    await waitFor(() => expect(updateTask).toHaveBeenCalledWith("t1", { due_date: "2026-10-22T09:30" }));
  });

  it("No date sends null and says so", async () => {
    await go((api) => { void api.one(task, { day: null, time: null }); });
    await waitFor(() => expect(updateTask).toHaveBeenCalledWith("t1", { due_date: null }));
    expect(await screen.findByText("“Pay the deposit” now has no date")).toBeInTheDocument();
  });

  it("an error shows a danger toast", async () => {
    updateTask.mockRejectedValue(new Error("down"));
    await go((api) => { void api.one(task, { day: "2026-10-22", time: null }); });
    await waitFor(() => expect(document.querySelector(".toast--danger")).not.toBeNull());
  });
});
