import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import TaskDrawer from "../src/components/tasks/TaskDrawer";
import { ToastProvider } from "../src/ui/Toast";
import { ApiError } from "../src/api/client";
import { makeProject } from "./projectFixtures";
import { makeTask, makeTaskDetail } from "./taskFixtures";

// Lead task 01: the task drawer saves each edit on its own. A pick saves at once; a typed field saves on
// Enter or when it is left; closing the drawer saves what is still typed; every save offers Undo.

const getTaskMock = vi.fn();
const updateTaskMock = vi.fn();
const parseQuickLineMock = vi.fn();
const onLeaveMock = vi.fn();
vi.mock("../src/api/tasks", () => ({
  updateTaskOnLeave: (...a: unknown[]) => onLeaveMock(...a),
  getTask: (...a: unknown[]) => getTaskMock(...a),
  updateTask: (...a: unknown[]) => updateTaskMock(...a),
  parseQuickLine: (...a: unknown[]) => parseQuickLineMock(...a),
  failTask: vi.fn(), deleteTask: vi.fn(), restoreDues: vi.fn(),
  completeTask: vi.fn(), reopenTask: vi.fn(), keepTask: vi.fn(),
}));
const listProjectsMock = vi.fn();
vi.mock("../src/api/projects", () => ({ listProjects: (...a: unknown[]) => listProjectsMock(...a) }));
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => ({ bots: {}, boardVersion: { tasks: 0, money: 0 } }) }));
vi.mock("../src/api/dates", () => ({ parseDate: vi.fn().mockResolvedValue({ due_date: null }) }));

const onClose = vi.fn();
const drawer = () => <ToastProvider><TaskDrawer taskId="t1" onClose={onClose} /></ToastProvider>;
const properties = () => screen.getByLabelText("Properties");
const ready = () => screen.findByRole("textbox", { name: "Title" });
const openProp = async (user: ReturnType<typeof userEvent.setup>, label: string) => {
  await user.click(within(properties()).getByRole("button", { name: new RegExp(`^${label}`) }));
  return screen.findByRole("dialog", { name: `Edit ${label}` });
};

beforeEach(() => {
  for (const mock of [getTaskMock, updateTaskMock, parseQuickLineMock, onLeaveMock, onClose]) mock.mockReset();
  getTaskMock.mockResolvedValue(makeTaskDetail());
  listProjectsMock.mockReset().mockResolvedValue([makeProject({ id: "p1", name: "Renovation" })]);
  updateTaskMock.mockImplementation(async (_id: string, patch: object) => makeTask({ ...patch, updated_at: "later" }));
});
afterEach(() => cleanup());

describe("Remind me in the drawer", () => {
  it("a quick pick saves at once: that time alone, no advance reminder", async () => {
    const user = userEvent.setup();
    render(drawer());
    await ready();
    const editor = await openProp(user, "Reminder");
    await user.click(within(editor).getByRole("button", { name: /10 min before/ }));
    await waitFor(() => expect(updateTaskMock).toHaveBeenCalledWith("t1",
      { reminder_at: "2026-10-16 08:50", pre_reminders: [] }));
  });
});

