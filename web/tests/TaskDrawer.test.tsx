import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import TaskDrawer from "../src/components/tasks/TaskDrawer";
import { ToastProvider } from "../src/ui/Toast";
import { ApiError } from "../src/api/client";
import { makeProject } from "./projectFixtures";
import { stubPhone } from "./phone";
import { makeTask, makeTaskDetail } from "./taskFixtures";

const getTaskMock = vi.fn();
const updateTaskMock = vi.fn();
const failTaskMock = vi.fn();
const deleteTaskMock = vi.fn();
const restoreDuesMock = vi.fn();
const parseQuickLineMock = vi.fn();
vi.mock("../src/api/tasks", () => ({
  getTask: (...a: unknown[]) => getTaskMock(...a),
  updateTask: (...a: unknown[]) => updateTaskMock(...a),
  failTask: (...a: unknown[]) => failTaskMock(...a),
  deleteTask: (...a: unknown[]) => deleteTaskMock(...a),
  restoreDues: (...a: unknown[]) => restoreDuesMock(...a),
  parseQuickLine: (...a: unknown[]) => parseQuickLineMock(...a),
  completeTask: vi.fn(), reopenTask: vi.fn(), keepTask: vi.fn(),
}));
const listProjectsMock = vi.fn();
vi.mock("../src/api/projects", () => ({ listProjects: (...a: unknown[]) => listProjectsMock(...a) }));
let live = { bots: {}, boardVersion: { tasks: 0, money: 0 } };
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => live }));
vi.mock("../src/api/dates", () => ({ parseDate: vi.fn().mockResolvedValue({ due_date: null }) }));

const onClose = vi.fn();
const drawer = () => <ToastProvider><TaskDrawer taskId="t1" onClose={onClose} /></ToastProvider>;
const renderDrawer = () => render(drawer());
const properties = () => screen.getByLabelText("Properties");

beforeEach(() => {
  live = { bots: {}, boardVersion: { tasks: 0, money: 0 } };
  for (const mock of [getTaskMock, updateTaskMock, failTaskMock, deleteTaskMock, restoreDuesMock, parseQuickLineMock, onClose]) mock.mockReset();
  getTaskMock.mockResolvedValue(makeTaskDetail());
  updateTaskMock.mockImplementation(async (_id: string, patch: object) => makeTask({ ...patch, updated_at: "later" }));
  listProjectsMock.mockReset().mockResolvedValue([
    makeProject({ id: "p1", name: "Renovation" }), makeProject({ id: "p2", name: "Old shed", status: "archived" }),
  ]);
});
afterEach(() => cleanup());

