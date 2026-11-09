import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { ProjectPeek } from "../src/components/board/rail/ProjectPeek";
import type { ProjectListState } from "../src/components/tasks/useProjects";
import type { ProjectOut } from "../src/api/types";
import { NO_LIMIT, budgetLine, makeProject } from "./projectFixtures";

const getProjectMock = vi.fn();
vi.mock("../src/api/projects", () => ({ getProject: (...a: unknown[]) => getProjectMock(...a) }));

const GARDEN = makeProject({ id: "p1", name: "Garden", color: "#22c55e", progress: { done: 3, failed: 1, total: 7, open: 3, overdue: 2, steps_done: 1, steps_total: 2, planned_total: "0.00" } });

function peek(list: Partial<ProjectListState> = {}, onAll = vi.fn()) {
  const state: ProjectListState = { projects: [GARDEN], loaded: true, error: null, reload: vi.fn(), ...list };
  render(<MemoryRouter><ProjectPeek projectId="p1" list={state} onAll={onAll} /></MemoryRouter>);
  return { onAll, reload: state.reload };
}

const only = (project: ProjectOut) => ({ projects: [project] });
afterEach(cleanup);

describe("the picked project's card on the Tasks area (lead tasks 15 and 20)", () => {
  it("reads the projects list: colour, name, open and overdue counts, budget bar, Open project; no project request", () => {
    peek();
    const card = screen.getByRole("region", { name: "Garden" });
    expect(within(card).getByRole("heading", { name: "Garden" })).toBeInTheDocument();
    expect(card.querySelector(".project-dot")).toHaveStyle({ background: "#22c55e" });
    expect(within(card).getByText("3 open")).toBeInTheDocument();
    expect(within(card).getByText("2 overdue")).toHaveClass("peek__late");
    expect(within(card).getByRole("meter", { name: "Total budget" })).toBeInTheDocument();
    expect(within(card).getByText("€80.00 left of €1,000.00")).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: "Open project ›" })).toHaveAttribute("href", "/board/projects/p1");
    expect(getProjectMock).not.toHaveBeenCalled();
  });

  it("with no total budget shows the monthly one, and with neither no bar; nothing overdue says nothing", () => {
    peek(only({ ...GARDEN, total: budgetLine({ ...NO_LIMIT, spent: "10.00" }), progress: { ...GARDEN.progress, overdue: 0 } }));
    const card = screen.getByRole("region", { name: "Garden" });
    expect(within(card).getByRole("meter", { name: "This month" })).toBeInTheDocument();
    expect(within(card).queryByText(/overdue/)).toBeNull();
    cleanup();
    peek(only({ ...GARDEN, total: budgetLine({ ...NO_LIMIT, spent: "10.00" }), month: budgetLine({ ...NO_LIMIT, spent: "0.00" }) }));
    expect(within(screen.getByRole("region", { name: "Garden" })).queryByRole("meter")).toBeNull();
  });

  it("an archived project says so", () => {
    peek(only({ ...GARDEN, status: "archived" }));
    expect(within(screen.getByRole("region", { name: "Garden" })).getByText("Archived")).toBeInTheDocument();
  });

  it("holds its place until the list has loaded", () => {
    const { container } = render(<MemoryRouter><ProjectPeek projectId="p1" onAll={vi.fn()}
      list={{ projects: [], loaded: false, error: null, reload: vi.fn() }} /></MemoryRouter>);
    expect(container.querySelector(".peek--loading")).not.toBeNull();
    expect(screen.queryByRole("button", { name: "Show all tasks" })).toBeNull();
  });

  it("a project the loaded list does not hold is gone: it offers All tasks", async () => {
    const { onAll } = peek({ projects: [makeProject({ id: "p2", name: "Kitchen" })] });
    expect(screen.getByText("This project is gone.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Show all tasks" }));
    expect(onAll).toHaveBeenCalled();
  });

  it("a list that failed to load says why and tries again", async () => {
    const { reload } = peek({ projects: [], loaded: false, error: "The Mac is offline." });
    expect(screen.getByText("The Mac is offline.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Try again|Retry/ }));
    expect(reload).toHaveBeenCalled();
  });
});
