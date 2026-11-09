import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ChoiceCard } from "../src/components/approvals/ChoiceCard";
import { makeApprovalCard } from "./fixtures";

const answerMock = vi.fn();
vi.mock("../src/api/approvals", () => ({
  answerApproval: (...a: unknown[]) => answerMock(...a),
  getApproval: vi.fn(),
}));
afterEach(() => { cleanup(); answerMock.mockReset(); });

const choice = { question: "Which invoice first?", options: ["The old one", "The new one"], safe: 1, own: true, why: "Both are due." };
const card = (over = {}) => makeApprovalCard({ choice, ...over });

describe("ChoiceCard", () => {
  it("marks the safe option in words", () => {
    render(<ChoiceCard card={card()} />);
    expect(screen.getByText("Which invoice first?")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /The new one/ })).toHaveTextContent("Safe choice");
    expect(screen.getByRole("button", { name: "The old one" })).not.toHaveTextContent("Safe choice");
    expect(screen.getByText("Both are due.")).toBeInTheDocument();
  });

  it("a pick sends only the index", async () => {
    answerMock.mockResolvedValue({ ...card(), state: "approved" });
    render(<ChoiceCard card={card()} />);
    await userEvent.click(screen.getByRole("button", { name: "The old one" }));
    expect(answerMock).toHaveBeenCalledWith("card-a", "pick", { choice: 0 });
  });

  it("type your own sends the text", async () => {
    answerMock.mockResolvedValue({ ...card(), state: "approved" });
    render(<ChoiceCard card={card()} />);
    await userEvent.type(screen.getByLabelText("Type your own"), "Neither");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(answerMock).toHaveBeenCalledWith("card-a", "own", { text: "Neither" });
  });

  it("has no own field when the card does not allow it", () => {
    render(<ChoiceCard card={card({ choice: { ...choice, own: false } })} />);
    expect(screen.queryByLabelText("Type your own")).not.toBeInTheDocument();
  });

  it("dismiss sends no", async () => {
    answerMock.mockResolvedValue({ ...card(), state: "declined" });
    render(<ChoiceCard card={card()} />);
    await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(answerMock).toHaveBeenCalledWith("card-a", "no", undefined);
  });

  it("buttons lock after a press", async () => {
    answerMock.mockReturnValue(new Promise(() => undefined));
    render(<ChoiceCard card={card()} />);
    await userEvent.click(screen.getByRole("button", { name: "The old one" }));
    expect(screen.getByRole("button", { name: "The old one" })).toBeDisabled();
    expect(screen.getByRole("button", { name: /The new one/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Dismiss" })).toBeDisabled();
    expect(answerMock).toHaveBeenCalledTimes(1);
  });

  it("an answered card is one quiet line", () => {
    const { rerender } = render(<ChoiceCard card={card({ state: "approved" })} />);
    expect(screen.getByText("You answered.")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    rerender(<ChoiceCard card={card({ state: "declined" })} />);
    expect(screen.getByText("Dismissed: counts as No.")).toBeInTheDocument();
  });

  it("shows the web content chip when tainted and renders text as text", () => {
    render(<ChoiceCard card={card({ tainted: true, choice: { ...choice, question: "<b>Hi</b>" } })} />);
    expect(screen.getByText("from web content")).toBeInTheDocument();
    expect(screen.getByText("<b>Hi</b>")).toBeInTheDocument();
  });
});
