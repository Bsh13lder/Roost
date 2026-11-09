import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PlanCard } from "../src/components/approvals/PlanCard";
import { makeApprovalCard, makeStep } from "./fixtures";

const answerMock = vi.fn();
vi.mock("../src/api/approvals", () => ({
  answerApproval: (id: string, answer: string, text?: string) => answerMock(id, answer, text),
  getApproval: vi.fn(),
}));
afterEach(() => { cleanup(); answerMock.mockReset(); });

const plan = (over = {}) => makeApprovalCard({
  id: "plan-1", kind: "plan",
  steps: [
    makeStep({ title: "Create notes.md", diff: { text: "+hello\n+world", plus: 2, minus: 0, truncated: false } }),
    makeStep({ title: "Move old.md to the trash", floor: "delete_beyond_trash", tool: "mac_trash" }),
  ],
  ...over,
});

describe("PlanCard (the Proposal)", () => {
  it("lists every step with its diff and floor badge", () => {
    render(<PlanCard card={plan()} />);
    expect(screen.getByText("Proposal")).toBeInTheDocument();
    const items = screen.getAllByRole("listitem").filter((li) => li.classList.contains("step-row"));
    expect(items).toHaveLength(2);
    expect(screen.getByText("Create notes.md")).toBeInTheDocument();
    expect(screen.getByText("+hello")).toBeInTheDocument();
    expect(screen.getByText("+2 −0 lines")).toBeInTheDocument();
    expect(screen.getByText("Hard floor")).toBeInTheDocument();
  });

  it("Accept, Edit with words, and Decline send their answers", async () => {
    answerMock.mockImplementation(async (id: string, answer: string) =>
      ({ ...plan(), id, state: answer === "decline" ? "declined" : "approved", closed_at: "x" }));
    const { unmount } = render(<PlanCard card={plan()} />);
    await userEvent.click(screen.getByRole("button", { name: "Accept" }));
    expect(answerMock).toHaveBeenLastCalledWith("plan-1", "accept", undefined);
    unmount();

    render(<PlanCard card={plan({ id: "plan-2" })} />);
    await userEvent.click(screen.getByRole("button", { name: "Edit" }));
    const send = screen.getByRole("button", { name: "Send" });
    expect(send).toBeDisabled();
    await userEvent.type(screen.getByRole("textbox", { name: "What should change?" }), "Skip the trash step");
    await userEvent.click(send);
    expect(answerMock).toHaveBeenLastCalledWith("plan-2", "edit", "Skip the trash step");
    cleanup();

    render(<PlanCard card={plan({ id: "plan-3" })} />);
    await userEvent.click(screen.getByRole("button", { name: "Decline" }));
    expect(answerMock).toHaveBeenLastCalledWith("plan-3", "decline", undefined);
    expect(await screen.findByText("You declined the proposal.")).toBeInTheDocument();
  });

  it("a step based on outside content shows the red line", () => {
    render(<PlanCard card={plan({ steps: [makeStep({ tainted_basis: true })] })} />);
    expect(screen.getByText("Based on outside content")).toBeInTheDocument();
  });

  it("buttons are disabled after one press", async () => {
    answerMock.mockReturnValue(new Promise(() => undefined));
    render(<PlanCard card={plan()} />);
    await userEvent.click(screen.getByRole("button", { name: "Accept" }));
    expect(screen.getByRole("button", { name: "Decline" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Edit" })).toBeDisabled();
  });
});
