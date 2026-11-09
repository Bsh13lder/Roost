import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { GeneralInbox } from "../src/components/board/reports/GeneralInbox";
import { NoProjectChip } from "../src/components/board/reports/NoProjectChip";
import { ApiError } from "../src/api/client";
import { ToastProvider } from "../src/ui/Toast";
import { makeRangeExpense } from "./moneyFixtures";

const moveMock = vi.fn();
vi.mock("../src/api/money", () => ({ moveExpenses: (...a: unknown[]) => moveMock(...a) }));
vi.mock("../src/api/projects", () => ({
  listProjects: () => Promise.resolve([
    { id: "p-casa", name: "Casa Nueva", status: "active" }, { id: "p-old", name: "Old", status: "archived" },
    { id: "p-trip", name: "Trip", status: "active" },
  ]),
}));
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => ({ bots: {}, boardVersion: { tasks: 0, money: 0 } }) }));

const ROWS = [
  makeRangeExpense({ id: "e1", description: "Tiles", amount: "40.00", project: "General", project_id: "p-gen" }),
  makeRangeExpense({ id: "e2", description: "Paint", amount: "25.00", project: "General", project_id: "p-gen",
    spent_at: "2026-10-18", vendor: "Bauhaus" }),
  makeRangeExpense({ id: "e3", description: "Taxi", amount: "12.00", currency: "USD", project: "General",
    project_id: "p-gen", spent_at: "2026-10-12" }),
];
const onMoved = vi.fn();
const onDone = vi.fn();

function renderInbox() {
  return render(<ToastProvider><GeneralInbox expenses={ROWS} hasMore={false} onMore={vi.fn()} onMoved={onMoved}
    onDone={onDone} /></ToastProvider>);
}

beforeEach(() => {
  moveMock.mockReset().mockImplementation((ids: string[]) =>
    Promise.resolve({ moved: ids.map((id) => ({ id, from_project_id: "p-gen" })) }));
  onMoved.mockReset();
  onDone.mockReset();
});
afterEach(() => cleanup());

describe("the General inbox", () => {
  it("selects rows and moves them, with Undo", async () => {
    const user = userEvent.setup();
    renderInbox();
    expect(screen.getByText("0 of 3 picked")).toBeInTheDocument();
    expect(screen.getByText("No project")).toBeInTheDocument();
    const move = screen.getByRole("button", { name: "Move" });
    expect(move).toBeDisabled();
    await user.click(screen.getByRole("checkbox", { name: "Tiles" }));
    await user.click(screen.getByRole("checkbox", { name: "Paint" }));
    expect(screen.getByText("2 of 3 picked")).toBeInTheDocument();
    await user.click(screen.getByRole("combobox", { name: "Move to…" }));
    expect(screen.getByRole("option", { name: "Old" })).toHaveAttribute("aria-disabled", "true");
    await user.click(screen.getByRole("option", { name: "Casa Nueva" }));
    await user.click(move);
    expect(moveMock).toHaveBeenCalledWith(["e1", "e2"], "p-casa");
    await waitFor(() => expect(onMoved).toHaveBeenCalledTimes(1));
    const toast = await screen.findByText("Moved 2 expenses to Casa Nueva");
    await user.click(within(toast.parentElement as HTMLElement).getByRole("button", { name: "Undo" }));
    expect(moveMock).toHaveBeenLastCalledWith(["e1", "e2"], "p-gen");
    await waitFor(() => expect(onMoved).toHaveBeenCalledTimes(2));
  });

  it("shows each row's day, vendor and amount, and picks all with one click", async () => {
    const user = userEvent.setup();
    renderInbox();
    const paint = screen.getByRole("checkbox", { name: "Paint" }).closest("label") as HTMLElement;
    expect(within(paint).getByText("Bauhaus")).toBeInTheDocument();
    expect(within(paint).getByText("Sun 18 Oct")).toBeInTheDocument();
    expect(within(paint).getByText("€25.00")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Select all" }));
    expect(screen.getByText("3 of 3 picked")).toBeInTheDocument();
  });

  it("says why a move was refused, and moves nothing", async () => {
    moveMock.mockRejectedValue(new ApiError(422, "Its task lives in another project."));
    const user = userEvent.setup();
    renderInbox();
    await user.click(screen.getByRole("checkbox", { name: "Tiles" }));
    await user.click(screen.getByRole("combobox", { name: "Move to…" }));
    await user.click(screen.getByRole("option", { name: "Trip" }));
    await user.click(screen.getByRole("button", { name: "Move" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Its task lives in another project.");
    expect(onMoved).not.toHaveBeenCalled();
    expect(screen.getByText("1 of 3 picked")).toBeInTheDocument();
  });

  it("Done closes the inbox", async () => {
    await userEvent.setup().click((renderInbox(), screen.getByRole("button", { name: "Done" })));
    expect(onDone).toHaveBeenCalled();
  });

  it("offers the next page when there is more", async () => {
    const onMore = vi.fn();
    render(<ToastProvider><GeneralInbox expenses={ROWS} hasMore onMore={onMore} onMoved={onMoved} onDone={onDone} /></ToastProvider>);
    await userEvent.setup().click(screen.getByRole("button", { name: "Show more" }));
    expect(onMore).toHaveBeenCalled();
  });
});

describe("the No project chip", () => {
  it("counts what waits and toggles the inbox, pressed while it is open", async () => {
    const onToggle = vi.fn();
    const user = userEvent.setup();
    const { rerender } = render(<NoProjectChip count={3} more={false} open={false} onToggle={onToggle} />);
    const chip = screen.getByRole("button", { name: "No project · 3" });
    expect(chip).toHaveAttribute("aria-pressed", "false");
    await user.click(chip);
    expect(onToggle).toHaveBeenCalled();
    rerender(<NoProjectChip count={3} more={false} open onToggle={onToggle} />);
    expect(screen.getByRole("button", { name: "No project · 3" })).toHaveAttribute("aria-pressed", "true");
  });

  it("with nothing waiting it is not there, unless the inbox is open", () => {
    const { rerender } = render(<NoProjectChip count={0} more={false} open={false} onToggle={vi.fn()} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    rerender(<NoProjectChip count={0} more={false} open onToggle={vi.fn()} />);
    expect(screen.getByRole("button", { name: "No project · 0" })).toBeInTheDocument();
  });

  it("a long inbox counts with a plus", () => {
    render(<NoProjectChip count={100} more open={false} onToggle={vi.fn()} />);
    expect(screen.getByRole("button", { name: "No project · 100+" })).toBeInTheDocument();
  });
});
