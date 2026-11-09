import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MoneyReports from "../src/components/board/reports/MoneyReports";
import { makeSummary, makeTrend } from "./moneyFixtures";

const getTrendMock = vi.fn();
vi.mock("../src/api/money", () => ({ getTrend: (...a: unknown[]) => getTrendMock(...a) }));

beforeEach(() => { getTrendMock.mockReset().mockResolvedValue(makeTrend()); });
afterEach(() => cleanup());

describe("the full reports", () => {
  it("open on the last 6 months (the side card's chart), with 12 one tap away", async () => {
    const user = userEvent.setup();
    render(<MoneyReports rows={makeSummary().by_project} monthLabel="October 2026" />);
    const span = screen.getByRole("group", { name: "Months" });
    expect(within(span).getByRole("button", { name: "Last 6 months" })).toHaveAttribute("aria-pressed", "true");
    await waitFor(() => expect(getTrendMock).toHaveBeenCalledWith(6, undefined));
    expect(await screen.findByRole("img", { name: "Spent per month, one series per currency" })).toBeInTheDocument();
    await user.click(within(span).getByRole("button", { name: "Last 12 months" }));
    await waitFor(() => expect(getTrendMock).toHaveBeenLastCalledWith(12, undefined));
    expect(screen.getByRole("heading", { name: "By project, October 2026" })).toBeInTheDocument();
  });

  it("says why the chart can't load", async () => {
    getTrendMock.mockRejectedValue(new Error("down"));
    render(<MoneyReports rows={[]} monthLabel="October 2026" />);
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong"));
  });
});
