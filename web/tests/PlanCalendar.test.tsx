import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { PlanCalendar } from "../src/components/plan/PlanCalendar";
import { item, plan } from "./planFixtures";
vi.mock("../src/api/routines", async (real) => ({ ...(await real<object>()), listRoutineOccurrences: vi.fn().mockResolvedValue({ occurrences: [], truncated: false }) }));

afterEach(cleanup);

const view = (items = plan().items) => render(
  <MemoryRouter initialEntries={["/?month=2026-10"]}><PlanCalendar items={items} today="2026-10-21" /></MemoryRouter>,
);
const cell = (day: string) => document.querySelector(`[data-day="${day}"]`) as HTMLElement;

describe("PlanCalendar", () => {
  it("the calendar marks days with items and lists the day sorted by time", () => {
    view();
    expect(cell("2026-10-21").querySelector(".cdot")).not.toBeNull();
    expect(cell("2026-10-22").querySelector(".cdot")).toBeNull();
    const list = screen.getByRole("list", { name: "Wed 21 Oct" });
    expect(within(list).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      expect.stringContaining("Pay rent"), expect.stringContaining("Write the report"),
    ]);
    expect(within(list).getByText("09:30")).toBeInTheDocument();
  });

  it("clicking another day lists that day", async () => {
    view([item({ id: "a", text: "Dentist", date: "2026-10-23", time: "10:00" })]);
    await userEvent.click(cell("2026-10-23"));
    expect(within(screen.getByRole("list", { name: "Fri 23 Oct" })).getByText("Dentist")).toBeInTheDocument();
  });

  it("undated items sit in No date", () => {
    view();
    const none = screen.getByRole("list", { name: "No date" });
    expect(within(none).getByText("Call the plumber")).toBeInTheDocument();
    expect(within(none).queryByText("Old idea")).not.toBeInTheDocument(); // dropped items stay out
  });

  it("says when the day has nothing", async () => {
    view();
    await userEvent.click(cell("2026-10-25"));
    expect(screen.getByText("Nothing on this day.")).toBeInTheDocument();
  });
});
