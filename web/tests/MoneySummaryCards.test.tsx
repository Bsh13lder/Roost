import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import { MoneySummaryCards } from "../src/components/board/MoneySummaryCards";
import { makeSummary } from "./moneyFixtures";

afterEach(() => cleanup());

const card = (name: string) => screen.getByRole("group", { name });

describe("MoneySummaryCards", () => {
  it("never sums two currencies in a card", () => {
    render(<MoneySummaryCards summary={makeSummary()} />);
    const spent = card("Spent this month");
    expect(within(spent).getByText("€4,238.74")).toBeInTheDocument();
    expect(within(spent).getByText(/\+ US\$153\.00 apart/)).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("4,391");
  });

  it("names the worst project under Monthly limits", () => {
    render(<MoneySummaryCards summary={makeSummary()} />);
    const limits = card("Monthly limits");
    expect(within(limits).getByText("1 over")).toBeInTheDocument();
    expect(within(limits).getByText(/Casa Nueva over by €200\.20/)).toBeInTheDocument();
    expect(within(limits).getByText(/Side business US\$247 left/)).toBeInTheDocument();
  });

  it("says All on track, or that no limits are set", () => {
    const calm = makeSummary({ limits: { over_count: 0, items: [
      { project_id: "p", project: "Casa", currency: "EUR", amount: "300.00", over: false, tone: "ok" }] } });
    const { rerender } = render(<MoneySummaryCards summary={calm} />);
    expect(within(card("Monthly limits")).getByText("All on track")).toBeInTheDocument();
    rerender(<MoneySummaryCards summary={makeSummary({ limits: { over_count: 0, items: [] } })} />);
    expect(within(card("Monthly limits")).getByText("No limits set")).toBeInTheDocument();
  });

  it("other currencies are secondary, not warn", () => {
    render(<MoneySummaryCards summary={makeSummary()} />);
    const apart = screen.getByText(/apart/);
    expect(apart.className).not.toMatch(/warn/);
    expect(apart.className).toMatch(/kpi__apart/);
  });

  it("shows +36% vs Sep from the server, and nothing without a previous month", () => {
    const { rerender } = render(<MoneySummaryCards summary={makeSummary()} />);
    const change = screen.getByText("+36% vs Sep");
    expect(change.className).toMatch(/kpi__change--up/);
    rerender(<MoneySummaryCards summary={makeSummary({ change_percent: -12 })} />);
    expect(screen.getByText("-12% vs Sep").className).toMatch(/kpi__change--down/);
    rerender(<MoneySummaryCards summary={makeSummary({ previous: null, change_percent: null })} />);
    expect(screen.queryByText(/vs /)).not.toBeInTheDocument();
  });

  it("Top project names it with its share of the month", () => {
    render(<MoneySummaryCards summary={makeSummary()} />);
    const top = card("Top project");
    expect(within(top).getByText("Casa Nueva")).toBeInTheDocument();
    expect(within(top).getByText("€1,234 · 29% of the month")).toBeInTheDocument();
  });

  it("Coming up shows the count and the next charge", () => {
    render(<MoneySummaryCards summary={makeSummary()} />);
    const coming = card("Coming up · 31 days");
    expect(within(coming).getByText("€9.99")).toBeInTheDocument();
    expect(within(coming).getByText("+ US$12")).toBeInTheDocument();
    expect(within(coming).getByText("2 repeating charges · next Netflix, 18 Nov")).toBeInTheDocument();
  });

  it("Coming up with nothing says so", () => {
    const none = makeSummary({ coming_up: { days: 31, count: 0, totals: {}, next: null } });
    render(<MoneySummaryCards summary={none} />);
    expect(within(card("Coming up · 31 days")).getByText("No repeating charges")).toBeInTheDocument();
  });
});
