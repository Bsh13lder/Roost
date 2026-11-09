import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { BudgetBar } from "../src/components/projects/BudgetBar";
import { budgetLine, NO_LIMIT } from "./projectFixtures";

afterEach(() => cleanup());

const THIS_MONTH = budgetLine({ budget: "300.00", spent: "120.00", remaining: "180.00", used_percent: 40, tone: "ok" });

describe("BudgetBar", () => {
  it("is a meter at the share used, saying what is left", () => {
    const { container } = render(<BudgetBar label="This month" line={THIS_MONTH} currency="EUR" />);
    const meter = screen.getByRole("meter", { name: "This month" });
    expect(meter).toHaveAttribute("aria-valuenow", "40");
    expect(meter).toHaveAttribute("aria-valuemin", "0");
    expect(meter).toHaveAttribute("aria-valuemax", "100");
    expect(meter).toHaveAttribute("aria-valuetext", "€180.00 left of €300.00");
    expect(screen.getByText("€180.00 left of €300.00")).toBeInTheDocument();
    expect(container.querySelector(".meter__fill")).toHaveClass("meter__fill--ok");
  });

  it("takes its colour from the server's tone: amber from 80 %", () => {
    const line = budgetLine({ budget: "300.00", spent: "255.00", remaining: "45.00", used_percent: 85, tone: "warn" });
    const { container } = render(<BudgetBar label="Total budget" line={line} currency="EUR" />);
    expect(screen.getByRole("meter", { name: "Total budget" })).toHaveAttribute("aria-valuenow", "85");
    expect(container.querySelector(".meter__fill")).toHaveClass("meter__fill--warn");
  });

  it("is full and red when over, and says by how much", () => {
    const line = budgetLine({ budget: "300.00", spent: "345.00", remaining: "-45.00", used_percent: 115, tone: "over" });
    const { container } = render(<BudgetBar label="Total budget" line={line} currency="EUR" />);
    const meter = screen.getByRole("meter", { name: "Total budget" });
    expect(meter).toHaveAttribute("aria-valuenow", "100");
    expect(meter).toHaveAttribute("aria-valuetext", "Over by €45.00");
    expect(screen.getByText("Over by €45.00")).toBeInTheDocument();
    const fill = container.querySelector(".meter__fill") as HTMLElement;
    expect(fill).toHaveClass("meter__fill--over");
    expect(fill.style.width).toBe("100%");
  });

  it("with no limit it shows only what was spent, and no meter", () => {
    render(<BudgetBar label="This month" line={budgetLine({ ...NO_LIMIT, spent: "12.50" })} currency="EUR" />);
    expect(screen.queryByRole("meter")).not.toBeInTheDocument();
    expect(screen.getByText("€12.50 spent, no limit")).toBeInTheDocument();
  });

  it("speaks the project's own currency", () => {
    render(<BudgetBar label="This month" line={THIS_MONTH} currency="USD" />);
    expect(screen.getByText("US$180.00 left of US$300.00")).toBeInTheDocument();
  });
});
