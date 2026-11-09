import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { PlanTab } from "../src/components/plan/PlanTab";
import { ApiError } from "../src/api/client";
import { ToastProvider } from "../src/ui/Toast";
import { makeBot } from "./fixtures";
import { plan } from "./planFixtures";
vi.mock("../src/api/routines", async (real) => ({ ...(await real<object>()), listRoutineOccurrences: vi.fn().mockResolvedValue({ occurrences: [], truncated: false }) }));

const api = { getPlan: vi.fn(), putPlan: vi.fn(), patchPlanItem: vi.fn() };
vi.mock("../src/api/plan", () => ({
  getPlan: (...a: unknown[]) => api.getPlan(...a), putPlan: (...a: unknown[]) => api.putPlan(...a),
  patchPlanItem: (...a: unknown[]) => api.patchPlanItem(...a),
}));
let live: { planRevisions: Record<string, number> } = { planRevisions: {} };
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => live }));

const view = () => render(
  <MemoryRouter><ToastProvider><PlanTab bot={makeBot()} /></ToastProvider></MemoryRouter>,
);
function dataTransfer() {
  const store = new Map<string, string>();
  return { setData: (k: string, v: string) => store.set(k, v), getData: (k: string) => store.get(k) ?? "", effectAllowed: "", dropEffect: "" };
}

beforeEach(() => { live = { planRevisions: {} }; api.getPlan.mockResolvedValue(plan()); });
afterEach(() => { cleanup(); Object.values(api).forEach((mock) => mock.mockReset()); });

describe("PlanView", () => {
  it("the plan loads as its own chunk and opens on the Calendar", async () => {
    view();
    expect(await screen.findByRole("button", { name: "Calendar" })).toHaveAttribute("aria-pressed", "true");
    expect(api.getPlan).toHaveBeenCalledWith("bot-1");
    expect(screen.getByRole("button", { name: "Kanban" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Text" })).toBeInTheDocument();
  });

  it("unreadable lines are counted", async () => {
    api.getPlan.mockResolvedValue(plan({ unreadable: 2 }));
    view();
    expect(await screen.findByText("2 lines couldn't be read")).toBeInTheDocument();
  });

  it("one unreadable line is singular", async () => {
    api.getPlan.mockResolvedValue(plan({ unreadable: 1 }));
    view();
    expect(await screen.findByText("1 line couldn't be read")).toBeInTheDocument();
  });

  it("drag moves a card and sends the item's id and revision", async () => {
    api.patchPlanItem.mockResolvedValue(plan({ revision: 4 }));
    view();
    await userEvent.click(await screen.findByRole("button", { name: "Kanban" }));
    const transfer = dataTransfer();
    const source = screen.getByText("Call the plumber").closest(".kcard") as HTMLElement;
    const target = screen.getByRole("region", { name: "Done" });
    fireEvent.dragStart(source, { dataTransfer: transfer });
    fireEvent.drop(target, { dataTransfer: transfer });
    await waitFor(() => expect(api.patchPlanItem).toHaveBeenCalledWith("bot-1", "i-1", 3, { status: "done" }));
  });

  it("a conflict reloads the Plan and says to try again", async () => {
    api.patchPlanItem.mockRejectedValue(new ApiError(409, "The Plan changed since you opened it.", { current: plan({ revision: 5 }) }));
    view();
    await userEvent.click(await screen.findByRole("button", { name: "Kanban" }));
    const transfer = dataTransfer();
    fireEvent.dragStart(screen.getByText("Call the plumber").closest(".kcard") as HTMLElement, { dataTransfer: transfer });
    fireEvent.drop(screen.getByRole("region", { name: "Done" }), { dataTransfer: transfer });
    expect(await screen.findByText("The Plan changed; try again.")).toBeInTheDocument();
    await waitFor(() => expect(api.getPlan).toHaveBeenCalledTimes(2));
  });

  it("reloads when a newer revision is announced", async () => {
    const { rerender } = view();
    await screen.findByRole("button", { name: "Calendar" });
    live = { planRevisions: { "bot-1": 4 } };
    rerender(<MemoryRouter><ToastProvider><PlanTab bot={makeBot()} /></ToastProvider></MemoryRouter>);
    await waitFor(() => expect(api.getPlan).toHaveBeenCalledTimes(2));
  });

  it("edit as text saves with the revision it read", async () => {
    api.putPlan.mockResolvedValue(plan({ revision: 4, content: "- [ ] New thing\n" }));
    view();
    await userEvent.click(await screen.findByRole("button", { name: "Text" }));
    const box = screen.getByLabelText("Plan text");
    expect(box).toHaveValue("- [ ] Call the plumber ^i-1\n");
    fireEvent.change(box, { target: { value: "- [ ] New thing\n" } });
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(api.putPlan).toHaveBeenCalledWith("bot-1", "- [ ] New thing\n", 3);
    expect(await screen.findByText("Saved")).toBeInTheDocument();
  });

  it("a conflict shows the newer copy, and Use theirs takes it", async () => {
    api.putPlan.mockRejectedValue(new ApiError(409, "The Plan changed since you opened it.",
      { current: plan({ revision: 5, content: "- [ ] Theirs\n" }) }));
    view();
    await userEvent.click(await screen.findByRole("button", { name: "Text" }));
    fireEvent.change(screen.getByLabelText("Plan text"), { target: { value: "- [ ] Mine\n" } });
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("The Plan changed since you opened it.")).toBeInTheDocument();
    expect(screen.getByLabelText("Newer copy")).toHaveValue("- [ ] Theirs\n");
    await userEvent.click(screen.getByRole("button", { name: "Use theirs" }));
    expect(screen.getByLabelText("Plan text")).toHaveValue("- [ ] Theirs\n");
    expect(screen.queryByLabelText("Newer copy")).not.toBeInTheDocument();
  });

  it("Keep mine saves over the newer copy with its revision", async () => {
    api.putPlan.mockRejectedValueOnce(new ApiError(409, "The Plan changed since you opened it.",
      { current: plan({ revision: 5, content: "- [ ] Theirs\n" }) }));
    api.putPlan.mockResolvedValue(plan({ revision: 6, content: "- [ ] Mine\n" }));
    view();
    await userEvent.click(await screen.findByRole("button", { name: "Text" }));
    fireEvent.change(screen.getByLabelText("Plan text"), { target: { value: "- [ ] Mine\n" } });
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await userEvent.click(await screen.findByRole("button", { name: "Keep mine" }));
    await waitFor(() => expect(api.putPlan).toHaveBeenLastCalledWith("bot-1", "- [ ] Mine\n", 5));
  });

  it("a refused save shows the server's sentence", async () => {
    api.putPlan.mockRejectedValue(new ApiError(422, "The Plan is too long."));
    view();
    await userEvent.click(await screen.findByRole("button", { name: "Text" }));
    fireEvent.change(screen.getByLabelText("Plan text"), { target: { value: "x" } });
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("The Plan is too long.")).toBeInTheDocument();
  });
});
