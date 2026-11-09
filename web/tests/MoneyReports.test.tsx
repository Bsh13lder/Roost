import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TrendChart } from "../src/components/board/reports/TrendChart";
import { ProjectBars } from "../src/components/board/reports/ProjectBars";
import { ReportsButton } from "../src/components/board/reports/ReportsButton";
import { ToastProvider } from "../src/ui/Toast";
import { makeSummary, makeTrend } from "./moneyFixtures";

const getTrendMock = vi.fn();
vi.mock("../src/api/money", () => ({ getTrend: (...a: unknown[]) => getTrendMock(...a) }));
vi.mock("../src/components/board/reports/MoneyReports", () => ({
  default: () => <div data-testid="full-reports">The full reports</div>,
}));

beforeEach(() => { getTrendMock.mockReset().mockResolvedValue(makeTrend()); });
afterEach(() => cleanup());

describe("TrendChart", () => {
  it("draws one bar group per month and one series per currency", () => {
    const { container } = render(<TrendChart months={makeTrend().months} />);
    expect(container.querySelectorAll("g.chart__month")).toHaveLength(6);
    expect(container.querySelectorAll("rect.chart__bar")).toHaveLength(12);
    expect(container.querySelectorAll("rect.chart__bar--0")).toHaveLength(6);
    expect(container.querySelectorAll("rect.chart__bar--1")).toHaveLength(6);
    const legend = screen.getByRole("list", { name: "Currencies" });
    expect(within(legend).getAllByRole("listitem").map((item) => item.textContent)).toEqual([
      "EUR (scale €4.2K)", "USD (scale US$153)"]);
  });

  it("gives every currency its own scale", () => {
    const { container } = render(<TrendChart months={makeTrend().months} />);
    const heights = (series: number) => [...container.querySelectorAll(`rect.chart__bar--${series}`)]
      .map((bar) => Number(bar.getAttribute("height")));
    expect(Math.max(...heights(0))).toBe(Math.max(...heights(1))); // each series' biggest month is full height
  });

  it("names every bar with its month and its own currency", () => {
    const { container } = render(<TrendChart months={makeTrend().months} />);
    const titles = [...container.querySelectorAll("rect.chart__bar title")].map((title) => title.textContent);
    expect(titles).toContain("Oct: €4,238.74");
    expect(titles).toContain("Oct: US$153.00");
  });

  it("has an accessible table of the same numbers", () => {
    render(<TrendChart months={makeTrend().months} />);
    const table = screen.getByRole("table", { name: "Spent per month" });
    expect(within(table).getAllByRole("columnheader").map((cell) => cell.textContent)).toEqual(["Month", "EUR", "USD"]);
    const october = within(table).getByRole("row", { name: /Oct/ });
    expect(within(october).getAllByRole("cell").map((cell) => cell.textContent)).toEqual(["€4,238.74", "US$153.00"]);
    expect(screen.getByRole("img", { name: "Spent per month, one series per currency" })).toBeInTheDocument();
  });

  it("never sums two currencies", () => {
    const { container } = render(<TrendChart months={makeTrend().months} />);
    expect(container.textContent).not.toContain("4,391"); // 4238.74 + 153
    const table = screen.getByRole("table", { name: "Spent per month" });
    expect(within(table).queryByRole("columnheader", { name: /total/i })).not.toBeInTheDocument();
  });

  it("a month without a currency is an empty slot, not a zero bar", () => {
    const sparse = [{ month: "2026-09", totals: { EUR: "10.00" } }, { month: "2026-10", totals: { EUR: "20.00", USD: "5.00" } }];
    const { container } = render(<TrendChart months={sparse} />);
    expect(container.querySelectorAll("rect.chart__bar--1")).toHaveLength(1);
  });

  it("says so when nothing was spent", () => {
    render(<TrendChart months={[{ month: "2026-10", totals: {} }]} />);
    expect(screen.getByText("Nothing spent in these months.")).toBeInTheDocument();
  });
});

describe("ProjectBars", () => {
  it("groups the month's projects by currency, each with its own scale", () => {
    render(<ProjectBars rows={makeSummary().by_project} />);
    const euro = screen.getByRole("group", { name: "EUR" });
    expect(within(euro).getAllByRole("listitem").map((item) => item.textContent)).toEqual([
      "Casa Nueva€1,700.20", "Trip to Lisbon€320.00", "Groceries€12.00"]);
    const usd = screen.getByRole("group", { name: "USD" });
    expect(within(usd).getAllByRole("listitem")).toHaveLength(1);
  });
});

describe("the Reports button", () => {
  it("the reports load as their own chunk", () => {
    const button = readFileSync(join(__dirname, "..", "src", "components", "board", "reports", "ReportsButton.tsx"), "utf8");
    expect(button).toContain('lazy(() => import("./MoneyReports"))');
    const board = readFileSync(join(__dirname, "..", "src", "components", "board", "MoneyBoard.tsx"), "utf8");
    expect(board).not.toMatch(/from "\.\/reports\/(TrendChart|MoneyReports|ProjectBars)"/);
  });

  it("opens the full reports in a sheet, asking nothing before", async () => {
    const user = userEvent.setup();
    render(<ToastProvider><ReportsButton rows={[]} monthLabel="October 2026" /></ToastProvider>);
    expect(getTrendMock).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Reports" }));
    expect(await screen.findByTestId("full-reports")).toBeInTheDocument();
  });
});
