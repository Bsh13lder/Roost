import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import { ExpenseDays } from "../src/components/board/ExpenseDays";
import { makeActions, makeRange } from "./moneyFixtures";

vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => ({ bots: {}, boardVersion: { tasks: 0, money: 0 } }) }));
vi.mock("../src/api/projects", () => ({ listProjects: () => Promise.resolve([]) }));
afterEach(() => cleanup());

const show = (showProject = true) => render(
  <ExpenseDays data={makeRange()} showProject={showProject} actions={makeActions()} today="2026-10-20" />);
const rowOf = (note: string) => screen.getByText(note).closest("li") as HTMLElement;

describe("ExpenseDays", () => {
  it("groups by Madrid day with the server's totals", () => {
    show();
    const heads = screen.getAllByTestId("xp-day").map((head) => head.textContent);
    expect(heads).toEqual(["Today€84.20 · US$12", "Yesterday€9.99", "Sun 18 Oct"]);
  });

  it("a void row is struck through with a badge", () => {
    show();
    const lamp = rowOf("Old lamp");
    expect(lamp).toHaveClass("is-void");
    expect(within(lamp).getByText("void")).toBeInTheDocument();
  });

  it("amounts sit in their own right-aligned column", () => {
    show();
    const paint = rowOf("Paint");
    const amount = within(paint).getByText("€84.20");
    expect(amount).toHaveClass("xp__amt");
    expect(amount.parentElement).toBe(paint);
    expect(within(rowOf("Taxi")).getByText("US$12.00")).toHaveClass("xp__amt");
  });

  it("a repeating expense shows ↻ monthly", () => {
    show();
    expect(within(rowOf("Netflix")).getByText("↻ monthly")).toBeInTheDocument();
    expect(within(rowOf("Paint")).queryByText(/↻/)).not.toBeInTheDocument();
  });

  it("shows the vendor after the note", () => {
    show();
    expect(within(rowOf("Taxi")).getByText("Cabify")).toHaveClass("xp__vendor");
  });

  it("hides the project tag on a project page", () => {
    const { unmount } = show(false);
    expect(document.querySelector(".xp__tag")).toBeNull();
    unmount();
    show(true);
    expect(within(rowOf("Netflix")).getByText("Home")).toHaveClass("xp__tag");
  });

  it("keeps the money in apart: a positive amount with a mark", () => {
    const range = makeRange({ expenses: [{ ...makeRange().expenses[0], id: "i1", kind: "income", description: "Salary",
      amount: "500.00" }] });
    render(<ExpenseDays data={range} showProject actions={makeActions()} today="2026-10-20" />);
    const salary = rowOf("Salary");
    expect(within(salary).getByText("+€500.00")).toBeInTheDocument();
    expect(within(salary).getByText("money in")).toBeInTheDocument();
  });

  it("says so when nothing is in the range", () => {
    render(<ExpenseDays data={makeRange({ expenses: [], days: [] })} showProject actions={makeActions()} today="2026-10-20" />);
    expect(screen.getByText("No expenses in this range.")).toBeInTheDocument();
  });
});
