import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QuickAdd } from "../src/components/tasks/QuickAdd";
import { makeRichLine } from "./quickRichFixtures";
import { makeTask } from "./taskFixtures";

const parseQuickLineMock = vi.fn();
const parsePastedListMock = vi.fn();
const createTaskMock = vi.fn();
vi.mock("../src/api/projects", () => ({ listProjects: () => Promise.resolve([]) }));
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => ({ bots: {}, boardVersion: { money: 0, tasks: 0 } }) }));
vi.mock("../src/api/tasks", () => ({
  parseQuickLine: (...a: unknown[]) => parseQuickLineMock(...a),
  parsePastedList: (...a: unknown[]) => parsePastedListMock(...a),
  createTask: (...a: unknown[]) => createTaskMock(...a),
}));

const LIST = "Buy milk\nCall Ana tomorrow\n  ask about rent";
const READ = {
  count: 2, ready: true, problem: null,
  tasks: [
    { ...makeRichLine({ title: "Buy milk", ready: true }), steps: [] },
    { ...makeRichLine({ title: "Call Ana", due_date: "2026-10-21", ready: true }), steps: ["ask about rent"] },
  ],
};
const onAdded = vi.fn();

function paste(text: string) {
  fireEvent.paste(screen.getByLabelText("New task"), { clipboardData: { getData: () => text } });
}

beforeEach(() => {
  parseQuickLineMock.mockReset().mockResolvedValue(makeRichLine({ title: "x", ready: true }));
  parsePastedListMock.mockReset().mockResolvedValue(READ);
  createTaskMock.mockReset().mockResolvedValue(makeTask());
  onAdded.mockReset();
});
afterEach(() => cleanup());

describe("pasting a list into the quick add", () => {
  it("asks 'Add 2 tasks?' and creates nothing until you say yes", async () => {
    render(<QuickAdd onAdded={onAdded} />);
    paste(LIST);
    expect(await screen.findByText("Add 2 tasks?")).toBeInTheDocument();
    expect(parsePastedListMock).toHaveBeenCalledWith({ text: LIST });
    expect(screen.getByText("Buy milk")).toBeInTheDocument();
    expect(screen.getByText("1 step")).toBeInTheDocument();
    expect(createTaskMock).not.toHaveBeenCalled();
  });

  it("creates each task with its steps on yes", async () => {
    const user = userEvent.setup();
    render(<QuickAdd onAdded={onAdded} />);
    paste(LIST);
    await user.click(await screen.findByRole("button", { name: "Add 2 tasks" }));
    await waitFor(() => expect(createTaskMock).toHaveBeenCalledTimes(2));
    expect(createTaskMock).toHaveBeenNthCalledWith(1, { title: "Buy milk" });
    expect(createTaskMock).toHaveBeenNthCalledWith(2, { title: "Call Ana", due_date: "2026-10-21", steps: ["ask about rent"] });
    await waitFor(() => expect(onAdded).toHaveBeenCalled());
    expect(screen.queryByText("Add 2 tasks?")).not.toBeInTheDocument();
  });

  it("cancel drops the paste", async () => {
    const user = userEvent.setup();
    render(<QuickAdd onAdded={onAdded} />);
    paste(LIST);
    await user.click(await screen.findByRole("button", { name: "Cancel" }));
    expect(screen.queryByText("Add 2 tasks?")).not.toBeInTheDocument();
    expect(createTaskMock).not.toHaveBeenCalled();
  });

  it("shows the server's problem and cannot add until it is fixed", async () => {
    parsePastedListMock.mockResolvedValue({ ...READ, ready: false, problem: "Line 2: No project is called “Nowhere”." });
    render(<QuickAdd onAdded={onAdded} />);
    paste(LIST);
    expect(await screen.findByText("Line 2: No project is called “Nowhere”.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add 2 tasks" })).toBeDisabled();
  });

  it("says 'Add 1 task?' for one", async () => {
    parsePastedListMock.mockResolvedValue({ ...READ, count: 1, tasks: [READ.tasks[1]] });
    render(<QuickAdd onAdded={onAdded} />);
    paste("Call Ana\n  ask");
    expect(await screen.findByText("Add 1 task?")).toBeInTheDocument();
  });

  it("leaves a one-line paste to the input", () => {
    render(<QuickAdd onAdded={onAdded} />);
    paste("just one line\n");
    expect(parsePastedListMock).not.toHaveBeenCalled();
  });
});
