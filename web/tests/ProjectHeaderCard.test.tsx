import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { ProjectHeaderCard } from "../src/components/projects/ProjectHeaderCard";
import { budgetLine, makeProjectDetail, makeRecurring, NO_LIMIT } from "./projectFixtures";

const pinMock = vi.fn();
const updateMock = vi.fn();
const deleteMock = vi.fn();
vi.mock("../src/api/projects", () => ({
  pinProject: (...a: unknown[]) => pinMock(...a),
  updateProject: (...a: unknown[]) => updateMock(...a),
  deleteProject: (...a: unknown[]) => deleteMock(...a),
  keepProject: vi.fn(),
}));

const TODAY = "2026-10-21";
const handlers = { onEdit: vi.fn(), onChanged: vi.fn(), onDeleted: vi.fn() };

function show(overrides = {}) {
  return render(
    <MemoryRouter>
      <ProjectHeaderCard project={makeProjectDetail(overrides)} today={TODAY} {...handlers} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  for (const mock of [pinMock, updateMock, deleteMock, ...Object.values(handlers)]) mock.mockReset();
  pinMock.mockResolvedValue({}); updateMock.mockResolvedValue({}); deleteMock.mockResolvedValue(undefined);
});
afterEach(() => cleanup());

const stat = (name: string) => screen.getByText(name).closest(".p-stat") as HTMLElement;

describe("ProjectHeaderCard", () => {
  it("shows three stats with meters from the server", () => {
    show({
      total: budgetLine({ budget: "12000.00", spent: "3200.20", remaining: "8799.80", used_percent: 27, tone: "ok" }),
      month: budgetLine({ budget: "1500.00", spent: "300.00", remaining: "1200.00", used_percent: 20, tone: "ok" }),
      topups: [],
    });
    const total = stat("Total budget");
    expect(within(total).getByText("€8,799.80")).toBeInTheDocument();
    expect(total).toHaveTextContent("left of €12,000.00");
    expect(total).toHaveTextContent("€3,200.20 spent · 27%");
    expect(within(total).getByRole("meter")).toHaveAttribute("aria-valuenow", "27");
    const tasks = stat("Tasks");
    expect(tasks).toHaveTextContent("3 of 5 done");
    expect(tasks).toHaveTextContent("2 overdue · 5 of 8 steps done · €3,850.00 planned");
    expect(within(tasks).getByText("2 overdue")).toHaveClass("danger");
    expect(screen.getByRole("heading", { name: "Garden" })).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByText(/Led by Helper · 1 Oct 2026 → 20 Dec 2026 · 60 days left/)).toBeInTheDocument();
  });

  it("the month stat says over in danger", () => {
    show({ month: budgetLine({ budget: "1500.00", spent: "1700.20", remaining: "-200.20", used_percent: 113, tone: "over" }) });
    const month = stat("October");
    expect(within(month).getByText("€200.20")).toHaveClass("danger");
    expect(month).toHaveTextContent("over €1,500.00");
    expect(month).toHaveTextContent("€1,700.20 spent this month · 10 days to go");
    expect(within(month).getByRole("meter")).toHaveClass("meter");
    expect(month.querySelector(".meter__fill--over")).not.toBeNull();
  });

  it("without budgets it says so and draws no meter", () => {
    show({ total: { ...budgetLine(), ...NO_LIMIT }, month: { ...budgetLine(), ...NO_LIMIT, spent: "12.00" } });
    expect(stat("Total budget")).toHaveTextContent("No total budget");
    expect(within(stat("Total budget")).queryByRole("meter")).toBeNull();
    expect(stat("October")).toHaveTextContent("No monthly limit");
  });

  it("Pin, Archive and Delete live in the menu, Delete in danger and asking first", async () => {
    const user = userEvent.setup();
    show();
    expect(screen.queryByRole("button", { name: "Archive" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "More for Garden" }));
    expect(screen.getByRole("menuitem", { name: "Delete" })).toHaveClass("menu__item--danger");
    await user.click(screen.getByRole("menuitem", { name: "Pin to Money" }));
    expect(pinMock).toHaveBeenCalledWith("p1", true);
    await user.click(screen.getByRole("button", { name: "More for Garden" }));
    await user.click(screen.getByRole("menuitem", { name: "Archive" }));
    expect(updateMock).toHaveBeenCalledWith("p1", { status: "archived" });
    await user.click(screen.getByRole("button", { name: "More for Garden" }));
    await user.click(screen.getByRole("menuitem", { name: "Delete" }));
    expect(deleteMock).not.toHaveBeenCalled();
    expect(screen.getByText("Its expenses move to General; its tasks, notes and documents stay, just unlinked."))
      .toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Delete Garden for good" }));
    expect(deleteMock).toHaveBeenCalledWith("p1");
  });

  it("other currencies are one secondary line, not warn", () => {
    show({ other_currencies: { USD: "153.00" } });
    const line = screen.getByText(/Also US\$153\.00/);
    expect(line).toHaveTextContent("Also US$153.00 (not in the total)");
    expect(line).toHaveClass("p-card__other");
    expect(line.className).not.toMatch(/warn/);
  });

  it("the Repeating strip lists the rules", () => {
    show({ repeating: [makeRecurring(), makeRecurring({ id: "r2", note: "Alarm", amount: "29.90", next_due: "2026-11-12" })] });
    const strip = screen.getByLabelText("Repeating");
    expect(strip).toHaveTextContent("↻ Home insurance €42.00 · monthly · next 5 Nov");
    expect(strip).toHaveTextContent("↻ Alarm €29.90 · monthly · next 12 Nov");
  });

  it("General's card has no menu and no Edit", () => {
    show({ name: "General" });
    expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
    expect(screen.queryByRole("button", { name: /More for/ })).toBeNull();
  });
});
