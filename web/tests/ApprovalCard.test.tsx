import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApprovalCard } from "../src/components/approvals/ApprovalCard";
import { ApiError } from "../src/api/client";
import { makeApprovalCard, makeStep } from "./fixtures";

const answerMock = vi.fn();
vi.mock("../src/api/approvals", () => ({
  answerApproval: (id: string, answer: string, text?: string) => answerMock(id, answer, text),
  getApproval: vi.fn(),
}));
afterEach(() => { cleanup(); answerMock.mockReset(); });

describe("ApprovalCard", () => {
  it("Yes answers yes and shows the card closed", async () => {
    const card = makeApprovalCard();
    answerMock.mockResolvedValue({ ...card, state: "approved", closed_at: "x" });
    render(<ApprovalCard card={card} />);
    expect(screen.getByText("Edit grtasks.md in MySpace")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Yes" }));
    expect(answerMock).toHaveBeenCalledWith("card-a", "yes", undefined);
    expect(await screen.findByText("You said yes: Edit grtasks.md in MySpace")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Yes" })).not.toBeInTheDocument();
  });

  it("an Open card for a new site says Open, and Open answers yes", async () => {
    const step = { ...makeStep(), tool: "open_page", floor: "new_site", title: "Open web.whatsapp.com" };
    const card = makeApprovalCard({ steps: [step] });
    answerMock.mockResolvedValue({ ...card, state: "approved", closed_at: "x" });
    render(<ApprovalCard card={card} />);
    expect(screen.queryByRole("button", { name: "Yes" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Open" }));
    expect(answerMock).toHaveBeenCalledWith("card-a", "yes", undefined);
  });

  it("No answers no", async () => {
    const card = makeApprovalCard();
    answerMock.mockResolvedValue({ ...card, state: "declined", closed_at: "x" });
    render(<ApprovalCard card={card} />);
    await userEvent.click(screen.getByRole("button", { name: "No" }));
    expect(answerMock).toHaveBeenCalledWith("card-a", "no", undefined);
    expect(await screen.findByText("You said no: Edit grtasks.md in MySpace")).toBeInTheDocument();
  });

  it("disables the buttons after one press", async () => {
    answerMock.mockReturnValue(new Promise(() => undefined));
    render(<ApprovalCard card={makeApprovalCard()} />);
    await userEvent.click(screen.getByRole("button", { name: "Yes" }));
    expect(screen.getByRole("button", { name: "Yes" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "No" })).toBeDisabled();
    expect(answerMock).toHaveBeenCalledTimes(1);
  });

  it("the session button shows only when offered", async () => {
    const card = makeApprovalCard({ session_offer: true });
    answerMock.mockResolvedValue({ ...card, state: "approved", closed_at: "x" });
    const { rerender } = render(<ApprovalCard card={card} />);
    await userEvent.click(screen.getByRole("button", { name: "Yes for this session" }));
    expect(answerMock).toHaveBeenCalledWith("card-a", "yes_session", undefined);
    rerender(<ApprovalCard card={makeApprovalCard({ id: "card-b" })} />);
    expect(screen.queryByRole("button", { name: "Yes for this session" })).not.toBeInTheDocument();
  });

  it("a 409 shows Already answered", async () => {
    answerMock.mockRejectedValue(new ApiError(409, "Already answered."));
    render(<ApprovalCard card={makeApprovalCard()} />);
    await userEvent.click(screen.getByRole("button", { name: "Yes" }));
    expect(await screen.findByText("Already answered.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Yes" })).toBeDisabled();
  });

  it("another failure shows its words and lets you press again", async () => {
    answerMock.mockRejectedValue(new ApiError(500, "Try again in a moment."));
    render(<ApprovalCard card={makeApprovalCard()} />);
    await userEvent.click(screen.getByRole("button", { name: "Yes" }));
    expect(await screen.findByText("Try again in a moment.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Yes" })).toBeEnabled();
  });

  it("shows the from web content chip on a tainted card", () => {
    render(<ApprovalCard card={makeApprovalCard({ tainted: true })} />);
    expect(screen.getByText("from web content")).toBeInTheDocument();
  });

  it("a card that arrives closed shows its line only", () => {
    render(<ApprovalCard card={makeApprovalCard({ state: "expired" })} />);
    expect(screen.getByText("Replaced by a newer question.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Yes" })).not.toBeInTheDocument();
  });
});