describe("the task drawer saves on its own", () => {
  it("has no Save changes button, even after an edit", async () => {
    const user = userEvent.setup();
    render(drawer());
    await ready();
    await openProp(user, "List");
    await user.type(screen.getByRole("textbox", { name: "List" }), "Home{Enter}");
    await waitFor(() => expect(updateTaskMock).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: "Save changes" })).not.toBeInTheDocument();
  });

  it("a picked property saves the moment it is picked, and Undo puts it back", async () => {
    const user = userEvent.setup();
    render(drawer());
    await ready();
    await openProp(user, "Priority");
    await user.click(screen.getByRole("combobox", { name: "Priority" }));
    await user.click(await screen.findByRole("option", { name: "High" }));
    await waitFor(() => expect(updateTaskMock).toHaveBeenCalledWith("t1", { priority: "high" }));
    expect(updateTaskMock).toHaveBeenCalledTimes(1);
    expect(await screen.findByText("Saved the priority")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Undo" })); // the toast sits outside the modal sheet
    await waitFor(() => expect(updateTaskMock).toHaveBeenLastCalledWith("t1", { priority: "medium" }));
  });

  it("a picked project saves at once", async () => {
    const user = userEvent.setup();
    render(drawer());
    await ready();
    await openProp(user, "Project");
    await user.click(screen.getByRole("combobox", { name: "Project" }));
    await user.click(await screen.findByRole("option", { name: "Renovation" }));
    await waitFor(() => expect(updateTaskMock).toHaveBeenCalledWith("t1", { project_id: "p1" }));
  });

  it("a typed field saves on Enter, trimmed, and its editor closes", async () => {
    const user = userEvent.setup();
    render(drawer());
    await ready();
    const editor = await openProp(user, "List");
    await user.type(within(editor).getByRole("textbox", { name: "List" }), "  Home  {Enter}");
    await waitFor(() => expect(updateTaskMock).toHaveBeenCalledWith("t1", { category: "Home" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Edit List" })).not.toBeInTheDocument());
    expect(updateTaskMock).toHaveBeenCalledTimes(1);
  });

  it("a task in no project takes a budget too, shown in General's currency (owner, 2026-10-26)", async () => {
    getTaskMock.mockResolvedValue(makeTaskDetail({
      money: { planned: null, spent: "0.00", left: null, currency: "EUR", steps: {}, other_currencies: {},
        steps_other_currencies: {}, used_percent: null, tone: null },
    }));
    const user = userEvent.setup();
    render(drawer());
    await ready();
    const editor = await openProp(user, "Budget");
    await user.type(within(editor).getByRole("textbox", { name: "Budget" }), "40{Enter}");
    await waitFor(() => expect(updateTaskMock).toHaveBeenCalledWith("t1", { allocated_budget: "40.00" }));
  });

  it("a typed field saves when it is left (its editor closes)", async () => {
    parseQuickLineMock.mockResolvedValue({ estimate_minutes: 45, recurring: null, repeat_problem: null });
    const user = userEvent.setup();
    render(drawer());
    await ready();
    await openProp(user, "Estimate");
    await user.type(screen.getByRole("textbox", { name: "Estimate" }), "~45m");
    await user.keyboard("{Escape}");
    await waitFor(() => expect(updateTaskMock).toHaveBeenCalledWith("t1", { estimate_minutes: 45 }));
  });

  it("the title saves when focus leaves it, with Undo", async () => {
    const user = userEvent.setup();
    render(drawer());
    const title = await ready();
    await user.clear(title);
    await user.type(title, "Fix the kitchen sink");
    await user.tab();
    await waitFor(() => expect(updateTaskMock).toHaveBeenCalledWith("t1", { title: "Fix the kitchen sink" }));
    expect(await screen.findByText("Renamed to “Fix the kitchen sink”")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Undo" }));
    await waitFor(() => expect(updateTaskMock).toHaveBeenLastCalledWith("t1", { title: "Fix the sink" }));
  });

  it("closing the drawer with an edit still typed saves it first", async () => {
    const user = userEvent.setup();
    render(drawer());
    await ready();
    await openProp(user, "List");
    await user.type(screen.getByRole("textbox", { name: "List" }), "Home");
    expect(updateTaskMock).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Close" }));
    await waitFor(() => expect(updateTaskMock).toHaveBeenCalledWith("t1", { category: "Home" }));
    expect(updateTaskMock).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalled();
  });

  it("leaving the page (the drawer goes away) saves a title still being typed", async () => {
    const user = userEvent.setup();
    const view = render(drawer());
    const title = await ready();
    await user.type(title, " today");
    view.unmount();
    await waitFor(() => expect(updateTaskMock).toHaveBeenCalledWith("t1", { title: "Fix the sink today" }));
  });

  it("an unchanged value saves nothing", async () => {
    const user = userEvent.setup();
    render(drawer());
    const title = await ready();
    await user.type(title, "  {Enter}");
    const editor = await openProp(user, "List");
    await user.type(within(editor).getByRole("textbox", { name: "List" }), "   {Enter}");
    await user.click(screen.getByRole("button", { name: "Close" }));
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(updateTaskMock).not.toHaveBeenCalled();
  });

  it("an empty title is never saved: the old one comes back with a gentle hint", async () => {
    const user = userEvent.setup();
    render(drawer());
    const title = await ready();
    await user.clear(title);
    await user.keyboard("{Enter}");
    expect(title).toHaveValue("Fix the sink");
    expect(await screen.findByText("A task needs a title, so the old one is back.")).toBeInTheDocument();
    expect(updateTaskMock).not.toHaveBeenCalled();
  });

  it("a failed save keeps what was typed and offers Try again", async () => {
    updateTaskMock.mockRejectedValueOnce(new ApiError(500, "The database is busy."));
    const user = userEvent.setup();
    render(drawer());
    await ready();
    await openProp(user, "List");
    await user.type(screen.getByRole("textbox", { name: "List" }), "Home{Enter}");
    expect(await screen.findByText("Couldn't save the list: The database is busy.")).toBeInTheDocument();
    expect(within(properties()).getByRole("button", { name: /^List, Home/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(updateTaskMock).toHaveBeenCalledTimes(2));
    expect(updateTaskMock).toHaveBeenLastCalledWith("t1", { category: "Home" });
    expect(await screen.findByText("Saved the list")).toBeInTheDocument();
  });

  it("a failed title save keeps the typed title", async () => {
    updateTaskMock.mockRejectedValueOnce(new ApiError(500, "The database is busy."));
    const user = userEvent.setup();
    render(drawer());
    const title = await ready();
    await user.clear(title);
    await user.type(title, "Fix the kitchen sink{Enter}");
    expect(await screen.findByText("Couldn't save the title: The database is busy.")).toBeInTheDocument();
    expect(title).toHaveValue("Fix the kitchen sink");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("a repeat it can't read is not sent, and says why", async () => {
    parseQuickLineMock.mockResolvedValue({ estimate_minutes: null, recurring: null, repeat_problem: "Repeats can be daily." });
    const user = userEvent.setup();
    render(drawer());
    await ready();
    await openProp(user, "Repeat");
    await user.type(screen.getByRole("textbox", { name: "Repeat" }), "every blue moon{Enter}");
    expect(await screen.findByText("Repeats can be daily.", { selector: ".toast__message" })).toBeInTheDocument();
    expect(updateTaskMock).not.toHaveBeenCalled();
    expect(within(properties()).getByRole("button", { name: /^Repeat, every blue moon/ })).toBeInTheDocument();
  });
});

describe("closing the tab while typing (lead 01b)", () => {
  const leave = () => window.dispatchEvent(new Event("pagehide"));

  it("a property still being typed is sent silently as the page goes", async () => {
    const user = userEvent.setup();
    render(drawer());
    await ready();
    await openProp(user, "List");
    await user.type(screen.getByRole("textbox", { name: "List" }), " Home ");
    leave();
    expect(onLeaveMock).toHaveBeenCalledWith("t1", { category: "Home" });
    expect(updateTaskMock).not.toHaveBeenCalled();
  });

  it("a title still being typed is sent too", async () => {
    const user = userEvent.setup();
    render(drawer());
    const title = await ready();
    await user.type(title, " today");
    leave();
    expect(onLeaveMock).toHaveBeenCalledWith("t1", { title: "Fix the sink today" });
  });

  it("nothing typed sends nothing", async () => {
    render(drawer());
    await ready();
    leave();
    expect(onLeaveMock).not.toHaveBeenCalled();
  });
});
