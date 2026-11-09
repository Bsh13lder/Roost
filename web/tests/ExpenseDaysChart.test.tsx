import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ExpenseDaysChart } from "../src/components/board/ExpenseDaysChart";
import { makeActions, makeRange } from "./moneyFixtures";

vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => ({ bots: {}, boardVersion: { tasks: 0, money: 0 } }) }));
vi.mock("../src/api/projects", () => ({ listProjects: () => Promise.resolve([]) }));

afterEach(() => cleanup());

const BARS = { from: "2026-10-16", to: "2026-10-20" };

function show(overrides = {}, selected: string | null = null, onPick = vi.fn()) {
  render(<ExpenseDaysChart data={makeRange({ ...BARS, ...overrides })} selected={selected} onPick={onPick}
    actions={makeActions()} today="2026-10-20" />);
  return onPick;
}
const strip = () => screen.getByRole("group", { name: "Spending per day" });

describe("ExpenseDaysChart", () => {
  it("says what the bars show, in the main currency's name", () => {
    show();
    expect(screen.getByText(/Bars show euro spending per day; other currencies are listed apart in the days below\. Today is bright\./))
      .toBeInTheDocument();
  });

  it("bar heights are the server's bar_percent", () => {
    show();
    const bars = within(strip()).getAllByRole("button");
    expect(bars.map((bar) => bar.getAttribute("aria-label"))).toEqual([
      "Fri 16 Oct: €0.00", "Sat 17 Oct: €0.00", "Sun 18 Oct: €0.00", "Mon 19 Oct: €9.99", "Tue 20 Oct: €84.20 · US$12",
    ]);
    const heights = bars.map((bar) => (bar.querySelector(".dbar__fill") as HTMLElement).style.height);
    expect(heights).toEqual(["0%", "0%", "0%", "12%", "100%"]);
    expect(bars[4]).toHaveAttribute("title", "Tue 20 Oct: €84.20 · US$12");
  });

  it("a bar or a day filters the list, with a Clear chip", async () => {
    const user = userEvent.setup();
    const onPick = show();
    await user.click(within(strip()).getByRole("button", { name: "Mon 19 Oct: €9.99" }));
    expect(onPick).toHaveBeenLastCalledWith("2026-10-19");
    await user.click(screen.getByRole("button", { name: /^Yesterday/ }));
    expect(onPick).toHaveBeenLastCalledWith("2026-10-19");
  });

  it("with a day picked, its group shows under the strip; with none, it says to pick one", () => {
    show({}, "2026-10-19");
    expect(within(strip()).getByRole("button", { name: /Mon 19 Oct/ })).toHaveClass("is-sel");
    expect(screen.getByRole("list", { name: "Expenses" })).toBeInTheDocument();
    expect(screen.getByText("Netflix")).toBeInTheDocument();
    expect(screen.queryByText("Paint")).not.toBeInTheDocument();
    cleanup();
    show();
    expect(screen.getByText("Pick a bar or a day to see its expenses.")).toBeInTheDocument();
  });

  it("lists the days that have expenses, newest first, as buttons", () => {
    show();
    const rows = screen.getAllByRole("button", { name: /^(Today|Yesterday|Sun 18 Oct)/ }).filter((row) => row.classList.contains("dayrow"));
    expect(rows.map((row) => row.textContent)).toEqual(["Today€84.20 · US$12", "Yesterday€9.99", "Sun 18 Oct€0.00"]);
  });

  it("today is bright", () => {
    show();
    const bars = within(strip()).getAllByRole("button");
    expect(bars[4]).toHaveClass("is-today");
    expect(bars[3]).not.toHaveClass("is-today");
    expect(document.querySelector(".dlabels .today")).toHaveTextContent("20");
  });

  it("labels every day on a short range", () => {
    show();
    expect([...document.querySelectorAll(".dlabels span")].map((label) => label.textContent)).toEqual(["16", "17", "18", "19", "20"]);
  });

  it("labels every fifth day on a long range, counting back from the last", () => {
    show({ from: "2026-09-21", to: "2026-10-20" });
    const labels = [...document.querySelectorAll(".dlabels span")].map((label) => label.textContent);
    expect(labels).toHaveLength(30);
    expect(labels.filter(Boolean)).toEqual(["25", "30", "5", "10", "15", "20"].slice(0, 6));
  });

  it("shows only the last 31 days of a longer range", () => {
    show({ from: "2026-07-01", to: "2026-10-20" });
    expect(within(strip()).getAllByRole("button")).toHaveLength(31);
    expect(within(strip()).getAllByRole("button")[30]).toHaveClass("is-today");
  });
});