describe("the task drawer as a property list (G5)", () => {
  it("edits the title in the head: Enter saves, Esc reverts", async () => {
    const user = userEvent.setup();
    renderDrawer();
    const title = await screen.findByRole("textbox", { name: "Title" });
    expect(title).toHaveValue("Fix the sink");
    await user.clear(title);
    await user.type(title, "Fix the kitchen sink{Escape}");
    expect(title).toHaveValue("Fix the sink");
    expect(updateTaskMock).not.toHaveBeenCalled();
    await user.clear(title);
    await user.type(title, "Fix the kitchen sink{Enter}");
    await waitFor(() => expect(updateTaskMock).toHaveBeenCalledTimes(1));
    expect(updateTaskMock).toHaveBeenCalledWith("t1", { title: "Fix the kitchen sink" });
  });

  it("each property opens its editor in a popover", async () => {
    const user = userEvent.setup();
    renderDrawer();
    await screen.findByRole("textbox", { name: "Title" });
    for (const label of ["Reminder", "Repeat", "Priority", "Project", "List", "Estimate"]) {
      await user.click(within(properties()).getByRole("button", { name: new RegExp(`^${label}`) }));
      expect(await screen.findByRole("dialog", { name: `Edit ${label}` })).toBeInTheDocument();
      await user.keyboard("{Escape}"); // a date field may keep it open: the next click outside closes it
    }
  });

  it("Due uses the reschedule popover and applies at once with Undo", async () => {
    restoreDuesMock.mockResolvedValue({ restored: 1 });
    const user = userEvent.setup();
    renderDrawer();
    await screen.findByRole("textbox", { name: "Title" });
    await user.click(within(properties()).getByRole("button", { name: /^Due/ }));
    await user.click(await screen.findByRole("button", { name: /^No date/ }));
    await waitFor(() => expect(updateTaskMock).toHaveBeenCalledWith("t1", { due_date: null }));
    expect(screen.queryByRole("button", { name: "Save changes" })).not.toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: "Undo" })); // the toast sits outside the modal sheet
    await waitFor(() => expect(restoreDuesMock).toHaveBeenCalled());
  });

  it("each editor saves its own field as it closes, and sends only that field", async () => {
    parseQuickLineMock.mockResolvedValue({ estimate_minutes: 45, recurring: null, repeat_problem: null });
    const user = userEvent.setup();
    renderDrawer();
    await screen.findByRole("textbox", { name: "Title" });
    await user.click(within(properties()).getByRole("button", { name: /^List/ }));
    await user.type(await screen.findByRole("textbox", { name: "List" }), "Home");
    await user.keyboard("{Escape}");
    await waitFor(() => expect(updateTaskMock).toHaveBeenCalledWith("t1", { category: "Home" }));
    await user.click(within(properties()).getByRole("button", { name: /^Estimate/ }));
    await user.type(await screen.findByRole("textbox", { name: "Estimate" }), "~45m");
    await user.keyboard("{Escape}");
    await waitFor(() => expect(updateTaskMock).toHaveBeenLastCalledWith("t1", { estimate_minutes: 45 }));
    expect(updateTaskMock).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole("button", { name: "Save changes" })).not.toBeInTheDocument();
  });

  it("the crumbs tone an overdue due in danger", async () => {
    getTaskMock.mockResolvedValue(makeTaskDetail({ due_date: "2020-01-01" }));
    renderDrawer();
    await screen.findByRole("textbox", { name: "Title" });
    const crumbs = document.querySelector(".drawer-crumbs") as HTMLElement;
    expect(within(crumbs).getByText("Wed 1 Jan")).toHaveClass("badge--danger");
  });
});

describe("the task drawer's actions", () => {
  it("marks an open task failed", async () => {
    failTaskMock.mockResolvedValue(makeTask({ status: "failed" }));
    const user = userEvent.setup();
    render(drawer());
    await user.click(await screen.findByRole("button", { name: "Mark failed" }));
    expect(failTaskMock).toHaveBeenCalledWith("t1");
  });

  it("Delete is danger and asks first, then closes", async () => {
    deleteTaskMock.mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(drawer());
    const del = await screen.findByRole("button", { name: "Delete task" });
    expect(del).toHaveClass("btn--danger");
    await user.click(del);
    expect(deleteTaskMock).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Delete Fix the sink for good" }));
    expect(deleteTaskMock).toHaveBeenCalledWith("t1");
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  it("says a task deleted elsewhere is gone, and shows the server's reason for any other failure", async () => {
    getTaskMock.mockRejectedValue(new ApiError(404, "Task not found"));
    const first = render(drawer());
    expect(await screen.findByText("This task is gone. It may have been deleted somewhere else.")).toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "Task not found" })).toBeInTheDocument();
    first.unmount();
    getTaskMock.mockRejectedValue(new ApiError(500, "The database is busy."));
    render(drawer());
    expect(await screen.findByRole("alert")).toHaveTextContent("The database is busy.");
  });
});

describe("the task drawer on a phone (G14)", () => {
  it("is full screen on a phone", async () => {
    const restore = stubPhone(true);
    try {
      renderDrawer();
      const sheet = (await screen.findByRole("dialog")) as HTMLElement;
      expect(sheet).toHaveClass("ui-sheet--full");
    } finally {
      restore();
    }
  });

  it("is the side drawer elsewhere", async () => {
    renderDrawer();
    expect(await screen.findByRole("dialog")).not.toHaveClass("ui-sheet--full");
  });
});
