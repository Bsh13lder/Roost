import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PinnedCards } from "../src/components/board/PinnedCards";
import { makeSummary } from "./moneyFixtures";

afterEach(() => cleanup());

function renderPinned(summary = makeSummary(), onUnstar = vi.fn()) {
  render(<PinnedCards projects={summary.pinned_projects} expenses={summary.pinned_expenses}
    colors={{ "p-casa": "#22c55e", "p-lisbon": "#3b82f6" }} onUnstar={onUnstar} />);
  return onUnstar;
}

describe("PinnedCards", () => {
  it("shows pinned projects with their bar and starred expenses", () => {
    renderPinned();
    const section = screen.getByRole("region", { name: "Pinned" });
    expect(within(section).getByText("3")).toBeInTheDocument();
    expect(within(section).getByText("Project")).toBeInTheDocument();
    expect(within(section).getByRole("meter", { name: /Casa Nueva/ })).toBeInTheDocument();
    expect(within(section).getByText("Sofa")).toBeInTheDocument();
    expect(within(section).getByText("€450")).toBeInTheDocument();
    expect(within(section).getByText("Sun 18 Oct · Casa Nueva")).toBeInTheDocument();
  });

  it("unstarring asks to remove the card", async () => {
    const onUnstar = renderPinned();
    await userEvent.setup().click(screen.getByRole("button", { name: "Unstar Sofa" }));
    expect(onUnstar).toHaveBeenCalledWith("s1");
  });

  it("hides when nothing is pinned", () => {
    renderPinned(makeSummary({ pinned_projects: [], pinned_expenses: [] }));
    expect(screen.queryByRole("region", { name: "Pinned" })).not.toBeInTheDocument();
  });
});
