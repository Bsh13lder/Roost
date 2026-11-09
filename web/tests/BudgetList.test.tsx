import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BudgetList } from "../src/components/board/BudgetList";
import { makeSummary } from "./moneyFixtures";

const pinProjectMock = vi.fn();
vi.mock("../src/api/projects", () => ({ pinProject: (...a: unknown[]) => pinProjectMock(...a) }));

beforeEach(() => { pinProjectMock.mockReset().mockResolvedValue({}); });
afterEach(() => cleanup());

const rowOf = (name: string) => screen.getByRole("group", { name });

describe("BudgetList", () => {
  it("a monthly limit shows its tone and Over by", () => {
    render(<BudgetList rows={makeSummary().by_project} onChanged={vi.fn()} />);
    const casa = rowOf("Casa Nueva");
    expect(within(casa).getByText("€1,700.20")).toBeInTheDocument();
    expect(within(casa).getByText("/ €1,500")).toBeInTheDocument();
    expect(within(casa).getByText("Over by €200.20").className).toMatch(/danger/);
    expect(within(casa).getByRole("meter")).toHaveAttribute("aria-valuenow", "100");
    expect(casa.querySelector(".meter__fill--over")).not.toBeNull();
    expect(within(rowOf("Side business")).getByText("US$247 left this month")).toBeInTheDocument();
  });

  it("a total-only project shows its total bar", () => {
    render(<BudgetList rows={makeSummary().by_project} onChanged={vi.fn()} />);
    const lisbon = rowOf("Trip to Lisbon");
    expect(within(lisbon).getByText("€320")).toBeInTheDocument();
    expect(within(lisbon).getByText("this month")).toBeInTheDocument();
    expect(within(lisbon).getByText("€1,050 left of €1,800 total")).toBeInTheDocument();
    expect(within(lisbon).getByRole("meter")).toHaveAttribute("aria-valuenow", "41");
  });

  it("a project without limits says No limit", () => {
    render(<BudgetList rows={makeSummary().by_project} onChanged={vi.fn()} />);
    const groceries = rowOf("Groceries");
    expect(within(groceries).getByText("No limit")).toBeInTheDocument();
    expect(within(groceries).queryByRole("meter")).not.toBeInTheDocument();
  });

  it("pin toggles through the pin route", async () => {
    const onChanged = vi.fn();
    const user = userEvent.setup();
    render(<BudgetList rows={makeSummary().by_project} onChanged={onChanged} />);
    await user.click(within(rowOf("Trip to Lisbon")).getByRole("button", { name: "Pin to the top" }));
    expect(pinProjectMock).toHaveBeenCalledWith("p-lisbon", true);
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    await user.click(within(rowOf("Casa Nueva")).getByRole("button", { name: "Unpin" }));
    expect(pinProjectMock).toHaveBeenLastCalledWith("p-casa", false);
  });

  it("pinned projects sit on top, the rest in the server's order", () => {
    const [casa, lisbon, groceries, side] = makeSummary().by_project;
    const rows = [{ ...casa, pinned: false }, lisbon, { ...groceries, pinned: true }, side];
    render(<BudgetList rows={rows} onChanged={vi.fn()} />);
    const names = screen.getAllByRole("group").map((row) => row.getAttribute("aria-label"));
    expect(names).toEqual([groceries.project, casa.project, lisbon.project, side.project]);
  });

  it("General can't be pinned", () => {
    const general = { ...makeSummary().by_project[3], project: "General", project_id: "p-gen" };
    render(<BudgetList rows={[general]} onChanged={vi.fn()} />);
    expect(screen.queryByRole("button", { name: "Pin to the top" })).not.toBeInTheDocument();
  });

  it("says why a pin failed", async () => {
    pinProjectMock.mockRejectedValue(new Error("down"));
    const user = userEvent.setup();
    render(<BudgetList rows={makeSummary().by_project} onChanged={vi.fn()} />);
    await user.click(within(rowOf("Trip to Lisbon")).getByRole("button", { name: "Pin to the top" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
