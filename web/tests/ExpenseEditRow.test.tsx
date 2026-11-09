import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ExpenseEditRow } from "../src/components/board/ExpenseEditRow";
import { makeRangeExpense } from "./moneyFixtures";

vi.mock("../src/api/dates", () => ({ parseDate: vi.fn() }));
afterEach(() => cleanup());

const PROJECTS = [
  { id: "p-casa", name: "Casa Nueva", archived: false }, { id: "p-trip", name: "Trip", archived: false },
  { id: "p-gen", name: "General", archived: false }, { id: "p-old", name: "Old", archived: true },
];
const expense = makeRangeExpense({ id: "e1", description: "Paint", amount: "84.20", vendor: "Bauhaus",
  project: "Casa Nueva", project_id: "p-casa", spent_at: "2026-10-20" });

function renderRow(onSave = vi.fn().mockResolvedValue(undefined), onCancel = vi.fn()) {
  render(<ul><ExpenseEditRow expense={expense} projects={PROJECTS} onSave={onSave} onCancel={onCancel} /></ul>);
  return { onSave, onCancel };
}

describe("ExpenseEditRow", () => {
  it("edits amount, note, day, project and vendor in place", async () => {
    const user = userEvent.setup();
    const { onSave } = renderRow();
    const amount = screen.getByLabelText("Amount");
    expect(amount).toHaveValue("84.20");
    await user.clear(amount);
    await user.type(amount, "90,50");
    await user.clear(screen.getByLabelText("Note"));
    await user.type(screen.getByLabelText("Note"), "Brushes");
    await user.clear(screen.getByLabelText("Vendor"));
    await user.type(screen.getByLabelText("Vendor"), "Leroy");
    await user.clear(screen.getByLabelText("Day"));
    await user.type(screen.getByLabelText("Day"), "2026-10-12");
    await user.click(screen.getByRole("combobox", { name: "Project" }));
    expect(screen.getByRole("option", { name: "Old" })).toHaveAttribute("aria-disabled", "true");
    await user.click(screen.getByRole("option", { name: "Trip" }));
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(onSave).toHaveBeenCalledWith({
      amount: "90.50", note: "Brushes", vendor: "Leroy", spent_at: "2026-10-12", project_id: "p-trip",
    });
  });

  it("sends only what changed, and Enter saves", async () => {
    const user = userEvent.setup();
    const { onSave } = renderRow();
    await user.clear(screen.getByLabelText("Note"));
    await user.type(screen.getByLabelText("Note"), "Rollers{Enter}");
    expect(onSave).toHaveBeenCalledWith({ note: "Rollers" });
  });

  it("saving with nothing changed just closes", async () => {
    const user = userEvent.setup();
    const { onSave, onCancel } = renderRow();
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(onSave).not.toHaveBeenCalled();
    expect(onCancel).toHaveBeenCalled();
  });

  it("Esc cancels an edit", async () => {
    const user = userEvent.setup();
    const { onSave, onCancel } = renderRow();
    await user.type(screen.getByLabelText("Note"), "x{Escape}");
    expect(onCancel).toHaveBeenCalled();
    expect(onSave).not.toHaveBeenCalled();
  });

  it("an amount it can't read is refused before the gateway", async () => {
    const user = userEvent.setup();
    const { onSave } = renderRow();
    await user.clear(screen.getByLabelText("Amount"));
    await user.type(screen.getByLabelText("Amount"), "1.234,56{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("Enter an amount like 12,50");
    expect(onSave).not.toHaveBeenCalled();
  });

  it("a 422 shows its sentence under the row", async () => {
    const { ApiError } = await import("../src/api/client");
    const user = userEvent.setup();
    const onSave = vi.fn().mockRejectedValue(new ApiError(422, "“Old” is archived; unarchive it first."));
    const { onCancel } = renderRow(onSave);
    await user.type(screen.getByLabelText("Note"), "!{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("“Old” is archived; unarchive it first.");
    expect(onCancel).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.getByLabelText("Note")).toHaveValue("Paint!"));
  });
});
