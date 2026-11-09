import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Navigate, Route, Routes, useSearchParams } from "react-router-dom";
import { Project } from "../src/pages/Project";
import { ALL_TASKS_HREF } from "../src/pages/boardPaths";
import { makeBot } from "./fixtures";
import { budgetLine, makeProjectDetail, makeTopup } from "./projectFixtures";

const getProjectMock = vi.fn();
const updateProjectMock = vi.fn();
const setProjectBudgetMock = vi.fn();
const deleteProjectMock = vi.fn();
const addTopupMock = vi.fn();
const createNoteMock = vi.fn();
const createDocumentMock = vi.fn();
const pinMock = vi.fn();
vi.mock("../src/api/notes", () => ({ createNote: (...a: unknown[]) => createNoteMock(...a) }));
vi.mock("../src/api/documents", () => ({ createDocument: (...a: unknown[]) => createDocumentMock(...a) }));
vi.mock("../src/api/projects", () => ({
  pinProject: (...a: unknown[]) => pinMock(...a),
  getProject: (...a: unknown[]) => getProjectMock(...a),
  updateProject: (...a: unknown[]) => updateProjectMock(...a),
  setProjectBudget: (...a: unknown[]) => setProjectBudgetMock(...a),
  deleteProject: (...a: unknown[]) => deleteProjectMock(...a),
  addTopup: (...a: unknown[]) => addTopupMock(...a),
}));
vi.mock("../src/components/board/TasksBoard", () => ({
  TasksBoard: ({ projectId, currency }: { projectId: string; currency: string }) => <p>Tasks of {projectId} in {currency}</p>,
}));
vi.mock("../src/components/board/MoneyBoard", () => ({
  MoneyBoard: ({ project }: { project: { name: string } }) => <p>Months of {project.name}</p>,
}));
vi.mock("../src/components/notes/NotesBoard", () => ({
  default: ({ projectId, openId }: { projectId: string; openId?: string | null }) => <p>Notes of {projectId} open {openId ?? "none"}</p>,
}));
vi.mock("../src/components/documents/DocumentsBoard", () => ({
  default: ({ projectId, openId }: { projectId: string; openId?: string | null }) => <p>Docs of {projectId} open {openId ?? "none"}</p>,
}));
vi.mock("../src/hooks/useLiveStore", () => ({
  useLiveState: () => ({
    bots: { "bot-1": makeBot({ id: "bot-1", name: "Helper" }) },
    boardVersion: { tasks: 0, money: 0, notes: 0, documents: 0 },
  }),
}));

function BoardSpy() {
  const [params] = useSearchParams();
  return <p>Board on {params.get("tab")}{params.get("project") ? `, ${params.get("project")}` : ""}</p>;
}

function renderAt(entry: string) {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route path="/board/projects/:projectId" element={<Project />} />
        <Route path="/board/projects" element={<Navigate to={ALL_TASKS_HREF} replace />} />
        <Route path="/board" element={<BoardSpy />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  for (const mock of [getProjectMock, updateProjectMock, setProjectBudgetMock, deleteProjectMock, addTopupMock, createNoteMock, createDocumentMock, pinMock]) {
    mock.mockReset();
  }
  getProjectMock.mockResolvedValue(makeProjectDetail({ other_currencies: { USD: "20.00" }, starred_total: "45.00" }));
});
afterEach(() => cleanup());

