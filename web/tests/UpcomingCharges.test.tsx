import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RepeatingExpenses } from "../src/components/projects/RepeatingExpenses";
import { UpcomingCharges } from "../src/components/projects/UpcomingCharges";
import { ExpenseLine } from "../src/components/board/ExpenseLine";
import { makeCharge, makeRecurring } from "./projectFixtures";
import { makeExpenseLine } from "./moneyFixtures";

const stopMock = vi.fn();
const updateMock = vi.fn();
const parseMock = vi.fn();
vi.mock("../src/api/money", () => ({
  stopRecurring: (...a: unknown[]) => stopMock(...a),
  updateRecurring: (...a: unknown[]) => updateMock(...a),
  parseExpenseLine: (...a: unknown[]) => parseMock(...a),
  createExpense: vi.fn(),
}));
vi.mock("../src/api/projects", () => ({ listProjects: vi.fn().mockResolvedValue([]) }));
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => ({ bots: {}, boardVersion: { tasks: 0, money: 0 } }) }));

beforeEach(() => {
  stopMock.mockReset().mockResolvedValue(undefined);
  updateMock.mockReset().mockResolvedValue({});
  parseMock.mockReset();
});
afterEach(() => cleanup());

describe("UpcomingCharges and RepeatingExpenses", () => {
  it("lists upcoming charges with day and amount in the project's currency", () => {
    render(<UpcomingCharges charges={[makeCharge(), makeCharge({ recurring_id: "r2", note: "Alarm", day: "2026-11-12", amount: "29.90", currency: "USD" })]} />);
    const card = screen.getByRole("region", { name: "Coming up" });
    expect(card).toHaveTextContent("Home insurance · 5 Nov");
    expect(card).toHaveTextContent("€42.00");
    expect(card).toHaveTextContent("Alarm · 12 Nov");
    expect(card).toHaveTextContent("US$29.90");
  });

  it("says so when nothing is coming", () => {
    render(<UpcomingCharges charges={[]} />);
    expect(screen.getByText("Nothing in the next 31 days.")).toBeInTheDocument();
  });

  it("Stop asks once and ends the rule", async () => {
    const onChanged = vi.fn();
    const user = userEvent.setup();
    render(<RepeatingExpenses rules={[makeRecurring()]} onChanged={onChanged} />);
    expect(screen.getByText("monthly, 5th", { exact: false })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Stop Home insurance" }));
    expect(stopMock).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Yes, stop it" }));
    expect(stopMock).toHaveBeenCalledWith("r1");
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it("Edit changes the amount", async () => {
    const onChanged = vi.fn();
    const user = userEvent.setup();
    render(<RepeatingExpenses rules={[makeRecurring()]} onChanged={onChanged} />);
    await user.click(screen.getByRole("button", { name: "Edit Home insurance" }));
    const amount = screen.getByLabelText("Amount");
    await user.clear(amount);
    await user.type(amount, "45,50");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(updateMock).toHaveBeenCalledWith("r1", { amount: "45.50", note: "Home insurance" });
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it("the expense line with 'monthly' shows a repeat chip", async () => {
    parseMock.mockResolvedValue(makeExpenseLine({
      note: "insurance", amount: "42.00", ready: true, cadence: "monthly", repeat_words: "monthly",
    }));
    render(<ExpenseLine projectId="p1" onAdded={vi.fn()} />);
    await userEvent.setup().type(screen.getByLabelText("New expense"), "€42 insurance monthly", { delay: null });
    expect(await screen.findByText("Repeats monthly")).toBeInTheDocument();
    expect(parseMock).toHaveBeenCalledWith(expect.objectContaining({ project_id: "p1" }));
  });
});
