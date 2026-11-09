import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { ChoiceCard } from "../src/components/approvals/ChoiceCard";
import { MessageList } from "../src/components/MessageList";
import { pairCardAnswers } from "../src/lib/approvals";
import { makeApprovalCard, makeMessage } from "./fixtures";

const answerMock = vi.fn();
const getMock = vi.fn();
vi.mock("../src/api/approvals", () => ({
  answerApproval: (...a: unknown[]) => answerMock(...a),
  getApproval: (...a: unknown[]) => getMock(...a),
}));
afterEach(() => { cleanup(); answerMock.mockReset(); getMock.mockReset(); });

const choice = { question: "Which day for the plumber?", options: ["Tuesday", "Thursday"], safe: 0, own: true, why: "" };
const card = (over = {}) => makeApprovalCard({ id: "card-c", choice, steps: [], ...over });
const approvalMessage = (id: string, cardId: string, seq: number) =>
  makeMessage({ id, seq, kind: "approval", body: JSON.stringify({ card_id: cardId, kind: "ask", steps: ["Which day for the plumber?"] }) });
const answerMessage = (id: string, body: string, seq: number) => makeMessage({ id, seq, role: "user", kind: "card_answer", body });

describe("pairCardAnswers", () => {
  it("gives each card the answer line that follows it, before the next card", () => {
    const pairs = pairCardAnswers([
      approvalMessage("m1", "card-1", 1), answerMessage("m2", "Tuesday", 2),
      approvalMessage("m3", "card-2", 3), makeMessage({ id: "m4", seq: 4, role: "user", body: "hello" }),
      approvalMessage("m5", "card-3", 5), answerMessage("m6", "Thursday", 6),
    ]);
    expect(pairs.get("card-1")).toBe("Tuesday");
    expect(pairs.has("card-2")).toBe(false); // replaced, never answered
    expect(pairs.get("card-3")).toBe("Thursday");
  });
});

describe("an answered options card", () => {
  it("shrinks to one line with a check and the chosen answer, the options hidden", () => {
    render(<ChoiceCard card={card({ state: "approved", closed_at: "2026-10-22T10:05:00Z" })} answer="Tuesday" />);
    const line = screen.getByText("Tuesday").closest(".choice-done") as HTMLElement;
    expect(line).not.toBeNull();
    expect(within(line).getByText("✓")).toHaveAttribute("aria-hidden", "true");
    expect(screen.getByText("You answered:", { exact: false })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Thursday" })).not.toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Needs your choice" })).not.toBeInTheDocument();
  });

  it("Show options opens the question and the options, the chosen one marked", async () => {
    render(<ChoiceCard card={card({ state: "approved" })} answer="Tuesday" />);
    await userEvent.click(screen.getByText("Show options"));
    expect(screen.getByText("Which day for the plumber?")).toBeVisible();
    const options = screen.getByRole("list", { name: "Options" });
    expect(within(options).getAllByRole("listitem").map((item) => item.textContent)).toEqual(["Tuesday (your answer)", "Thursday"]);
  });

  it("a pick in this window shrinks the card to that option at once", async () => {
    answerMock.mockResolvedValue(card({ state: "approved" }));
    render(<ChoiceCard card={card()} />);
    await userEvent.click(screen.getByRole("button", { name: /Thursday/ }));
    expect(await screen.findByText("Thursday", { selector: ".choice-done__answer" })).toBeInTheDocument();
  });

  it("without a known answer, a closed card keeps its quiet line", () => {
    render(<ChoiceCard card={card({ state: "approved" })} />);
    expect(screen.getByText("You answered.")).toBeInTheDocument();
  });

  it("after a reload the chat asks for the closed card and shows the stored answer line", async () => {
    getMock.mockResolvedValue(card({ state: "approved" }));
    render(
      <MemoryRouter>
        <MessageList botName="Scout" approvals={{}}
          messages={[approvalMessage("m1", "card-c", 1), answerMessage("m2", "Tuesday", 2)]} />
      </MemoryRouter>,
    );
    expect(await screen.findByText("Tuesday", { selector: ".choice-done__answer" })).toBeInTheDocument();
    expect(getMock).toHaveBeenCalledWith("card-c", false);
  });

  it("a card that was never answered is not asked for", async () => {
    render(<MemoryRouter><MessageList botName="Scout" approvals={{}} messages={[approvalMessage("m1", "card-c", 1)]} /></MemoryRouter>);
    expect(screen.getByText("Which day for the plumber?")).toBeInTheDocument();
    await waitFor(() => expect(getMock).not.toHaveBeenCalled());
  });
});