describe("Project", () => {
  it("shows the lead bot, the dates, progress and both budgets, then the project's tasks", async () => {
    renderAt("/board/projects/p1");
    expect(await screen.findByRole("heading", { name: "Garden" })).toBeInTheDocument();
    expect(getProjectMock).toHaveBeenCalledWith("p1");
    expect(screen.getByText(/Led by Helper · 1 Oct 2026 → 20 Dec 2026 · \d+ days? (left|ago)|Led by Helper · 1 Oct 2026 → 20 Dec 2026 · ended/)).toBeInTheDocument();
    expect(screen.getByRole("meter", { name: "Total budget" })).toHaveAttribute("aria-valuenow", "92");
    expect(screen.getByText(/Also .*20\.00.*not in the total/)).toBeInTheDocument();
    const tasks = screen.getByRole("region", { name: "Tasks" });
    expect(within(tasks).getByText("Tasks of p1 in EUR")).toBeInTheDocument();
    const money = screen.getByRole("region", { name: "Money" });
    expect(within(money).getByText("Months of Garden")).toBeInTheDocument();
    expect(tasks.compareDocumentPosition(money) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getAllByRole("tab").map((tab) => tab.textContent)).toEqual(["Notes3", "Documents1"]);
    expect(screen.getByRole("link", { name: "Back to tasks" })).toHaveAttribute("href", "/board?tab=tasks&project=p1");
    expect(screen.getByText("Workspace / Tasks /")).toBeInTheDocument();
  });

  it("its sections and tabs carry counts", async () => {
    renderAt("/board/projects/p1");
    await screen.findByRole("heading", { name: "Garden" });
    const counts = Object.fromEntries(screen.getAllByRole("tab").map((tab) => [tab.firstChild?.textContent, tab.querySelector(".tabs__count")?.textContent]));
    expect(counts).toEqual({ Notes: "3", Documents: "1" });
    expect(within(screen.getByRole("region", { name: "Tasks" })).getByText("2", { selector: ".count" })).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Money" })).getByText("7", { selector: ".count" })).toBeInTheDocument();
  });

  it("the breadcrumb goes back to this project's tasks in the Workspace", async () => {
    const user = userEvent.setup();
    renderAt("/board/projects/p1");
    await screen.findByRole("heading", { name: "Garden" });
    expect(screen.getByText("Workspace / Tasks /")).toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: "Back to tasks" }));
    expect(await screen.findByText("Board on tasks, p1")).toBeInTheDocument();
  });

  it("Top-ups sit below the spending, folded until Add top-up", async () => {
    addTopupMock.mockResolvedValue({ id: "tu2" });
    const user = userEvent.setup();
    renderAt("/board/projects/p1?tab=money");
    const months = await screen.findByText("Months of Garden");
    expect(screen.getByRole("region", { name: "Coming up" })).toHaveTextContent("Home insurance");
    expect(screen.getByRole("region", { name: "Repeating charges" })).toHaveTextContent("monthly, 5th");
    const topups = screen.getByRole("region", { name: "Top-ups" });
    expect(months.compareDocumentPosition(topups) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.queryByRole("list", { name: "Top-up history" })).toBeNull();
    expect(screen.queryByLabelText("Top-up amount")).toBeNull();
    await user.click(within(topups).getByRole("button", { name: /Top-ups/ }));
    expect(within(screen.getByRole("list", { name: "Top-up history" })).getByText("birthday")).toBeInTheDocument();
    await user.click(within(topups).getByRole("button", { name: "Add top-up" }));
    expect(within(topups).getAllByRole("button", { name: "Add top-up" })).toHaveLength(1); // the toggle becomes Cancel
    await user.type(screen.getByLabelText("Top-up amount"), "50");
    await user.type(screen.getByLabelText("Where from"), "gift");
    await user.click(screen.getByRole("button", { name: "Add top-up" }));
    expect(addTopupMock).toHaveBeenCalledWith("p1", { amount: "50.00", source: "gift" });
    await waitFor(() => expect(getProjectMock).toHaveBeenCalledTimes(2));
  });

  it("opens Notes and Documents as their own chunks, narrowed to the project", async () => {
    const user = userEvent.setup();
    renderAt("/board/projects/p1");
    await user.click(await screen.findByRole("tab", { name: /Notes/ }));
    expect(await screen.findByText("Notes of p1 open none")).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: /Documents/ }));
    expect(await screen.findByText("Docs of p1 open none")).toBeInTheDocument();
  });

  it("New note in the project creates it there and opens it", async () => {
    createNoteMock.mockResolvedValue({ id: "n9" });
    createDocumentMock.mockResolvedValue({ id: "d9" });
    const user = userEvent.setup();
    renderAt("/board/projects/p1?tab=notes");
    const line = await screen.findByPlaceholderText("New note in Garden…");
    await user.type(line, "Paint ideas{Enter}");
    expect(createNoteMock).toHaveBeenCalledWith({ title: "Paint ideas", content: "# Paint ideas\n\n", project_id: "p1" });
    expect(await screen.findByText("Notes of p1 open n9")).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: /Documents/ }));
    await user.type(await screen.findByPlaceholderText("New document in Garden…"), "Plan{Enter}");
    expect(createDocumentMock).toHaveBeenCalledWith({ kind: "doc", title: "Plan", project_id: "p1" });
    expect(await screen.findByText("Docs of p1 open d9")).toBeInTheDocument();
  });

  it("the tasks tab groups Overdue, Next up, Later and Done without the project column", async () => {
    renderAt("/board/projects/p1");
    expect(await screen.findByText("Tasks of p1 in EUR")).toBeInTheDocument();
    // TasksBoard's own tests cover the groups (projectGroups); the page hands it the project and nothing else.
    expect(screen.queryByText("Project")).toBeNull();
  });

  it("edits the project and sends only what changed", async () => {
    updateProjectMock.mockResolvedValue(makeProjectDetail({ name: "Back garden" }));
    const user = userEvent.setup();
    renderAt("/board/projects/p1");
    await user.click(await screen.findByRole("button", { name: "Edit" }));
    const form = screen.getByRole("form", { name: "Edit Garden" });
    expect(within(form).getByLabelText("Total budget")).toHaveValue("1000.00");
    const name = within(form).getByLabelText("Name");
    await user.clear(name);
    await user.type(name, "Back garden");
    const monthly = within(form).getByLabelText("Monthly limit");
    expect(monthly).toHaveValue("200.00");
    await user.clear(monthly);
    await user.type(monthly, "150");
    await user.click(within(form).getByRole("button", { name: "Save" }));
    expect(updateProjectMock).toHaveBeenCalledWith("p1", { name: "Back garden", monthly_budget: "150.00" });
    expect(setProjectBudgetMock).not.toHaveBeenCalled();
    await waitFor(() => expect(getProjectMock).toHaveBeenCalledTimes(2));
  });

  it("saves a changed total budget on its own route, and an emptied one clears it", async () => {
    setProjectBudgetMock.mockResolvedValue(makeProjectDetail());
    const user = userEvent.setup();
    const editForm = () => screen.getByRole("form", { name: "Edit Garden" });
    renderAt("/board/projects/p1");
    await user.click(await screen.findByRole("button", { name: "Edit" }));
    await user.clear(within(editForm()).getByLabelText("Total budget"));
    await user.type(within(editForm()).getByLabelText("Total budget"), "1500,50");
    await user.click(within(editForm()).getByRole("button", { name: "Save" }));
    expect(setProjectBudgetMock).toHaveBeenCalledWith("p1", "1500.50");
    await waitFor(() => expect(getProjectMock).toHaveBeenCalledTimes(2));
    await user.click(await screen.findByRole("button", { name: "Edit" }));
    await user.clear(within(editForm()).getByLabelText("Total budget"));
    await user.click(within(editForm()).getByRole("button", { name: "Save" }));
    expect(setProjectBudgetMock).toHaveBeenLastCalledWith("p1", null);
    expect(setProjectBudgetMock).toHaveBeenCalledTimes(2);
    expect(updateProjectMock).not.toHaveBeenCalled();
    await waitFor(() => expect(getProjectMock).toHaveBeenCalledTimes(3));
  });

  it("does not send the total budget again when it was not edited, even after a top-up changed it meanwhile", async () => {
    addTopupMock.mockResolvedValue(makeTopup({ id: "tu2", amount: "50.00" }));
    updateProjectMock.mockResolvedValue(makeProjectDetail({ name: "Back garden" }));
    const user = userEvent.setup();
    renderAt("/board/projects/p1");
    await user.click(await screen.findByRole("button", { name: "Edit" }));
    const form = screen.getByRole("form", { name: "Edit Garden" });
    expect(within(form).getByLabelText("Total budget")).toHaveValue("1000.00");
    // Meanwhile a 50 top-up raises the total to 1050.00; the page reloads under the open form.
    getProjectMock.mockResolvedValue(makeProjectDetail({
      total: budgetLine({ budget: "1050.00" }), topups: [makeTopup({ id: "tu2", amount: "50.00", source: "gift" }), makeTopup()],
    }));
    await user.click(await screen.findByRole("button", { name: "Add top-up" }));
    await user.type(await screen.findByLabelText("Top-up amount"), "50");
    await user.click(screen.getByRole("button", { name: "Add top-up" }));
    await waitFor(() => expect(getProjectMock).toHaveBeenCalledTimes(2)); // the page reloaded under the open form
    expect(getProjectMock).toHaveBeenCalledTimes(2);
    const name = within(form).getByLabelText("Name");
    await user.clear(name);
    await user.type(name, "Back garden");
    await user.click(within(form).getByRole("button", { name: "Save" }));
    expect(updateProjectMock).toHaveBeenCalledWith("p1", { name: "Back garden" });
    expect(setProjectBudgetMock).not.toHaveBeenCalled();
  });

  it("sends the total budget when it was edited, and not when it was typed back to what it opened with", async () => {
    setProjectBudgetMock.mockResolvedValue(makeProjectDetail());
    const user = userEvent.setup();
    renderAt("/board/projects/p1");
    await user.click(await screen.findByRole("button", { name: "Edit" }));
    const form = () => screen.getByRole("form", { name: "Edit Garden" });
    const budget = () => within(form()).getByLabelText("Total budget");
    await user.clear(budget());
    await user.type(budget(), "1000");   // the opened 1000.00, written differently: no change
    await user.click(within(form()).getByRole("button", { name: "Save" }));
    expect(setProjectBudgetMock).not.toHaveBeenCalled();
    await waitFor(() => expect(getProjectMock).toHaveBeenCalledTimes(2));
    getProjectMock.mockResolvedValue(makeProjectDetail({ total: budgetLine({ budget: "1050.00" }) }));
    await user.click(await screen.findByRole("button", { name: "Edit" }));
    await user.clear(budget());
    await user.type(budget(), "1200");
    await user.click(within(form()).getByRole("button", { name: "Save" }));
    expect(setProjectBudgetMock).toHaveBeenCalledWith("p1", "1200.00");
  });

  it("General's page has no Edit, Archive or Delete: it can be neither changed nor deleted", async () => {
    getProjectMock.mockResolvedValue(makeProjectDetail({ name: " general " }));
    renderAt("/board/projects/p1");
    expect(await screen.findByRole("heading", { name: "general" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Tasks" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /More for/ })).not.toBeInTheDocument();
  });

  it("archives the project", async () => {
    updateProjectMock.mockResolvedValue(makeProjectDetail({ status: "archived" }));
    const user = userEvent.setup();
    renderAt("/board/projects/p1");
    await user.click(await screen.findByRole("button", { name: "More for Garden" }));
    await user.click(screen.getByRole("menuitem", { name: "Archive" }));
    expect(updateProjectMock).toHaveBeenCalledWith("p1", { status: "archived" });
    await waitFor(() => expect(getProjectMock).toHaveBeenCalledTimes(2));
  });

  it("deletes only after the second click, saying what happens to its records, then goes back to Projects", async () => {
    deleteProjectMock.mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderAt("/board/projects/p1");
    await user.click(await screen.findByRole("button", { name: "More for Garden" }));
    await user.click(screen.getByRole("menuitem", { name: "Delete" }));
    expect(screen.getByText("Its expenses move to General; its tasks, notes and documents stay, just unlinked."))
      .toBeInTheDocument();
    expect(deleteProjectMock).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Delete Garden for good" }));
    expect(deleteProjectMock).toHaveBeenCalledWith("p1");
    expect(await screen.findByText("Board on tasks, all")).toBeInTheDocument();
  });

  it("says so when the project is gone, with the way back", async () => {
    const { ApiError } = await import("../src/api/client");
    getProjectMock.mockRejectedValue(new ApiError(404, "Project not found"));
    renderAt("/board/projects/gone");
    expect(await screen.findByRole("alert")).toHaveTextContent("Project not found");
    expect(screen.getByRole("link", { name: "Back to tasks" })).toHaveAttribute("href", "/board?tab=tasks&project=gone");
  });

  it("/board/projects opens the Tasks area on All tasks (lead task 15: no Projects tab)", async () => {
    renderAt("/board/projects");
    expect(await screen.findByText("Board on tasks, all")).toBeInTheDocument();
  });
});
