import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TopupHistory } from "../src/components/projects/TopupHistory";
import { makeTopup } from "./projectFixtures";

const editTopupMock = vi.fn();
const undoTopupMock = vi.fn();
vi.mock("../src/api/projects", () => ({
  editTopup: (...a: unknown[]) => editTopupMock(...a),
  undoTopup: (...a: unknown[]) => undoTopupMock(...a),
}));

beforeEach(() => { editTopupMock.mockReset(); undoTopupMock.mockReset(); });
afterEach(() => cleanup());

// Newest first, as the server sends it: a change to the birthday top-up, the top-up itself,
// an undone refund, and the budget set by hand when the project was made.
// `can_change` is the server's say-so: false for an edit row, an undone top-up, and one that clearing the budget took back.
const HISTORY = [
  makeTopup({ id: "tu3", kind: "edit", topup_id: "tu1", amount: "-50.00", source: null, can_change: false,
    created_at: "2026-10-12T09:00:00Z" }),
  makeTopup(),
  makeTopup({ id: "tu2", amount: "30.00", source: "refund", undone: true, can_change: false, created_at: "2026-10-05T09:00:00Z" }),
  makeTopup({ id: "tu0", kind: "edit", topup_id: null, amount: "500.00", source: null, can_change: false,
    created_at: "2026-10-01T09:00:00Z" }),
];

const rowOf = (text: string) => screen.getByText(text).closest("li") as HTMLElement;

describe("TopupHistory", () => {
  it("names each row: a top-up, a change to one, and a budget set by hand", () => {
    render(<TopupHistory topups={HISTORY} onChanged={vi.fn()} />);
    expect(within(screen.getByRole("list", { name: "Top-up history" })).getAllByRole("listitem")).toHaveLength(4);
    expect(within(rowOf("Top-up changed")).getByText("-€50.00")).toBeInTheDocument();
    expect(within(rowOf("Budget set")).getByText("+€500.00")).toBeInTheDocument();
    const birthday = rowOf("birthday");
    expect(within(birthday).getByText("Top-up")).toBeInTheDocument();
    expect(within(birthday).getByText("€200.00")).toBeInTheDocument();
    expect(within(birthday).getByText("10 Oct 2026")).toBeInTheDocument();
  });

  it("an undone top-up says so, and only a live top-up can be changed or undone", () => {
    render(<TopupHistory topups={HISTORY} onChanged={vi.fn()} />);
    const refund = rowOf("refund");
    expect(within(refund).getByText("undone")).toBeInTheDocument();
    expect(within(refund).queryByRole("button")).not.toBeInTheDocument();
    expect(within(rowOf("Budget set")).queryByRole("button")).not.toBeInTheDocument();
    expect(within(rowOf("Top-up changed")).queryByRole("button")).not.toBeInTheDocument();
  });

  it("hides Change and Undo on a top-up the server says can't change, such as one a cleared budget took back", () => {
    const taken = makeTopup({ id: "tu9", amount: "75.00", source: "old gift", can_change: false });
    render(<TopupHistory topups={[makeTopup(), taken]} onChanged={vi.fn()} />);
    expect(within(rowOf("old gift")).queryByRole("button")).not.toBeInTheDocument();
    expect(within(rowOf("old gift")).queryByText("undone")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Change the top-up of €75.00" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Undo the top-up of €75.00" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Change the top-up of €200.00" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Undo the top-up of €200.00" })).toBeInTheDocument();
  });

  it("undoes a top-up and tells the page", async () => {
    undoTopupMock.mockResolvedValue(makeTopup({ undone: true }));
    const onChanged = vi.fn();
    const user = userEvent.setup();
    render(<TopupHistory topups={HISTORY} onChanged={onChanged} />);
    await user.click(screen.getByRole("button", { name: "Undo the top-up of €200.00" }));
    expect(undoTopupMock).toHaveBeenCalledWith("tu1");
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
  });

  it("changes a top-up to a new amount", async () => {
    editTopupMock.mockResolvedValue(makeTopup({ id: "tu4", kind: "edit", topup_id: "tu1", amount: "-20.00" }));
    const onChanged = vi.fn();
    const user = userEvent.setup();
    render(<TopupHistory topups={HISTORY} onChanged={onChanged} />);
    await user.click(screen.getByRole("button", { name: "Change the top-up of €200.00" }));
    await user.type(screen.getByLabelText("New amount"), "180");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(editTopupMock).toHaveBeenCalledWith("tu1", "180.00");
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
  });

  it("shows why an undo was refused and changes nothing", async () => {
    const { ApiError } = await import("../src/api/client");
    undoTopupMock.mockRejectedValue(new ApiError(409, "That top-up is already undone."));
    const onChanged = vi.fn();
    const user = userEvent.setup();
    render(<TopupHistory topups={HISTORY} onChanged={onChanged} />);
    await user.click(screen.getByRole("button", { name: "Undo the top-up of €200.00" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("already undone");
    expect(onChanged).not.toHaveBeenCalled();
  });

  it("says when there are no top-ups yet", () => {
    render(<TopupHistory topups={[]} onChanged={vi.fn()} />);
    expect(screen.getByText("No top-ups yet.")).toBeInTheDocument();
  });
});
